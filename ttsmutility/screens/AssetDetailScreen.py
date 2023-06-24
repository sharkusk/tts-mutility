from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.screen import ModalScreen

from rich.markdown import Markdown

import time

ASSET_DETAIL_MD = """
# {mod_name}

## URL
{url}

## Local File URI
{uri}

## TTS Mod Filepath
{filename}

| Asset Details | |
|------------------------------:|:------------------|
| Modified Time                 | {mtime}           |
| File Size                     | {fsize:,}         |
| JSON Trail                    | {trail}           |
| Content Filename              | {content_name}    |
| SHA1 Hexdigest                | {sha1}            |
| Download Error Status         | {dl_status}       |

## All TTS Mods Using Asset
{other_mods}
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
        yield Static(id="ad_screen")

    def action_toggle_fullscreen(self) -> None:
        self.query_one("#ad_screen").toggle_class("fs")

    def on_mount(self) -> None:
        static = next(self.query("#ad_screen").results(Static))
        if self.asset_detail["mtime"] == 0:
            self.asset_detail["mtime"] = "File not found"
        else:
            self.asset_detail["mtime"] = time.ctime(self.asset_detail["mtime"])
        self.asset_detail["other_mods"] = "`\n- `".join(
            self.asset_detail["other_mods"]
        ).join(["\n- `", "`\n"])
        static.update(Markdown(ASSET_DETAIL_MD.format(**self.asset_detail)))
