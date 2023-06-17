from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, DataTable
from textual.containers import Horizontal
from textual.widgets import TabbedContent, TabPane, Static, Label
from textual.screen import Screen

from ttsmutility.parse import modlist
from ttsmutility.parse import assetlist

import time

MOD_DIR = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Tabletop Simulator\\Tabletop Simulator_Data\\Mods\\Workshop"
SAVE_DIR = "C:\\Users\\shark\\OneDrive\\Documents\\My Games\\Tabletop Simulator\\Saves"

SCREEN_PARAMETERS = {}

class AssetListScreen(Screen):

    BINDINGS = [("escape", "app.pop_screen", "OK")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="mod_name")
        yield DataTable(id="asset-list")
        yield Footer()

    def on_mount(self) -> None:
        self.sort_order = {
            "url": False,
            "trail": False,
            "sha1": False,
            "filename": False,
            }
        self.last_sort_key = 'url'
        self.asset_list = assetlist.AssetList(SCREEN_PARAMETERS["mod_dir"])

        table = next(self.query('#asset-list').results(DataTable))
        table.focus()

        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order['url'])
    
        #TODO: Better way than globals for sharing data across screens?
        self.mod_filename = SCREEN_PARAMETERS['mod_filename']
        self.mod_name = SCREEN_PARAMETERS['mod_name']

        static = next(self.query("#mod_name").results(Static))
        static.update(self.mod_name)

        #TODO: Add columns universally to allow columns to not be cleared
        table.clear(columns=True)
        table.focus()

        # TODO: Generate column names and keys in outside module
        table.add_column("URL", key="url")
        table.add_column("Trail", key="trail")
        table.add_column("SHA1", key="sha1")
        table.add_column("filename", key="filename")

        assets = self.asset_list.parse_assets(self.mod_filename)

        for i, asset in enumerate(assets):
            table.add_row(asset['url'], asset['trail'], asset['sha1'], asset['asset_filename'], key=i)
        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order['url'])
        self.last_sort_key = 'url'
    
class TTSMutility(App):

    CSS_PATH = "ttsmutility.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with TabbedContent(initial='workshop'):
            with TabPane("Workshop", id="workshop"):
                yield DataTable(id="mod-list")
            with TabPane("Saves", id="saves"):
                yield DataTable(id="save-list")
    
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
                self.mod_list = modlist.ModList(MOD_DIR)
                self.mods = self.mod_list.get_mods()
                mods = self.mods
            else:
                self.save_list = modlist.ModList(SAVE_DIR)
                self.saves = self.save_list.get_mods()
                mods = self.saves
            for i, mod in enumerate(mods):
                table.add_row(mod['name'].ljust(35), time.strftime("%Y-%m-%d %H:%M", time.localtime(mod['modification_time'])), mod['total_assets'], '0', mod['filename'], key=i)
            table.cursor_type = "row"
            table.sort("name", reverse=self.sort_order['name'])
            self.last_sort_key = 'name'

    def action_show_tab(self, tab: str) -> None:
        self.get_child_by_type(TabbedContent).active = tab
    
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tab.id == "workshop":
            id = "#mod-list"
        else:
            id = "#save-list"
        table = next(self.query(id).results(DataTable))
        table.focus()
        table.sort("name", reverse=self.sort_order['name'])
        self.last_sort_key = 'name'

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "asset-list":
            return
        if event.data_table.id == "mod-list":
            mod_filename = self.mods[event.row_key.value]['filename']
            mod_name = self.mods[event.row_key.value]['name']
            SCREEN_PARAMETERS['mod_dir'] = MOD_DIR
        else:
            mod_filename = self.saves[event.row_key.value]['filename']
            mod_name = self.saves[event.row_key.value]['name']
            SCREEN_PARAMETERS['mod_dir'] = SAVE_DIR
        SCREEN_PARAMETERS['mod_filename'] = mod_filename
        SCREEN_PARAMETERS['mod_name'] = mod_name
        self.push_screen(AssetListScreen())
    
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if self.last_sort_key == event.column_key.value:
            self.sort_order[event.column_key.value] = not self.sort_order[event.column_key.value]
        else:
            self.sort_order[event.column_key.value] = False

        reverse = self.sort_order[event.column_key.value]
        self.last_sort_key = event.column_key.value

        event.data_table.sort(event.column_key, reverse=reverse)