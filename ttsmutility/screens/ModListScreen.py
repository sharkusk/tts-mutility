import csv
import math
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import NamedTuple
from webbrowser import open as open_url

from aiopath import AsyncPath
from rich.markdown import Markdown
from textual import work
from textual.actions import SkipAction
from textual.app import ComposeResult, App
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Center
from textual.coordinate import Coordinate
from textual.events import Key
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input
from textual.widgets.data_table import CellDoesNotExist, RowKey
from textual.worker import get_current_worker

from ..data.config import config_file, load_config
from ..dialogs.HelpDialog import HelpDialog
from ..dialogs.InfoDialog import InfoDialog
from ..parse import ModList
from ..parse.AssetList import AssetList
from ..parse.FileFinder import trailstring_to_trail
from ..parse.ModParser import INFECTION_URL
from ..utility.messages import UpdateLog
from ..utility.util import MyText, format_time, make_safe_filename, sizeof_fmt
from ..widgets.DataTableFilter import DataTableFilter
from ..workers.backup import unzip_backup
from ..workers.downloader import FileDownload
from .DebugScreen import DebugScreen
from .LoadingScreen import LoadingScreen
from .ModExplorerScreen import ModExplorerScreen


class ModListCommands(Provider):
    ML_COMMANDS = {
        "View Log": ("Open Log in External Viewer", "action_view_log"),
        "Open Config": (
            "Open Config file in External Viewer",
            "action_open_config",
        ),
        "Download All": (
            "Attept to download all mising assets",
            "action_download_all",
        ),
        "Backup All": ("Backup all mods needing a backup", "action_backup_all"),
        "Scan SHA1s": ("Calculate SHA1 values for all assets", "action_scan_sha1"),
        "Show SHA1 Mistmatches": (
            "Show SteamCloud SHA-1 assets that don't match their SHA1 vales",
            "action_sha1_mismatches",
        ),
        "Save ContentNames": (
            "Saves asset content names to csv file in backup directory",
            "action_content_name_report",
        ),
        "Load ContentNames": (
            "Loads asset content names from csv file in backup directory",
            "action_content_name_load",
        ),
        "Show All Missing": (
            "Shows list of all missing assets",
            "action_missing_assets",
        ),
        "Fetch ContentNames": (
            "Attempt to get content names for all assets",
            "action_scan_names",
        ),
    }

    async def startup(self) -> None:
        """Called once when the command palette is opened, prior to searching."""
        app = self.app
        self.cmd_screen = app.get_screen("mod_list")
        pass

    async def search(self, query: str) -> Hits:
        """Search for Python files."""
        matcher = self.matcher(query)

        for command in self.ML_COMMANDS.keys():
            score = matcher.match(command)
            if score > 0:
                help, func_name = self.ML_COMMANDS[command]
                func = getattr(self.cmd_screen, func_name)
                yield Hit(
                    score,
                    matcher.highlight(command),
                    func,
                    help=help,
                )


