from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.widgets import Markdown, MarkdownViewer
from textual.screen import ModalScreen

from rich.markdown import Markdown

import time
import re
import os
from pathlib import Path

ASSET_DETAIL_MD = """
# {mod_name}


## URL
[{url}]({url})


## Local File URI
<a href="{uri}">{uri}</a>


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
        yield MarkdownViewer(
            self.get_markdown(),
            id="ad_screen",
            show_table_of_contents=False,
        )
        yield Footer()

    def action_toggle_fullscreen(self) -> None:
        self.query_one("#ad_screen").toggle_class("fs")

    def get_markdown(self) -> str:
        if self.asset_detail["mtime"] == 0:
            self.asset_detail["mtime"] = "File not found"
        else:
            self.asset_detail["mtime"] = time.ctime(self.asset_detail["mtime"])
        self.asset_detail["other_mods"] = "`\n- `".join(self.asset_detail["other_mods"])
        self.asset_detail["other_mods"] = self.asset_detail["other_mods"].join(
            ["\n- `", "`\n"]
        )
        self.asset_detail["uri"] = self.asset_detail["uri"]
        return ASSET_DETAIL_MD.format(**self.asset_detail)

    def _validate_uri_file_link(self, text, pos):
        tail = text[pos:]

        validate = "^///(\S*)"

        founds = re.search(self.re["not_http"], tail, flags=re.IGNORECASE)
        if founds:
            return len(founds.group(0))

        return 0
