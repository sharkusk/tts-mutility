from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Center
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from ..data.config import load_config
from ..dialogs.InfoDialog import InfoDialog
from ..parse.AssetList import AssetList
from ..parse.ModList import ModList
from ..parse.ModParser import INFECTION_URL
from ..utility.util import format_time, make_safe_filename


class AssetListScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("d", "download_asset", "Download Asset"),
        ("r", "missing_report", "Missing Report"),
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

    def __init__(self, mod_filename: str, mod_name: str) -> None:
        self.mod_filename = mod_filename
        self.mod_name = mod_name
        self.current_row = 0
        self.url_width = 40
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Label(id="title")
        yield Label(id="infection_warning")
        with Center(id="al_center"):
            yield DataTable(id="asset-list")

    def on_mount(self) -> None:
        self.sort_order = {
            "url": False,
            "ext": False,
            "mtime": False,
            "trail": False,
            "fsize": False,
        }
        self.last_sort_key = "url"

        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir

        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        if self.mod_name in infected_mods:
            iw = self.query_one("#infection_warning")
            iw.update(
                "WARNING!  A TTS viral infection has been detected in this mod.  Do not copy objects from this mod!"
            )
            iw.add_class("unhide")

        table = next(self.query("#asset-list").results(DataTable))
        table.focus()

        table.cursor_type = "row"
        table.sort("url", reverse=self.sort_order["url"])

        self.query_one("#title").update(self.mod_name)

        table.clear(columns=True)
        table.focus()

        table.add_column("URL", width=self.url_width, key="url")
        table.add_column("Ext", key="ext", width=4)
        table.add_column("Size(KB)", key="fsize", width=9)
        table.add_column("Modified", key="mtime", width=10)
        table.add_column("Trail", key="trail")

        assets = asset_list.get_mod_assets(self.mod_filename)
        self.assets = {}

        for i, asset in enumerate(assets):
            self.assets[asset["url"]] = asset
            readable_asset = self.format_asset(asset)
            table.add_row(
                readable_asset["url"],
                readable_asset["ext"],
                readable_asset["fsize"],
                readable_asset["mtime"],
                self.trail_reformat(readable_asset["trail"]),
                key=asset["url"],  # Use original url for our key
            )
        table.cursor_type = "row"
        table.sort("trail", reverse=self.sort_order["trail"])
        self.last_sort_key = "trail"

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
                readable_time = "*" + asset["dl_status"]
        else:
            readable_time = format_time(asset["mtime"])
        new_asset["mtime"] = readable_time

        readable_size = sizeof_fmt(asset["fsize"])
        new_asset["fsize"] = new_asset["fsize"] / 1024

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
            new_asset["ext"] = Path(asset["filename"]).suffix
        new_asset["url"] = self.format_long_entry(asset["url"], self.url_width)

        return new_asset

    def update_asset(
        self,
        asset,
    ) -> None:
        row_key = asset["url"]

        try:
            # We need to update both our internal asset information
            # and what is shown on the table...
            self.assets[row_key]["mtime"] = asset["mtime"]
            self.assets[row_key]["fsize"] = asset["fsize"]
            self.assets[row_key]["content_name"] = asset["content_name"]
            self.assets[row_key]["filename"] = asset["filename"]
            self.assets[row_key]["dl_status"] = asset["dl_status"]
        except KeyError:
            # This happens if the download process finishes and updates
            # assets for a mod that is not currently loaded
            return

        readable_asset = self.format_asset(asset)
        table = next(self.query("#asset-list").results(DataTable))
        col_keys = ["url", "mtime", "fsize", "trail", "ext"]
        table.update_cell(
            row_key, col_keys[0], readable_asset["url"], update_width=True
        )
        table.update_cell(
            row_key, col_keys[1], readable_asset["mtime"], update_width=True
        )
        table.update_cell(
            row_key, col_keys[2], readable_asset["fsize"], update_width=True
        )
        # Skip Trail....  It doesn't change anyhow.
        table.update_cell(
            row_key, col_keys[4], readable_asset["ext"], update_width=True
        )

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
            filepath = Path(self.mod_dir) / self.assets[event.row_key.value]["filename"]
        else:
            filepath = ""

        asset_detail = self.assets[event.row_key.value].copy()
        asset_detail["uri"] = Path(filepath).as_uri() if filepath != "" else ""
        asset_detail["filepath"] = Path(filepath) if filepath != "" else ""
        asset_detail["mod_name"] = self.mod_name

        if "Workshop" in self.mod_filename:
            asset_detail["mod_path"] = Path(self.mod_dir) / self.mod_filename
        else:
            asset_detail["mod_path"] = Path(self.save_dir) / self.mod_filename

        asset_list = AssetList()
        other_mods = asset_list.get_mods_using_asset(asset_detail["url"])
        asset_detail["other_mods"] = sorted(other_mods)
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

    def action_missing_report(self):
        config = load_config()

        outname = (
            Path(config.mod_backup_dir) / make_safe_filename(self.mod_name)
        ).with_suffix(".missing.csv")
        with open(outname, "w", encoding="utf-8") as f:
            for url in self.assets:
                if (
                    self.assets[url]["dl_status"] != ""
                    or self.assets[url]["fsize"] == 0
                ):
                    f.write(
                        f"{url}, {self.assets[url]['dl_status']}, ({self.assets[url]['trail']})\n"
                    )

        self.app.push_screen(InfoDialog(f"Saved missing asset report to '{outname}'."))
