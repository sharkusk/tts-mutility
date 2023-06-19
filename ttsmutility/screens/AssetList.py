from textual.app import ComposeResult
from textual.screen import Screen
from textual.message import Message
from textual.widgets import Footer, Header, DataTable
from textual.widgets import Static

from ttsmutility.parse import AssetList
from ttsmutility.util import format_time

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
        self.asset_list = AssetList.AssetList(self.mod_dir)

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