from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, DataTable
from textual.message import Message
from textual.containers import Horizontal
from textual.widgets import TabbedContent, TabPane, Static, LoadingIndicator, MarkdownViewer
from textual.screen import Screen, ModalScreen
from textual.reactive import reactive

from ttsmutility.parse import modlist
from ttsmutility.parse import assetlist

from ttsmutility import FIRST_PASS

import time

MOD_DIR = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Tabletop Simulator\\Tabletop Simulator_Data\\Mods"
SAVE_DIR = "C:\\Users\\shark\\OneDrive\\Documents\\My Games\\Tabletop Simulator"

ASSET_DETAIL_MD = """
URL
---
{url}

Filename
--------
{filename}

Modified Time
-------------
{mtime}

SHA1
----
{sha1}

JSON Trail
----------
{trail}
"""

def format_time(mtime: float) -> str:
    if mtime == 0:
        return "File not found."
    else:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))

class AssetDetailScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "OK")]

    def __init__(self, asset_detail: dict) -> None:
        self.asset_detail = asset_detail
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Static(id="asset_detail")
    
    def on_mount(self) -> None:
        static = next(self.query("#asset_detail").results(Static))
        static.update(ASSET_DETAIL_MD.format(
            url=self.asset_detail['url'],
            filename=self.asset_detail['asset_filename'],
            trail=self.asset_detail['trail'],
            sha1=self.asset_detail['sha1'],
            mtime=self.asset_detail['mtime'],
            ))

class AssetListScreen(Screen):

    BINDINGS = [("escape", "app.pop_screen", "OK")]

    class AssetSelected(Message):
        def __init__(self, asset_detail: dict) -> None:
            self.asset_detail = asset_detail
            super().__init__()
    
    def __init__(self, mod_filename: str, mod_name: str, mod_dir: str) -> None:
        self.mod_dir = mod_dir
        self.mod_name = mod_name
        self.mod_filename = mod_filename
        super().__init__()

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
            "mtime": False,
            }
        self.last_sort_key = 'url'
        self.asset_list = assetlist.AssetList(self.mod_dir)

        table = next(self.query('#asset-list').results(DataTable))
        table.focus()

        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order['url'])
    
        static = next(self.query("#mod_name").results(Static))
        static.update(self.mod_name)

        #TODO: Add columns universally to allow columns to not be cleared
        table.clear(columns=True)
        table.focus()

        # TODO: Generate column names and keys in outside module
        table.add_column("URL", width=40, key="url")
        table.add_column("Modified", key="mtime")
        table.add_column("Trail", width=40, key="trail")
        table.add_column("Filepath", width=40, key="filename")
        table.add_column("SHA1", width=40, key="sha1")

        self.assets = self.asset_list.parse_assets(self.mod_filename)

        for i, asset in enumerate(self.assets):
            table.add_row(
                self.asset_list.url_reformat(asset['url']),
                format_time(asset['mtime']),
                self.asset_list.trail_reformat(asset['trail']),
                asset['asset_filename'],
                '..'+asset['sha1'][15:],
                key=i
                )
        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order['url'])
        self.last_sort_key = 'url'

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        asset_detail = {
            'url': self.assets[event.row_key.value]['url'],
            'asset_filename': self.assets[event.row_key.value]['asset_filename'],
            'trail': self.assets[event.row_key.value]['trail'],
            'sha1': self.assets[event.row_key.value]['sha1'],
            'mtime': self.assets[event.row_key.value]['mtime'],
        }
        self.post_message(self.AssetSelected(asset_detail))
    
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if self.last_sort_key == event.column_key.value:
            self.sort_order[event.column_key.value] = not self.sort_order[event.column_key.value]
        else:
            self.sort_order[event.column_key.value] = False

        reverse = self.sort_order[event.column_key.value]
        self.last_sort_key = event.column_key.value

        event.data_table.sort(event.column_key, reverse=reverse)
    
    def init_db(self, filename):
        pass
    
