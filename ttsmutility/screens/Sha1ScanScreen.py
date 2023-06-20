from textual.app import ComposeResult
from textual.widgets import Static, ProgressBar
from textual.containers import Container
from textual.screen import ModalScreen
from textual.message import Message

from ttsmutility.parse.Sha1Scan import scan_sha1s
from ttsmutility.parse.AssetList import AssetList

import sys


class Sha1ScanScreen(ModalScreen):
    class StatusOutput(Message):
        def __init__(self, status: str) -> None:
            self.status = status
            super().__init__()

    class ScanComplete(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(self, mod_dir: str) -> None:
        self.mod_dir = mod_dir
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Container(
            ProgressBar(id="sha1progress"), Static(id="sha1output"), id="sha1screen"
        )
        self.run_worker(self.scan_sha1s)

    def scan_sha1s(self):
        asset = None
        filepath = None
        sha1_mtime = None
        mtime = None
        asset_list = AssetList(self.mod_dir)

        scanner = scan_sha1s(self.mod_dir)
        for result in scanner:
            if result[0] == "new_directory":
                pb = self.query_one(ProgressBar).update(total=result[1], progress=0)
                self.post_message(self.StatusOutput(f"Computing SHA1s for {result[2]}"))
                continue
            elif result[0] == "filepath":
                filepath = result[1]
                asset = asset_list.get_sha1_info(filepath)
                if asset is None:
                    # Skip this filepath since it doesn't exist in our DB
                    scanner.send(False)
                    continue
                elif asset["sha1_mtime"] is None:
                    scanner.send(False)
                    continue
                elif asset["mtime"] <= asset["sha1_mtime"]:
                    scanner.send(False)
                    continue
                else:
                    scanner.send(True)
                    continue
            elif result[0] == "sha1":
                asset_list.sha1_scan_done(filepath, result[1], result[2], mtime)
                self.query_one(ProgressBar).advance(1)

                continue
            else:
                # Our state machine is broken!
                sys.exit(1)
        asset_list.commit()
        self.post_message(self.ScanComplete())

    def on_sha1scan_screen_status_output(self, event: StatusOutput):
        self.query_one("#sha1output").update(event.status)
        self.query_one(ProgressBar).advance(1)
