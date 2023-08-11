import time
from pathlib import Path
from webbrowser import open as open_url

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Markdown

from ..dialogs.InfoDialog import InfoDialog
from ..dialogs.SelectOptionDialog import SelectOptionDialog
from ..parse.AssetList import AssetList


class AssetDetailScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("f", "find", "Find Match"),
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
            try:
                with open(self.asset_detail["mod_path"], "r", encoding="utf-8") as f:
                    data = f.read()
            except FileNotFoundError:
                # Expected for sha1 mismatches
                pass
            else:
                lines_before = 18
                lines_after = 18
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

                if start_lua < url_loc - (lines_before * 120):
                    start_lua = url_loc - (lines_before * 120)

                if end_lua > url_loc + (lines_after * 120):
                    end_lua = url_loc + (lines_after * 120)

                self.asset_detail["LuaScript"] = (
                    data[start_lua:end_lua]
                    .replace(r"\r", "")
                    .replace(r"\n", "\n")
                    .replace(r"\"", '"')
                    .replace(r"\t", "\t")
                    # .strip()
                )

        return asset_detail_md.format(**self.asset_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
        else:
            link = event.href

        open_url(link)

    def action_find(self):
        asset_list = AssetList(post_message=self.post_message)
        # Look for matching SHA1, filename, content_name, JSON trail
        matches = asset_list.find_asset(self.asset_detail["url"])
        if len(matches) > 0:
            options = [f"{url} ({type})" for url, type in matches]

            def set_id(index: int) -> None:
                if index >= 0:
                    asset_list.copy_asset(
                        options[index].split("(")[0].strip(), self.asset_detail["url"]
                    )
                    self.app.push_screen(
                        InfoDialog("Copied asset. Restart to update mod.")
                    )

            self.app.push_screen(SelectOptionDialog(options), set_id)
