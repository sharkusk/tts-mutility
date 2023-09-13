import http.client
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from pathlib import Path

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget

from ..data.config import load_config
from ..parse.FileFinder import (
    ALL_VALID_EXTS,
    UPPER_EXTS,
    get_fs_path,
    get_fs_path_from_extension,
    is_assetbundle,
    is_audiolibrary,
    is_custom_ui_asset,
    is_from_script,
    is_image,
    is_model,
    is_pdf,
)
from ..utility.advertising import USER_AGENT
from ..utility.messages import UpdateLog
from ..utility.util import get_steam_sha1_from_url, get_content_name, detect_file_type


class FileDownload(Widget):
    class FileDownloadProgress(Message):
        def __init__(self, url, filesize=None, bytes_complete=0) -> None:
            super().__init__()
            self.url = url
            self.filesize = filesize
            self.bytes_complete = bytes_complete

    DEFAULT_EXT = {
        "text/plain": ".obj",
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "video/mp4": ".mp4",
    }

    MIME_TYPES = {
        "model": (
            "text/plain",
            "application/binary",
            "application/octet-stream",
            "application/json",
            "application/x-tgif",
            "binary/octet-stream",
            "model/obj",
        ),
        "assetbundle": (
            "text/plain",
            "application/binary",
            "application/octet-stream",
            "application/vnd.unity",
        ),
        "image": (
            "image/jpeg",
            "image/jpg",
            "image/png",
            "application/octet-stream",
            "application/binary",
            "video/mp4",
            "video/webm",
        ),
        "audiolibrary": (
            "application/octet-stream",
            "application/binary",
            "audio/",
        ),
        "pdf": (
            "application/pdf",
            "application/binary",
            "application/octet-stream",
        ),
        "script": (
            "text/plain",
            "application/pdf",
            "application/binary",
            "application/octet-stream",
            "application/json",
            "application/x-tgif",
            "application/vnd.unity",
            "image/jpeg",
            "image/jpg",
            "image/png",
            "video/mp4",
        ),
    }

    def __init__(
        self,
        url,
        trail,
        timeout: int = 10,
        timeout_retries: int = 10,
        user_agent: str = USER_AGENT,
        status_id: int = 0,
        ignore_content_type: bool = False,
        chunk_size: int = 64 * 1024,
    ):
        super().__init__()
        self.url = url.strip()
        self.trail = trail
        self.timeout = timeout
        self.timeout_retries = timeout_retries
        self.user_agent = user_agent
        self.status_id = status_id
        self.ignore_content_type = ignore_content_type
        self.chunk_size = chunk_size

        config = load_config()
        self.mod_dir = config.tts_mods_dir

        # Asset information
        # TODO: Convert assets and other structures to named tuples
        self.cur_retry = 0
        self.filename = ""
        self.content_name = ""
        self.filesize = 0
        self.steam_sha1 = ""
        self.error = ""
        self.mtime = 0

    def compose(self) -> ComposeResult:
        return []

    def make_asset(self):
        asset = {
            "url": self.url,
            "filename": self.filename,
            "mtime": self.mtime,
            "size": self.filesize,
            "sha1": "",
            "steam_sha1": self.steam_sha1,
            "dl_status": self.error,
            "content_name": self.content_name,
            "ignore_missing": False,
        }
        return asset

    def fix_ext_case(self, ext):
        if ext.lower() in UPPER_EXTS:
            return ext.upper()
        else:
            return ext.lower()

    def content_expected(self, mime, tts_asset_type):
        return any(
            map(
                mime.startswith,
                self.MIME_TYPES[tts_asset_type],
            )
        )

    def _prep_url_for_download(self):
        # Some mods contain malformed URLs missing a prefix. I’m not
        # sure how TTS deals with these. Let’s assume http for now.
        if not urllib.parse.urlparse(self.url).scheme:
            self.fetch_url = "http://" + self.url
        else:
            self.fetch_url = self.url

        self.fetch_url = self.fetch_url.replace(" ", "%20")

        try:
            hostname = urllib.parse.urlparse(self.fetch_url).hostname
            if hostname.find("localhost") >= 0:
                self.error = "localhost url"
                return
        except (ValueError, AttributeError):
            # URL was so badly formatted that there is no hostname.
            self.error = "Invalid hostname"
            return

        if "paste.ee" in hostname and "/p/" in self.fetch_url:
            self.fetch_url = self.fetch_url.replace("paste.ee/p/", "paste.ee/d/")

        if "steamusercontent" in hostname and self.fetch_url[-1] != "/":
            # Steam links must always end in / or the download will fail
            self.fetch_url += "/"

        # Obtain preliminary content_name from url if possible
        self.content_name = get_content_name(self.url)

        # type in the response.
        if is_model(self.trail):
            self.default_ext = ".obj"
            self.tts_type = "model"
        elif is_assetbundle(self.trail):
            self.default_ext = ".unity3d"
            self.tts_type = "assetbundle"
        elif is_image(self.trail):
            self.default_ext = ".png"
            self.tts_type = "image"
        elif is_audiolibrary(self.trail):
            self.default_ext = ".WAV"
            self.tts_type = "audiolibrary"
        elif is_pdf(self.trail):
            self.default_ext = ".PDF"
            self.tts_type = "pdf"
        elif is_from_script(self.trail) or is_custom_ui_asset(self.trail):
            self.default_ext = ".png"
            self.tts_type = "script"
        else:
            errstr = "Do not know how to retrieve URL {url} at {trail}.".format(
                url=self.url, trail=self.trail
            )
            self.error = errstr
            return

        self.filename = get_fs_path(self.trail, self.url)
        return

    def download(self):
        self._prep_url_for_download()
        if self.error != "":
            return self.error, self.make_asset()

        first_error = ""
        for i in range(self.timeout_retries):
            if i == 0:
                self.post_message(UpdateLog("---", prefix=""))
                self.post_message(UpdateLog(f"Downloading: `{self.url}`"))
            else:
                self.post_message(UpdateLog(f"Retry #{i}"))
            try:
                error = self._download_file()
            except socket.timeout:
                continue
            except http.client.IncompleteRead:
                continue
            if error is not None:
                if first_error == "":
                    first_error = error

                # See if we have some trailing URL options and retry if so
                offset = self.fetch_url.rfind("?")
                if offset > 0:
                    self.fetch_url = self.fetch_url[0 : self.fetch_url.rfind("?")]
                    continue

                if "mismatch" in error:
                    # Try again...
                    continue
            break
        else:
            return "Retries exhausted", self.make_asset()

        if error is None:
            filepath = os.path.join(self.mod_dir, str(self.filename))
            self.filesize = os.path.getsize(filepath)
            self.mtime = os.path.getmtime(filepath)
            self.post_message(
                UpdateLog(f"Download Success: `{self.filename}`", flush=True)
            )
            self.error = ""
            return "", self.make_asset()
        else:
            # We retried with a different URL, but use the first error
            if first_error != "":
                self.error = first_error
            return self.error, self.make_asset()

    def _download_file(self):
        headers = {"User-Agent": self.user_agent}

        if "pastebin.com" in self.fetch_url:
            # Pastebin will provide us the original filename if we use the dl link.
            # This requires a referer from the original pastebin link, so we need
            # to extract it.
            pastebin_ref = ""
            if "pastebin.com/raw.php" in self.fetch_url:
                pastebin_ref = self.fetch_url.split("=")[-1]
            else:
                pastebin_ref = self.fetch_url.split("/")[-1]

            if len(pastebin_ref) > 0:
                headers["Referer"] = f"http://pastebin.com/{pastebin_ref}"
                self.fetch_url = f"http://pastebin.com/dl/{pastebin_ref}"

        if (
            self.filename is not None
            and (existing_file := Path(self.filename).with_suffix(".tmp")).exists()
        ):
            headers["Range"] = f"bytes={existing_file.stat().st_size}-"
        else:
            existing_file = None

        request = urllib.request.Request(url=self.fetch_url, headers=headers)

        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)

        except urllib.error.HTTPError as error:
            return f"HTTPError {error.code} ({error.reason})"

        except urllib.error.URLError as error:
            return f"URLError ({error.reason})"

        except http.client.HTTPException as error:
            return f"HTTPException ({error})"

        try:
            if os.path.basename(response.url) == "removed.png":
                # Imgur sends bogus png when files are missing, ignore them
                return "Removed"
        except UnboundLocalError:
            pass

        # Possible ways to determine the file extension.
        # Use them in this order...
        extensions = {
            "content-disposition": "",
            "filename": "",
            "url": "",
            "mime": "",
            "trail": "",
        }

        extensions["trail"] = self.default_ext

        if self.filename is not None:
            extensions["filename"] = os.path.splitext(self.filename)[1]

        range_support = response.getheader("Accept-Ranges")
        # Some content_type arrives as: 'text/plain; charset=utf-8', we only care about
        # the first part...
        content_type = response.getheader("Content-Type", "").split(";")[0].strip()
        is_expected = not content_type or self.content_expected(
            content_type, self.tts_type
        )
        if not (is_expected or self.ignore_content_type):
            # Google drive sends html error page when file is removed/missing
            return f"Wrong context type ({content_type})"

        self.steam_sha1 = get_steam_sha1_from_url(self.url)

        if content_type in self.DEFAULT_EXT:
            extensions["mime"] = self.DEFAULT_EXT[content_type]

        # Format of content disposition looks like this:
        content_disposition = response.getheader("Content-Disposition", "").strip()
        if content_disposition == "":
            content_disposition = response.getheader("content-disposition", "").strip()
        self.content_name = get_content_name(self.url, content_disposition)

        if self.content_name != "":
            self.post_message(UpdateLog(f"Content Filename: `{self.content_name}`"))
            extensions["content-disposition"] = os.path.splitext(self.content_name)[1]

        # Use the url to extract the extension,
        # ignoring any trailing ? url parameters
        offset = self.url.rfind("?")
        if offset > 0:
            extensions["url"] = os.path.splitext(self.url[0 : self.url.rfind("?")])[1]
        else:
            extensions["url"] = os.path.splitext(self.url)[1]

        ext = ""
        for key in extensions.keys():
            if extensions[key] != "" and extensions[key] in ALL_VALID_EXTS:
                ext = extensions[key]
                break

        # Override text extensions to be objects
        if ext.lower() == ".txt":
            ext = ".obj"

        if ext.lower() == ".jpeg":
            ext = ".jpg"

        # TTS saves some file extensions as upper case
        ext = self.fix_ext_case(ext)

        if self.filename is None:
            self.filename = get_fs_path_from_extension(self.url, ext)
            if self.filename is None:
                return f"Invalid filename ({ext})"

        self.filename = Path(self.filename).with_suffix(ext)
        filepath = Path(self.mod_dir) / self.filename
        asset_dir = os.path.split(os.path.split(filepath)[0])[1]
        self.post_message(UpdateLog(f"Asset dir: `{asset_dir}`"))

        length = int(response.getheader("Content-Length", 0))
        self.post_message(
            self.FileDownloadProgress(self.url, filesize=length, bytes_complete=0)
        )
        self.post_message(UpdateLog(f"URL Filesize: `{length}`"))

        temp_path = filepath.with_suffix(".tmp")

        # We are unable to resume, but still have existing file
        if existing_file is None and temp_path.exists():
            os.remove(temp_path)

        # This will actually go negative since we already assume
        # that we will read the chunk_size.
        remaining = length
        try:
            with open(temp_path, "ab") as outfile:
                data = response.read(self.chunk_size)
                remaining -= self.chunk_size
                while data:
                    if remaining < 0:
                        bytes_complete = self.chunk_size - remaining
                    else:
                        bytes_complete = self.chunk_size

                    self.post_message(
                        self.FileDownloadProgress(
                            self.url, bytes_complete=bytes_complete
                        )
                    )
                    outfile.write(data)
                    data = response.read(self.chunk_size)
                    remaining -= self.chunk_size

        except FileNotFoundError as error:
            return f"Error writing object to disk: {error}"

        except OSError as error:
            if "[Errno 22]" in str(error):
                return f"Filename too long ({len(str(temp_path))} chars) for Windows. "
            else:
                return f"{error}"

        # Don’t leave files with partial content lying around.
        except SystemExit:
            with suppress(FileNotFoundError):
                os.remove(temp_path)
            raise

        if length != 0 and os.path.getsize(temp_path) != length:
            msg = (
                f"Filesize mismatch. Received {os.path.getsize(temp_path)}. "
                f"Expected {length}."
            )
            # Check if the server supports resuming downloads,
            # if not remove the temp file
            if range_support is None or range_support != "bytes":
                os.remove(temp_path)
            return msg

        # We are all good!
        if filepath.exists():
            # There may be an old file around, delete it.
            os.remove(filepath)

        file_ext = detect_file_type(temp_path)
        if file_ext != "":
            filepath = filepath.with_suffix(file_ext)
            self.filename = self.filename.with_suffix(file_ext)

        os.rename(temp_path, filepath)

        return None
