from textual.app import ComposeResult
from textual.screen import Screen
from textual.message import Message
from textual.widgets import Footer, Header, DataTable
from textual.widgets import Static

from ttsmutility.parse import AssetList
from ttsmutility.util import format_time
from ttsmutility.fetch.AssetDownload import download_files
from ttsmutility.screens.AssetDownloadScreen import AssetDownloadScreen
from ttsmutility.screens.AssetDetailScreen import AssetDetailScreen

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
        def __init__(self, mod_dir: str, save_dir: str, assets: list) -> None:
            self.mod_dir = mod_dir
            self.save_dir = save_dir
            self.assets = assets
            super().__init__()

    def __init__(
        self, mod_filename: str, mod_name: str, mod_dir: str, save_dir: str
    ) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir
        self.mod_name = mod_name
        self.mod_filename = mod_filename
        self.current_row = 0
        self.url_width = 40
        self.filepath_width = 40
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="mod_name")
        yield DataTable(id="asset-list")
        yield Footer()

    def on_mount(self) -> None:
        self.sort_order = {
            "url": False,
            "ext": False,
            "trail": False,
            "sha1": False,
            "filename": False,
            "mtime": False,
            "fsize": False,
        }
        self.last_sort_key = "url"
        asset_list = AssetList.AssetList(self.mod_dir, self.save_dir)

        table = next(self.query("#asset-list").results(DataTable))
        table.focus()

        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order["url"])

        static = next(self.query("#mod_name").results(Static))
        static.update(self.mod_name)

        table.clear(columns=True)
        table.focus()

        table.add_column("URL", width=self.url_width, key="url")
        table.add_column("Extension", key="ext")
        table.add_column("Size", key="fsize")
        table.add_column("Trail", key="trail")
        table.add_column("Modified", key="mtime")
        table.add_column("Filepath", width=self.filepath_width, key="filename")
        table.add_column("SHA1", key="sha1")

        assets = asset_list.parse_assets(self.mod_filename)
        self.assets = {}

        for i, asset in enumerate(assets):
            self.assets[asset["url"]] = asset
            readable_asset = self.format_asset(asset)
            table.add_row(
                readable_asset["url"],
                readable_asset["ext"],
                readable_asset["fsize"],
                self.trail_reformat(readable_asset["trail"]),
                readable_asset["mtime"],
                readable_asset["filename"],
                readable_asset["sha1"],
                key=asset["url"],  # Use original url for our key
            )
        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order["url"])
        self.last_sort_key = "url"

    def format_long_entry(self, entry, width):
        if not entry or len(entry) < width:
            return entry

        seg_width = int(width / 2)
        return f"{entry[:seg_width-3]}..{entry[len(entry)-seg_width-1:]}"

    def format_asset(self, asset: dict) -> dict:
        def sizeof_fmt(num, suffix="B"):
            if num == 0:
                return ""
            for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
                if abs(num) < 1024.0:
                    return f"{num:3.1f} {unit}{suffix}"
                num /= 1024.0
            return f"{num:.1f} Yi{suffix}"

        new_asset = asset.copy()
        if asset["mtime"] == 0:
            if asset["dl_status"] == "":
                readable_time = "Not Found"
            else:
                readable_time = "* " + asset["dl_status"]
        else:
            readable_time = format_time(asset["mtime"])
        new_asset["mtime"] = readable_time

        readable_size = sizeof_fmt(asset["fsize"])
        new_asset["fsize"] = readable_size

        if asset["url"][-1] == "/":
            url_end = asset["url"][:-1].rsplit("/", 1)[-1]
        else:
            url_end = asset["url"].rsplit("/", 1)[-1]

        if len(asset["url"]) < 19:
            start_length = len(asset["url"])
        else:
            start_length = 19

        if len(url_end) < 19:
            end_length = len(url_end)
        else:
            end_length = 19

        new_asset[
            "url"
        ] = f"{asset['url'][:start_length-1]}..{url_end[len(url_end)-end_length:]}"
        if asset["filename"] is None:
            new_asset["ext"] = None
        else:
            new_asset["ext"] = os.path.splitext(asset["filename"])[1]
        new_asset["url"] = self.format_long_entry(asset["url"], self.url_width)
        new_asset["filename"] = self.format_long_entry(
            asset["filename"], self.filepath_width
        )

        return new_asset

    def update_asset(
        self,
        asset,
    ) -> None:
        row_key = asset["url"]

        # We need to update both our internal asset information
        # and what is shown on the table...
        self.assets[row_key]["mtime"] = asset["mtime"]
        self.assets[row_key]["fsize"] = asset["fsize"]
        self.assets[row_key]["filename"] = asset["filename"]
        self.assets[row_key]["sha1"] = asset["sha1"]

        readable_asset = self.format_asset(asset)
        table = next(self.query("#asset-list").results(DataTable))
        col_keys = ["url", "mtime", "fsize", "trail", "filename", "sha1", "ext"]
        table.update_cell(row_key, col_keys[0], readable_asset["url"])
        table.update_cell(row_key, col_keys[1], readable_asset["mtime"])
        table.update_cell(row_key, col_keys[2], readable_asset["fsize"])
        # Skip Trail....  It doesn't change anyhow.
        table.update_cell(row_key, col_keys[4], readable_asset["filename"])
        table.update_cell(row_key, col_keys[5], readable_asset["sha1"])
        table.update_cell(row_key, col_keys[6], readable_asset["ext"])

    def url_reformat(self, url):
        replacements = [
            ("http://", ""),
            ("https://", ""),
            ("cloud-3.steamusercontent.com/ugc", ".steamuser."),
            ("www.dropbox.com/s", ".dropbox."),
        ]
        for x, y in replacements:
            url = url.replace(x, y)
        return url

    def trail_reformat(self, trail):
        replacements = [
            ("ObjectStates", "O.S"),
            ("Custom", "C."),
            ("ContainedObjects", "Con.O"),
        ]
        for x, y in replacements:
            trail = trail.replace(x, y)
        return trail

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if self.assets[event.row_key.value]["filename"] is not None:
            filepath = os.path.join(
                self.mod_dir, self.assets[event.row_key.value]["filename"]
            )
        else:
            filepath = ""

        asset_detail = self.assets[event.row_key.value].copy()
        asset_detail["uri"] = pathlib.Path(filepath).as_uri() if filepath != "" else ""

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
            self.assets[row_key],
        ]
        self.post_message(self.DownloadSelected(self.mod_dir, self.save_dir, assets))
