from rich.highlighter import ReprHighlighter
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Footer, Static


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


class TextDialog(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, info: str = "") -> None:
        super().__init__()
        self.info = info

    def compose(self) -> ComposeResult:
        highlighter = ReprHighlighter()
        label = highlighter(self.info)
        yield Footer()
        yield Static(label, id="id_text")
