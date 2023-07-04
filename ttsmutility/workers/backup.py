import glob
import os
import os.path
from pathlib import Path
from zipfile import ZipFile

from textual.app import ComposeResult
from textual.worker import get_current_worker

from ..data.config import load_config
from ..parse.AssetList import AssetList
from ..parse.ModList import ModList
from .TTSWorker import TTSWorker


def make_safe_filename(filename):
    return "".join(
        [
            c if c.isalpha() or c.isdigit() or c in " ()[]-_{}." else "-"
            for c in filename
        ]
    ).rstrip()


class ModBackup(TTSWorker):
    # Base class is installed in each screen, so we don't want
    # to inherit the same widgets when this subclass is mounted
    def compose(self) -> ComposeResult:
        return []

    def add_mod(self, mod_filename):
        self.mod_filename = mod_filename

    def backup(self) -> None:
        config = load_config()
        asset_list = AssetList()
        mod_list = ModList()

        if self.mod_filename == "":
            return

        mod_details = mod_list.get_mod_details(self.mod_filename)

        worker = get_current_worker()

        self.post_message(
            self.UpdateLog(
                f"Starting backup of {self.mod_filename}: {mod_details['name']}."
            )
        )
        self.post_message(self.UpdateProgress(mod_details["size"], None))

        assets = asset_list.get_mod_assets(self.mod_filename)
        missing = asset_list.get_missing_assets(self.mod_filename)

        # Don't keep the path component from the mod_filename
        zip_basename = (
            Path(make_safe_filename(mod_details["name"])).stem
            + f" [{Path(self.mod_filename).stem}]"
        )
        if len(missing) > 0:
            zip_filename = zip_basename + f" (-{len(missing)})" + ".zip"
        else:
            zip_filename = zip_basename + ".zip"

        zip_path = Path(config.mod_backup_dir) / zip_filename
        # Check if we have any old zipfiles for this mod with filename used with missing files
        glob_path = glob.escape(Path(config.mod_backup_dir) / zip_basename)
        old_files = glob.glob(f"{glob_path} (-*")

        if len(old_files) > 0:
            for f_name in old_files:
                self.post_message(self.UpdateLog(f"Removing old backup: '{f_name}"))
                os.remove(f_name)

        self.post_message(self.UpdateStatus(f"Backing up to '{zip_path}'"))
        self.post_message(self.UpdateLog(f"Backing up to '{zip_path}'"))

        cancelled = False
        with ZipFile(zip_path, "w") as modzip:
            amount_stored = 0
            for asset in assets:
                if worker.is_cancelled:
                    cancelled = True
                    break
                if asset["mtime"] > 0:
                    # self.post_message(self.UpdateLog(f"Adding {asset['filename']}."))
                    modzip.write(
                        Path(config.tts_mods_dir) / asset["filename"], asset["filename"]
                    )
                    amount_stored += asset["fsize"]
                    # Reduce number of messages to improve performance
                    if amount_stored > 512 * 1024:
                        self.post_message(self.UpdateProgress(None, amount_stored))
                        amount_stored = 0

            # Make sure we get progress bar to 100%
            self.post_message(self.UpdateProgress(None, amount_stored))
            amount_stored = 0

            # Store the json and png files
            if "Workshop" in mod_details["filename"]:
                mod_path = Path(config.tts_mods_dir) / mod_details["filename"]
            else:
                mod_path = Path(config.tts_saves_dir) / mod_details["filename"]
            modzip.write(mod_path, mod_details["filename"])

            mod_png_path = os.path.splitext(mod_path)[0] + ".png"
            if Path(mod_png_path).exists():
                modzip.write(
                    mod_png_path, os.path.splitext(mod_details["filename"])[0] + ".png"
                )

        if cancelled:
            self.post_message(self.UpdateLog(f"Backup cancelled."))
            os.remove(zip_path)
        else:
            self.post_message(self.UpdateLog(f"Backup complete."))
            self.post_message(self.UpdateStatus(f"Backup complete: {zip_path}"))

        self.mod_filename = ""
