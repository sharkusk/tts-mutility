from textual.app import ComposeResult
from textual.worker import get_current_worker

from ..data.config import load_config
from ..parse.AssetList import AssetList
from ..utility.messages import UpdateLog
from ..utility.util import get_content_name
from .TTSWorker import TTSWorker

# Recursively read each directory
# Load existing dictionary, for each file not found in dictionary:
# Files that match steam pattern, extract SHA-1 values, add to {SHA1, filename}
# For non-steam files generate SHA-1 values, add to dictionary
# For each line is missing url file:
#   Extract SHA-1
#   Check if matching SHA-1 file is found
#   Copy and rename to destination directory


class NameScanner(TTSWorker):
    # Base class is installed in each screen, so we don't want
    # to inherit the same widgets when this subclass is mounted
    def compose(self) -> ComposeResult:
        return []

    def scan_names(self) -> None:
        asset_list = AssetList()

        worker = get_current_worker()

        self.post_message(UpdateLog("Starting Name Detection"))
        self.post_message(self.UpdateProgress(100, None))

        urls = asset_list.get_blank_content_names()

        updated_urls = []
        updated_names = []

        for url in urls:
            if worker.is_cancelled:
                self.post_message(UpdateLog("Name detection cancelled."))
                break

            if (content_name := get_content_name(url)) != "":
                updated_urls.append(url)
                updated_names.append(content_name)
                continue

            # TODO: Get HEAD to determine if content_disposition is included

            if False:
                self.post_message(self.UpdateProgress(len(files), None))

                # Updating bar for every file can be very expensive, so scale it to
                # a min of 100 times, but no more than every 10 files
                if len(files) < 100:
                    update_amount = 1
                else:
                    update_amount = int(len(files) / 100)
                if update_amount > 10:
                    update_amount = 10

                skip_update_amount = update_amount * 100

                i = 0
                if len(files) > 0:
                    self.post_message(self.UpdateProgress(len(files), None))
                self.post_message(
                    UpdateLog(f"Computing SHA1s for {dir_name} ({len(files)}).")
                )

        asset_list.set_content_names(updated_urls, updated_names)

        self.post_message(UpdateLog("Content Name detection complete."))
        self.post_message(self.UpdateStatus("Content Name detection complete."))
