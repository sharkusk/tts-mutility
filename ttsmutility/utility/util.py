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
    if "steamusercontent" in url or "steamuserimages" in url:
        if url[-1] == "/":
            hexdigest = os.path.splitext(url)[0][-41:-1]
        else:
            hexdigest = os.path.splitext(url)[0][-40:]
    return hexdigest


def get_content_name(url: str, content_disposition: str = "") -> str:
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

        if "." not in content_name:
            content_name = ""
        elif ext.lower() not in ALL_VALID_EXTS:
            content_name = ""

    if content_name != "":
        steam_sha1 = get_steam_sha1_from_url(url)
        if steam_sha1 != "" and steam_sha1 in content_name and "_" in content_name:
            # Steam context_disp_names is formatted like: SHA1_<filename>
            content_name = content_name.split("_", 1)[1]

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
