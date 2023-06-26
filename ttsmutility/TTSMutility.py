import time
import platform
import os
import sys
from pathlib import Path

from importlib.metadata import version, PackageNotFoundError

from textual.app import App, ComposeResult
from textual.widgets import Header
from textual.message import Message
from textual.widgets import Static, LoadingIndicator, Markdown

from ttsmutility.screens.AssetDetailScreen import AssetDetailScreen
from ttsmutility.screens.AssetListScreen import AssetListScreen
from ttsmutility.screens.ModListScreen import ModListScreen
from ttsmutility.screens.Sha1ScanScreen import Sha1ScanScreen
from ttsmutility.screens.AssetDownloadScreen import AssetDownloadScreen

from ttsmutility.parse import ModList
from ttsmutility.parse import AssetList

from ttsmutility import FIRST_PASS

gamedata_map = {
    "Windows": "~/Documents/My Games/Tabletop Simulator",
    "Darwin": "~/Library/Tabletop Simulator",  # MacOS
    "Linux": "~/.local/share/Tabletop Simulator",
}
try:
    active_platform = platform.system()
    GAMEDATA_DEFAULT = os.path.expanduser(gamedata_map[active_platform])
except KeyError:
    GAMEDATA_DEFAULT = os.path.expanduser(gamedata_map["Windows"])

# If the mod location is somewhere other than the default location we can
# provide the path to the new location through a simple one-line test file
mod_link_path = Path(GAMEDATA_DEFAULT, "mod_location.txt")
if not os.path.exists(Path(GAMEDATA_DEFAULT, "Mods") or os.path.exists(mod_link_path)):
    print(f"Reading default gamedata directory information from: {mod_link_path}")
    if os.path.exists(mod_link_path):
        with open(Path(GAMEDATA_DEFAULT, "mod_location.txt")) as f:
            GAMEDATA_DEFAULT = f.readline().strip()
        print(f"Default gamedata directory = {GAMEDATA_DEFAULT}")
    else:
        print(
            f"Warning: default gamedata directory not detected, must specify at command line!"
        )
        sys.exit(1)

MOD_DIR = os.path.join(GAMEDATA_DEFAULT, "Mods")
SAVE_DIR = GAMEDATA_DEFAULT


class TTSMutility(App):
    CSS_PATH = "ttsmutility.css"

    try:
        __version__ = version("ttsmutility")
        SUB_TITLE = __version__
    except PackageNotFoundError:
        # package is not installed
        pass

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
            time.sleep(1)

        self.post_message(self.InitProcessing(f"Loading Workshop Mods"))
        mod_list = ModList.ModList(MOD_DIR, SAVE_DIR)
        mods = mod_list.get_mods()

        mod_asset_list = AssetList.AssetList(MOD_DIR, SAVE_DIR)

        self.post_message(self.InitProcessing(f"Scanning Cached Assets"))
        mod_asset_list.scan_cached_assets()

        mods = mod_list.get_mods_needing_asset_refresh()
        for i, mod_filename in enumerate(mods):
            self.post_message(
                self.InitProcessing(
                    f"Finding assets in {mod_filename} ({i}/{len(mods)})"
                )
            )
            mod_asset_list.get_mod_assets(mod_filename, parse_only=True)
            mod_list.update_mod_counts(mod_filename)

        self.post_message(self.InitProcessing(f"Init complete. Loading UI."))
        self.post_message(self.InitComplete())

    def refresh_mods(self) -> None:
        mod_list = ModList.ModList(MOD_DIR, SAVE_DIR)
        mod_asset_list = AssetList.AssetList(MOD_DIR, SAVE_DIR)

        mods = mod_list.get_mods_needing_asset_refresh()
        for i, mod_filename in enumerate(mods):
            mod_asset_list.get_mod_assets(mod_filename, parse_only=True)
            counts = mod_list.update_mod_counts(mod_filename)

            if self.is_screen_installed("mod_list"):
                screen = self.get_screen("mod_list")
                screen.update_counts(
                    mod_filename, counts["total"], counts["missing"], counts["size"]
                )

    def on_ttsmutility_init_complete(self):
        self.install_screen(ModListScreen(MOD_DIR, SAVE_DIR), name="mod_list")
        self.push_screen("mod_list")

    def on_ttsmutility_init_processing(self, event: InitProcessing):
        static = next(self.query("#status").results(Static))
        static.update(event.status)

    def on_mod_list_screen_mod_selected(self, event: ModListScreen.ModSelected):
        if self.is_screen_installed("asset_list"):
            self.uninstall_screen("asset_list")
        self.install_screen(
            AssetListScreen(
                event.mod_filename, event.mod_name, event.mod_dir, event.save_dir
            ),
            name="asset_list",
        )
        self.push_screen("asset_list")

    def on_mod_list_screen_download_selected(
        self, event: ModListScreen.DownloadSelected
    ):
        self.push_screen(
            AssetDownloadScreen(event.mod_dir, event.save_dir, event.mod_filename)
        )

    def on_asset_list_screen_asset_selected(self, event: AssetListScreen.AssetSelected):
        self.push_screen(AssetDetailScreen(event.asset_detail))

    def on_asset_list_screen_download_selected(
        self, event: AssetListScreen.DownloadSelected
    ):
        self.push_screen(
            AssetDownloadScreen(event.mod_dir, event.save_dir, event.assets)
        )

    def on_mod_list_screen_sha1selected(self, event: ModListScreen.Sha1Selected):
        self.push_screen(Sha1ScanScreen(event.mod_dir, event.save_dir))

    def on_asset_download_screen_file_download_complete(
        self, event: AssetDownloadScreen.FileDownloadComplete
    ):
        if self.is_screen_installed("asset_list"):
            screen = self.get_screen("asset_list")
            screen.update_asset(event.asset)

    def on_asset_download_screen_download_complete(self):
        self.refresh_mods()
