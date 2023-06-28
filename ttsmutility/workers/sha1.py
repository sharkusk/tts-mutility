from textual.worker import Worker

from ..parse.Sha1Scan import scan_sha1s
from ..parse.AssetList import AssetList
from .messages import UpdateProgress, UpdateStatus
from ..data.config import load_config

import sys
import os


class Sha1Scanner(Worker):
    def run(self) -> None:
        asset = None
        filepath = None
        mtime = 0
        skip = False
        i = 0

        config = load_config()
        asset_list = AssetList(config.tts_mods_dir, config.tts_saves_dir)

        self.node.post_message(UpdateProgress(100, None))

        scanner = scan_sha1s(config.tts_mods_dir)
        for result in scanner:
            if result[0] == "new_directory":
                i = 0
                # Updating bar for every file can be very expensive, so do it 100 times
                if result[1] < 100:
                    update_amount = 1
                else:
                    update_amount = int(result[1] / 100)
                if result[1] > 0:
                    self.node.post_message(UpdateProgress(result[1], None))
                self.node.post_message(UpdateStatus(f"Computing SHA1s for {result[2]}"))
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
                    self.node.post_message(UpdateProgress(None, update_amount))

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
        self.node.post_message(UpdateStatus(f"SHA1 Scanning Complete"))
