from textual.app import ComposeResult
from textual.screen import Screen
from textual.message import Message
from textual.widgets import Footer, Header, DataTable
from textual.widgets import Static

from ttsmutility.parse import AssetList
from ttsmutility.util import format_time
from ttsmutility.fetch.AssetDownload import download_files

import os.path
import pathlib


class AssetListScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("d", "download_asset", "Download Asset"),
    ]

    class AssetSelected(Message):
        def __init__(self, asset_detail: dict) -> None:
            self.asset_detail = asset_detail
            super().__init__()

    class DownloadSelected(Message):
        def __init__(self, mod_dir: str, assets: list) -> None:
            self.mod_dir = mod_dir
            self.assets = assets
            super().__init__()

    def __init__(self, mod_filename: str, mod_name: str, mod_dir: str) -> None:
        self.mod_dir = mod_dir
        self.mod_name = mod_name
        self.mod_filename = mod_filename
        self.current_row = 0
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
        self.last_sort_key = "url"
        asset_list = AssetList.AssetList(self.mod_dir)

        table = next(self.query("#asset-list").results(DataTable))
        table.focus()

        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order["url"])

        static = next(self.query("#mod_name").results(Static))
        static.update(self.mod_name)

        table.clear(columns=True)
        table.focus()

        table.add_column("URL", width=40, key="url")
        table.add_column("Modified", key="mtime")
        table.add_column("Trail", width=40, key="trail")
        table.add_column("Filepath", width=40, key="filename")
        table.add_column("SHA1", width=40, key="sha1")

        self.assets = asset_list.parse_assets(self.mod_filename)

        for i, asset in enumerate(self.assets):
            if asset["mtime"] == 0:
                readable_time = "* " + asset["dl_status"]
            else:
                readable_time = format_time(asset["mtime"])
            table.add_row(
                asset_list.url_reformat(asset["url"]),
                readable_time,
                asset_list.trail_reformat(asset["trail"]),
                asset["asset_filename"],
                ".." + asset["sha1"][15:],
                key=i,
            )
        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order["url"])
        self.last_sort_key = "url"

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        filepath = os.path.join(
            self.mod_dir, self.assets[event.row_key.value]["asset_filename"]
        )

        asset_detail = {
            "url": self.assets[event.row_key.value]["url"],
            "filename": self.assets[event.row_key.value]["asset_filename"],
            "uri": pathlib.Path(filepath).as_uri(),
            "trail": self.assets[event.row_key.value]["trail"],
            "sha1": self.assets[event.row_key.value]["sha1"],
            "mtime": self.assets[event.row_key.value]["mtime"],
            "dl_status": self.assets[event.row_key.value]["dl_status"],
        }
        self.post_message(self.AssetSelected(asset_detail))

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

    def action_download_asset(self):
        table = next(self.query("#asset-list").results(DataTable))
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        assets = [
            self.assets[row_key.value],
        ]
        self.post_message(self.DownloadSelected(self.mod_dir, assets))
