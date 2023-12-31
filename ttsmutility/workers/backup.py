import csv
import datetime
import io
import os
import os.path
import time
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
from zipfile import ZipFile

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.worker import get_current_worker

from ..data.config import load_config
from ..parse.AssetList import AssetList
from ..parse.ModList import ModList
from ..utility.messages import UpdateLog


class ModBackup(Widget):
    class UpdateProgress(Message):
        def __init__(self, filename, update_total=None, advance_amount=None):
            super().__init__()
            self.filename = filename
            self.update_total = update_total
            self.advance_amount = advance_amount

    class BackupStart(Message):
        def __init__(self, filename, zip_path):
            super().__init__()
            self.filename = filename
            self.zip_path = zip_path

    class BackupComplete(Message):
        def __init__(self, filename):
            super().__init__()
            self.filename = filename

    def __init__(self):
        super().__init__()
        self.mod_filenames = Queue()

    # Base class is installed in each screen, so we don't want
    # to inherit the same widgets when this subclass is mounted
    def compose(self) -> ComposeResult:
        return []

    def add_mods(self, to_backup):
        for entry in to_backup:
            self.mod_filenames.put(entry)

    def backup_daemon(self) -> None:
        worker = get_current_worker()

        while True:
            if worker.is_cancelled:
                return

            try:
                (
                    mod_filename,
                    zip_path,
                    existing_backup,
                ) = self.mod_filenames.get(timeout=1)
            except Empty:
                continue

            self.backup_mod(mod_filename, zip_path, existing_backup)

    def backup_mod(self, mod_filename, zip_path, old_file):
        config = load_config()
        worker = get_current_worker()
        asset_list = AssetList()
        mod_list = ModList()
        mod = mod_list.get_mod_details(mod_filename)

        self.post_message(
            UpdateLog(f"Starting backup of {mod_filename}: {mod['name']}.")
        )
        self.post_message(self.UpdateProgress(mod_filename, mod["size"], None))

        assets = asset_list.get_mod_assets(mod_filename)

        if old_file != "":
            self.post_message(UpdateLog(f"Removing old backup: '{old_file}"))
            os.remove(old_file)

        self.post_message(UpdateLog(f"Backing up to '{zip_path}'"))
        self.post_message(self.BackupStart(mod["filename"], zip_path))

        cancelled = False
        with ZipFile(zip_path, "w") as modzip:
            # Store the json and png files
            if "Workshop" in mod["filename"]:
                mod_path = Path(config.tts_mods_dir) / mod["filename"]
                path_in_zip = Path("Mods") / mod["filename"]
            else:
                mod_path = Path(config.tts_saves_dir) / mod["filename"]
                path_in_zip = mod["filename"]
            modzip.write(mod_path, path_in_zip)

            mod_png_path = os.path.splitext(mod_path)[0] + ".png"
            if Path(mod_png_path).exists():
                modzip.write(
                    mod_png_path,
                    os.path.splitext(path_in_zip)[0] + ".png",
                )

            amount_stored = 0
            missing_csv = io.StringIO()
            missing_writer = csv.writer(missing_csv, delimiter="\t")
            invalid_urls_csv = io.StringIO()
            invalid_writer = csv.writer(invalid_urls_csv, delimiter="\t")
            content_names_csv = io.StringIO()
            content_writer = csv.writer(content_names_csv, delimiter="\t")
            for asset in assets:
                if worker.is_cancelled:
                    cancelled = True
                    break
                if asset["size"] > 0:
                    # self.post_message(UpdateLog(f"Adding {asset['filename']}."))
                    modzip.write(
                        Path(config.tts_mods_dir) / asset["filename"],
                        Path("Mods") / asset["filename"],
                    )
                    amount_stored += asset["size"]
                    # Reduce number of messages to improve performance
                    if amount_stored > 2 * 1024 * 1024:
                        self.post_message(
                            self.UpdateProgress(mod_filename, None, amount_stored)
                        )
                        amount_stored = 0
                    if asset["dl_status"] != "":
                        invalid_writer.writerow(
                            [
                                f"{asset['url']}",
                                f"{asset['trail']}",
                                f"{asset['dl_status']}",
                            ]
                        )
                else:
                    missing_writer.writerow(
                        [
                            f"{asset['url']}",
                            f"{asset['trail']}",
                            f"{asset['dl_status']}",
                        ]
                    )
                    invalid_writer.writerow(
                        [
                            f"{asset['url']}",
                            f"{asset['trail']}",
                            f"{asset['dl_status']}",
                        ]
                    )
                if asset["content_name"] != "":
                    content_writer.writerow(
                        [
                            f"{PurePosixPath(Path(asset['filename']))}",  # Use posix path formatting
                            f"{asset['content_name']}",
                            f"{asset['url']}",
                        ]
                    )

            if missing_csv.tell() > 0:
                modzip.writestr("missing_assets.csv", missing_csv.getvalue())
            if invalid_urls_csv.tell() > 0:
                modzip.writestr("invalid_urls.csv", invalid_urls_csv.getvalue())
            if content_names_csv.tell() > 0:
                modzip.writestr("content_names.csv", content_names_csv.getvalue())

            missing_csv.close()
            invalid_urls_csv.close()
            content_names_csv.close()

            # Make sure we get progress bar to 100%
            self.post_message(self.UpdateProgress(mod_filename, None, amount_stored))
            amount_stored = 0

        if cancelled:
            self.post_message(UpdateLog("Backup cancelled."))
            os.remove(zip_path)
        else:
            self.post_message(UpdateLog("Backup complete."))

        self.post_message(self.BackupComplete(mod_filename))
        self.mod_filenames.task_done()


def unzip_backup(backup_path: Path, dest_path: Path, backup_name) -> None:
    with ZipFile(backup_path, "r") as zf:
        infos = zf.infolist()
        files_to_unzip = []
        for info in infos:
            filepath = dest_path / info.filename
            if filepath.exists() and filepath.stat().st_mtime > time.mktime(
                datetime.datetime(*info.date_time).timetuple()
            ):
                continue
            files_to_unzip.append(info)
        zf.extractall(dest_path, members=files_to_unzip)
        if "content_names.csv" in zf.namelist():
            urls = []
            content_names = []

            with io.StringIO(zf.read("content_names.csv").decode("utf-8")) as f:
                csv_in = csv.reader(f, delimiter="\t")
                for line in csv_in:
                    # Ignore filenames
                    content_names.append(line[1].strip())
                    urls.append(line[2].strip())

            asset_list = AssetList()
            asset_list.set_content_names(urls, content_names)
    return backup_name
