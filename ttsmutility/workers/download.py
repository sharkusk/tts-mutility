from textual.worker import Worker
from textual.message import Message
from textual.message import Message
from textual.worker import Worker, get_current_worker
from rich.markdown import Markdown as RichMarkdown

from ..parse.FileFinder import trailstring_to_trail
from ..parse.AssetList import AssetList
from ..data.config import load_config
from ..parse.FileFinder import (
    UPPER_EXTS,
    get_fs_path_from_extension,
    is_obj,
    is_assetbundle,
    is_audiolibrary,
    is_custom_ui_asset,
    is_from_script,
    is_image,
    is_pdf,
    get_fs_path,
)
from ..utility.advertising import USER_AGENT
from ..workers.messages import (
    UpdateLog,
    UpdateProgress,
    DownloadComplete,
    FileDownloadComplete,
)

from contextlib import suppress
import http.client
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class AssetDownloader(Worker):
    DEFAULT_EXT = {
        "text/plain": ".obj",
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "video/mp4": ".mp4",
    }

    def add_assets(
        self,
        assets: list or str,
        timeout: int = 10,
        timeout_retries: int = 10,
        user_agent: str = USER_AGENT,
        status_id: int = 0,
        ignore_content_type: bool = False,
    ) -> None:
        self.assets = assets
        self.status = ""
        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir
        self.timeout = timeout
        self.timeout_retries = timeout_retries
        self.user_agent = user_agent
        self.status_id = status_id
        self.ignore_content_type = ignore_content_type

    def run(self) -> None:
        self.asset_list = AssetList()
        self.cur_retry = 0
        self.cur_filepath = ""
        self.cur_filesize = 0

        self.urls = []

        # A mod name was passed insteam of a list of assets
        if type(self.assets) is str:
            self.urls = self.asset_list.get_missing_assets(self.assets)
        else:
            for asset in self.assets:
                self.urls.append((asset["url"], trailstring_to_trail(asset["trail"])))

        self.node.post_message(
            UpdateProgress(
                update_total=len(self.urls), advance_amount=0, status_id=self.status_id
            )
        )
        self.download_files()
        self.node.post_message(DownloadComplete(status_id=self.status_id))

    def state_callback(self, state: str, url: str, data) -> None:
        if state == "error":
            error = data
            asset = {
                "url": url,
                "filename": self.cur_filepath,
                "mtime": 0,
                "fsize": 0,
                "sha1": "",
                "steam_sha1": self.steam_sha1,
                "dl_status": error,
                "content_name": self.cur_content_name,
            }
            self.asset_list.download_done(asset)
            self.node.post_message(FileDownloadComplete(asset))
            self.node.post_message(UpdateLog(f"Download Failed ({error}): `{url}`"))
        elif state == "download_starting":
            self.cur_retry = data
            if self.cur_retry == 0:
                self.node.post_message(
                    UpdateLog(f"---", prefix="", update_status=False)
                )
                self.node.post_message(UpdateLog(f"Downloading: `{url}`"))
            else:
                self.node.post_message(
                    UpdateLog(f"Retry #{self.cur_retry}", update_status=False)
                )
        elif state == "file_size":
            self.cur_filesize = data
            self.node.post_message(
                UpdateProgress(
                    update_total=data, advance_amount=0, status_id=self.status_id
                )
            )
            self.node.post_message(
                UpdateLog(f"Filesize: {self.cur_filesize:,}", update_status=False)
            )
        elif state == "data_read":
            self.node.post_message(
                UpdateProgress(advance_amount=data, status_id=self.status_id)
            )
        elif state == "content_name":
            self.cur_content_name = data
            self.node.post_message(
                UpdateLog(
                    f"Content Filename: {self.cur_content_name}", update_status=False
                )
            )
        elif state == "filepath":
            self.cur_filepath = data
        elif state == "steam_sha1":
            self.steam_sha1 = data
        elif state == "asset_dir":
            self.node.post_message(UpdateLog(f"Asset dir: {data}", update_status=False))
        elif state == "success":
            filepath = os.path.join(self.mod_dir, self.cur_filepath)
            filesize = os.path.getsize(filepath)
            if self.cur_filesize == 0 or filesize == self.cur_filesize:
                mtime = os.path.getmtime(filepath)
                asset = {
                    "url": url,
                    "filename": self.cur_filepath,
                    "mtime": mtime,
                    "fsize": filesize,
                    "sha1": "",
                    "steam_sha1": self.steam_sha1,
                    "dl_status": "",
                    "content_name": self.cur_content_name,
                }
                self.asset_list.download_done(asset)
                self.node.post_message(FileDownloadComplete(asset))
                self.node.post_message(
                    UpdateLog(f"Download Success: `{self.cur_filepath}`")
                )
            else:
                mtime = 0
                asset = {
                    "url": url,
                    "filename": self.cur_filepath,
                    "mtime": mtime,
                    "fsize": filesize,
                    "sha1": "",
                    "steam_sha1": self.steam_sha1,
                    "dl_status": f"Filesize mismatch (expected {self.cur_filesize})",
                    "content_name": self.cur_content_name,
                }
                self.asset_list.download_done(asset)
                self.node.post_message(FileDownloadComplete(asset))
                self.node.post_message(
                    UpdateLog(
                        f"Filesize Mismatch. Expected {self.cur_filesize}; received {filesize}: `{self.cur_filepath}`"
                    )
                )
        else:
            # Generic status for logging...
            self.node.post_message(UpdateLog(f"{state}: {data}", update_status=False))

        if state in ["error", "success"]:
            # Increment overall progress here
            # self.query_one("#dl_progress_all").advance(1)
            pass

        if state in ["init", "error", "download_starting", "success"]:
            # Reset state data here
            self.cur_retry = 0
            self.cur_filepath = ""
            self.cur_content_name = ""
            self.cur_filesize = 0
            self.steam_sha1 = ""

        if state in ["download_starting"]:
            self.node.post_message(
                UpdateProgress(
                    update_total=100, advance_amount=0, status_id=self.status_id
                )
            )

    def fix_ext_case(self, ext):
        if ext.lower() in UPPER_EXTS:
            return ext.upper()
        else:
            return ext.lower()

    def download_files(self):
        self.state_callback("init", None, None)
        worker = get_current_worker()

        for url, trail in self.urls:
            if worker.is_cancelled:
                self.node.post_message(UpdateLog(f"Download worker cancelled."))
                return

            if type(trail) is not list:
                self.state_callback(
                    "error", url, f"trail '{trail}' not converted to list"
                )
                continue

            # Some mods contain malformed URLs missing a prefix. I’m not
            # sure how TTS deals with these. Let’s assume http for now.
            if not urllib.parse.urlparse(url).scheme:
                fetch_url = "http://" + url
            else:
                fetch_url = url

            try:
                if urllib.parse.urlparse(fetch_url).hostname.find("localhost") >= 0:
                    self.state_callback("error", url, f"localhost url")
                    continue
            except:
                # URL was so badly formatted that there is no hostname.
                self.state_callback("error", url, f"Invalid hostname")
                continue

            # type in the response.
            if is_obj(trail):
                default_ext = ".obj"

                def content_expected(mime):
                    return any(
                        map(
                            mime.startswith,
                            (
                                "text/plain",
                                "application/binary",
                                "application/octet-stream",
                                "application/json",
                                "application/x-tgif",
                            ),
                        )
                    )

            elif is_assetbundle(trail):
                default_ext = ".unity3d"

                def content_expected(mime):
                    return any(
                        map(
                            mime.startswith,
                            (
                                "text/plain",
                                "application/binary",
                                "application/octet-stream",
                            ),
                        )
                    )

            elif is_image(trail):
                default_ext = ".png"

                def content_expected(mime):
                    return mime in (
                        "image/jpeg",
                        "image/jpg",
                        "image/png",
                        "application/octet-stream",
                        "application/binary",
                        "video/mp4",
                    )

            elif is_audiolibrary(trail):
                default_ext = ".WAV"

                def content_expected(mime):
                    return mime in (
                        "application/octet-stream",
                        "application/binary",
                    ) or mime.startswith("audio/")

            elif is_pdf(trail):
                default_ext = ".PDF"

                def content_expected(mime):
                    return mime in (
                        "application/pdf",
                        "application/binary",
                        "application/octet-stream",
                    )

            elif is_from_script(trail) or is_custom_ui_asset(trail):
                default_ext = ".png"

                def content_expected(mime):
                    return mime in (
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
                    )

            else:
                errstr = "Do not know how to retrieve URL {url} at {trail}.".format(
                    url=url, trail=trail
                )
                raise ValueError(errstr)

            filepath = get_fs_path(trail, url)
            if filepath is not None:
                filepath = Path(self.mod_dir) / filepath

            for i in range(self.timeout_retries):
                self.state_callback("download_starting", url, i)
                try:
                    results = self.download_file(
                        url,
                        fetch_url,
                        filepath,
                        content_expected,
                        default_ext,
                    )
                except socket.timeout as error:
                    continue
                except http.client.IncompleteRead as error:
                    continue
                if results is not None:
                    # See if we have some trailing URL options and retry if so
                    offset = fetch_url.rfind("?")
                    if offset > 0:
                        fetch_url = fetch_url[0 : fetch_url.rfind("?")]
                        continue
                break
            else:
                self.state_callback("error", url, f"Retries exhausted")
                continue

            if results is None:
                self.state_callback("success", url, None)
            else:
                self.state_callback("error", url, results)

    def download_file(
        self, url, fetch_url, filepath, content_expected, default_ext_from_trail
    ):
        headers = {"User-Agent": self.user_agent}
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
                return f"Removed"
        except UnboundLocalError:
            pass

        length = response.getheader("Content-Length", 0)
        self.state_callback("file_size", url, int(length))

        # Possible ways to determine the file extension.
        # Use them in this order...
        extensions = {
            "content-disposition": "",
            "filepath": "",
            "url": "",
            "mime": "",
            "trail": "",
        }

        extensions["trail"] = default_ext_from_trail

        if filepath is not None:
            extensions["filepath"] = os.path.splitext(filepath)[1]

        # Some content_type arrives as: 'text/plain; charset=utf-8', we only care about
        # the first part...
        content_type = response.getheader("Content-Type", "").split(";")[0].strip()
        is_expected = not content_type or content_expected(content_type)
        if not (is_expected or self.ignore_content_type):
            # Google drive sends html error page when file is removed/missing
            return f"Wrong context type ({content_type})"

        if content_type in self.DEFAULT_EXT:
            extensions["mime"] = self.DEFAULT_EXT[content_type]

        # Format of content disposition looks like this:
        # 'attachment; filename="03_Die nostrische Hochzeit (Instrumental).mp3"; filename*=UTF-8\'\'03_Die%20nostrische%20Hochzeit%20%28Instrumental%29.mp3'
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
            # Use the url to extract the extension, ignoring any trailing ? url parameters
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

        # TTS saves some file extensions as upper case
        ext = self.fix_ext_case(ext)
        self.state_callback("ext", url, f"`{ext}` from `{key}`.")

        if filepath is None:
            filepath = get_fs_path_from_extension(url, ext)
            if filepath is None:
                return f"Cannot detect filepath ({ext})"

        filepath = Path(self.mod_dir) / (os.path.splitext(filepath)[0] + ext)
        self.state_callback("filepath", url, filepath)

        asset_dir = os.path.split(os.path.split(filepath)[0])[1]
        self.state_callback("asset_dir", url, f"Mods/{asset_dir}")

        try:
            with open(filepath, "wb") as outfile:
                data = response.read(1024 * 8)
                while data:
                    self.state_callback("data_read", url, 1024 * 8)
                    outfile.write(data)
                    data = response.read(1024 * 8)

        except FileNotFoundError as error:
            return f"Error writing object to disk: {error}"

        # Don’t leave files with partial content lying around.
        except Exception:
            with suppress(FileNotFoundError):
                os.remove(filepath)
            raise

        except SystemExit:
            with suppress(FileNotFoundError):
                os.remove(filepath)
            raise

        return None
