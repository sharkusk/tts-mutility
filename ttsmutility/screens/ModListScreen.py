import csv
import glob
from dataclasses import dataclass
from itertools import filterfalse
from pathlib import Path
from queue import Empty, Queue
from typing import NamedTuple
from webbrowser import open as open_url

from rich.markdown import Markdown
from rich.progress import BarColumn, DownloadColumn, MofNCompleteColumn, Progress
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center
from textual.events import Key
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, TabbedContent, TabPane
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
from ..utility.util import MyText, format_time, make_safe_filename
from ..workers.downloader import FileDownload
from .DebugScreen import DebugScreen


class ModListScreen(Screen):
    class FileDownloadComplete(Message):
        def __init__(
            self,
            asset: dict,
        ) -> None:
            super().__init__()
            self.asset = asset

    class DownloadEntry(NamedTuple):
        url: str
        trail: str

    @dataclass
    class WorkerStatus:
        download: str
        backup: str

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("ctrl+q", "app.quit", "Quit"),
        Binding("/", "filter", "Filter"),
        Binding("ctrl+l", "view_log", "View Log", show=False),
        Binding("ctrl+o", "open_config", "Open Config", show=False),
        Binding("ctrl+a", "download_all", "Download All Missing Assets", show=False),
        Binding("ctrl+d", "download_assets", "Download Missing Assets", show=False),
        Binding("ctrl+b", "backup_mod", "Backup mod to zip", show=False),
        Binding("ctrl+w", "backup_all", "Backup all mods", show=False),
        Binding("ctrl+r", "mod_refresh", "Refresh Mod", show=False),
        Binding("ctrl+l", "view_log", "View Log", show=False),
        Binding("ctrl+o", "open_config", "Open Config", show=False),
        Binding("ctrl+s", "scan_sha1", "Compute SHA1s", show=False),
        Binding("ctrl+p", "sha1_mismatches", "Show SHA1 Mismatches", show=False),
        Binding("ctrl+n", "content_name_report", "Save Content Names", show=False),
        Binding("ctrl+f", "content_name_load", "Load Content Names", show=False),
    ]

    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        self.prev_selected = None
        self.filter = ""
        self.prev_filter = ""
        self.active_rows = {}
        self.filtered_rows = {}
        self.progress = {}
        self.progress_id = {}
        self.status = {}
        self.dl_queue = Queue()
        self.filter_timer = None
        self.downloads = []
        super().__init__()

        config = load_config()

        for i in range(int(config.num_download_threads)):
            self.run_worker(
                self.download_daemon,
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
        with TabbedContent(initial="ml_pane_workshop"):
            with TabPane("Workshop", id="ml_pane_workshop"):
                yield DataTable(id="ml_workshop_dt")
            with TabPane("Saves", id="ml_pane_saves"):
                yield DataTable(id="ml_saves_dt")

    class ModRefresh(Message):
        def __init__(self, mod_filename: str) -> None:
            self.filename = mod_filename
            super().__init__()

    class ModSelected(Message):
        def __init__(self, mod_filename: str) -> None:
            self.filename = mod_filename
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

    def on_mount(self) -> None:
        self.sort_order = {
            "name": False,
            "type": False,
            "created": True,
            "modified": True,
            "size": True,
            "total_assets": True,
            "missing_assets": True,
            "min_players": True,
            "max_players": True,
            "status": True,
        }

        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))
        table.fixed_columns = 1
        table.zebra_stripes = True

        table.add_column("Mod Name", width=40, key="name")
        table.add_column("Type", key="type")
        table.add_column("Created", key="created", width=10)
        table.add_column("Modified", key="modified", width=10)
        table.add_column("Size(MB)", key="size")
        table.add_column("Assets", key="total_assets")
        table.add_column("Missing", key="missing_assets")
        table.add_column("MinP", key="min_players")
        table.add_column("MaxP", key="max_players")
        table.add_column("Status", key="status")
        table.add_column("Progress", key="progress")

        table.cursor_type = "row"
        table.sort("name", reverse=self.sort_order["name"])
        self.last_sort_key = "name"

        self.load_mods()

    def load_mods(self) -> None:
        mod_list = ModList.ModList()
        self.mods = mod_list.get_mods()

        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        self.infected_filenames = [mod_filename for mod_filename, _ in infected_mods]

        for mod_filename in self.mods.keys():
            self.add_mod_row(self.mods[mod_filename])
            self.status[mod_filename] = self.WorkerStatus("", "")

        f = self.query_one("#ml_filter")
        f.placeholder = "Filter"
        f.disabled = False

    def clean_name(self, name):
        words_to_move = [
            "scripted deal ",
            "scripted ",
            "wip ",
            "complete ",
            "gf9 ",
            "epic ",
            "v2 automated ",
            "reiner knizia's ",
            "- ",
            "(remastered) ",
        ]
        if name[0] == "[":
            # Move [] to end of name
            e = name.find("]")
            name = (name[e + 1 :] + " " + name[0 : e + 1]).strip()
        for to_move in words_to_move:
            if name.lower().find(to_move) == 0:
                name = name[len(to_move) :] + ", " + name[: len(to_move)]
        if name.find("the") == 0:
            name = name.replace("the", "The")
        if name.find("TTS-") == 0:
            name = name[4:].strip()
        if name[0] == "+":
            name = name[1:].strip()
        if name[0] == '"':
            name = name.replace('"', "")

        return name

    def add_mod_row(self, mod: dict) -> None:
        filename = mod["filename"]
        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))

        name = self.clean_name(mod["name"])
        if mod["filename"] in self.infected_filenames:
            name = MyText(name, style="#FF0000")
        if mod["deleted"]:
            name = MyText(name, style="strike")

        table.add_row(
            name,
            "Mod" if "Workshop" in filename else "Save",
            format_time(mod["epoch"], ""),
            format_time(mod["mtime"], "Scanning..."),
            mod["size"] / (1024 * 1024),
            mod["total_assets"],
            mod["missing_assets"],
            mod["min_players"],
            mod["max_players"],
            "",  # No status to start...
            "",  # No progress to start...
            key=filename,
        )
        self.active_rows[filename] = mod["name"]

    def update_filtered_rows(self) -> None:
        self.filter_timer = None

        row_key = self.get_current_row_key()
        if len(self.filter) > len(self.prev_filter):
            # Filter is getting longer, so we are going to be removing rows
            filenames_to_remove = list(
                filterfalse(
                    lambda x: self.filter.lower() in self.active_rows[x].lower(),
                    self.active_rows.keys(),
                )
            )
            id = "#ml_workshop_dt"
            table = next(self.query(id).results(DataTable))
            for i, filename in enumerate(filenames_to_remove):
                table.remove_row(filename)
                self.filtered_rows[filename] = self.active_rows[filename]
                self.active_rows.pop(filename)
        else:
            # Filter is getting shorter, so we may be adding rows (if any now match)
            filenames_to_add = list(
                filter(
                    lambda x: self.filter.lower() in self.filtered_rows[x].lower(),
                    self.filtered_rows.keys(),
                )
            )
            for i, filename in enumerate(filenames_to_add):
                self.filtered_rows.pop(filename)
                self.add_mod_row(self.mods[filename])
                # self.active_rows is updated in the add_mod_row function
            self.get_active_table()[0].sort(
                self.last_sort_key, reverse=self.sort_order[self.last_sort_key]
            )

        # Now jump to the previously selected row
        if row_key != "":
            self.call_after_refresh(self.jump_to_row_key, row_key)

        self.prev_filter = self.filter

    def jump_to_row_key(self, row_key):
        (
            table,
            _,
        ) = self.get_active_table()
        # TODO: Remove internal API calls once Textual #2876 is published
        row_index = table._row_locations.get(row_key)
        if row_index is not None and table.is_valid_row_index(row_index):
            table.cursor_coordinate = (row_index, 0)

    def update_counts(self, mod_filename, total_assets, missing_assets, size):
        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        self.infected_filenames = [mod_filename for mod_filename, _ in infected_mods]

        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))

        row_key = mod_filename
        if row_key not in self.mods:
            return

        name = self.clean_name(self.mods[row_key]["name"])
        if self.mods[row_key]["filename"] in self.infected_filenames:
            name = MyText(name, style="#FF0000")
        if self.mods[row_key]["deleted"]:
            name = MyText(name, style="strike")

        # We need to update both our internal asset information
        # and what is shown on the table...
        self.mods[row_key]["total_assets"] = total_assets
        self.mods[row_key]["missing_assets"] = missing_assets
        self.mods[row_key]["size"] = size

        try:
            table.update_cell(row_key, "name", name)
            table.update_cell(row_key, "total_assets", total_assets)
            table.update_cell(row_key, "missing_assets", missing_assets)
            table.update_cell(row_key, "size", size / (1024 * 1024))
        except CellDoesNotExist:
            # This can happen if some of our mods are filtered and an
            # asset is shared with a filtered one that isn't being displayed.
            pass

    def action_show_tab(self, tab: str) -> None:
        self.get_child_by_type(TabbedContent).active = tab

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        if event.tab.id == "ml_pane_workshop":
            id = "#ml_workshop_dt"
        else:
            id = "#ml_saves_dt"
        table = next(self.query(id).results(DataTable))
        table.sort(self.last_sort_key, reverse=self.sort_order[self.last_sort_key])
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if self.prev_selected is not None and event.row_key == self.prev_selected:
            self.post_message(self.ModSelected(event.row_key.value))
        self.prev_selected = event.row_key

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if event.column_key.value == "progress":
            # Progress bars don't support sort operations
            return
        sort_key = event.column_key.value

        if self.last_sort_key == sort_key:
            self.sort_order[sort_key] = not self.sort_order[sort_key]

        reverse = self.sort_order[sort_key]

        self.last_sort_key = event.column_key.value
        self.sort_order[sort_key] = reverse

        event.data_table.sort(event.column_key, reverse=reverse)

    def on_mod_list_screen_mod_loaded(self, event: ModLoaded) -> None:
        self.add_mod_row(event.mod)

    def action_scan_sha1(self) -> None:
        self.post_message(self.Sha1Selected(self.mod_dir, self.save_dir))

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
            self.update_status(filename)
        self.post_message(self.DownloadSelected(filenames))

    def action_filter(self) -> None:
        f = self.query_one("#ml_filter_center")
        if self.filter == "":
            f.toggle_class("unhide")
        if "unhide" in f.classes:
            self.query_one("#ml_filter").focus()
        else:
            self.get_active_table()[0].focus()

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

        if not Path(backup_path).exists():
            self.app.push_screen(InfoDialog(f"Backup path '{backup_path}' not found."))
            return

        row_key = self.get_current_row_key()
        filename = row_key.value
        zip_path, _ = self.get_backup_name(self.mods[filename])
        self.post_message(
            self.BackupSelected(
                [
                    (filename, zip_path, []),
                ]
            )
        )

    def get_active_table(self) -> tuple[DataTable, int]:
        if self.query_one("TabbedContent").active == "ml_pane_workshop":
            table_id = "#ml_workshop_dt"
        else:
            table_id = "#ml_saves_dt"
        return next(self.query(table_id).results(DataTable)), table_id[1:]

    def get_current_row_key(self) -> RowKey:
        tabbed = self.query_one(TabbedContent)
        if tabbed.active == "ml_pane_workshop":
            id = "ml_workshop_dt"
        else:
            id = "ml_saves_dt"
        table = next(self.query("#" + id).results(DataTable))
        if table.is_valid_coordinate(table.cursor_coordinate):
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        else:
            row_key = ""
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
                f = self.query_one("#ml_filter")
                if "focus-within" in fc.pseudo_classes:
                    fc.remove_class("unhide")
                    f.value = ""
                    table, _ = self.get_active_table()
                    table.focus()
                else:
                    fc.remove_class("unhide")
                    # Focus is elsewhere, clear the filter
                    # alue and close the filter window
                    f.value = ""
                event.stop()

        elif event.key == "up":
            if filter_open:
                table, _ = self.get_active_table()
                row, col = table.cursor_coordinate
                if row > 0:
                    table.cursor_coordinate = (row - 1, col)
                    event.stop()

        elif event.key == "down":
            if filter_open:
                table, _ = self.get_active_table()
                row, col = table.cursor_coordinate
                if row < table.row_count - 1:
                    table.cursor_coordinate = (row + 1, col)
                    event.stop()

        elif event.key == "enter":
            # Select requires two activations (to simulate double click with mouse)
            # However, we want single enter to select a row.  Also, we want enter to
            # auto-select row if filter is enabled.
            table, _ = self.get_active_table()
            f = self.query_one("#ml_filter_center")
            if "focus-within" in f.pseudo_classes:
                if self.filter == "":
                    table.focus()
                    f.toggle_class("unhide")
            row_key, _ = table.coordinate_to_cell_key((table.cursor_row, 0))
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

        elif event.key == "tab":
            if not filter_open:
                tabbed_content = self.query_one(TabbedContent)
                if tabbed_content.active == "ml_pane_workshop":
                    tabbed_content.active = "ml_pane_saves"
                    id = "ml_pane_saves"
                else:
                    tabbed_content.active = "ml_pane_workshop"
                    id = "ml_pane_workshop"

                tabbed_content = self.query_one(TabbedContent)
                pane = next(self.query("#" + id).results(TabPane))
                new_event = TabbedContent.TabActivated(tabbed_content, pane)
                self.post_message(new_event)
                event.stop()

    def on_input_changed(self, event: Input.Changed):
        self.filter = event.input.value
        if self.filter_timer is None:
            self.filter_timer = self.set_timer(0.25, callback=self.update_filtered_rows)
        else:
            self.filter_timer.reset()

    def on_timer(self):
        self.update_filtered_rows()

    def action_sha1_mismatches(self):
        self.post_message(self.ShowSha1())

    def action_mod_refresh(self):
        tabbed = self.query_one(TabbedContent)
        if tabbed.active == "ml_pane_workshop":
            id = "ml_workshop_dt"
        else:
            id = "ml_saves_dt"
        table = next(self.query("#" + id).results(DataTable))
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        self.post_message(self.ModRefresh(row_key.value))

    def action_content_name_report(self):
        config = load_config()

        outname = Path(config.mod_backup_dir) / "content_names.csv"

        asset_list = AssetList()
        urls, content_names = asset_list.get_content_names()

        with open(outname, "w", encoding="utf-8") as f:
            for url, cn in zip(urls, content_names):
                f.write(f"{url}, {cn}\n")

        self.app.push_screen(InfoDialog(f"Saved content name report to '{outname}'."))

    def action_content_name_load(self):
        config = load_config()

        urls = []
        content_names = []

        inname = Path(config.mod_backup_dir) / "content_names.csv"

        if not inname.exists():
            self.app.push_screen(
                InfoDialog(f"'{inname}' not found, unable to load content names.")
            )
            return

        with open(inname, "r", encoding="utf-8") as f:
            csv_file = csv.reader(f)

            for lines in csv_file:
                urls.append(lines[0].strip())
                content_names.append(lines[1].strip())

        asset_list = AssetList()
        asset_list.set_content_names(urls, content_names)

        self.app.push_screen(InfoDialog(f"Loaded content names from '{inname}'."))

    def action_help(self) -> None:
        """Show the help."""
        self.app.push_screen(HelpDialog())

    def update_status(self, filename):
        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))

        stat = []
        if self.status[filename].download == "Queued":
            stat.append("DLoad-Q")
        elif self.status[filename].download == "Running":
            stat.append("DLoad")
        if self.status[filename].backup == "Queued":
            stat.append("Backup-Q")
        elif self.status[filename].backup == "Running":
            stat.append("Backup")
        if len(stat) > 0:
            stat_message = ",".join(stat)
        else:
            stat_message = ""

        try:
            table.update_cell(filename, "status", stat_message, update_width=True)
        except CellDoesNotExist:
            # This cell may be currently filtered, so ignore any errors
            pass

    def set_files_remaining(self, filename, files_remaining):
        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))

        if self.status[filename].download == "Queued":
            self.status[filename].download = "Running"
            self.update_status(filename)

            # This is the first update, so configure our progress bar
            self.progress[filename] = Progress(MofNCompleteColumn(), BarColumn())

            # This function gets called after the first file is already downloaded.
            # Therefore we need to add 1 to our total number of files
            self.progress_id[filename] = self.progress[filename].add_task(
                "Files", total=files_remaining + 1
            )
            try:
                table.update_cell(
                    filename, "progress", self.progress[filename], update_width=True
                )
            except CellDoesNotExist:
                # This cell may be currently filtered, so ignore any errors
                pass

        self.progress[filename].update(self.progress_id[filename], advance=1)
        try:
            table.update_cell(filename, "progress", self.progress[filename])
        except CellDoesNotExist:
            # This cell may be currently filtered, so ignore any errors
            pass

        if files_remaining == 0:
            self.status[filename].download = ""
            self.update_status(filename)

    def dl_urls(self, urls, trails) -> None:
        for url, trail in zip(urls, trails):
            if url in self.downloads:
                continue
            self.downloads.append(url)
            if type(trail) is not list:
                trail = trailstring_to_trail(trail)

            self.dl_queue.put(self.DownloadEntry(url, trail))

    def download_daemon(self) -> None:
        worker = get_current_worker()

        while True:
            if worker.is_cancelled:
                return

            try:
                dl_task = self.dl_queue.get(timeout=1)
            except Empty:
                continue

            fd = FileDownload(dl_task.url, dl_task.trail)

            error, asset = fd.download()

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

            self.post_message(self.FileDownloadComplete(asset))
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

        return zip_path, backup_filepath

    def action_backup_all(self):
        config = load_config()
        backup_path = config.mod_backup_dir

        if not Path(backup_path).exists():
            self.app.push_screen(InfoDialog(f"Backup path '{backup_path}' not found."))
            return

        to_backup = []
        for mod in self.mods.values():
            if mod["deleted"]:
                continue

            zip_path, backup_filepath = self.get_backup_name(mod)

            backup = False
            if zip_path.exists():
                backup_mtime = zip_path.stat().st_mtime
                if backup_mtime < mod["mtime"] or backup_mtime < mod["newest_asset"]:
                    backup = True
            else:
                backup = True

            if backup:
                existing = sorted(
                    backup_filepath.parent.glob(
                        glob.escape(backup_filepath.name) + " (-*"
                    )
                )
                to_backup.append((mod["filename"], zip_path, existing))
                self.status[mod["filename"]].backup = "Queued"
                self.update_status(mod["filename"])

        self.post_message(self.BackupSelected(to_backup))

    def set_backup_progress(self, filename, update_total, advance_amount):
        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))

        if (
            self.status[filename].backup == "Queued"
            or self.status[filename].backup == ""
        ):
            self.status[filename].backup = "Running"
            self.update_status(filename)

            # This is the first update, so configure our progress bar
            self.progress[filename] = Progress(
                DownloadColumn(binary_units=True), BarColumn()
            )

            # This function gets called after the first file is already downloaded.
            # Therefore we need to add 1 to our total number of files
            self.progress_id[filename] = self.progress[filename].add_task(
                "Bytes", total=update_total
            )
            try:
                table.update_cell(
                    filename, "progress", self.progress[filename], update_width=True
                )
            except CellDoesNotExist:
                # This cell may be currently filtered, so ignore any errors
                pass
        if advance_amount is not None:
            self.progress[filename].update(
                self.progress_id[filename], advance=advance_amount
            )
            try:
                table.update_cell(filename, "progress", self.progress[filename])
            except CellDoesNotExist:
                # This cell may be currently filtered, so ignore any errors
                pass

    def set_backup_start(self, filename, zip_path):
        id = "#ml_workshop_dt"
        table = next(self.query(id).results(DataTable))
        try:
            table.update_cell(filename, "status", str(zip_path), update_width=True)
        except CellDoesNotExist:
            # This cell may be currently filtered, so ignore any errors
            pass

    def set_backup_complete(self, filename):
        self.status[filename].backup = ""
        self.update_status(filename)
