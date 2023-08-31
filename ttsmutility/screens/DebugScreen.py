from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


class DebugScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, message: str | Markdown) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="debug_container"):
            with VerticalScroll(id="debug_scroll"):
                yield Static(
                    self.message,
                    id="debug_static",
                )
