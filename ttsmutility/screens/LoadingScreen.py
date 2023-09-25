from textual import work
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator


class LoadingScreen(ModalScreen[int]):
    def __init__(self, busy_work, args):
        super().__init__()
        self.busy_work = busy_work
        self.busy_work_args = args

    def compose(self) -> ComposeResult:
        """Compose the child widgets."""
        yield LoadingIndicator(id="busy_indicator")

    def on_mount(self) -> None:
        self.do_busy_work()

    @work(thread=True)
    def do_busy_work(self) -> None:
        return_value = self.busy_work(*self.busy_work_args)
        self.app.call_from_thread(self.dismiss, return_value)
