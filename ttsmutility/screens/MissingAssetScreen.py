from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Label

from .AssetListScreen import AssetListScreen


class MissingAssetScreen(Screen):
    def __init__(self, filename, mod_name):
        super().__init__()
        self.filename = filename
        self.mod_name = mod_name

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Label(self.mod_name, id="title")
        yield AssetListScreen(self.filename, self.mod_name)
