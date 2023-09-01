from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Label

from .AssetListScreen import AssetListScreen


class MissingAssetScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, filename, mod_name):
        super().__init__()
        self.filename = filename
        self.mod_name = mod_name

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Label(
            "SHA1 Mismatches - Press ESC to Exit",
            id="title",
            classes="aa_label",
        )
        yield AssetListScreen(self.filename, self.mod_name)
