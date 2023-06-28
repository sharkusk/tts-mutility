from textual.app import ComposeResult
from textual.widgets import Static, ProgressBar, Footer
from textual.containers import Container
from textual.screen import ModalScreen
from textual.message import Message

from ..parse.Sha1Scan import scan_sha1s
from ..parse.AssetList import AssetList

import sys
import os


class Sha1ScanScreen(ModalScreen):
    BINDINGS = [("escape", "exit", "OK")]

    class StatusOutput(Message):
        def __init__(self, status: str) -> None:
            self.status = status
            super().__init__()

    class ScanComplete(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        self.scan_complete = False
        super().__init__()

    def compose(self) -> ComposeResult:
        with Container(id="sha1_screen"):
            yield ProgressBar(id="sha1_progress")
            yield Static(id="sha1_status")
            yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.scan_sha1s)

    def action_exit(self) -> None:
        if self.scan_complete:
            self.app.pop_screen()

    def scan_sha1s(self) -> None:
        asset = None
        filepath = None
        mtime = 0
        asset_list = AssetList(self.mod_dir, self.save_dir)
        skip = False
        update_frequency = 0
        i = 0

        self.query_one(ProgressBar).update(total=100)

        scanner = scan_sha1s(self.mod_dir)
        for result in scanner:
            if result[0] == "new_directory":
                i = 0
                # Updating bar for every file can be very expensive, so do it 100 times
                if result[1] < 100:
                    update_amount = 1
                else:
                    update_amount = int(result[1] / 100)
                if result[1] > 0:
                    self.query_one(ProgressBar).update(total=result[1])
                self.post_message(self.StatusOutput(f"Computing SHA1s for {result[2]}"))
                continue
            elif result[0] == "filepath":
                filepath = result[1]
                mtime = os.path.getmtime(filepath)
                asset = asset_list.get_sha1_info(filepath)
                if asset is None:
                    # Skip this filepath since it doesn't exist in our DB
                    skip = True
                elif asset["sha1_mtime"] == 0:
                    skip = False
                elif mtime > asset["sha1_mtime"]:
                    skip = False
                else:
                    skip = True

                i += 1
                if (i % update_amount) == 0:
                    self.query_one(ProgressBar).advance(update_amount)

                if skip:
                    scanner.send(False)
                    continue
                else:
                    scanner.send(True)
                    continue
            elif result[0] == "sha1":
                asset_list.sha1_scan_done(filepath, result[1], result[2], mtime)
                continue
            else:
                # Our state machine is broken!
                sys.exit(1)
        self.post_message(self.StatusOutput(f"SHA1 Scanning Complete"))
        self.post_message(self.ScanComplete())

    def on_sha1scan_screen_status_output(self, event: StatusOutput):
        self.query_one("#sha1_status").update(event.status)

    def on_sha1scan_screen_scan_complete(self):
        self.query_one("#sha1_screen").toggle_class("unhide")
        self.scan_complete = True
