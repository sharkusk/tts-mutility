from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Footer, Header, DataTable
from textual.containers import Horizontal, VerticalScroll, HorizontalScroll
from textual.widgets import Button, ContentSwitcher, Markdown

from ttsmutility.parse import modlist


MARKDOWN_EXAMPLE = """
## {mod_name}
"""

class TTSMutility(App):

    CSS_PATH = "ttsmutility.css"

    def compose(self) -> ComposeResult:
        #yield Header()

        with Horizontal(id="buttons"):
            yield Button("DataTable", id="mod-list")
            yield Button("Markdown", id="files")
        
        with ContentSwitcher(initial="mod-list"):
            yield DataTable(id="mod-list")
            with VerticalScroll(id="files"):
                yield Markdown(MARKDOWN_EXAMPLE.format(mod_name="Hello"))

        #yield Footer()
    

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.query_one(ContentSwitcher).current = event.button.id

    def on_mount(self) -> None:
        mod_dir = "C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop"
        table = self.query_one(DataTable)
        table.focus()

        # TODO: Generate column names and keys in outside module
        table.add_column("Mod Name", width=35, key="name")
        table.add_column("Modified", key="modified")
        table.add_column("Assets", key="total_assets")
        table.add_column("Missing", key="total_missing")
        table.add_column("Filename", key="filename")

        self.sort_order = {
            "name": False,
            "modified": False,
            "total_assets": False,
            "total_missing": False,
            "filename": False,
            }

        self.mod_list = modlist.ModList(mod_dir)
        self.mods = self.mod_list.get_mods()
        for i, mod in enumerate(self.mods):
            table.add_row(mod['name'].ljust(35), str(mod['modification_time']), '0', '0', mod['filename'], key=i)
        table.cursor_type = "row"
        table.sort("name", reverse=self.sort_order['name'])
        self.last_sort_key = 'name'
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        #table = event.data_table
        #mod_name = table.get_cell(*table.coordinate_to_cell_key((event.cursor_row, 0))).strip()
        mod_name = self.mods[event.row_key.value]['name']
        self.query_one(ContentSwitcher).current = "files"
        self.query_one(Markdown).update(MARKDOWN_EXAMPLE.format(mod_name=mod_name))
    
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if self.last_sort_key == event.column_key.value:
            self.sort_order[event.column_key.value] = not self.sort_order[event.column_key.value]
        else:
            self.sort_order[event.column_key.value] = False

        reverse = self.sort_order[event.column_key.value]
        self.last_sort_key = event.column_key.value

        event.data_table.sort(event.column_key, reverse=reverse)