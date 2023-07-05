from textual.app import ComposeResult
from textual.widgets import Footer
from textual.widgets import Markdown
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen

import time
from pathlib import Path
from webbrowser import open as open_url


class AssetDetailScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, asset_detail: dict) -> None:
        self.asset_detail = asset_detail
        super().__init__()

    def compose(self) -> ComposeResult:
        with Container(id="ad_screen"):
            yield Footer()
            with VerticalScroll(id="ad_scroll"):
                yield Markdown(
                    self.get_markdown(),
                    id="ad_markdown",
                )

    def get_markdown(self) -> str:
        asset_detail_md = ""
        ad_filepath = Path(__file__).with_name("AssetDetailScreen.md")
        with ad_filepath.open("r") as f:
            asset_detail_md = f.read()
        if self.asset_detail["mtime"] == 0:
            self.asset_detail["mtime"] = "File not found"
        else:
            self.asset_detail["mtime"] = time.ctime(self.asset_detail["mtime"])
        self.asset_detail["other_mods"] = "`\n- `".join(self.asset_detail["other_mods"])
        self.asset_detail["other_mods"] = self.asset_detail["other_mods"].join(
            ["\n- `", "`\n"]
        )
        self.asset_detail["uri"] = self.asset_detail["uri"]

        self.asset_detail["uri_short"] = self.asset_detail["uri"].replace(
            "file:///", "//localhost/"
        )

        self.asset_detail["url"] = self.asset_detail["url"].replace(" ", "%20")

        self.asset_detail["LuaScript"] = "N/A"
        if "LuaScript" in self.asset_detail["trail"]:
            # Read in mod file, find string in first LUA script section,
            # find start/end of function, and extract...
            with open(self.asset_detail["mod_path"], "r", encoding="utf-8") as f:
                lines_before = 12
                lines_after = 12
                data = f.read()
                url_loc = data.find(self.asset_detail["url"])
                if url_loc == -1:
                    url_loc = data.find("tcejbo gninwapS")
                start_lua = url_loc
                for i in range(lines_before):
                    new_start = data.rfind(r"\n", 0, start_lua)
                    # Don't go past the LuaScript start section
                    if (
                        start_lua := data.rfind('"LuaScript":', new_start, start_lua)
                    ) >= 0:
                        start_lua += len('"LuaScript":')
                        start_lua = data.find('"', start_lua) + 1
                        break
                    start_lua = new_start
                end_lua = url_loc + len(self.asset_detail["url"])
                for i in range(lines_after):
                    new_end = data.find(r"\n", end_lua + 1)
                    # Don't go past the end of the LuaScript section.
                    # This is detected by finding a " mark without it
                    # being escaped (e.g. not \").
                    pot_end = data.find('"', end_lua, new_end)
                    while pot_end >= 0 and data[pot_end - 1] == "\\":
                        pot_end = data.find('"', pot_end + 1, new_end)
                    if pot_end >= 0:
                        end_lua = pot_end
                        break
                    end_lua = new_end

                self.asset_detail["LuaScript"] = (
                    data[start_lua:end_lua]
                    .replace(r"\r", "")
                    .replace(r"\n", "\n")
                    .replace(r"\"", '"')
                    .replace(r"\t", "\t")
                    .strip()
                )

        return asset_detail_md.format(**self.asset_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
        else:
            link = event.href

        open_url(link)
