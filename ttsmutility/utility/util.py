import time


def format_time(mtime: float, zero_string: str = "") -> str:
    if mtime == 0:
        if zero_string == "":
            return "Not Found"
        else:
            return zero_string
    else:
        return time.strftime("%Y-%m-%d", time.localtime(mtime))


def make_safe_filename(filename):
    return "".join([c if c not in r'<>:"/\|?*' else "-" for c in filename]).rstrip()
