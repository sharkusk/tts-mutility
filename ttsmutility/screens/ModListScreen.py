from textual.app import ComposeResult
from textual.widgets import Footer, Header, DataTable
from textual.message import Message
from textual.widgets import TabbedContent, TabPane, Static, Input
from textual.screen import Screen
from textual.containers import Center
from textual.events import Key

from ..parse import ModList
from ..utility.util import format_time

from itertools import filterfalse


class ModListScreen(Screen):
    BINDINGS = [
        ("q", "exit", "Quit"),
        ("s", "scan_sha1", "Scan SHA1s"),
        ("d", "download_assets", "Download Assets"),
        ("f", "filter", "Filter"),
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
                table.add_column("Mod Name", width=35, key="name")
            else:
                table.add_column("Save Name", width=35, key="name")
            table.add_column("Created", key="created")
            table.add_column("File Modified", key="modified")
            table.add_column("Size (MB)", key="size")
            table.add_column("Assets", key="total_assets")
            table.add_column("Missing", key="missing_assets")
            table.add_column("Min P", key="min_players")
            table.add_column("Max P", key="max_players")

            table.cursor_type = "row"
            table.sort("name", reverse=self.sort_order["name"])
            self.last_sort_key = "name"

        self.load_mods()

    def load_mods(self) -> None:
        mod_list = ModList.ModList()
        self.mods = mod_list.get_mods()

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

    def add_mod_row(self, mod: dict) -> None:
        filename = mod["filename"]
        table, mods = self.get_mod_table(filename)

        table.add_row(
            mods[filename]["name"].ljust(35),
            format_time(mods[filename]["epoch"], ""),
            format_time(mods[filename]["mtime"], "Scanning..."),
            mods[filename]["size"] / (1024 * 1024),
            mods[filename]["total_assets"],
            mods[filename]["missing_assets"],
            mods[filename]["min_players"],
            mods[filename]["max_players"],
            key=filename,
        )
        self.active_rows[filename] = mods[filename]["name"]

    def update_filtered_rows(self) -> None:
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
        self.prev_filter = self.filter

    def update_counts(self, mod_filename, total_assets, missing_assets, size):
        row_key = mod_filename
        table, mods = self.get_mod_table(mod_filename)

        # We need to update both our internal asset information
        # and what is shown on the table...
        mods[row_key]["total_assets"] = total_assets
        mods[row_key]["missing_assets"] = missing_assets
        mods[row_key]["size"] = size

        table.update_cell(row_key, "total_assets", total_assets)
        table.update_cell(row_key, "missing_assets", missing_assets)
        table.update_cell(row_key, "size", size / (1024 * 1024))

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
        table.focus()
        table.sort("name", reverse=self.sort_order["name"])
        self.last_sort_key = "name"
        self.log(self.css_tree)

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

        event.data_table.sort(event.column_key, reverse=reverse)

    def on_mod_list_screen_mod_loaded(self, event: ModLoaded) -> None:
        self.add_mod_row(event.mod)

    def action_scan_sha1(self) -> None:
        self.post_message(self.Sha1Selected(self.mod_dir, self.save_dir))

    def action_download_assets(self) -> None:
        tabbed = self.query_one(TabbedContent)
        if tabbed.active == "ml_pane_workshop":
            id = "ml_workshop_dt"
        else:
            id = "ml_saves_dt"
        table = next(self.query("#" + id).results(DataTable))
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
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

    def action_exit(self) -> None:
        self.app.exit()

    def get_active_table(self) -> tuple:
        if self.query_one("TabbedContent").active == "ml_pane_workshop":
            table_id = "#ml_workshop_dt"
        else:
            table_id = "#ml_saves_dt"
        return next(self.query(table_id).results(DataTable)), table_id[1:]

    def on_key(self, event: Key):
        if event.key == "escape":
            fc = self.query_one("#ml_filter_center")
            # Check if our filter window is open...
            if "unhide" in fc.classes:
                f = self.query_one("#ml_filter")
                if "focus-within" in fc.pseudo_classes:
                    # If focus in on the filter, exit if filter is empty, otherwise clear it
                    if f.value == "":
                        table, _ = self.get_active_table()
                        table.focus()
                        fc.toggle_class("unhide")
                    else:
                        f.value = ""
                else:
                    # Focus is elsewhere, clear the filter value and close the filter window
                    f.value = ""
                    fc.toggle_class("unhide")

        if event.key == "enter":
            table, _ = self.get_active_table()
            f = self.query_one("#ml_filter_center")
            if "focus-within" in f.pseudo_classes:
                self.prev_selected = ""
                table.focus()
                if self.filter == "":
                    f.toggle_class("unhide")
                return
            row_key, _ = table.coordinate_to_cell_key((table.cursor_row, 0))
            # The row selected event will run after this, normally the first
            # row selected event will be ignored (so that single mouse clicks
            # do not jump immediately into the asset screen).  However, when
            # enter is pressed we want to jump to the next screen.  This can
            # be done by forcing the prev_selected to be the current row, then
            # when the row selected even runs it will think this is the second
            # selection event.
            self.prev_selected = row_key

    def on_input_changed(self, event: Input.Changed):
        self.filter = event.input.value
        self.update_filtered_rows()
