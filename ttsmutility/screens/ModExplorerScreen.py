from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer

from ..widgets.ModExplorer import ModExplorer


class ModExplorerScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, mod_filepath, trail=[]):
        super().__init__()
        self.mod_filepath = mod_filepath
        self.trail = trail

    def compose(self) -> ComposeResult:
        yield Footer()
        yield ModExplorer(self.mod_filepath, start_trail=self.trail)
