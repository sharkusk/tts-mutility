import time
from pathlib import Path

from importlib.metadata import version, PackageNotFoundError

from textual.app import App, ComposeResult
from textual.widgets import Header
from textual.message import Message
from textual.widgets import Static, LoadingIndicator, Markdown

from .screens.AssetDetailScreen import AssetDetailScreen
from .screens.AssetListScreen import AssetListScreen
from .screens.ModListScreen import ModListScreen
from .screens.Sha1ScanScreen import Sha1ScanScreen
from .screens.AssetDownloadScreen import AssetDownloadScreen

from .parse import ModList
from .parse import AssetList
from .data import load_config, save_config

from . import create_new_db


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
        config = load_config()

        # Update config file in case some settings have been added
        save_config(config)

        # Wait for DB to be created on first pass
        if not Path(config.db_path).exists():
            self.post_message(self.InitProcessing(f"Creating Database"))
            create_new_db(config.db_path)
            time.sleep(0.5)

        self.post_message(self.InitProcessing(f"Loading Workshop Mods"))
        mod_list = ModList.ModList(config.tts_mods_dir, config.tts_saves_dir)
        mods = mod_list.get_mods()

        mod_asset_list = AssetList.AssetList(config.tts_mods_dir, config.tts_saves_dir)

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
        config = load_config()
        mod_list = ModList.ModList(config.tts_mods_dir, config.tts_saves_dir)
        mod_asset_list = AssetList.AssetList(config.tts_mods_dir, config.tts_saves_dir)

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
        config = load_config()
        self.install_screen(
            ModListScreen(config.tts_mods_dir, config.tts_saves_dir), name="mod_list"
        )
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
