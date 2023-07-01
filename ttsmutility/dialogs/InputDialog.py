from textual.app import ComposeResult
from textual.widgets import Footer, Input
from textual.screen import ModalScreen


class InputDialog(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, starting_input: str = "") -> None:
        super().__init__()
        self.starting_input = starting_input

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Input(placeholder=self.starting_input, id="id_input")

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)
