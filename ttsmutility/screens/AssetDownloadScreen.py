from textual.app import ComposeResult
from textual.widgets import Static, ProgressBar, Footer
from textual.containers import Container
from textual.screen import ModalScreen
from textual.message import Message

from ttsmutility.parse.AssetList import AssetList
from ttsmutility.fetch.AssetDownload import download_files

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

    def __init__(self, mod_dir: str, assets: list or str) -> None:
        self.mod_dir = mod_dir
        self.assets = assets
        self.download_complete = False
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Container(
            ProgressBar(id="all_dl_progress", show_eta=False),
            ProgressBar(id="cur_dl_progress", show_eta=False),
            Static(id="downloadoutput"),
            Footer(),
            id="downloadscreen",
        )
        self.run_worker(self.download_assets)

    def action_exit(self) -> None:
        if self.download_complete:
            self.app.pop_screen()

    def status_cb(self, state: str, url: str, data) -> None:
        if state == "error":
            error = data
            self.asset_list.download_done(url, self.cur_filepath, 0, 0, error)
            self.post_message(
                self.FileDownloadComplete(
                    {
                        "url": url,
                        "filename": self.cur_filepath,
                        "mtime": 0,
                        "fsize": 0,
                        "sha1": "",
                        "dl_status": error,
                    }
                )
            )
            self.post_message(
                self.StatusOutput(
                    f"Download Failed: {url} -> {self.cur_filepath} -- {error}"
                )
            )
        elif state == "download_starting":
            self.cur_retry = data
            self.post_message(
                self.StatusOutput(f"Downloading (Retry {self.cur_retry}): {url}")
            )
        elif state == "file_size":
            self.cur_filesize = data
            self.query_one("#cur_dl_progress").update(total=data, progress=0)
        elif state == "data_read":
            self.query_one("#cur_dl_progress").advance(data)
        elif state == "filepath":
            self.cur_filepath = data
        elif state == "asset_dir":
            self.post_message(
                self.StatusOutput(
                    f"Downloading (Retry {self.cur_retry}): {url} -> {data}"
                )
            )
        elif state == "success":
            filepath = os.path.join(self.mod_dir, self.cur_filepath)
            filesize = os.path.getsize(filepath)
            if filesize == self.cur_filesize:
                mtime = os.path.getmtime(filepath)
                self.asset_list.download_done(
                    url,
                    self.cur_filepath,
                    mtime,
                    self.cur_filesize,
                    "",
                )
                self.post_message(
                    self.FileDownloadComplete(
                        {
                            "url": url,
                            "filename": self.cur_filepath,
                            "mtime": mtime,
                            "fsize": filesize,
                            "sha1": "",
                            "dl_status": "",
                        }
                    )
                )
                self.post_message(
                    self.StatusOutput(f"Download complete: {self.cur_filepath}")
                )
            else:
                mtime = 0
                self.asset_list.download_done(
                    url, self.cur_filepath, mtime, filesize, "Filesize mismatch"
                )
                self.post_message(
                    self.FileDownloadComplete(
                        {
                            "url": url,
                            "filename": self.cur_filepath,
                            "mtime": mtime,
                            "fsize": filesize,
                            "sha1": "",
                            "dl_status": "Filesize mismatch",
                        }
                    )
                )
        else:
            # Unknown state!
            sys.exit(1)

        if state in ["error", "success"]:
            # Increment overall progress here
            self.query_one("#all_dl_progress").advance(1)

        if state in ["error", "download_starting", "success"]:
            # Reset state data here
            self.cur_retry = 0
            self.cur_filepath = ""
            self.cur_filesize = 0
            self.query_one("#cur_dl_progress").update(total=100, progress=0)

    def download_assets(self) -> None:
        self.asset_list = AssetList(self.mod_dir)
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

        self.query_one("#all_dl_progress").update(total=len(urls), progress=0)

        download_files(
            urls, self.mod_dir, self.status_cb, ignore_content_type=overwrite
        )

        self.asset_list.commit()
        self.post_message(self.DownloadComplete())

    def on_asset_download_screen_status_output(self, event: StatusOutput):
        self.query_one("#downloadoutput").update(event.status)

    def on_asset_download_screen_download_complete(self):
        self.query_one("#downloadscreen").toggle_class("unhide")
        self.download_complete = True
