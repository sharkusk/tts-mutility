from textual.app import ComposeResult
from textual.widgets import TextLog, ProgressBar, Footer
from textual.containers import VerticalScroll, Container
from textual.screen import ModalScreen
from textual.message import Message

from ttsmutility.parse.AssetList import AssetList
from ttsmutility.fetch.AssetDownload import download_files

from rich.markdown import Markdown

import sys
import os


class AssetDownloadScreen(ModalScreen):
    BINDINGS = [("escape", "exit", "OK")]

    class StatusOutput(Message):
        def __init__(self, status: str) -> None:
            self.status = status
            super().__init__()

    class FileDownloadComplete(Message):
        def __init__(
            self,
            asset: dict,
        ) -> None:
            self.asset = asset
            super().__init__()

    class DownloadComplete(Message):
        def __init__(self):
            super().__init__()

    def __init__(self, mod_dir: str, save_dir: str, assets: list or str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        self.assets = assets
        self.download_complete = False
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Container(
            ProgressBar(id="dl_progress_all", show_eta=False),
            ProgressBar(id="dl_progress_cur", show_eta=False),
            VerticalScroll(
                TextLog(id="dl_log", highlight=True, markup=True),
                id="dl_scroll",
            ),
            Footer(),
            id="dl_screen",
        )
        self.run_worker(self.download_assets)

    def action_exit(self) -> None:
        if self.download_complete:
            self.app.pop_screen()

    def status_cb(self, state: str, url: str, data) -> None:
        if state == "error":
            error = data
            asset = {
                "url": url,
                "filename": self.cur_filepath,
                "mtime": 0,
                "fsize": 0,
                "sha1": "",
                "dl_status": error,
                "content_name": self.cur_content_name,
            }
            self.asset_list.download_done(url, asset)
            self.post_message(self.FileDownloadComplete(asset))
            self.post_message(self.StatusOutput(f"- Download Failed: {error}\n"))
        elif state == "download_starting":
            self.cur_retry = data
            if self.cur_retry == 0:
                self.post_message(self.StatusOutput(f"---\n"))
                self.post_message(self.StatusOutput(f"- Downloading: {url}\n"))
            else:
                self.post_message(self.StatusOutput(f"- Retry #{self.cur_retry}\n"))
        elif state == "file_size":
            self.cur_filesize = data
            self.query_one("#dl_progress_cur").update(total=data, progress=0)
        elif state == "data_read":
            self.query_one("#dl_progress_cur").advance(data)
        elif state == "content_name":
            self.cur_content_name = data
            self.post_message(
                self.StatusOutput(f"- Content Filename: {self.cur_content_name}\n")
            )
        elif state == "filepath":
            self.cur_filepath = data
        elif state == "asset_dir":
            self.post_message(self.StatusOutput(f"- Asset dir: {data}"))
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
                    "dl_status": "",
                    "content_name": self.cur_content_name,
                }
                self.asset_list.download_done(asset)
                self.post_message(self.FileDownloadComplete(asset))
                self.post_message(
                    self.StatusOutput(f"- Download success: {self.cur_filepath}\n")
                )
            else:
                mtime = 0
                asset = {
                    "url": url,
                    "filename": self.cur_filepath,
                    "mtime": mtime,
                    "fsize": filesize,
                    "sha1": "",
                    "dl_status": f"Filesize mismatch (expected {self.cur_filesize})",
                    "content_name": self.cur_content_name,
                }
                self.asset_list.download_done(asset)
                self.post_message(self.FileDownloadComplete(asset))
                self.post_message(
                    self.StatusOutput(
                        f"- Filesize mismatch. Expected {self.cur_filesize}, received {filesize} \n- {self.cur_filepath}\n"
                    )
                )
        else:
            # Unknown state!
            sys.exit(1)

        if state in ["error", "success"]:
            # Increment overall progress here
            self.query_one("#dl_progress_all").advance(1)

        if state in ["error", "download_starting", "success"]:
            # Reset state data here
            self.cur_retry = 0
            self.cur_filepath = ""
            self.cur_content_name = ""
            self.cur_filesize = 0
            self.query_one("#dl_progress_cur").update(total=100, progress=0)

    def download_assets(self) -> None:
        self.asset_list = AssetList(self.mod_dir, self.save_dir)
        self.cur_retry = 0
        self.cur_filepath = ""
        self.cur_filesize = 0

        urls = []

        # A mod name was passed insteam of a list of assets
        if type(self.assets) is str:
            urls = self.asset_list.get_missing_assets(self.assets)
            overwrite = False
        else:
            for asset in self.assets:
                urls.append((asset["url"], asset["trail"].split("->")))
            overwrite = True

        self.query_one("#dl_progress_all").update(total=len(urls), progress=0)

        download_files(
            urls, self.mod_dir, self.status_cb, ignore_content_type=overwrite
        )

        self.asset_list.commit()
        self.post_message(self.DownloadComplete())

    def on_asset_download_screen_status_output(self, event: StatusOutput):
        self.query_one("#dl_log").write(Markdown(event.status))

    def on_asset_download_screen_download_complete(self):
        self.query_one("#dl_screen").toggle_class("unhide")
        self.download_complete = True
