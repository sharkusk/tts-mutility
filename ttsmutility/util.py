import time

def format_time(mtime: float) -> str:
    if mtime == 0:
        return "File not found."
    else:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
