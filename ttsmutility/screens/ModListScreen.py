import csv
from itertools import filterfalse
from pathlib import Path
from webbrowser import open as open_url

from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center
from textual.events import Key, ScreenResume
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, TabbedContent, TabPane
from textual.widgets.data_table import CellDoesNotExist, RowKey

from ..data.config import config_file, load_config
from ..dialogs.HelpDialog import HelpDialog
from ..dialogs.InfoDialog import InfoDialog
from ..parse import ModList
from ..parse.AssetList import AssetList
from ..parse.ModParser import INFECTION_URL
from ..utility.messages import UpdateLog
from ..utility.util import format_time
from .DebugScreen import DebugScreen


# Remove this once Rich accepts pull request #3016
class MyText(Text):
    def __lt__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.plain < other
        elif isinstance(other, MyText):
            return self.plain < other.plain
        return False

    def __gt__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.plain > other
        elif isinstance(other, MyText):
            return self.plain > other.plain
        return False


class ModListScreen(Screen):
    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("ctrl+q", "app.quit", "Quit"),
        Binding("/", "filter", "Filter"),
        Binding("ctrl+l", "view_log", "View Log", show=False),
        Binding("ctrl+o", "open_config", "Open Config", show=False),
        Binding("ctrl+d", "download_assets", "Download Missing Assets", show=False),
        Binding("ctrl+b", "backup_mod", "Backup mod to zip", show=False),
        Binding("ctrl+r", "mod_refresh", "Refresh Mod", show=False),
        Binding("ctrl+l", "view_log", "View Log", show=False),
        Binding("ctrl+o", "open_config", "Open Config", show=False),
        Binding("ctrl+s", "scan_sha1", "Compute SHA1s", show=False),
        Binding("ctrl+m", "sha1_mismatches", "Show SHA1 Mismatches", show=False),
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
        super().__init__()

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
        def __init__(
            self, mod_filename: str, mod_name: str, mod_dir: str, save_dir: str
        ) -> None:
            self.mod_dir = mod_dir
            self.save_dir = save_dir
            self.mod_filename = mod_filename
            self.mod_name = mod_name
            super().__init__()

    class BackupSelected(Message):
        def __init__(
            self, mod_filename: str, mod_name: str, mod_dir: str, save_dir: str
        ) -> None:
            self.mod_dir = mod_dir
            self.save_dir = save_dir
            self.mod_filename = mod_filename
            self.mod_name = mod_name
            super().__init__()

    class ShowSha1(Message):
        def __init__(self) -> None:
            super().__init__()

    def on_mount(self) -> None:
        self.sort_order = {
            "name": False,
            "created": False,
            "modified": False,
            "size": False,
            "total_assets": False,
            "missing_assets": False,
            "min_players": False,
            "max_players": False,
        }

        for id in "#ml_workshop_dt", "#ml_saves_dt":
            table = next(self.query(id).results(DataTable))

            # TODO: Generate column names and keys in outside module
            if id == "#ml_workshop_dt":
                table.add_column("Mod Name", width=40, key="name")
            else:
                table.add_column("Save Name", width=40, key="name")
            table.add_column("Created", key="created")
            table.add_column("Modified", key="modified")
            table.add_column("Size(MB)", key="size")
            table.add_column("Assets", key="total_assets")
            table.add_column("Missing", key="missing_assets")
            table.add_column("MinP", key="min_players")
            table.add_column("MaxP", key="max_players")

            table.cursor_type = "row"
            table.sort("name", reverse=self.sort_order["name"])
            self.last_sort_key = "name"

        self.load_mods()

    def on_screen_resume(self, event: ScreenResume):
        pass

    def load_mods(self) -> None:
        mod_list = ModList.ModList()
        self.mods = mod_list.get_mods()

        asset_list = AssetList()
        self.infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)

        for mod_filename in self.mods.keys():
            self.add_mod_row(self.mods[mod_filename])

        f = self.query_one("#ml_filter")
        f.placeholder = "Filter"
        f.disabled = False

    def get_mod_table(self, filename: str) -> tuple:
        mods = self.mods
        if filename.find("Workshop") == 0:
            id = "#ml_workshop_dt"
        else:
            id = "#ml_saves_dt"

        table = next(self.query(id).results(DataTable))
        return table, mods

    def clean_name(self, name):
        if name[0] == "[":
            # Move [] to end of name
            e = name.find("]")
            name = (name[e + 1 :] + " " + name[0 : e + 1]).strip()
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
        table, _ = self.get_mod_table(filename)

        name = self.clean_name(mod["name"])
        if mod["name"] in self.infected_mods:
            name = MyText(name, style="#FF0000")

        table.add_row(
            name,
            format_time(mod["epoch"], ""),
            format_time(mod["mtime"], "Scanning..."),
            mod["size"] / (1024 * 1024),
            mod["total_assets"],
            mod["missing_assets"],
            mod["min_players"],
            mod["max_players"],
            key=filename,
        )
        self.active_rows[filename] = mod["name"]

    def update_filtered_rows(self) -> None:
        row_key = self.get_current_row_key()
        if len(self.filter) > len(self.prev_filter):
            # Filter is getting longer, so we are going to be removing rows
            filenames_to_remove = list(
                filterfalse(
                    lambda x: self.filter.lower() in self.active_rows[x].lower(),
                    self.active_rows.keys(),
                )
            )
            for filename in filenames_to_remove:
                table, _ = self.get_mod_table(filename)
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
            for filename in filenames_to_add:
                self.filtered_rows.pop(filename)
                _, mods = self.get_mod_table(filename)
                self.add_mod_row(mods[filename])
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
        self.infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)

        row_key = mod_filename
        table, mods = self.get_mod_table(mod_filename)

        name = self.clean_name(mods[row_key]["name"])
        if mods[row_key]["name"] in self.infected_mods:
            name = MyText(name, style="#FF0000")

        # We need to update both our internal asset information
        # and what is shown on the table...
        mods[row_key]["total_assets"] = total_assets
        mods[row_key]["missing_assets"] = missing_assets
        mods[row_key]["size"] = size

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

    def get_mod_by_row(self, id: str, row_key) -> tuple:
        mod_filename = self.mods[row_key.value]["filename"]
        mod_name = self.mods[row_key.value]["name"]
        # assets are always stored in mod_dir
        mod_dir = self.mod_dir
        save_dir = self.save_dir
        return (mod_filename, mod_name, mod_dir, save_dir)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if self.prev_selected is not None and event.row_key == self.prev_selected:
            self.post_message(self.ModSelected(event.row_key.value))
        self.prev_selected = event.row_key

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if self.last_sort_key == event.column_key.value:
            self.sort_order[event.column_key.value] = not self.sort_order[
                event.column_key.value
            ]
        else:
            self.sort_order[event.column_key.value] = False

        reverse = self.sort_order[event.column_key.value]

        self.last_sort_key = event.column_key.value
        self.sort_order[self.last_sort_key] = reverse

        event.data_table.sort(event.column_key, reverse=reverse)

    def on_mod_list_screen_mod_loaded(self, event: ModLoaded) -> None:
        self.add_mod_row(event.mod)

    def action_scan_sha1(self) -> None:
        self.post_message(self.Sha1Selected(self.mod_dir, self.save_dir))

    def action_download_assets(self) -> None:
        row_key = self.get_current_row_key()
        args = self.get_mod_by_row(id, row_key)
        self.post_message(self.DownloadSelected(*args))

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
        row_key = self.get_current_row_key()
        args = self.get_mod_by_row(id, row_key)
        self.post_message(self.BackupSelected(*args))

    def get_active_table(self) -> tuple:
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

                # table = next(self.query(id).results(DataTable))
                # table.focus()
                tabbed_content = self.query_one(TabbedContent)
                pane = next(self.query("#" + id).results(TabPane))
                new_event = TabbedContent.TabActivated(tabbed_content, pane)
                self.post_message(new_event)
                event.stop()

    def on_input_changed(self, event: Input.Changed):
        self.filter = event.input.value
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
