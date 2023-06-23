import time


def format_time(mtime: float, zero_string: str = "") -> str:
    if mtime == 0:
        if zero_string == "":
            return "File not found."
        else:
            return zero_string
    else:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
