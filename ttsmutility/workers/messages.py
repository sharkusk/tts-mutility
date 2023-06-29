from textual.message import Message


class UpdateProgress(Message):
    def __init__(self, update_total=None, advance_amount=None):
        self.update_total = update_total
        self.advance_amount = advance_amount
        super().__init__()


class UpdateStatus(Message):
    def __init__(self, status: str):
        self.status = status
        super().__init__()


class UpdateLog(Message):
    def __init__(self, status: str):
        self.status = status
        super().__init__()