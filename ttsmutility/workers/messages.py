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
        update_status: bool = True,
        status_id: int = 0,
        prefix=None,
        suffix=None,
    ):
        super().__init__()
        self.status = status
        self.status_id = status_id
        self.prefix = prefix
        self.suffix = suffix
        self.update_status = update_status


class FileDownloadComplete(Message):
    def __init__(
        self,
        asset: dict,
        status_id: int = 0,
    ) -> None:
        super().__init__()
        self.asset = asset
        self.status_id = status_id


class DownloadComplete(Message):
    def __init__(self, status_id: int = 0) -> None:
        super().__init__()
        self.status_id = status_id
