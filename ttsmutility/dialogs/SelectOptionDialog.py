from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, OptionList
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
        with VerticalScroll(id="sod_option_scroll"):
            yield OptionList(*self.options, id="sod_option_list")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.dismiss(event.option_index)
