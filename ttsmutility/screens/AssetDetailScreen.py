from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.widgets import Markdown, MarkdownViewer
from textual.screen import ModalScreen

import time
import re
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
        yield Markdown(
            self.get_markdown(),
            id="ad_screen",
            # show_table_of_contents=False,
        )
        yield Footer()

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

        return asset_detail_md.format(**self.asset_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
        else:
            link = event.href

        open_url(link)
