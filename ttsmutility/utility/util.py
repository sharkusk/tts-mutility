import os
import time
from urllib.parse import unquote, urlparse

from rich.text import Text

from ..parse.FileFinder import ALL_VALID_EXTS


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


def get_steam_sha1_from_url(url):
    hexdigest = ""
    if "steamuser" in url:
        if url[-1] == "/":
            hexdigest = os.path.splitext(url)[0][-41:-1]
        else:
            hexdigest = os.path.splitext(url)[0][-40:]
    return hexdigest


def get_content_name(url: str, content_disposition: str = "") -> str:
    url = url.strip()
    domain = urlparse(url).netloc

    content_name = ""
    if content_disposition != "":
        offset_std = content_disposition.find('filename="')
        offset_utf = content_disposition.find("filename*=UTF-8")
        if offset_std >= 0:
            # 'attachment; filename="03_Die nostrische Hochzeit (Instrumental).mp3";
            content_name = content_disposition[offset_std:].split('"')[1]
            # We need to convert the default latin-1 string to python's UTF-8 format
            content_name = bytes(content_name, "latin-1")
            content_name = content_name.decode("utf-8")
        elif offset_utf >= 0:
            # filename*=UTF-8\'\'03_Die%20nostrische%20Hochzeit%20%28Instrumental%29.mp3
            # filename*=UTF-8''653EFA7169C93BDC37E31595198855C3AD4A308F_tombstone_map-oct2018.jpg;
            content_name = content_disposition[offset_utf:].split("=UTF-8")[1]
            content_name = content_name.split("'")[2]
            if content_name[-1] == ";":
                content_name = content_name[:-1]
            content_name = unquote(content_name)
    elif "nocookie.net" in domain and "/revision" in url:
        # https://static.wikia.nocookie.net/zombicide/images/4/45/Rocksteady_1ed_2ed.png/revision/latest?cb=20210309165458
        content_name = url.split("/revision")[0]
        content_name = content_name.split("/")[-1]
        content_name = unquote(content_name)
    else:
        # imgur.com can have garbage appended after extension
        if "imgur.com" in domain:
            if url[-1] == "/":
                url = url[0:-1]

        # Attempt to get content name from URL
        content_name = unquote(url.split("/")[-1])
        if "?" in content_name:
            content_name = content_name.split("?")[0]

        name, ext = os.path.splitext(content_name)
        # imgur.com can have garbage appended after extension
        if "imgur.com" in domain:
            if len(ext) > 4:
                ext = ext[0:4]
                content_name = name + ext

        if content_name != "" and "." not in content_name:
            # githubusercontent doesn't always contain the ext :(
            if "githubusercontent" not in domain and "singlecolorimage" not in domain:
                content_name = ""
        elif ext.lower() not in ALL_VALID_EXTS:
            content_name = ""

    if content_name != "":
        steam_sha1 = get_steam_sha1_from_url(url)
        if steam_sha1 != "" and steam_sha1 in content_name and "_" in content_name:
            # Steam context_disp_names is formatted like: SHA1_<filename>
            content_name = content_name.rsplit(steam_sha1 + "_", 1)[1]

    return content_name


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


def detect_file_type(filepath):
    FILE_TYPES = {
        ".unity3d": b"\x55\x6e\x69\x74\x79\x46\x53",  # UnityFS
        ".OGG": b"\x47\x67\x67\x53",
        ".WAV": b"\x52\x49\x46\x46",  # RIFF
        ".MP3": b"\x49\x44\x33",  # ID3
        ".png": b"\x89\x50\x4E\x47",  # ?PNG
        ".jpg": b"\xFF\xD8",  # ??
        ".obj": b"\x23\x20",  # "# "
        ".PDF": b"\x25\x50\x44\x46",  # %PDF
    }
    with open(filepath, "rb") as f:
        f_data = f.read(10)
        for ext, pattern in FILE_TYPES.items():
            if pattern in f_data[0 : len(pattern)]:
                return ext
        else:
            return ""


def sizeof_fmt(num, suffix="B"):
    for i, unit in enumerate(("  ", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi")):
        if abs(num) < 1024.0:
            return f"{num:7.2f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.{i}f} Yi{suffix}"


def unsizeof_fmt(size, suffix="B"):
    for i, unit in enumerate(("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi")):
        if f" {unit}{suffix}" in size:
            try:
                size = float(size[: size.find(f" {unit}{suffix}")]) * (1024.0**i)
            except ValueError:
                pass
            break
    return size


def is_number(s: str) -> bool:
    return s.replace(".", "", 1).isdigit()


def str_to_num(s: str) -> int | float | str:
    if s.isdigit():
        return int(s)
    elif is_number(s):
        return float(s)
    return s