class ModListScreen(Screen):

    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with TabbedContent(initial='workshop'):
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
                self.mod_list = modlist.ModList(self.mod_dir)
                self.mods = self.mod_list.get_mods()
                mods = self.mods
            else:
                self.save_list = modlist.ModList(self.save_dir, is_save=True)
                self.saves = self.save_list.get_mods()
                mods = self.saves
            for i, mod in enumerate(mods):
                table.add_row(
                    mod['name'].ljust(35),
                    format_time(mod['mtime']),
                    mod['total_assets'],
                    mod['missing_assets'],
                    mod['filename'],
                    key=i)
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
            mod_dir = MOD_DIR
        else:
            mod_filename = self.saves[event.row_key.value]['filename']
            mod_name = self.saves[event.row_key.value]['name']
            mod_dir = SAVE_DIR
        self.post_message(self.ModSelected(mod_filename, mod_name, mod_dir))
    
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if self.last_sort_key == event.column_key.value:
            self.sort_order[event.column_key.value] = not self.sort_order[event.column_key.value]
        else:
            self.sort_order[event.column_key.value] = False

        reverse = self.sort_order[event.column_key.value]
        self.last_sort_key = event.column_key.value

        event.data_table.sort(event.column_key, reverse=reverse)

class TTSMutility(App):

    CSS_PATH = "ttsmutility.css"

    class InitComplete(Message):
        def __init__(self) -> None:
            super().__init__()

    class InitProcessing(Message):
        def __init__(self, status: str) -> None:
            self.status = status
            super().__init__()
        
    def compose(self) -> ComposeResult:
        yield Header()
        yield LoadingIndicator(id="loading")
        yield Static(id="status")
        self.run_worker(self.initialize_database)

    def initialize_database(self) -> None:
        # Wait for DB to be created on first pass
        if FIRST_PASS:
            self.post_message(self.InitProcessing(f"Creating Database"))
            time.sleep(2)
        self.post_message(self.InitProcessing(f"Loading Workshop Mods"))
        mod_list = modlist.ModList(MOD_DIR)
        mods = mod_list.get_mods()
        self.post_message(self.InitProcessing(f"Loading Save Mods"))
        save_list = modlist.ModList(SAVE_DIR)
        saves = save_list.get_mods()

        mod_asset_list = assetlist.AssetList(MOD_DIR)
        save_asset_list = assetlist.AssetList(SAVE_DIR)

        for i, mod in enumerate(mods):
            mod_filename = mod['filename']
            self.post_message(self.InitProcessing(f"Finding assets in {mod_filename} ({i}/{len(mods)})"))
            mod_asset_list.parse_assets(mod_filename, parse_only=True)
        for mod in saves:
            mod_filename = mod['filename']
            self.post_message(self.InitProcessing(f"Finding assets in {mod_filename} ({i}/{len(mods)})"))
            save_asset_list.parse_assets(mod_filename, parse_only=True)
        
        results = mod_list.get_mods_needing_asset_refresh()
        for i, mod_filename in enumerate(results):
            if i % 5:
                self.post_message(self.InitProcessing(f"Calculating asset counts ({i/len(results):.0%})"))
            mod_list.count_missing_assets(mod_filename)
            mod_list.count_total_assets(mod_filename)

        self.post_message(self.InitProcessing(f"Init complete. Loading UI."))
        time.sleep(0.1)
        self.post_message(self.InitComplete())

    def on_ttsmutility_init_complete(self):
        self.push_screen(ModListScreen(MOD_DIR, SAVE_DIR))
    
    def on_ttsmutility_init_processing(self, event: InitProcessing):
        static = next(self.query("#status").results(Static))
        static.update(event.status)

    def on_mod_list_screen_mod_selected(self, event: ModListScreen.ModSelected):
        self.push_screen(AssetListScreen(event.mod_filename, event.mod_name, event.mod_dir))

    def on_asset_list_screen_asset_selected(self, event: AssetListScreen.AssetSelected):
        self.push_screen(AssetDetailScreen(event.asset_detail))