from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.screen import ModalScreen

import time

ASSET_DETAIL_MD = """# URL
{url}

## Mod Filepath
{filepath}

## URI
{uri}

- Modified Time: {mtime}
- File Size: {fsize:,} Bytes
- JSON Trail: {trail}
- SHA1: {sha1}
- DL Status: {dl_status}"""


class AssetDetailScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("f", "toggle_fullscreen", "Fullscreen"),
    ]

    def __init__(self, asset_detail: dict) -> None:
        self.asset_detail = asset_detail
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Static(id="asset_detail")

    def action_toggle_fullscreen(self) -> None:
        self.query_one("#asset_detail").toggle_class("fs")

    def on_mount(self) -> None:
        static = next(self.query("#asset_detail").results(Static))
        if self.asset_detail["mtime"] == 0:
            readable_time = "File not found"
        else:
            readable_time = time.ctime(self.asset_detail["mtime"])
        static.update(
            ASSET_DETAIL_MD.format(
                url=self.asset_detail["url"],
                uri=self.asset_detail["uri"],
                filepath=self.asset_detail["filename"],
                trail=self.asset_detail["trail"],
                sha1=self.asset_detail["sha1"],
                mtime=readable_time,
                fsize=self.asset_detail["fsize"],
                dl_status=self.asset_detail["dl_status"],
            )
        )
