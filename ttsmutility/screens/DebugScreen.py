from textual.app import ComposeResult
from textual.widgets import Footer
from textual.widgets import Static
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen


class DebugScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="debug_container"):
            yield Footer()
            with VerticalScroll(id="debug_scroll"):
                yield Static(
                    self.message,
                    id="debug_static",
                )
