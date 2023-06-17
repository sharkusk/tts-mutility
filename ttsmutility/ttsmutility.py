from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Footer, Header, DataTable
from textual.containers import Horizontal, VerticalScroll, HorizontalScroll
from textual.widgets import Button, ContentSwitcher, Pretty

from ttsmutility.parse import modlist
from ttsmutility.parse import assetlist

import time


PRETTY_EXAMPLE = {"intro": "hello world"}

class TTSMutility(App):

    CSS_PATH = "ttsmutility.css"

    def compose(self) -> ComposeResult:
        #yield Header()

        with Horizontal(id="buttons"):
            yield Button("TTS Mods", id="mod-list")
            yield Button("Assets", id="assets-list")
        
        with ContentSwitcher(initial="mod-list"):
            yield DataTable(id="mod-list")
            yield DataTable(id="assets-list")

        #yield Footer()
    

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.query_one(ContentSwitcher).current = event.button.id
    
    def on_mount(self) -> None:
        mod_dir = "C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop"
        table = next(self.query('#mod-list').results(DataTable))
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
            "url": False,
            "trail": False,
            "sha1": False,
            "asset_filename": False,
            }

        self.asset_list = assetlist.AssetList(mod_dir)
        self.mod_list = modlist.ModList(mod_dir)
        self.mods = self.mod_list.get_mods()
        for i, mod in enumerate(self.mods):
            table.add_row(mod['name'].ljust(35), time.strftime("%Y-%m-%d %H:%M", time.localtime(mod['modification_time'])), mod['total_assets'], '0', mod['filename'], key=i)
        table.cursor_type = "row"
        table.sort("name", reverse=self.sort_order['name'])
        self.last_sort_key = 'name'
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "assets-list":
            return
        mod_filename = self.mods[event.row_key.value]['filename']
        self.query_one(ContentSwitcher).current = "assets-list"
        table = next(self.query('#assets-list').results(DataTable))
        button = next(self.query('#assets-list').results(Button))
        button.label = self.mods[event.row_key.value]['name']
        #TODO: Add columns universally to allow columns to not be cleared
        table.clear(columns=True)
        table.focus()

        # TODO: Generate column names and keys in outside module
        table.add_column("URL", key="url")
        table.add_column("Trail", key="trail")
        table.add_column("SHA1", key="sha1")
        table.add_column("filename", key="filename")

        self.sort_order = {
            "url": False,
            "trail": False,
            "sha1": False,
            "filename": False,
            }

        assets = self.asset_list.parse_assets(mod_filename)

        for i, asset in enumerate(assets):
            table.add_row(asset['url'], asset['trail'], asset['sha1'], asset['asset_filename'], key=i)
        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order['url'])
        self.last_sort_key = 'url'
    
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if self.last_sort_key == event.column_key.value:
            self.sort_order[event.column_key.value] = not self.sort_order[event.column_key.value]
        else:
            self.sort_order[event.column_key.value] = False

        reverse = self.sort_order[event.column_key.value]
        self.last_sort_key = event.column_key.value

        event.data_table.sort(event.column_key, reverse=reverse)