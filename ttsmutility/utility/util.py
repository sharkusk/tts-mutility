import time
from rich.text import Text


def format_time(mtime: float, zero_string: str = "") -> str:
    if mtime == 0:
        if zero_string == "":
            return "Not Found"
        else:
            return zero_string
    else:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


def make_safe_filename(filename):
    return "".join([c if c not in r'<>:"/\|?*' else "-" for c in filename]).rstrip()


# Remove this once Rich accepts pull request #3016
class MyText(Text):
    def __lt__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.plain < other
        elif isinstance(other, MyText):
            return self.plain < other.plain
        return False

    def __gt__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.plain > other
        elif isinstance(other, MyText):
            return self.plain > other.plain
        return False
