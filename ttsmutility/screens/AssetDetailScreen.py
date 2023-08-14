import time
from pathlib import Path
from webbrowser import open as open_url

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Markdown

from ..data.config import load_config
from ..dialogs.InfoDialog import InfoDialog
from ..dialogs.SelectOptionDialog import SelectOptionDialog
from ..parse.AssetList import AssetList
from ..parse.ModList import ModList


class AssetDetailScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("f", "find", "Find Match"),
    ]

    def __init__(self, url: str, mod_filename: str = "") -> None:
        self.url = url
        self.mod_filename = mod_filename
        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir
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
        asset_list = AssetList(post_message=self.post_message)
        asset_detail = asset_list.get_asset(self.url, self.mod_filename)

        asset_detail_md = ""
        ad_filepath = Path(__file__).with_name("AssetDetailScreen.md")
        with ad_filepath.open("r") as f:
            asset_detail_md = f.read()
        if asset_detail["mtime"] == 0:
            asset_detail["mtime"] = "File not found"
        else:
            asset_detail["mtime"] = time.ctime(asset_detail["mtime"])
        asset_detail["mods"] = "`\n- `".join(asset_detail["mods"])
        asset_detail["mods"] = asset_detail["mods"].join(["\n- `", "`\n"])

        filepath = Path(self.mod_dir) / asset_detail["filename"]
        asset_detail["uri"] = Path(filepath).as_uri() if filepath != "" else ""

        if self.mod_filename == "":
            asset_detail["mod_name"] = ""
        else:
            mod_list = ModList()
            mod_detail = mod_list.get_mod_details(self.mod_filename)
            asset_detail["mod_name"] = mod_detail["name"]

        asset_detail["LuaScript"] = "N/A"
        if "LuaScript" in asset_detail["trail"]:
            if "Workshop" in self.mod_filename:
                mod_path = Path(self.mod_dir) / self.mod_filename
            else:
                mod_path = Path(self.save_dir) / self.mod_filename

            # Read in mod file, find string in first LUA script section,
            # find start/end of function, and extract...
            try:
                with open(mod_path, "r", encoding="utf-8") as f:
                    data = f.read()
            except FileNotFoundError:
                # Expected for sha1 mismatches
                pass
            else:
                lines_before = 18
                lines_after = 18
                url_loc = data.find(asset_detail["url"])
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
                end_lua = url_loc + len(asset_detail["url"])
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

                asset_detail["LuaScript"] = (
                    data[start_lua:end_lua]
                    .replace(r"\r", "")
                    .replace(r"\n", "\n")
                    .replace(r"\"", '"')
                    .replace(r"\t", "\t")
                    # .strip()
                )

        asset_detail["uri_short"] = asset_detail["uri"].replace(
            "file:///", "//localhost/"
        )
        asset_detail["url"] = asset_detail["url"].replace(" ", "%20")

        return asset_detail_md.format(**asset_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
        else:
            link = event.href

        open_url(link)

    def action_find(self):
        asset_list = AssetList(post_message=self.post_message)
        # Look for matching SHA1, filename, content_name, JSON trail
        matches = asset_list.find_asset(self.url)
        if len(matches) > 0:
            options = [f"{url} ({type})" for url, type in matches]

            def set_id(index: int) -> None:
                if index >= 0:
                    self.app.push_screen(AssetDetailScreen(matches[index][0]))
                    if False:
                        asset_list.copy_asset(
                            # options[index].split("(")[0].strip(),
                            matches[index][0],
                            self.url,
                        )
                        self.app.push_screen(
                            InfoDialog("Copied asset. Restart to update mod.")
                        )

            self.app.push_screen(SelectOptionDialog(options), set_id)