class ModListScreen(Screen):
    class FileDownloadComplete(Message):
        def __init__(
            self,
            worker_num: int,
            asset: dict,
        ) -> None:
            super().__init__()
            self.asset = asset
            self.worker_num = worker_num

    class DownloadEntry(NamedTuple):
        url: str
        trail: list

    @dataclass
    class WorkerStatus:
        backup: str
        download: str

    @dataclass
    class DlWorkerStatus:
        filename: str
        url: str
        filesize: int
        bytes_complete: int

    @dataclass
    class ModDlProgress:
        files_remaining: int

    COMMANDS = App.COMMANDS | {ModListCommands}

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("ctrl+q", "app.quit", "Quit"),
        Binding("/", "filter", "Filter"),
        Binding("d", "download_assets", "Download"),
        Binding("b", "backup_mod", "Backup"),
        Binding("r", "mod_refresh", "Refresh"),
        Binding("u", "unzip", "Unzip"),
        Binding("e", "explore", "Explore", show=True),
    ]

    def __init__(self) -> None:
        self.prev_selected = None
        self.filter = ""
        self.prev_filter = ""
        self.active_rows = {}
        self.filtered_rows = {}
        self.progress = {}
        self.status = {}
        self.backup_status = {}
        self.backup_filenames = {}
        self.backup_ready = False
        self.dl_queue = Queue()
        self.filter_timer = None
        self.downloads = []
        self.fds = []
        self.dl_worker_status = []
        super().__init__()

        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir
        self.num_dl_threads = int(config.num_download_threads)
        self.last_dl_update_time = 0.0

        for i in range(self.num_dl_threads):
            fd = FileDownload()
            self.fds.append(fd)
            self.dl_worker_status.append(self.DlWorkerStatus("", "", 0, 0))
            self.mount(fd)
            self.run_worker(
                self.download_daemon,
                name=f"{i}",
                group="downloaders",
                description=f"DL Task {i}",
                thread=True,
            )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with Center(id="ml_filter_center"):
            yield Input(
                placeholder="Loading. Please wait...",
                disabled=True,
                id="ml_filter",
            )
        yield DataTableFilter(id="ml_workshop_dt")

    class ModRefresh(Message):
        def __init__(self, mod_filename: str) -> None:
            self.filename = mod_filename
            super().__init__()

    class ModSelected(Message):
        def __init__(self, mod_filename: str, backup_time: float) -> None:
            self.filename = mod_filename
            self.backup_time = backup_time
            super().__init__()

    class ModLoaded(Message):
        def __init__(self, mod: dict) -> None:
            self.mod = mod
            super().__init__()

    class Sha1Selected(Message):
        def __init__(self, mod_dir: str, save_dir: str) -> None:
            self.mod_dir = mod_dir
            self.save_dir = save_dir
            super().__init__()

    class ScanNames(Message):
        def __init__(self) -> None:
            super().__init__()

    class DownloadSelected(Message):
        def __init__(self, mod_filenames: list[str]) -> None:
            self.mod_filenames = mod_filenames
            super().__init__()

    class BackupSelected(Message):
        def __init__(self, backup_list: list) -> None:
            self.backup_list = backup_list
            super().__init__()

    class ShowSha1(Message):
        def __init__(self) -> None:
            super().__init__()

    class ShowMissing(Message):
        def __init__(self) -> None:
            super().__init__()

    def on_mount(self) -> None:
        self.sort_order = {
            "name": False,
            "type": False,
            "created": True,
            "modified": True,
            "size": True,
            "total_assets": True,
            "missing_assets": True,
            "invalid_assets": True,
            "min_players": True,
            "max_players": True,
            "backup": True,
            "bgg": False,
            "dl_status": True,
        }

        table = self.query_one(DataTable)
        table.fixed_columns = 1
        table.zebra_stripes = True

        table.add_column("Mod Name", width=40, key="name")
        table.add_column("Type", key="type")
        table.add_column("Created", key="created", width=10)
        table.add_column("Modified", key="modified", width=10)
        table.add_column("Size", key="size", width=12)
        table.add_column("Assets", key="total_assets")
        table.add_column("Missing", key="missing_assets")
        table.add_column("Invalid", key="invalid_assets")
        table.add_column("MinP", key="min_players")
        table.add_column("MaxP", key="max_players")
        table.add_column("BGG", key="bgg")
        table.add_column("BUp", key="backup")
        table.add_column("DL", key="dl_status")

        table.cursor_type = "row"
        table.sort("name", reverse=self.sort_order["name"])
        self.last_sort_key = "name"

        self.load_mods()

        table.sort(self.last_sort_key, reverse=self.sort_order[self.last_sort_key])
        table.focus()

        self.backup_times = {}
        self.update_backup()

    def load_mods(self) -> None:
        mod_list = ModList.ModList()
        self.mods = mod_list.get_mods()

        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        self.infected_filenames = [mod_filename for mod_filename, _ in infected_mods]

        for mod_filename in self.mods.keys():
            self.add_mod_row(self.mods[mod_filename])
            self.status[mod_filename] = self.WorkerStatus("", "")

        f = self.query_one("#ml_filter", expect_type=Input)
        f.placeholder = "Filter"
        f.disabled = False

    def clean_name(self, name):
        words_to_move = [
            "scripted deal ",
            "scripted ",
            "semi-scripted ",
            "wip ",
            "complete ",
            "gf9 ",
            "v2 automated ",
            "reiner knizia's ",
            "betterized ",
            "(remastered) ",
            "improved ",
            "- ",
            "the ",
            "a ",
        ]
        if len(name) == 0:
            return name

        while name[0] == "[":
            # Move [] to end of name
            e = name.find("]")
            name = (name[e + 1 :] + " " + name[0 : e + 1]).strip()
        if name.find("the") == 0:
            name = name.replace("the", "The")
        for to_move in words_to_move:
            if name.lower().find(to_move) == 0:
                name = name[len(to_move) :] + ", " + name[: len(to_move)].strip()
        if name.find("TTS-") == 0:
            name = name[4:].strip()
        if name.find("EPIC ") == 0:
            name = name[5:] + ", EPIC"
        if name[0] == "+":
            name = name[1:].strip()
        if name[0] == '"':
            name = name.replace('"', "")

        return name

    @work(exclusive=True)
    async def update_backup(self):
        table = self.query_one(DataTable)

        config = load_config()
        if not Path(config.mod_backup_dir).exists():
            return

        async for bf in AsyncPath(config.mod_backup_dir).glob("*.zip"):
            stat = await bf.stat()
            name = bf.name
            s = name.rfind("[")
            e = name.rfind("]")
            # Handle embedded []'s in name
            t = name.rfind("]", 0, e)
            while t > s:
                s = name.rfind("[", 0, s)
                t = name.rfind("]", 0, t)
            mod_filename = name[s + 1 : e] + ".json"
            self.backup_times[mod_filename] = stat.st_mtime
            self.backup_filenames[mod_filename] = bf

        for mod_filename in self.mods.keys():
            name = Path(mod_filename).name
            if name in self.backup_times:
                if (
                    self.backup_times[name] > self.mods[mod_filename]["mtime"]
                    and self.backup_times[name] > self.mods[mod_filename]["epoch"]
                    and self.backup_times[name]
                    > self.mods[mod_filename]["newest_asset"]
                ):
                    b = " ✓"
                elif (
                    config.backup_read_only
                    and self.backup_times[name] > self.mods[mod_filename]["epoch"]
                ):
                    # If we are using a read-only backup dir, we don't care about
                    # when assets were last updated or if the local mod timestamp is older
                    # than the backup
                    b = " ✓"
                else:
                    self.post_message(
                        UpdateLog(
                            f"BT: {self.backup_times[name]}, MT: {self.mods[mod_filename]['epoch']}, AT: {self.mods[mod_filename]['newest_asset']}",
                            flush=True,
                        )
                    )
                    b = "!"
            else:
                b = "✘"

            if config.backup_read_only:
                b += "·"

            self.backup_status[mod_filename] = b
            try:
                table.update_cell(mod_filename, "backup", b)
            except CellDoesNotExist:
                # This cell may be currently filtered, so ignore any errors
                pass
        self.backup_ready = True

    def stylize_name(self, mod):
        clean_name = self.clean_name(mod["name"])

        if mod["filename"] in self.infected_filenames:
            name = MyText(clean_name, style="#FF0000")
        elif mod["deleted"]:
            name = MyText(clean_name, style="strike")
        else:
            name = MyText(clean_name)
        return name

    def add_mod_row(self, mod: dict) -> None:
        filename = mod["filename"]
        table = self.query_one(DataTable)

        name = self.stylize_name(mod)

        if filename in self.backup_status:
            b = self.backup_status[filename]
        else:
            b = ""

        table.add_row(
            name,
            "Mod" if "Workshop" in filename else "Save",
            format_time(mod["epoch"], ""),
            format_time(mod["mtime"], "Scanning..."),
            sizeof_fmt(mod["size"]),
            mod["total_assets"],
            mod["missing_assets"],
            mod["invalid_assets"],
            mod["min_players"],
            mod["max_players"],
            " ✓ " if mod["bgg_id"] is not None else "",
            b,  # No backup status
            "",  # Update status in func below
            key=filename,
        )
        self.active_rows[filename] = mod["name"]
        self.update_backup_status(filename)
        self.update_dl_status(filename)

    def update_filtered_rows(self) -> None:
        self.filter_timer = None

        row_key = self.get_current_row_key()

        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTableFilter))
        if self.filter != self.prev_filter:
            table.filter(self.filter, "name")

        table.sort(self.last_sort_key, reverse=self.sort_order[self.last_sort_key])

        # Now jump to the previously selected row
        if row_key != "":
            self.call_after_refresh(self.jump_to_row_key, row_key)

        self.prev_filter = self.filter

    def jump_to_row_key(self, row_key):
        table = self.get_active_table()
        # TODO: Remove internal API calls once Textual #2876 is published
        row_index = table._row_locations.get(row_key)
        if row_index is not None and table.is_valid_row_index(row_index):
            table.cursor_coordinate = Coordinate(row_index, 0)
        else:
            table.cursor_coordinate = Coordinate(0, 0)

    def update_counts(
        self, mod_filename, total_assets, missing_assets, invalid_assets, size
    ):
        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        self.infected_filenames = [mod_filename for mod_filename, _ in infected_mods]

        table = self.query_one(DataTable)

        row_key = mod_filename
        if row_key not in self.mods:
            return

        name = self.stylize_name(self.mods[row_key])

        # We need to update both our internal asset information
        # and what is shown on the table...
        self.mods[row_key]["total_assets"] = total_assets
        self.mods[row_key]["missing_assets"] = missing_assets
        self.mods[row_key]["invalid_assets"] = missing_assets
        self.mods[row_key]["size"] = size

        try:
            table.update_cell(row_key, "name", name)
            table.update_cell(row_key, "total_assets", total_assets)
            table.update_cell(row_key, "missing_assets", missing_assets)
            table.update_cell(row_key, "invalid_assets", invalid_assets)
            table.update_cell(row_key, "size", sizeof_fmt(size))
        except CellDoesNotExist:
            # This can happen if some of our mods are filtered and an
            # asset is shared with a filtered one that isn't being displayed.
            pass

    async def update_counts_a(
        self, mod_filename, total_assets, missing_assets, invalid_assets, size
    ):
        asset_list = AssetList()
        infected_mods = await asset_list.get_mods_using_asset_a(INFECTION_URL)
        self.infected_filenames = [mod_filename for mod_filename, _ in infected_mods]

        table = self.query_one(DataTable)

        row_key = mod_filename
        if row_key not in self.mods:
            return

        name = self.stylize_name(self.mods[row_key])

        # We need to update both our internal asset information
        # and what is shown on the table...
        self.mods[row_key]["total_assets"] = total_assets
        self.mods[row_key]["missing_assets"] = missing_assets
        self.mods[row_key]["invalid_assets"] = missing_assets
        self.mods[row_key]["size"] = sizeof_fmt(size)

        try:
            table.update_cell(row_key, "name", name)
            table.update_cell(row_key, "total_assets", total_assets)
            table.update_cell(row_key, "missing_assets", missing_assets)
            table.update_cell(row_key, "invalid_assets", invalid_assets)
            table.update_cell(row_key, "size", sizeof_fmt(size))
        except CellDoesNotExist:
            # This can happen if some of our mods are filtered and an
            # asset is shared with a filtered one that isn't being displayed.
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.row_key.value is not None:
            if self.prev_selected is not None and event.row_key == self.prev_selected:
                mod_filename = event.row_key.value
                name = Path(mod_filename).name
                # We have to pass the backup time to the detail page
                if name in self.backup_times:
                    backup_time = self.backup_times[name]
                else:
                    backup_time = 0
                self.post_message(self.ModSelected(mod_filename, backup_time))
            self.prev_selected = event.row_key

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        sort_key = event.column_key.value
        if sort_key is not None:
            if self.last_sort_key == sort_key:
                self.sort_order[sort_key] = not self.sort_order[sort_key]
            reverse = self.sort_order[sort_key]
            if event.column_key.value is not None:
                self.last_sort_key = event.column_key.value
            self.sort_order[sort_key] = reverse
            event.data_table.sort(event.column_key, reverse=reverse)

    def on_mod_list_screen_mod_loaded(self, event: ModLoaded) -> None:
        self.add_mod_row(event.mod)

    def action_scan_sha1(self) -> None:
        self.post_message(self.Sha1Selected(self.mod_dir, self.save_dir))

    def action_scan_names(self) -> None:
        self.post_message(self.ScanNames())

    def action_download_all(self) -> None:
        filenames = []
        for filename in self.active_rows:
            if self.mods[filename]["missing_assets"] > 0:
                filenames.append(filename)
        self.download_missing_assets(filenames)

    def action_download_assets(self) -> None:
        row_key = self.get_current_row_key()
        self.download_missing_assets([row_key.value])

    def download_missing_assets(self, filenames):
        for filename in filenames:
            self.status[filename].download = "Queued"
            self.update_dl_status(filename)
        self.post_message(self.DownloadSelected(filenames))

    def action_filter(self) -> None:
        f = self.query_one("#ml_filter_center")
        if self.filter == "":
            f.toggle_class("unhide")
        if "unhide" in f.classes:
            self.query_one("#ml_filter").focus()
        else:
            self.get_active_table().focus()

    def action_view_log(self) -> None:
        # TODO: This requires loading log twice, need to flush log before this
        # or wait until flush is complete...
        self.post_message(UpdateLog("", prefix="", suffix="", flush=True))
        config = load_config()
        with open(config.log_path, "r", encoding="utf-8") as f:
            self.app.push_screen(DebugScreen(Markdown(f.read())))

    def action_open_config(self) -> None:
        open_url(config_file().as_uri())

    def action_backup_mod(self) -> None:
        config = load_config()
        backup_path = config.mod_backup_dir

        if not Path(backup_path).exists() or not self.backup_ready:
            self.app.push_screen(InfoDialog(f"Backup path '{backup_path}' not found."))
            return

        if config.backup_read_only:
            self.app.push_screen(InfoDialog("Backup is set as read-only."))
            return

        row_key = self.get_current_row_key()
        filename = row_key.value
        mod = self.mods[filename]
        zip_path, existing = self.get_backup_name(mod)
        if zip_path != "":
            self.status[mod["filename"]].backup = "Queued"
            self.update_backup_status(mod["filename"])
            self.post_message(
                self.BackupSelected(
                    [
                        (filename, zip_path, existing),
                    ]
                )
            )

    def get_active_table(self) -> DataTable:
        table = self.query_one(DataTable)
        return table

    def get_current_row_key(self) -> RowKey:
        table = self.query_one(DataTable)
        if table.is_valid_coordinate(table.cursor_coordinate):
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        else:
            row_key = RowKey("")
        return row_key

    def on_key(self, event: Key):
        fc = self.query_one("#ml_filter_center")
        # Check if our filter window is open...
        if "unhide" in fc.classes:
            filter_open = True
        else:
            filter_open = False

        if event.key == "escape":
            if filter_open:
                f = self.query_one("#ml_filter", expect_type=Input)
                if "focus-within" in fc.pseudo_classes:
                    fc.remove_class("unhide")
                    f.value = ""
                    table = self.get_active_table()
                    table.focus()
                else:
                    fc.remove_class("unhide")
                    # Focus is elsewhere, clear the filter
                    # alue and close the filter window
                    f.value = ""
                event.stop()

        elif event.key == "up":
            if filter_open and "focus-within" in fc.pseudo_classes:
                table = self.get_active_table()
                try:
                    table.action_cursor_up()
                except SkipAction:
                    pass

        elif event.key == "down":
            if filter_open and "focus-within" in fc.pseudo_classes:
                table = self.get_active_table()
                try:
                    table.action_cursor_down()
                except SkipAction:
                    pass

        elif event.key == "enter":
            # Select requires two activations (to simulate double click with mouse)
            # However, we want single enter to select a row.  Also, we want enter to
            # auto-select row if filter is enabled.
            table = self.get_active_table()
            if "focus-within" in fc.pseudo_classes:
                table.focus()
            else:
                row_key, _ = table.coordinate_to_cell_key(
                    Coordinate(table.cursor_row, 0)
                )
                # The row selected event will run after this, normally the first
                # row selected event will be ignored (so that single mouse clicks
                # do not jump immediately into the asset screen).  However, when
                # enter is pressed we want to jump to the next screen.  This can
                # be done by forcing the prev_selected to be the current row, then
                # when the row selected even runs it will think this is the second
                # selection event.
                self.prev_selected = row_key
                row_sel_event = DataTable.RowSelected(table, table.cursor_row, row_key)

                # Manually trigger this event, then stop it from bubbling so we can
                # keep focus on the filter box (if it is currently in focus).
                self.on_data_table_row_selected(row_sel_event)
            event.stop()

    def on_input_changed(self, event: Input.Changed):
        self.filter = event.input.value
        if False:
            if self.filter_timer is None:
                self.filter_timer = self.set_timer(
                    0.25, callback=self.update_filtered_rows
                )
            else:
                self.filter_timer.reset()
        else:
            self.update_filtered_rows()

    def on_timer(self):
        self.update_filtered_rows()

    def action_sha1_mismatches(self):
        self.post_message(self.ShowSha1())

    def action_missing_assets(self):
        self.post_message(self.ShowMissing())

    def action_mod_refresh(self):
        table = self.query_one(DataTable)
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key.value is not None:
            self.post_message(self.ModRefresh(row_key.value))

    def action_content_name_report(self):
        config = load_config()

        outname = Path(config.mod_backup_dir) / "content_names.csv"

        asset_list = AssetList()
        urls, content_names, sha1s = asset_list.get_content_names()

        with open(outname, "w", encoding="utf-8", newline="") as f:
            csv_out = csv.writer(f, delimiter="\t")
            for url, cn, sha1 in zip(urls, content_names, sha1s):
                csv_out.writerow([f"{url}", f"{cn}", f"{sha1}"])

        self.app.push_screen(InfoDialog(f"Saved content name report to '{outname}'."))

    def action_content_name_load(self):
        urls = []
        content_names = []

        config = load_config()
        inname = Path(config.mod_backup_dir) / "content_names.csv"

        if not inname.exists():
            self.app.push_screen(
                InfoDialog(f"'{inname}' not found, unable to load content names.")
            )
            return

        with open(inname, "r", encoding="utf-8", newline="") as f:
            csv_in = csv.reader(f, delimiter="\t")
            for line in csv_in:
                urls.append(line[0].strip())
                content_names.append(line[1].strip())

        asset_list = AssetList()
        asset_list.set_content_names(urls, content_names)

        self.app.push_screen(InfoDialog(f"Loaded content names from '{inname}'."))

    def action_help(self) -> None:
        """Show the help."""
        self.app.push_screen(HelpDialog())

    def update_backup_status(self, filename):
        if filename not in self.status:
            return

        if self.status[filename].backup == "Queued":
            self.backup_status[filename] = "Q"
        elif self.status[filename].backup == "Running":
            self.backup_status[filename] = "..."

        table = self.query_one(DataTable)
        try:
            table.update_cell(filename, "backup", self.backup_status[filename])
        except (CellDoesNotExist, KeyError):
            # This cell may be currently filtered, so ignore any errors
            pass

    def update_dl_status(self, filename):
        chart_chars = " ▁▂▃▄▅▆▇█"
        if filename not in self.status:
            return

        cur_time = time.time()
        if cur_time > (self.last_dl_update_time + 0.5):
            do_update = True
            self.last_dl_update_time = cur_time
        else:
            do_update = False

        stat_message = ""
        if self.status[filename].download == "Queued":
            stat_message += "Q"
            do_update = True
        elif self.status[filename].download == "Done":
            stat_message += "✓"
            do_update = True
        elif self.status[filename].download == "Running":
            stat_message += f"{self.progress[filename].files_remaining}->"
            if self.progress[filename].files_remaining == 0:
                do_update = True
            for i, dl_stat in enumerate(self.dl_worker_status):
                if dl_stat.filename == filename:
                    if dl_stat.filesize == 0:
                        stat_message += "?"
                    else:
                        stat_message += f"{i}:"
                        percent_done = float(dl_stat.bytes_complete / dl_stat.filesize)
                        index = math.floor(percent_done * 8)
                        stat_message += chart_chars[index]
                    stat_message += "▏"

        if do_update:
            try:
                table = self.query_one(DataTable)
                table.update_cell(
                    filename, "dl_status", stat_message, update_width=True
                )
            except (CellDoesNotExist, KeyError):
                # This cell may be currently filtered, so ignore any errors
                pass

    def set_dl_progress(self, filename, url, worker_num, filesize, bytes_complete):
        if self.status[filename].download != "Running":
            self.status[filename].download = "Running"
        self.dl_worker_status[worker_num].filename = filename
        self.dl_worker_status[worker_num].url = url
        self.dl_worker_status[worker_num].filesize = filesize
        self.dl_worker_status[worker_num].bytes_complete = bytes_complete
        # No need to update status when file is done, as we will get updated when remaining files are updated
        if bytes_complete != filesize:
            self.update_dl_status(filename)

    def set_files_remaining(self, filename, url_completed, files_remaining, worker_num):
        if url_completed is not None and url_completed in self.downloads:
            self.downloads.remove(url_completed)
        self.progress[filename] = self.ModDlProgress(files_remaining)
        if worker_num != -1:
            if self.status[filename].download == "Queued":
                self.status[filename].download = "Running"
            if files_remaining == 0:
                self.status[filename].download = "Done"
        self.update_dl_status(filename)

    def dl_urls(self, urls, trails, mod_filename="") -> None:
        for url, trail in zip(urls, trails):
            if url in self.downloads:
                continue
            self.downloads.append(url)
            if type(trail) is not list:
                trail = trailstring_to_trail(trail)

            self.dl_queue.put(self.DownloadEntry(url, trail))

    def download_daemon(self) -> None:
        worker = get_current_worker()
        fd = self.fds[int(worker.name)]

        while True:
            if worker.is_cancelled:
                return

            try:
                dl_task = self.dl_queue.get(timeout=1)
            except Empty:
                continue

            error, asset = fd.download(int(worker.name), dl_task.url, dl_task.trail)

            if error == "":
                message = (
                    f"{worker.description}: Download Complete `{asset['filename']}`"
                )
                if asset["content_name"] != "":
                    message += f" (`{asset['content_name']}`)"
                self.post_message(UpdateLog(message, flush=True))
            else:
                self.post_message(
                    UpdateLog(
                        f"{worker.description}: Download Failed ({error}): `{dl_task.url}`",
                        flush=True,
                    )
                )

            self.post_message(self.FileDownloadComplete(int(worker.name), asset))
            self.dl_queue.task_done()

    def get_backup_name(self, mod):
        config = load_config()
        backup_path = config.mod_backup_dir

        backup_basename = Path(
            make_safe_filename(mod["name"]) + f" [{str(Path(mod['filename']).stem)}]"
        )

        backup_filepath = Path(backup_path) / backup_basename

        if mod["missing_assets"] > 0:
            zip_path = Path(
                str(backup_filepath) + f" (-{mod['missing_assets']})" + ".zip"
            )
        else:
            zip_path = Path(str(backup_filepath) + ".zip")

        mf = Path(mod["filename"]).name
        if mf in self.backup_filenames:
            existing = self.backup_filenames[mf]
        else:
            existing = ""

        self.backup_filenames[mf] = zip_path
        return zip_path, existing

    def action_backup_all(self):
        config = load_config()
        backup_path = config.mod_backup_dir

        if not Path(backup_path).exists() or not self.backup_ready:
            self.app.push_screen(InfoDialog(f"Backup path '{backup_path}' not found."))
            return

        if config.backup_read_only:
            self.app.push_screen(InfoDialog("Backup is set as read-only."))
            return

        to_backup = []
        for mod in self.mods.values():
            if mod["deleted"]:
                continue

            if "✓" in self.backup_status[mod["filename"]]:
                continue

            zip_path, existing = self.get_backup_name(mod)

            if zip_path != "":
                to_backup.append((mod["filename"], zip_path, existing))
                self.status[mod["filename"]].backup = "Queued"
                self.update_backup_status(mod["filename"])

        self.post_message(self.BackupSelected(to_backup))

    def set_backup_start(self, filename, zip_path):
        self.status[filename].backup = "Running"
        self.update_backup_status(filename)

    def set_backup_complete(self, filename):
        self.status[filename].backup = ""
        self.backup_status[filename] = " ✓"
        self.update_backup_status(filename)

    def update_bgg(self, mod_filename, bgg_id):
        self.mods[mod_filename]["bgg_id"] = bgg_id
        table = self.query_one(DataTable)
        table.update_cell(
            mod_filename, "bgg", " ✓ " if bgg_id is not None else "", update_width=False
        )

    def action_unzip(self):
        table = self.query_one(DataTable)
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key.value is not None:
            backup_name = Path(row_key.value).name
            if backup_name in self.backup_filenames:
                self.app.push_screen(
                    LoadingScreen(
                        unzip_backup,
                        self.backup_filenames[backup_name],
                        Path(self.mod_dir).parent,
                        backup_name,
                    ),
                    callback=self.unzip_done,
                )
        else:
            self.post_message(
                UpdateLog(
                    f"Mod Backup ({backup_name}) cannot be unzipped (backup not found).",
                    flush=True,
                )
            )

    def unzip_done(self, backup_name):
        self.post_message(
            UpdateLog(
                f"Mod Backup ({self.backup_filenames[backup_name]}) unzipped.",
                flush=True,
            )
        )
        self.app.push_screen(
            InfoDialog(
                f"Mod Backup ({self.backup_filenames[backup_name]}) unzipped.  Restart to scan for new assets."
            )
        )

    def action_explore(self):
        row_key = self.get_current_row_key()
        mod_filename = row_key.value
        if mod_filename is None:
            return

        if "Workshop" in mod_filename:
            mod_filepath = Path(self.mod_dir) / mod_filename
        else:
            mod_filepath = Path(self.save_dir) / mod_filename

        self.app.push_screen(ModExplorerScreen(mod_filepath))
