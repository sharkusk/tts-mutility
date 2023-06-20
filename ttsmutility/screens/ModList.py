from textual.app import ComposeResult
from textual.widgets import Footer, Header, DataTable
from textual.message import Message
from textual.widgets import TabbedContent, TabPane
from textual.screen import Screen

from ttsmutility.parse import ModList
from ttsmutility.util import format_time


class ModListScreen(Screen):
    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with TabbedContent(initial="workshop"):
            with TabPane("Workshop", id="workshop"):
                yield DataTable(id="mod-list")
            with TabPane("Saves", id="saves"):
                yield DataTable(id="save-list")

    class ModSelected(Message):
        def __init__(self, mod_filename: str, mod_name: str, mod_dir: str) -> None:
            self.mod_filename = mod_filename
            self.mod_name = mod_name
            self.mod_dir = mod_dir
            super().__init__()

    def on_mount(self) -> None:
        self.sort_order = {
            "name": False,
            "modified": False,
            "total_assets": False,
            "total_missing": False,
            "filename": False,
            "url": False,
            "trail": False,
            "sha1": False,
            "asset_filename": False,
        }

        for id in "#mod-list", "#save-list":
            table = next(self.query(id).results(DataTable))

            # TODO: Generate column names and keys in outside module
            if id == "#mod-list":
                table.add_column("Mod Name", width=35, key="name")
            else:
                table.add_column("Save Name", width=35, key="name")
            table.add_column("Modified", key="modified")
            table.add_column("Assets", key="total_assets")
            table.add_column("Missing", key="total_missing")
            table.add_column("Filename", key="filename")

            if id == "#mod-list":
                self.mod_list = ModList.ModList(self.mod_dir)
                self.mods = self.mod_list.get_mods()
                mods = self.mods
            else:
                self.save_list = ModList.ModList(self.save_dir, is_save=True)
                self.saves = self.save_list.get_mods()
                mods = self.saves
            for i, mod in enumerate(mods):
                table.add_row(
                    mod["name"].ljust(35),
                    format_time(mod["mtime"]),
                    mod["total_assets"],
                    mod["missing_assets"],
                    mod["filename"],
                    key=i,
                )
            table.cursor_type = "row"
            table.sort("name", reverse=self.sort_order["name"])
            self.last_sort_key = "name"

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

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "asset-list":
            return
        if event.data_table.id == "mod-list":
            mod_filename = self.mods[event.row_key.value]["filename"]
            mod_name = self.mods[event.row_key.value]["name"]
            mod_dir = self.mod_dir
        else:
            mod_filename = self.saves[event.row_key.value]["filename"]
            mod_name = self.saves[event.row_key.value]["name"]
            mod_dir = self.save_dir
        self.post_message(self.ModSelected(mod_filename, mod_name, mod_dir))

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
