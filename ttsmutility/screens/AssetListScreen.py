import asyncio
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import DataTable, Header, Label

from ..data.config import load_config
from ..dialogs.InfoDialog import InfoDialog
from ..parse.AssetList import AssetList
from ..utility.util import MyText, format_time, make_safe_filename


class AllAssetScreen(Screen):
    def __init__(self, filename, mod_name):
        super().__init__()
        self.filename = filename
        self.mod_name = mod_name

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(
            f"{self.mod_name} - All Nodes - Press ESC to Exit",
            id="title",
            classes="aa_label",
        )
        yield AssetListScreen(self.filename, self.mod_name, all_nodes=True)


class AssetListScreen(Widget):
    BINDINGS = [
        ("d", "download_asset", "Download Asset"),
        ("r", "missing_report", "Missing Report"),
        ("i", "ignore_missing", "Ignore Missing"),
        ("a", "all_nodes", "Show All Nodes"),
    ]

    class AssetSelected(Message):
        def __init__(self, url: str, mod_filename: str, trail: str = "") -> None:
            self.url = url
            self.mod_filename = mod_filename
            self.trail = trail
            super().__init__()

    class DownloadSelected(Message):
        def __init__(self, assets: list) -> None:
            self.assets = assets
            super().__init__()

    class UpdateCounts(Message):
        def __init__(self, mod_filename) -> None:
            self.mod_filename = mod_filename
            super().__init__()

    def __init__(
        self, mod_filename: str, mod_name: str, al_id: str = "", all_nodes=False
    ) -> None:
        self.mod_filename = mod_filename
        self.mod_name = mod_name
        self.all_nodes = all_nodes
        self.current_row = 0
        self.url_width = 40
        if al_id == "":
            self.al_id = "asset-list"
        else:
            self.al_id = al_id

        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir

        self.updated_counts = False

        super().__init__()

    def compose(self) -> ComposeResult:
        yield DataTable(id=self.al_id)

    def on_mount(self) -> None:
        self.sort_order = {
            "url": False,
            "ext": False,
            "mtime": False,
            "trail": False,
            "fsize": False,
        }
        self.last_sort_key = "url"

        table = next(self.query("#" + self.al_id).results(DataTable))

        table.add_column("URL", width=self.url_width, key="url")
        table.add_column("Ext", key="ext")
        table.add_column("Content Name", key="name", width=25)
        table.add_column("Size(KB)", key="fsize", width=9)
        table.add_column("Modified", key="mtime", width=25)
        table.add_column("Trail", key="trail")

        self.load_data()

    def load_data(self):
        asset_list = AssetList()
        assets = asset_list.get_mod_assets(self.mod_filename, all_nodes=self.all_nodes)
        self.assets = {}

        table = next(self.query("#" + self.al_id).results(DataTable))

        for i, asset in enumerate(assets):
            if not self.all_nodes:
                trails = [asset["trail"]]
            else:
                trails = asset["trail"]

            readable_asset = self.format_asset(asset)

            for i, trail in enumerate(trails):
                if asset["url"] in self.assets and not self.all_nodes:
                    # When showing sha1 mismatches we can sometimes have multiple
                    # matches with the same URL being used by multiple mods.
                    # Ignore the dups as we only need a single match.
                    continue
                if self.all_nodes:
                    row_key = asset["url"] + f"#{i}"
                else:
                    row_key = asset["url"]
                self.assets[row_key] = asset
                table.add_row(
                    readable_asset["url"],
                    readable_asset["ext"],
                    readable_asset["content_name"],
                    readable_asset["fsize"],
                    readable_asset["mtime"],
                    self.trail_reformat(trail),
                    key=row_key,  # Use original url for our key
                )
        table.cursor_type = "row"
        table.sort("trail", reverse=self.sort_order["trail"])
        self.last_sort_key = "trail"

        if not self.all_nodes:
            self.check_for_matches()

    def format_long_entry(self, entry, width):
        if not entry or len(entry) < width:
            return entry

        seg_width = int(width / 2)
        return f"{entry[:seg_width-3]}..{entry[len(entry)-seg_width-1:]}"

    @work(exclusive=True)
    async def check_for_matches(self):
        asset_list = AssetList()
        table = next(self.query("#" + self.al_id).results(DataTable))
        for asset in self.assets.values():
            if asset["fsize"] == 0:
                if len(await asset_list.find_asset_a(asset["url"])) > 0:
                    asset["fsize"] = -1.0
                    table.update_cell(
                        asset["url"], "fsize", asset["fsize"], update_width=True
                    )

    def format_url(self, url: str) -> str:
        if url[-1] == "/":
            url_end = url[:-1].rsplit("/", 1)[-1]
        else:
            url_end = url.rsplit("/", 1)[-1]

        if len(url) < 19:
            start_length = len(url)
        else:
            start_length = 19

        if len(url_end) < 19:
            end_length = len(url_end)
        else:
            end_length = 19

        return f"{url[:start_length-1]}..{url_end[len(url_end)-end_length:]}"

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

        new_asset["fsize"] = new_asset["fsize"] / 1024
        new_asset["url"] = self.format_url(asset["url"])

        if asset["filename"] is None:
            new_asset["ext"] = None
        else:
            new_asset["ext"] = Path(asset["filename"]).suffix
        new_asset["url"] = self.format_long_entry(asset["url"], self.url_width)

        try:
            if asset["ignore_missing"]:
                new_asset["url"] = MyText(new_asset["url"], style="#00D000")
        except KeyError:
            pass

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
        table = next(self.query("#" + self.al_id).results(DataTable))
        col_keys = ["url", "mtime", "fsize", "trail", "ext", "name"]
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
        table.update_cell(
            row_key, col_keys[5], readable_asset["content_name"], update_width=False
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
        if event.row_key.value is not None:
            if self.all_nodes and "#" in event.row_key.value:
                url, i = event.row_key.value.split("#")
                trail = self.assets[event.row_key.value]["trail"][int(i)]
            else:
                url = event.row_key.value
                trail = ""
            self.post_message(self.AssetSelected(url, self.mod_filename, trail))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if event.column_key.value is not None:
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
        if self.all_nodes:
            return

        table = next(self.query("#" + self.al_id).results(DataTable))
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)

        assets = [
            self.assets[row_key],
        ]
        self.post_message(self.DownloadSelected(assets))
        self.updated_counts = True

    def action_missing_report(self):
        if self.all_nodes:
            return

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
                        (
                            f"{url}, "
                            f"({self.assets[url]['trail']}), "
                            f"{self.assets[url]['dl_status']}\n"
                        )
                    )

        self.app.push_screen(InfoDialog(f"Saved missing asset report to '{outname}'."))

    def action_ignore_missing(self):
        if self.all_nodes:
            return

        table = next(self.query("#" + self.al_id).results(DataTable))
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)

        asset_list = AssetList()
        self.assets[row_key]["ignore_missing"] = not self.assets[row_key][
            "ignore_missing"
        ]
        asset_list.set_ignore(
            self.mod_filename, row_key.value, self.assets[row_key]["ignore_missing"]
        )
        self.updated_counts = True
        self.update_asset(self.assets[row_key])

    def action_all_nodes(self):
        if self.all_nodes:
            return

        self.app.push_screen(AllAssetScreen(self.mod_filename, self.mod_name))
