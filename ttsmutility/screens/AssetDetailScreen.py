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
    ]

    def __init__(self, url: str, mod_filename: str = "", trail: str = "") -> None:
        super().__init__()
        self.url = url
        self.mod_filename = mod_filename
        self.trail = trail
        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir
        self.ad_uri_prefix = "//asset_detail/"
        self.uri_copy = "//copy/"
        self.uri_delete = "//delete/"
        self.asset_list = AssetList(post_message=self.post_message)

    def compose(self) -> ComposeResult:
        with Container(id="ad_screen"):
            yield Footer()
            with VerticalScroll(id="ad_scroll"):
                yield Markdown(
                    self.get_markdown(),
                    id="ad_markdown",
                )

    def get_markdown(self) -> str:
        asset_detail = self.asset_list.get_asset(self.url, self.mod_filename)

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

        if self.mod_filename == "" or self.mod_filename == "sha1":
            asset_detail["mod_name"] = ""
        else:
            mod_list = ModList()
            mod_detail = mod_list.get_mod_details(self.mod_filename)
            asset_detail["mod_name"] = mod_detail["name"]

        if self.trail != "":
            asset_detail["trail"] = self.trail

        asset_detail["LuaScript"] = "N/A"
        if "LuaScript" in asset_detail["trail"] and self.mod_filename != "":
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

        asset_detail["matches"] = ""
        asset_detail["delete"] = ""

        if asset_detail["dl_status"] != "":
            asset_detail["matches"] = "### Asset Matches\n"
            matches = self.asset_list.find_asset(self.url)
            if len(matches) == 0:
                asset_detail["matches"] += "None Found\n"
            else:
                for match in matches:
                    uri = f"[{match[0]}]({self.ad_uri_prefix}{match[0]})"
                    copy_link = f"[copy]({self.uri_copy}{match[0]})"
                    asset_detail["matches"] += f"- {uri} [{match[1]}] <-- {copy_link}\n"

            if asset_detail["fsize"] > 0:
                asset_detail["delete"] = "### Copied Asset Options\n"
                asset_detail["delete"] += f"[delete]({self.uri_delete}{self.url})\n"

        return asset_detail_md.format(**asset_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        link = None
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
        elif self.uri_copy in event.href:
            self.asset_list.copy_asset(event.href.split(self.uri_copy)[1], self.url)
            self.app.push_screen(InfoDialog("Copied asset. Restart to update mod."))
        elif self.uri_delete in event.href:
            self.asset_list.delete_asset(self.url)
            self.app.push_screen(InfoDialog("Deleted asset. Restart to update mod."))
        elif self.ad_uri_prefix in event.href:
            self.app.push_screen(
                AssetDetailScreen(event.href.split(self.ad_uri_prefix)[1])
            )
        else:
            link = event.href

        if link is not None:
            open_url(link)

    def action_find(self):
        # Look for matching SHA1, filename, content_name, JSON trail
        matches = self.asset_list.find_asset(self.url)
        if len(matches) > 0:
            options = [f"{url} ({type})" for url, type in matches]

            def set_id(index: int) -> None:
                if index >= 0:
                    self.app.push_screen(AssetDetailScreen(matches[index][0]))
                    if False:
                        self.asset_list.copy_asset(
                            # options[index].split("(")[0].strip(),
                            matches[index][0],
                            self.url,
                        )
                        self.app.push_screen(
                            InfoDialog("Copied asset. Restart to update mod.")
                        )

            self.app.push_screen(SelectOptionDialog(options), set_id)
