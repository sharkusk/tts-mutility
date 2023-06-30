from textual.message import Message


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
