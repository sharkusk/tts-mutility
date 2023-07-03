from textual.app import ComposeResult
from textual.widgets import Footer, Static
from textual.screen import ModalScreen


class InfoDialog(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, info: str = "") -> None:
        super().__init__()
        self.info = info

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Static(self.info, id="id_static")
