from textual.app import ComposeResult
from textual.widgets import Footer
from textual.widgets import Markdown
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen


class InfoScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="info_container"):
            yield Footer()
            with VerticalScroll(id="info_scroll"):
                yield Markdown(
                    id="info_markdown",
                )

    def on_mount(self) -> None:
        md = self.query_one("#info_markdown", expect_type=Markdown)
        md.update(self.message)
