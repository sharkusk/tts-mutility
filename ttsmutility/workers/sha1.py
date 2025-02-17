import hashlib
import os
import pathlib

from textual.app import ComposeResult
from textual.worker import get_current_worker

from ..data.config import load_config
from ..parse.AssetList import AssetList
from ..parse.FileFinder import FILES_TO_IGNORE, TTS_RAW_DIRS
from ..utility.messages import UpdateLog
from .TTSWorker import TTSWorker

# Recursively read each directory
# Load existing dictionary, for each file not found in dictionary:
# Files that match steam pattern, extract SHA-1 values, add to {SHA1, filename}
# For non-steam files generate SHA-1 values, add to dictionary
# For each line is missing url file:
#   Extract SHA-1
#   Check if matching SHA-1 file is found
#   Copy and rename to destination directory


class Sha1Scanner(TTSWorker):
    # Base class is installed in each screen, so we don't want
    # to inherit the same widgets when this subclass is mounted
    def compose(self) -> ComposeResult:
        return []

    async def scan_sha1s(self) -> None:
        filepath = None
        mtime = 0
        skip = False

        config = load_config()
        asset_list = AssetList()

        worker = get_current_worker()

        self.post_message(UpdateLog("Starting SHA1 scan."))
        self.post_message(self.UpdateProgress(100, None))

        ignore_paths = ["Mods", "Workshop"]

        for root, dirnames, files in os.walk(config.tts_mods_dir, topdown=True):
            dir_name = pathlib.PurePath(root).name

            if dir_name in TTS_RAW_DIRS or dir_name in ignore_paths:
                if dir_name != "Mods":
                    # Do not recurse into directories we are ignoring
                    while len(dirnames) > 0:
                        _ = dirnames.pop()
                continue

            self.post_message(self.UpdateProgress(len(files), None))

            # Updating bar for every file can be very expensive, so scale it to
            # a min of 100 times, but no more than every 51 files
            if len(files) < 100:
                update_amount = 1
            else:
                update_amount = int(len(files) / 100)
            if update_amount > 50:
                update_amount = 51

            skip_update_amount = 1000

            i = 0
            if len(files) > 0:
                self.post_message(self.UpdateProgress(len(files), None))
            self.post_message(
                UpdateLog(f"Computing SHA1s for {dir_name} ({len(files)}).")
            )

            assets = asset_list.get_sha1_info(dir_name)
            if len(assets) == 0:
                continue

            for filename in files:
                if worker.is_cancelled:
                    self.post_message(UpdateLog("SHA1 scan cancelled."))
                    return

                ext = os.path.splitext(filename)[1]
                if ext.upper() in FILES_TO_IGNORE:
                    continue

                # Remove the '.\' at the front of the path
                filepath = str(pathlib.PurePath(os.path.join(root, filename)))
                asset_path = pathlib.Path(dir_name) / filename

                filestem = pathlib.Path(filename).stem
                if filestem not in assets:
                    continue

                update_steam_sha1 = False
                update_sha1 = False

                steam_sha1 = ""
                if (
                    filestem.find("httpcloud3steamusercontent") == 0
                    or filestem.find("httpssteamusercontentaakamaihdnetugc") == 0
                ):
                    hexdigest = os.path.splitext(filestem)[0][-40:]
                    steam_sha1 = hexdigest.upper()
                    if steam_sha1 != assets[filestem]["steam_sha1"]:
                        update_steam_sha1 = True

                sha1 = assets[filestem]["sha1"]

                mtime = os.path.getmtime(filepath)
                if (
                    assets[filestem]["sha1_mtime"] == 0
                    or sha1 is None
                    or sha1 == ""
                    or sha1 == "0"
                ):
                    update_sha1 = True
                elif mtime > assets[filestem]["sha1_mtime"]:
                    update_sha1 = True

                i += 1

                if update_sha1:
                    with open(filepath, "rb") as f:
                        digest = hashlib.file_digest(f, "sha1")
                    hexdigest = digest.hexdigest()
                    sha1 = hexdigest.upper()

                update_progress = skip_update_amount

                if update_sha1 or update_steam_sha1:
                    await asset_list.sha1_scan_done(
                        str(asset_path), sha1, steam_sha1, mtime
                    )
                    update_progress = update_amount

                if i % update_progress == 0:
                    self.post_message(self.UpdateProgress(None, update_progress))
                    self.post_message(
                        self.UpdateStatus(
                            f"Computing SHA1s for {dir_name} ({i}/{len(files)})"
                        )
                    )

        self.post_message(UpdateLog("SHA1 scan complete."))
        self.post_message(self.UpdateStatus("SHA1 scan complete."))
