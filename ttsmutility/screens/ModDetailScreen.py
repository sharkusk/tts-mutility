from textual.app import ComposeResult
from textual.widgets import Footer
from textual.widgets import Markdown
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.message import Message

import time
from pathlib import Path
from webbrowser import open as open_url
from urllib.parse import unquote, urlparse, quote

from ..data.config import load_config
from ..parse.ModList import ModList
from ..parse.BggSearch import BggSearch
from ..dialogs.SelectOptionDialog import SelectOptionDialog
from ..dialogs.InputDialog import InputDialog


class ModDetailScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("a", "asset_list", "Asset List"),
        ("b", "bgg_lookup", "BGG Lookup"),
        ("n", "bgg_lookup_input", "BGG Lookup (Input Name)"),
    ]

    class AssetsSelected(Message):
        def __init__(self, mod_filename: str) -> None:
            self.mod_filename = mod_filename
            super().__init__()

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.ad_uri_prefix = "//asset_detail/"
        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir
        self.mod_list = ModList()
        self.mod_detail = self.mod_list.get_mod_details(self.filename)
        self.bs = BggSearch()
        super().__init__()

    def compose(self) -> ComposeResult:
        with Container(id="md_screen"):
            yield Footer()
            with VerticalScroll(id="md_scroll"):
                yield Markdown(
                    self.get_markdown(),
                    id="md_markdown",
                )

    def get_markdown(self) -> str:
        mod_detail_md = ""
        md_filepath = Path(__file__).with_name("ModDetailScreen.md")
        with md_filepath.open("r") as f:
            mod_detail_md = f.read()

        mod_detail = self.mod_detail.copy()

        mod_detail["asset_detail_url"] = quote(f"{self.ad_uri_prefix}{self.filename}")
        mod_detail["size"] = mod_detail["size"] / (1024)
        mod_detail["mtime"] = time.ctime(mod_detail["mtime"])
        mod_detail["epoch"] = time.ctime(mod_detail["epoch"])
        if "Workshop" in self.filename:
            mod_detail["uri"] = (Path(self.mod_dir) / self.filename).as_uri()
        else:
            mod_detail["uri"] = (Path(self.save_dir) / self.filename).as_uri()
        mod_detail["uri_short"] = mod_detail["uri"].replace("file:///", "//localhost/")
        mod_detail["tag_list"] = "`\n- `".join(mod_detail["tags"])
        mod_detail["tag_list"] = mod_detail["tag_list"].join(["\n- `", "`\n"])
        mod_detail[
            "steam_link"
        ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={Path(self.filename).stem}"
        if "bgg_id" in mod_detail:
            mod_detail["bgg_link"] = self.bs.get_game_url(mod_detail["bgg_id"])
        else:
            mod_detail["bgg_link"] = ""

        return mod_detail_md.format(**mod_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
            open_url(link)
        elif self.ad_uri_prefix in event.href:
            filename = unquote(urlparse(event.href[len(self.ad_uri_prefix) :]).path)
            self.post_message(self.AssetsSelected(filename))
        else:
            open_url(event.href)

    def refresh_mod_details(self):
        self.query_one("#md_markdown").update(self.get_markdown())

    def action_asset_list(self):
        self.post_message(self.AssetsSelected(self.filename))

    def action_bgg_lookup_input(self):
        def set_name(name: str) -> None:
            self.action_bgg_lookup(name)

        self.app.push_screen(InputDialog(self.mod_detail["name"]), set_name)

    def action_bgg_lookup(self, mod_name=""):
        if mod_name == "":
            mod_name = self.mod_detail["name"]

        bgg_matches = self.bs.search(mod_name)

        options = [
            f"{m} ({bgg_matches[m][1]}) [{bgg_matches[m][0]}]" for m in bgg_matches
        ]

        if len(options) > 0:

            def set_id(index: int) -> None:
                offset_start = options[index].rfind("[") + 1
                offset_end = options[index].rfind("]")
                self.mod_detail["bgg_id"] = options[index][offset_start:offset_end]
                md = self.query_one("#md_markdown")
                md.update(self.get_markdown())
                self.mod_list.set_bgg_id(self.filename, self.mod_detail["bgg_id"])

            self.app.push_screen(SelectOptionDialog(options), set_id)
