import hashlib
import os
import pathlib

from ..parse.FileFinder import TTS_RAW_DIRS, FILES_TO_IGNORE

from textual.worker import Worker, get_current_worker

from ..parse.AssetList import AssetList
from .messages import UpdateProgress, UpdateStatus, UpdateLog
from ..data.config import load_config

import sys
import os

# Recursively read each directory
# Load existing dictionary, for each file not found in dictionary:
# Files that match steam pattern, extract SHA-1 values, add to {SHA1, filename}
# For non-steam files generate SHA-1 values, add to dictionary
# For each line is missing url file:
#   Extract SHA-1
#   Check if matching SHA-1 file is found
#   Copy and rename to destination directory


class Sha1Scanner(Worker):
    def run(self) -> None:
        asset = None
        filepath = None
        mtime = 0
        skip = False

        config = load_config()
        asset_list = AssetList()

        self.node.post_message(UpdateLog(f"Starting SHA1 scan."))
        self.node.post_message(UpdateProgress(100, None))
        worker = get_current_worker()

        old_dir = os.getcwd()
        os.chdir(config.tts_mods_dir)

        for root, _, files in os.walk("."):
            dir_name = pathlib.PurePath(root).name

            if dir_name in TTS_RAW_DIRS or dir_name == "":
                continue

            self.node.post_message(UpdateProgress(len(files), None))

            # Updating bar for every file can be very expensive, so scale it to
            # a min of 100 times, but no more than every 10 files
            if len(files) < 100:
                update_amount = 1
            else:
                update_amount = int(len(files) / 100)
            if update_amount > 10:
                update_amount = 10

            skip_update_amount = update_amount * 10

            i = 0
            if len(files) > 0:
                self.node.post_message(UpdateProgress(len(files), None))
            self.node.post_message(
                UpdateLog(f"Computing SHA1s for {dir_name} ({len(files)}).")
            )

            for filename in files:
                if worker.is_cancelled:
                    self.node.post_message(UpdateLog(f"SHA1 scan cancelled."))
                    return

                ext = os.path.splitext(filename)[1]
                if ext.upper() in FILES_TO_IGNORE:
                    continue

                # Remove the '.\' at the front of the path
                filepath = str(pathlib.PurePath(os.path.join(root, filename)))

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
                if skip:
                    if (i % skip_update_amount) == 0:
                        self.node.post_message(UpdateProgress(None, skip_update_amount))
                        self.node.post_message(
                            UpdateStatus(
                                f"Computing SHA1s for {dir_name} ({i}/{len(files)})"
                            )
                        )
                    continue

                if (i % update_amount) == 0:
                    self.node.post_message(UpdateProgress(None, update_amount))
                    self.node.post_message(
                        UpdateStatus(
                            f"Computing SHA1s for {dir_name} ({i}/{len(files)})"
                        )
                    )

                sha1 = ""
                steam_sha1 = ""

                if "httpcloud3steamusercontent" in filename:
                    hexdigest = os.path.splitext(filename)[0][-40:]
                    steam_sha1 = hexdigest.upper()

                with open(filepath, "rb") as f:
                    digest = hashlib.file_digest(f, "sha1")
                hexdigest = digest.hexdigest()
                sha1 = hexdigest.upper()

                asset_list.sha1_scan_done(filepath, sha1, steam_sha1, mtime)
        self.node.post_message(UpdateLog(f"SHA1 scan complete."))
        os.chdir(old_dir)
