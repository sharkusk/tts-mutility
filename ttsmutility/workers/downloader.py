import http.client
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from pathlib import Path
from queue import Empty, Queue

from textual.app import ComposeResult
from textual.message import Message
from textual.worker import get_current_worker

from ..data.config import load_config
from ..parse.AssetList import AssetList
from ..parse.FileFinder import (
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
    trailstring_to_trail,
)
from ..parse.ModList import ModList
from ..utility.advertising import USER_AGENT
from ..utility.messages import UpdateLog
from .TTSWorker import TTSWorker


class Downloader(TTSWorker):
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
            "model/obj",
        ),
        "assetbundle": (
            "text/plain",
            "application/binary",
            "application/octet-stream",
        ),
        "image": (
            "image/jpeg",
            "image/jpg",
            "image/png",
            "application/octet-stream",
            "application/binary",
            "video/mp4",
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
            "image/jpeg",
            "image/jpg",
            "image/png",
            "video/mp4",
        ),
    }

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

    def __init__(
        self,
        timeout: int = 10,
        timeout_retries: int = 10,
        user_agent: str = USER_AGENT,
        status_id: int = 0,
        ignore_content_type: bool = False,
        chunk_size: int = 64 * 1024,
    ):
        super().__init__()
        self.asset_list = AssetList()
        self.mod_list = ModList()
        self.status = ""
        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir
        self.timeout = timeout
        self.timeout_retries = timeout_retries
        self.user_agent = user_agent
        self.status_id = status_id
        self.ignore_content_type = ignore_content_type
        self.chunk_size = chunk_size
        self.tasks = Queue()

    # Base class is installed in each screen, so we don't want
    # to inherit the same widgets when this subclass is mounted
    def compose(self) -> ComposeResult:
        return []

    def add_mods(self, mod_filenames: list) -> None:
        for mod_filename in mod_filenames:
            self.tasks.put(("mod", mod_filename))

    def add_assets(self, assets: list) -> None:
        self.tasks.put(("assets", assets))

    def download_daemon(self) -> None:
        self.worker = get_current_worker()
        mod_name = ""
        mod_filename = ""

        while True:
            if self.worker.is_cancelled:
                return

            try:
                task = self.tasks.get(timeout=1)
            except Empty:
                continue

            fetch_time = time.time()

            if task[0] == "mod":
                mod_filename = task[1]
                turls = self.asset_list.get_missing_assets(mod_filename)
                mod_details = self.mod_list.get_mod_details(mod_filename)
                mod_name = mod_details["name"]
                self.post_message(UpdateLog(f"From mod {mod_name}:"))
            else:
                turls = []
                for asset in task[1]:
                    turls.append((asset["url"], trailstring_to_trail(asset["trail"])))

            self.post_message(
                UpdateLog(
                    f"Starting Download of {len(turls)} assets.",
                    prefix="## ",
                )
            )

            self.post_message(
                self.UpdateProgress(
                    update_total=len(turls),
                    advance_amount=0,
                    status_id=self.status_id,
                )
            )

            for i, (url, trail) in enumerate(turls):
                if self.worker.is_cancelled:
                    self.post_message(UpdateLog("Download worker cancelled."))
                    return
                self.post_message(
                    self.UpdateStatus(
                        f"{mod_name}: Downloading ({i+1}/{len(turls)}): `{url}`"
                    )
                )
                self.download_file(url, trail)

            self.post_message(self.DownloadComplete(status_id=self.status_id))
            self.post_message(self.UpdateStatus(f"Download Complete: {mod_name}"))

            if mod_filename != "":
                self.mod_list.set_fetch_time(mod_filename, fetch_time)

    def state_callback(self, state: str, url: str, data) -> None:
        if state == "error":
            error = data
            asset = {
                "url": url,
                "filename": self.cur_filename,
                "mtime": 0,
                "fsize": 0,
                "sha1": "",
                "steam_sha1": self.steam_sha1,
                "dl_status": error,
                "content_name": self.cur_content_name,
            }
            self.asset_list.download_done(asset)
            self.post_message(self.FileDownloadComplete(asset))
            self.post_message(
                UpdateLog(f"Download Failed ({error}): `{url}`", flush=True)
            )
        elif state == "download_starting":
            self.cur_retry = data
            if self.cur_retry == 0:
                self.post_message(UpdateLog("---", prefix=""))
                self.post_message(UpdateLog(f"Downloading: `{url}`"))
            else:
                self.post_message(UpdateLog(f"Retry #{self.cur_retry}"))
        elif state == "file_size":
            self.cur_filesize = data
            self.post_message(
                self.UpdateProgress(
                    update_total=data, advance_amount=0, status_id=self.status_id
                )
            )
            self.post_message(UpdateLog(f"Filesize: `{self.cur_filesize:,}`"))
        elif state == "data_read":
            self.post_message(
                self.UpdateProgress(advance_amount=data, status_id=self.status_id)
            )
        elif state == "content_name":
            self.cur_content_name = data
            self.post_message(UpdateLog(f"Content Filename: `{self.cur_content_name}`"))
        elif state == "filename":
            self.cur_filename = data
        elif state == "steam_sha1":
            self.steam_sha1 = data
        elif state == "asset_dir":
            self.post_message(UpdateLog(f"Asset dir: `{data}`"))
        elif state == "success":
            filepath = os.path.join(self.mod_dir, self.cur_filename)
            filesize = os.path.getsize(filepath)
            if self.cur_filesize == 0 or filesize == self.cur_filesize:
                mtime = os.path.getmtime(filepath)
                asset = {
                    "url": url,
                    "filename": self.cur_filename,
                    "mtime": mtime,
                    "fsize": filesize,
                    "sha1": "",
                    "steam_sha1": self.steam_sha1,
                    "dl_status": "",
                    "content_name": self.cur_content_name,
                }
                self.asset_list.download_done(asset)
                self.post_message(self.FileDownloadComplete(asset))
                self.post_message(
                    UpdateLog(f"Download Success: `{self.cur_filename}`", flush=True)
                )
            else:
                mtime = 0
                asset = {
                    "url": url,
                    "filename": self.cur_filename,
                    "mtime": mtime,
                    "fsize": filesize,
                    "sha1": "",
                    "steam_sha1": self.steam_sha1,
                    "dl_status": f"Filesize mismatch (expected {self.cur_filesize})",
                    "content_name": self.cur_content_name,
                }
                self.asset_list.download_done(asset)
                self.post_message(self.FileDownloadComplete(asset))
                self.post_message(
                    UpdateLog(
                        (
                            f"Filesize Mismatch. Expected {self.cur_filesize}; "
                            f"received {filesize}: `{self.cur_filename}`"
                        ),
                        flush=True,
                    )
                )
        else:
            # Generic status for logging...
            # self.post_message(UpdateLog(f"{state}: {data}"))
            pass

        if state in ["error", "success"]:
            # Increment overall progress here
            # self.query_one("#dl_progress_all").advance(1)
            pass

        if state in ["init", "error", "download_starting", "success"]:
            # Reset state data here
            self.cur_retry = 0
            self.cur_filename = ""
            self.cur_content_name = ""
            self.cur_filesize = 0
            self.steam_sha1 = ""

        if state in ["download_starting"]:
            self.post_message(
                self.UpdateProgress(
                    update_total=100, advance_amount=0, status_id=self.status_id
                )
            )

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

    def _prep_url_for_download(self, url, trail):
        if type(trail) is not list:
            self.state_callback("error", url, f"trail '{trail}' not converted to list")
            return None

        # Some mods contain malformed URLs missing a prefix. I’m not
        # sure how TTS deals with these. Let’s assume http for now.
        if not urllib.parse.urlparse(url).scheme:
            fetch_url = "http://" + url
        else:
            fetch_url = url

        fetch_url = fetch_url.replace(" ", "%20")

        try:
            hostname = urllib.parse.urlparse(fetch_url).hostname
            if hostname.find("localhost") >= 0:
                self.state_callback("error", url, "localhost url")
                return None
        except (ValueError, AttributeError):
            # URL was so badly formatted that there is no hostname.
            self.state_callback("error", url, "Invalid hostname")
            return None

        # Some MODS do not include the 'raw' link in their pastebin urls, help them out
        if "pastebin.com" in hostname and "raw" not in fetch_url:
            fetch_url = fetch_url.replace("pastebin.com/", "pastebin.com/raw/")

        # type in the response.
        if is_model(trail):
            default_ext = ".obj"
            tts_type = "model"

        elif is_assetbundle(trail):
            default_ext = ".unity3d"
            tts_type = "assetbundle"

        elif is_image(trail):
            default_ext = ".png"
            tts_type = "image"

        elif is_audiolibrary(trail):
            default_ext = ".WAV"
            tts_type = "audiolibrary"

        elif is_pdf(trail):
            default_ext = ".PDF"
            tts_type = "pdf"

        elif is_from_script(trail) or is_custom_ui_asset(trail):
            default_ext = ".png"
            tts_type = "script"

        else:
            errstr = "Do not know how to retrieve URL {url} at {trail}.".format(
                url=url, trail=trail
            )
            # raise ValueError(errstr)
            self.state_callback("error", url, errstr)
            return None

        filename = get_fs_path(trail, url)

        return {
            "url": url,
            "fetch_url": fetch_url,
            "filename": filename,
            "tts_type": tts_type,
            "default_ext": default_ext,
        }

    def download_file(self, url, trail):
        self.state_callback("init", None, None)

        if (dl_info := self._prep_url_for_download(url, trail)) is None:
            return

        first_error = ""
        for i in range(self.timeout_retries):
            self.state_callback("download_starting", url, i)
            try:
                results = self._download_file(
                    url,
                    dl_info["fetch_url"],
                    dl_info["filename"],
                    dl_info["tts_type"],
                    dl_info["default_ext"],
                )
            except socket.timeout:
                continue
            except http.client.IncompleteRead:
                continue
            if results is not None:
                if first_error == "":
                    first_error = results

                # See if we have some trailing URL options and retry if so
                offset = dl_info["fetch_url"].rfind("?")
                if offset > 0:
                    dl_info["fetch_url"] = dl_info["fetch_url"][
                        0 : dl_info["fetch_url"].rfind("?")
                    ]
                    continue

                if "mismatch" in results:
                    # Try again...
                    continue
            break
        else:
            self.state_callback("error", url, "Retries exhausted")
            results = "Retries exhausted"

        if results is None:
            self.state_callback("success", url, None)
            return None
        else:
            # We retried with a different URL, but use the first error
            if first_error != "":
                results = first_error

            self.state_callback("error", url, results)
            return results

    def _download_file(
        self, url, fetch_url, filename, tts_type, default_ext_from_trail
    ):
        headers = {"User-Agent": self.user_agent}

        if (
            filename is not None
            and (existing_file := Path(filename).with_suffix(".tmp")).exists()
        ):
            headers["Range"] = f"bytes={existing_file.stat().st_size}-"
        else:
            existing_file = None

        request = urllib.request.Request(url=fetch_url, headers=headers)

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

        extensions["trail"] = default_ext_from_trail

        if filename is not None:
            extensions["filename"] = os.path.splitext(filename)[1]

        range_support = response.getheader("Accept-Ranges")
        # Some content_type arrives as: 'text/plain; charset=utf-8', we only care about
        # the first part...
        content_type = response.getheader("Content-Type", "").split(";")[0].strip()
        is_expected = not content_type or self.content_expected(content_type, tts_type)
        if not (is_expected or self.ignore_content_type):
            # Google drive sends html error page when file is removed/missing
            return f"Wrong context type ({content_type})"

        if content_type in self.DEFAULT_EXT:
            extensions["mime"] = self.DEFAULT_EXT[content_type]

        # Format of content disposition looks like this:
        # 'attachment; filename="03_Die nostrische Hochzeit (Instrumental).mp3";
        # filename*=UTF-8\'\'03_Die%20nostrische%20Hochzeit%20%28Instrumental%29.mp3'
        content_disposition = response.getheader("Content-Disposition", "").strip()
        offset_std = content_disposition.find('filename="')
        offset_utf = content_disposition.find("filename*=UTF-8")
        content_disp_name = ""
        if offset_std >= 0:
            content_disp_name = content_disposition[offset_std:].split('"')[1]
            extensions["content-disposition"] = os.path.splitext(content_disp_name)[1]
        elif offset_utf >= 0:
            content_disp_name = content_disposition[offset_utf:].split("=UTF-8")[1]
            extensions["content-disposition"] = os.path.splitext(
                content_disp_name.split(";")[0]
            )
        else:
            # Use the url to extract the extension,
            # ignoring any trailing ? url parameters
            offset = url.rfind("?")
            if offset > 0:
                extensions["url"] = os.path.splitext(url[0 : url.rfind("?")])[1]
            else:
                extensions["url"] = os.path.splitext(url)[1]

        if content_disp_name != "":
            if "steamusercontent" in url:
                if url[-1] == "/":
                    hexdigest = os.path.splitext(url)[0][-41:-1]
                else:
                    hexdigest = os.path.splitext(url)[0][-40:]
                content_disp_name = content_disp_name.split(hexdigest + "_")[1]
                self.state_callback("steam_sha1", url, hexdigest)
            self.state_callback("content_name", url, content_disp_name)

        ext = ""
        for key in extensions.keys():
            if extensions[key] != "":
                ext = extensions[key]
                break

        # Override text extensions to be objects
        if ext.lower() == ".txt":
            ext = ".obj"

        # TTS saves some file extensions as upper case
        ext = self.fix_ext_case(ext)
        self.state_callback("ext", url, f"`{ext}` from `{key}`.")

        if filename is None:
            filename = get_fs_path_from_extension(url, ext)
            if filename is None:
                return f"Cannot detect filename ({ext})"

        filename = Path(filename).with_suffix(ext)
        self.state_callback("filename", url, filename)

        filepath = Path(self.mod_dir) / filename
        self.state_callback("filepath", url, filepath)

        asset_dir = os.path.split(os.path.split(filepath)[0])[1]
        self.state_callback("asset_dir", url, f"Mods/{asset_dir}")

        length = response.getheader("Content-Length", 0)
        self.state_callback("file_size", url, int(length))

        temp_path = filepath.with_suffix(".tmp")

        # We are unable to resume, but still have existing file
        if existing_file is None and temp_path.exists():
            os.remove(temp_path)

        try:
            with open(temp_path, "ab") as outfile:
                data = response.read(self.chunk_size)
                while data:
                    self.state_callback("data_read", url, self.chunk_size)
                    outfile.write(data)
                    data = response.read(self.chunk_size)

        except FileNotFoundError as error:
            return f"Error writing object to disk: {error}"

        # Don’t leave files with partial content lying around.
        except Exception:
            with suppress(FileNotFoundError):
                os.remove(temp_path)
            raise

        except SystemExit:
            with suppress(FileNotFoundError):
                os.remove(temp_path)
            raise

        if length != 0 and os.path.getsize(temp_path) != int(length):
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
            os.remove(filepath)

        os.rename(temp_path, filepath)

        return None
