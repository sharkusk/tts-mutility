from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.screen import ModalScreen

from rich.markdown import Markdown

import time

ASSET_DETAIL_MD = """
## URL
{url}

## Local File URI
{uri}

## TTS Mod Filepath
{filename}

| Asset Details | |
|--------------------------:|:------------------|
| Modified Time             | {mtime}           |
| File Size                 | {fsize:,}         |
| JSON Trail                | {trail}           |
| Content Filename          | {content_name}    |
| SHA1 Hexdigest            | {sha1}            |
| Download Error Status     | {dl_status}       |

"""


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
            self.asset_detail["mtime"] = "File not found"
        else:
            self.asset_detail["mtime"] = time.ctime(self.asset_detail["mtime"])
        static.update(Markdown(ASSET_DETAIL_MD.format(**self.asset_detail)))
