from textual.message import Message


class UpdateLog(Message):
    def __init__(
        self,
        status: str,
        status_id: int = 0,
        prefix=None,
        suffix=None,
    ):
        super().__init__()
        self.status = status
        self.status_id = status_id
        self.prefix = prefix
        self.suffix = suffix
