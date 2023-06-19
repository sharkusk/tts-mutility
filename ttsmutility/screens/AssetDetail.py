from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.screen import ModalScreen

import time

ASSET_DETAIL_MD = """
URL
---
{url}

Filename
--------
{filename}

Modified Time
-------------
{mtime}

SHA1
----
{sha1}

JSON Trail
----------
{trail}
"""

class AssetDetailScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "OK")]

    def __init__(self, asset_detail: dict) -> None:
        self.asset_detail = asset_detail
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Static(id="asset_detail")
    
    def on_mount(self) -> None:
        static = next(self.query("#asset_detail").results(Static))
        static.update(ASSET_DETAIL_MD.format(
            url=self.asset_detail['url'],
            filename=self.asset_detail['asset_filename'],
            trail=self.asset_detail['trail'],
            sha1=self.asset_detail['sha1'],
            mtime=self.asset_detail['mtime'],
            ))
