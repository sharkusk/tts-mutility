import time
from importlib.metadata import version, PackageNotFoundError

from textual.app import App, ComposeResult
from textual.widgets import Header
from textual.message import Message
from textual.widgets import Static, LoadingIndicator

from ttsmutility.screens.AssetDetailScreen import AssetDetailScreen
from ttsmutility.screens.AssetListScreen import AssetListScreen
from ttsmutility.screens.ModListScreen import ModListScreen
from ttsmutility.screens.Sha1ScanScreen import Sha1ScanScreen
from ttsmutility.screens.AssetDownloadScreen import AssetDownloadScreen

from ttsmutility.parse import ModList
from ttsmutility.parse import AssetList

from ttsmutility import FIRST_PASS

MOD_DIR = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Tabletop Simulator\\Tabletop Simulator_Data\\Mods"
SAVE_DIR = "C:\\Users\\shark\\OneDrive\\Documents\\My Games\\Tabletop Simulator"


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
        # self.full_initialization()

        self.post_message(self.InitProcessing(f"Scanning Mod Directory"))
        mod_asset_list = AssetList.AssetList(MOD_DIR, SAVE_DIR)
        mod_asset_list.scan_mod_dir()

        self.post_message(self.InitProcessing(f"Init complete. Loading UI."))
        time.sleep(0.1)
        self.post_message(self.InitComplete())

    def refresh_mods(self, init=False):
        mod_list = ModList.ModList(MOD_DIR)
        results = mod_list.get_mods_needing_asset_refresh()

        for i, mod_filename in enumerate(results):
            if init and i % 5:
                self.post_message(
                    self.InitProcessing(
                        f"Calculating asset counts ({i/len(results):.0%})"
                    )
                )
            missing_assets = mod_list.count_missing_assets(mod_filename)
            total_assets = mod_list.count_total_assets(mod_filename)
            mod_size = mod_list.calc_asset_size(mod_filename)

            if self.is_screen_installed("mod_list"):
                screen = self.get_screen("mod_list")
                screen.update_counts(
                    mod_filename, total_assets, missing_assets, mod_size
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
        # This gives error due to sqlite cursor being from wrong thread
        self.refresh_mods()
