from textual.app import ComposeResult
from textual.containers import Center
from textual.widgets import Footer, Input, Label
from textual.screen import ModalScreen


class InputDialog(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, starting_input: str = "", msg: str = "") -> None:
        super().__init__()
        self.starting_input = starting_input
        self.msg = msg

    def compose(self) -> ComposeResult:
        yield Footer()
        with Center(id="id_center"):
            yield Label(self.msg, id="id_label")
            yield Input(value=self.starting_input, id="id_input")

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)
