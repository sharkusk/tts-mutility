from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, OptionList
from textual.screen import ModalScreen


class SelectOptionDialog(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, options: list) -> None:
        super().__init__()
        self.options = options

    def compose(self) -> ComposeResult:
        yield Footer()
        yield OptionList(*self.options, id="sod_option_list")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.dismiss(event.option_index)
