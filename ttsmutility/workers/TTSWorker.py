from textual.app import ComposeResult
from textual.containers import Center
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ProgressBar, Static


class TTSWorker(Widget):
    class UpdateProgress(Message):
        def __init__(self, update_total=None, advance_amount=None, status_id: int = 0):
            super().__init__()
            self.update_total = update_total
            self.advance_amount = advance_amount
            self.status_id = status_id

    class UpdateStatus(Message):
        def __init__(self, status: str, status_id: int = 0, prefix=None, suffix=None):
            super().__init__()
            self.status = status
            self.status_id = status_id
            self.prefix = prefix
            self.suffix = suffix

    def compose(self) -> ComposeResult:
        with Center(id="worker_center"):
            yield ProgressBar(id="worker_progress")
            yield Static(id="worker_status")
