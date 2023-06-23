from textual.app import ComposeResult
from textual.widgets import Footer, Header, DataTable
from textual.message import Message
from textual.widgets import TabbedContent, TabPane, Static, Input
from textual.screen import Screen
from textual.containers import Center
from textual.events import Key

from ttsmutility.parse import ModList
from ttsmutility.util import format_time
from ttsmutility.parse.AssetList import AssetList


class ModListScreen(Screen):
    BINDINGS = [
        ("s", "scan_sha1", "Scan SHA1s"),
        ("d", "download_assets", "Download Assets"),
        ("f", "filter", "Enable Filter"),
    ]

    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        self.prev_selected = None
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        yield Center(Static(id="ml_status"), id="ml_status_center")
        yield Center(Input(placeholder="Filter", id="ml_filter"), id="ml_filter_center")

        with TabbedContent(initial="workshop"):
            with TabPane("Workshop", id="workshop"):
                yield DataTable(id="mod-list")
            with TabPane("Saves", id="saves"):
                yield DataTable(id="save-list")

    class ModSelected(Message):
        def __init__(
            self, mod_filename: str, mod_name: str, mod_dir: str, save_dir: str
        ) -> None:
            self.mod_filename = mod_filename
            self.mod_name = mod_name
            self.mod_dir = mod_dir
            self.save_dir = save_dir
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
            "modified": False,
            "size": False,
            "total_assets": False,
            "missing_assets": False,
            "filename": False,
        }

        for id in "#mod-list", "#save-list":
            table = next(self.query(id).results(DataTable))

            # TODO: Generate column names and keys in outside module
            if id == "#mod-list":
                table.add_column("Mod Name", width=35, key="name")
            else:
                table.add_column("Save Name", width=35, key="name")
            table.add_column("Modified", key="modified")
            table.add_column("Size (Bytes)", key="size")
            table.add_column("Assets", key="total_assets")
            table.add_column("Missing", key="missing_assets")
            table.add_column("Filename", key="filename")

            table.cursor_type = "row"
            table.sort("name", reverse=self.sort_order["name"])
            self.last_sort_key = "name"

            # self.full_load(id, table)
        self.run_worker(self.load_mods)

    def load_mods(self) -> None:
        self.query_one("#ml_status_center").add_class("unhide")
        mod_asset_list = AssetList(self.mod_dir, self.save_dir)

        def update(mod_names, mod_list, mods):
            total_mods = len(mod_names)
            for i, mod_filename in enumerate(mod_names):
                self.update_status(f"Scanning Mod {i} of {total_mods}")
                mod_asset_list.get_mod_assets(mod_filename, parse_only=True)
                mod_list.update_mod_counts(mod_filename)
                mod = mod_list.get_mod_from_db(mod_filename)
                mods[mod_filename] = mod
                self.add_mod_row(mod)

        self.mods = {}
        mod_list = ModList.ModList(self.mod_dir)
        mod_names = mod_list.get_mods(parse_only=True, sort_by=self.last_sort_key)
        update(mod_names, mod_list, self.mods)

        self.saves = {}
        save_list = ModList.ModList(self.save_dir, is_save=True)
        save_names = save_list.get_mods(parse_only=True, sort_by=self.last_sort_key)
        update(save_names, save_list, self.saves)

        self.query_one("#ml_status_center").remove_class("unhide")

    def get_mod_table(self, filename: str) -> DataTable:
        if filename.split("\\")[0] == "Workshop":
            id = "#mod-list"
            mods = self.mods
        else:
            id = "#save-list"
            mods = self.saves

        table = next(self.query(id).results(DataTable))
        return table, mods

    def add_mod_row(self, mod: dict) -> None:
        filename = mod["filename"]
        table, mods = self.get_mod_table(filename)

        table.add_row(
            mods[filename]["name"].ljust(35),
            format_time(mods[filename]["mtime"], "Scanning..."),
            mods[filename]["size"],
            mods[filename]["total_assets"],
            mods[filename]["missing_assets"],
            filename,
            key=filename,
        )

    def update_status(self, message: str, disabled=False):
        status = next(self.query("#ml_status").results(Static))
        status.update(message)

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
        table.update_cell(row_key, "size", size)

    def action_show_tab(self, tab: str) -> None:
        self.get_child_by_type(TabbedContent).active = tab

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        if event.tab.id == "workshop":
            id = "#mod-list"
        else:
            id = "#save-list"
        table = next(self.query(id).results(DataTable))
        table.focus()
        table.sort("name", reverse=self.sort_order["name"])
        self.last_sort_key = "name"
        self.log(self.css_tree)

    def get_mod_by_row(self, id: str, row_key) -> tuple:
        if id == "mod-list":
            mod_filename = self.mods[row_key.value]["filename"]
            mod_name = self.mods[row_key.value]["name"]
        else:
            mod_filename = self.saves[row_key.value]["filename"]
            mod_name = self.saves[row_key.value]["name"]
        # assets are always stored in mod_dir
        mod_dir = self.mod_dir
        save_dir = self.save_dir
        return (mod_filename, mod_name, mod_dir, save_dir)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if self.prev_selected is not None and event.row_key == self.prev_selected:
            args = self.get_mod_by_row(event.data_table.id, event.row_key)
            self.post_message(self.ModSelected(*args))
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
        if tabbed.active == "workshop":
            id = "mod-list"
        else:
            id = "save-list"
        table = next(self.query("#" + id).results(DataTable))
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        args = self.get_mod_by_row(id, row_key)
        self.post_message(self.DownloadSelected(*args))

    def action_filter(self) -> None:
        self.query_one("#ml_filter_center").toggle_class("unhide")

    def on_key(self, event: Key):
        if event.key == "enter":
            if self.query_one("TabbedContent").active == "workshop":
                id = "#mod-list"
            else:
                id = "#save-list"
            table = next(self.query(id).results(DataTable))
            row_key, _ = table.coordinate_to_cell_key((table.cursor_row, 0))
            args = self.get_mod_by_row(id[1:], row_key)
            self.post_message(self.ModSelected(*args))
