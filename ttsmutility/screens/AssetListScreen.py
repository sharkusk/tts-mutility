from pathlib import Path

from textual import work
from textual.actions import SkipAction
from textual.app import ComposeResult
from textual.containers import Center, Container
from textual.coordinate import Coordinate
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Input
from textual.widgets.data_table import CellDoesNotExist, RowKey

from ttsmutility.widgets.ModExplorer import ModExplorer

from ..data.config import load_config
from ..dialogs.InfoDialog import InfoDialog
from ..parse.AssetList import AssetList
from ..parse.FileFinder import trailstring_to_trail
from ..utility.util import MyText, format_time, make_safe_filename, sizeof_fmt
from ..widgets.DataTableFilter import DataTableFilter


class AssetListScreen(Widget):
    BINDINGS = [
        ("/", "filter", "Filter"),
        ("d", "download_asset", "Download"),
        ("i", "ignore_missing", "Ignore"),
        ("a", "all_nodes", "Toggle All"),
        ("e", "explore", "Explore"),
        ("m", "missing_report", "Missing Report"),
    ]

    class AssetSelected(Message):
        def __init__(self, url: str, mod_filename: str, trail: str = "") -> None:
            self.url = url
            self.mod_filename = mod_filename
            self.trail = trail
            super().__init__()

    class DownloadSelected(Message):
        def __init__(self, mod_filename, assets: list) -> None:
            self.mod_filename = mod_filename
            self.assets = assets
            super().__init__()

    class UpdateCounts(Message):
        def __init__(self, mod_filename) -> None:
            self.mod_filename = mod_filename
            super().__init__()

    def __init__(
        self, mod_filename: str, mod_name: str, al_id: str = "al_screen"
    ) -> None:
        self.mod_filename = mod_filename
        self.mod_name = mod_name
        self.all_nodes = False
        self.current_row = 0
        self.url_width = 40
        self.al_id = al_id
        self.explore = False

        config = load_config()
        self.mod_dir = config.tts_mods_dir
        self.save_dir = config.tts_saves_dir

        self.filter = ""
        self.prev_filter = ""
        self.updated_counts = False

        super().__init__()

    def compose(self) -> ComposeResult:
        with Center(id="al_filter_center"):
            yield Input(
                placeholder="Loading. Please wait...",
                disabled=True,
                id="al_filter",
            )
        with Container(id="al_container"):
            yield DataTableFilter(id=self.al_id)

    def on_mount(self) -> None:
        self.sort_order = {
            "url": False,
            "ext": False,
            "name": False,
            "mtime": False,
            "trail": False,
            "size": False,
        }
        self.last_sort_key = "url"

        table = next(self.query("#" + self.al_id).results(DataTable))

        table.add_column("URL", width=self.url_width, key="url")
        table.add_column("Ext", key="ext")
        table.add_column("Content Name", key="name", width=25)
        table.add_column("Size", key="size", width=12)
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
                    readable_asset["size"],
                    readable_asset["mtime"],
                    self.trail_reformat(trail),
                    key=row_key,  # Use original url for our key
                )
        table.cursor_type = "row"
        table.sort("trail", reverse=self.sort_order["trail"])
        self.last_sort_key = "trail"

        f = self.query_one("#al_filter", expect_type=Input)
        f.placeholder = "Filter"
        f.disabled = False

        if not self.all_nodes:
            self.check_for_matches()

        table.focus()

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
            if asset["size"] == 0 and asset["dl_status"] != "":
                if await asset_list.find_asset_a(asset["url"], asset["trail"]):
                    asset["size"] = "-1.0 B"
                    try:
                        table.update_cell(
                            asset["url"], "size", asset["size"], update_width=True
                        )
                    except CellDoesNotExist:
                        # This can happen if the table cell is filtered at the moment
                        pass

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
        new_asset = asset.copy()
        if asset["mtime"] == 0:
            if asset["dl_status"] == "":
                readable_time = "Not Found"
            else:
                readable_time = "*" + asset["dl_status"]
        else:
            readable_time = format_time(asset["mtime"])
        new_asset["mtime"] = readable_time

        # Don't reformat our size if it's already been converted to readable form
        if type(new_asset["size"]) is int:
            new_asset["size"] = sizeof_fmt(new_asset["size"])
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

    def update_size(self, url, size):
        table = next(self.query("#" + self.al_id).results(DataTable))
        try:
            table.update_cell(url, "size", sizeof_fmt(size))
        except KeyError:
            pass

    def update_asset(
        self,
        asset,
    ) -> None:
        row_key = asset["url"]

        try:
            # We need to update both our internal asset information
            # and what is shown on the table...
            self.assets[row_key]["mtime"] = asset["mtime"]
            self.assets[row_key]["size"] = asset["size"]
            self.assets[row_key]["content_name"] = asset["content_name"]
            self.assets[row_key]["filename"] = asset["filename"]
            self.assets[row_key]["dl_status"] = asset["dl_status"]
        except KeyError:
            # This happens if the download process finishes and updates
            # assets for a mod that is not currently loaded
            return

        readable_asset = self.format_asset(asset)
        table = next(self.query("#" + self.al_id).results(DataTable))
        col_keys = ["url", "mtime", "size", "trail", "ext", "name"]
        table.update_cell(
            row_key, col_keys[0], readable_asset["url"], update_width=True
        )
        table.update_cell(
            row_key, col_keys[1], readable_asset["mtime"], update_width=True
        )
        table.update_cell(
            row_key, col_keys[2], readable_asset["size"], update_width=True
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

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if event.row_key.value is not None:
            if self.explore:
                self.app.call_after_refresh(self.action_explore)

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

        table.update_cell(row_key, "mtime", "Downloading", update_width=True)

        assets = [
            self.assets[row_key],
        ]
        self.post_message(self.DownloadSelected(self.mod_filename, assets))
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
                if self.assets[url]["dl_status"] != "" or self.assets[url]["size"] == 0:
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
        self.all_nodes = not self.all_nodes
        table = next(self.query("#" + self.al_id).results(DataTable))
        table.clear()
        self.load_data()

    def action_filter(self) -> None:
        f = self.query_one("#al_filter_center")
        if self.filter == "":
            f.toggle_class("unhide")
        if "unhide" in f.classes:
            self.query_one("#al_filter").focus()
        else:
            self.get_active_table().focus()

    def on_key(self, event: Key):
        fc = self.query_one("#al_filter_center")
        # Check if our filter window is open...
        if "unhide" in fc.classes:
            filter_open = True
        else:
            filter_open = False

        if event.key == "escape":
            if filter_open:
                f = self.query_one("#al_filter", expect_type=Input)
                if "focus-within" in fc.pseudo_classes:
                    fc.remove_class("unhide")
                    f.value = ""
                    table = self.get_active_table()
                    table.focus()
                else:
                    fc.remove_class("unhide")
                    # Focus is elsewhere, clear the filter
                    # alue and close the filter window
                    f.value = ""
                event.stop()

        elif event.key == "up":
            if filter_open and "focus-within" in fc.pseudo_classes:
                table = self.get_active_table()
                try:
                    table.action_cursor_up()
                except SkipAction:
                    pass

        elif event.key == "down":
            if filter_open and "focus-within" in fc.pseudo_classes:
                table = self.get_active_table()
                try:
                    table.action_cursor_down()
                except SkipAction:
                    pass

        elif event.key == "enter":
            table = self.get_active_table()
            if "focus-within" in fc.pseudo_classes:
                table.focus()
                event.stop()

        elif event.key == "tab" or event.key == "shift+tab":
            if filter_open:
                if "focus-within" in fc.pseudo_classes:
                    table = self.get_active_table()
                    table.focus()
                else:
                    f = self.query_one("#al_filter", expect_type=Input)
                    f.focus()
                event.stop()

    def on_input_changed(self, event: Input.Changed):
        self.filter = event.input.value
        self.update_filtered_rows()

    def update_filtered_rows(self) -> None:
        self.filter_timer = None

        row_key = self.get_current_row_key()

        table = self.get_active_table()
        if self.filter != self.prev_filter:
            table.filter(self.filter, "name", "trail", "url")

        table.sort(self.last_sort_key, reverse=self.sort_order[self.last_sort_key])

        # Now jump to the previously selected row
        if row_key != "":
            self.call_after_refresh(self.jump_to_row_key, row_key)

        self.prev_filter = self.filter

    def get_current_row_key(self) -> RowKey:
        table = self.get_active_table()
        if table.is_valid_coordinate(table.cursor_coordinate):
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        else:
            row_key = RowKey("")
        return row_key

    def jump_to_row_key(self, row_key):
        table = self.get_active_table()
        # TODO: Remove internal API calls once Textual #2876 is published
        row_index = table._row_locations.get(row_key)
        if row_index is not None and table.is_valid_row_index(row_index):
            table.cursor_coordinate = Coordinate(row_index, 0)
        else:
            table.cursor_coordinate = Coordinate(0, 0)

    def get_active_table(self) -> DataTable:
        return next(self.query("#" + self.al_id).results(DataTable))

    async def action_explore(self) -> None:
        row_key = self.get_current_row_key()

        if "Workshop" in self.mod_filename:
            mod_filepath = Path(self.mod_dir) / self.mod_filename
        else:
            mod_filepath = Path(self.save_dir) / self.mod_filename

        if self.all_nodes and "#" in row_key.value:
            i = row_key.value.split("#")[1]
            trail = self.assets[row_key.value]["trail"][int(i)]
        else:
            trail = self.assets[row_key.value]["trail"]

        try:
            me = self.query_one(ModExplorer)
            node = me.find_node(trailstring_to_trail(trail))
            me.jump_to_node(node)
        except NoMatches:
            container = self.query_one(Container)
            await container.mount(ModExplorer(mod_filepath, id="mod_explorer"))
            self.explore = True
