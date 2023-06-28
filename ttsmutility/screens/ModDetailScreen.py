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


class ModDetailScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("a", "asset_list", "Asset List"),
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
        mod_list = ModList()
        self.mod_detail = mod_list.get_mod_details(self.filename)

        mod_detail_md = ""
        md_filepath = Path(__file__).with_name("ModDetailScreen.md")
        with md_filepath.open("r") as f:
            mod_detail_md = f.read()

        self.mod_detail["asset_detail_url"] = quote(
            f"{self.ad_uri_prefix}{self.filename}"
        )
        self.mod_detail["size"] = self.mod_detail["size"] / (1024)
        self.mod_detail["mtime"] = time.ctime(self.mod_detail["mtime"])
        self.mod_detail["epoch"] = time.ctime(self.mod_detail["epoch"])
        if "Workshop" in self.filename:
            self.mod_detail["uri"] = (Path(self.mod_dir) / self.filename).as_uri()
        else:
            self.mod_detail["uri"] = (Path(self.save_dir) / self.filename).as_uri()
        self.mod_detail["uri_short"] = self.mod_detail["uri"].replace(
            "file:///", "//localhost/"
        )
        self.mod_detail["tag_list"] = "`\n- `".join(self.mod_detail["tags"])
        self.mod_detail["tag_list"] = self.mod_detail["tag_list"].join(["\n- `", "`\n"])

        return mod_detail_md.format(**self.mod_detail)

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
