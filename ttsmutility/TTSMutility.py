import time
from argparse import ArgumentParser, Namespace
from pathlib import Path

from textual import __version__ as textual_version  # pylint: disable=no-name-in-module
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Center
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Header, LoadingIndicator, ProgressBar, Static
from textual.worker import Worker

from . import __version__
from .data import load_config, save_config
from .data.db import create_new_db, update_db_schema
from .parse import AssetList, ModList
from .screens.AssetDetailScreen import AssetDetailScreen
from .screens.AssetListScreen import AssetListScreen
from .screens.DebugScreen import DebugScreen
from .screens.ModDetailScreen import ModDetailScreen
from .screens.ModListScreen import ModListScreen
from .utility.advertising import APPLICATION_TITLE, PACKAGE_NAME
from .workers.downloader import Downloader
from .workers.sha1 import Sha1Scanner
from .workers.TTSWorker import TTSWorker


class TTSMutility(App):
    CSS_PATH = "ttsmutility.css"

    TITLE = APPLICATION_TITLE
    SUB_TITLE = __version__

    class InitComplete(Message):
        def __init__(self) -> None:
            super().__init__()

    class InitProcessing(Message):
        def __init__(self, status: str) -> None:
            self.status = status
            super().__init__()

    def __init__(self, cli_args: Namespace) -> None:
        super().__init__()
        self.args = cli_args
        self.last_status = ""
        self.progress_total = 100
        self.progress_advance = 0
        config = load_config()
        # Update config file in case some settings have been added
        save_config(config)
        self.max_mods = cli_args.max_mods
        self.start_time = time.time()
        self.ad = Downloader()
        self.sha1 = Sha1Scanner()

        if cli_args.overwrite_log:
            log_flags = "w"
        else:
            log_flags = "a"

        if cli_args.force_refresh:
            self.force_refresh = True
        else:
            self.force_refresh = False

        if cli_args.log:
            self.f_log = open(config.log_path, log_flags)
        else:
            self.f_log = None

        self.write_log(f"TTSMutility v{__version__}", prefix="\n# ")
        self.write_log(
            f"Started at {time.ctime(self.start_time)}", prefix="", suffix="\n\n"
        )

    def __del__(self):
        if self.f_log is not None:
            self.f_log.close()

    def compose(self) -> ComposeResult:
        config = load_config()
        yield Header()
        yield LoadingIndicator(id="loading")
        yield Static(id="status")
        self.run_worker(self.initialize_database)

    def write_log(self, output: str, prefix: str = "- ", suffix: str = "\n") -> None:
        if self.f_log is not None:
            if prefix == "":
                self.f_log.write(f"{output}{suffix}")
            else:
                self.f_log.write(
                    f"{prefix}{time.time() - self.start_time:.3f}: {output}{suffix}"
                )

    def initialize_database(self) -> None:
        config = load_config()

        self.write_log(f"## Init", prefix="")

        # Wait for DB to be created on first pass
        if not Path(config.db_path).exists():
            self.post_message(self.InitProcessing(f"Creating Database"))
            db_schema = create_new_db(config.db_path)
            self.write_log(f"Created DB with schema version {db_schema}.")
        else:
            db_schema = update_db_schema(config.db_path)
            self.write_log(f"Using DB schema version {db_schema}.")

        self.post_message(self.InitProcessing(f"Loading Workshop Mods"))
        mod_list = ModList.ModList(max_mods=self.max_mods)
        mod_list.get_mods(parse_only=True)
        self.write_log(f"Loaded Mods.")

        mod_asset_list = AssetList.AssetList()

        self.post_message(self.InitProcessing(f"Scanning Cached Assets"))
        num_assets = mod_asset_list.scan_cached_assets()
        self.write_log(f"Found {num_assets} new assets.")

        if self.force_refresh:
            mods = mod_list.get_all_mod_filenames()
        else:
            mods = mod_list.get_mods_needing_asset_refresh()

        self.write_log(f"Refreshing {len(mods)} Mods.")
        for i, mod_filename in enumerate(mods):
            self.post_message(
                self.InitProcessing(
                    f"Finding assets in {mod_filename} ({i}/{len(mods)})"
                )
            )
            mod_asset_list.get_mod_assets(
                mod_filename, parse_only=True, force_refresh=self.force_refresh
            )
            mod_list.set_mod_details(
                {mod_filename: mod_asset_list.get_mod_info(mod_filename)}
            )
            mod_list.update_mod_counts(mod_filename)
            self.write_log(f"'{mod_filename}' refreshed.")

        self.post_message(self.InitProcessing(f"Init complete. Loading UI."))
        self.post_message(self.InitComplete())
        self.write_log(f"Initialization complete.")
        self.f_log.flush()

    def refresh_mods(self) -> None:
        mod_list = ModList.ModList()
        mod_asset_list = AssetList.AssetList()

        mods = mod_list.get_mods_needing_asset_refresh()
        for mod_filename in mods:
            mod_asset_list.get_mod_assets(mod_filename, parse_only=True)
            counts = mod_list.update_mod_counts(mod_filename)

            if self.is_screen_installed("mod_list"):
                screen = self.get_screen("mod_list")
                screen.update_counts(
                    mod_filename, counts["total"], counts["missing"], counts["size"]
                )

            if self.is_screen_installed("mod_details"):
                screen = self.get_screen("mod_details")
                screen.refresh_mod_details()

    def load_screen(self, new_screen: Screen, name: str):
        if self.is_screen_installed(name):
            self.uninstall_screen(name)
        self.install_screen(new_screen, name)
        self.push_screen(name)
        screen = self.get_screen(name)

        # Mount the worker screens so our messages bubbled
        if name == "mod_list":
            screen.mount(self.ad)
            screen.mount(self.sha1)
        screen.mount(TTSWorker())

    def on_ttsmutility_init_complete(self):
        config = load_config()
        self.load_screen(
            ModListScreen(config.tts_mods_dir, config.tts_saves_dir), "mod_list"
        )

    def on_ttsmutility_init_processing(self, event: InitProcessing):
        static = next(self.query("#status").results(Static))
        static.update(event.status)

    def on_key(self, event: Key):
        if event.key == "escape":
            try:
                status_center = self.screen_stack[-1].query_one("#worker_center")
                status_center.remove_class("unhide")
            except NoMatches:
                pass
        if event.key == "ctrl+t":
            self.push_screen(DebugScreen(self.screen_stack[-1].css_tree))

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        self.f_log.flush()

    #  █████╗ ███████╗███████╗███████╗████████╗██╗     ██╗███████╗████████╗███████╗ ██████╗██████╗ ███████╗███████╗███╗   ██╗
    # ██╔══██╗██╔════╝██╔════╝██╔════╝╚══██╔══╝██║     ██║██╔════╝╚══██╔══╝██╔════╝██╔════╝██╔══██╗██╔════╝██╔════╝████╗  ██║
    # ███████║███████╗███████╗█████╗     ██║   ██║     ██║███████╗   ██║   ███████╗██║     ██████╔╝█████╗  █████╗  ██╔██╗ ██║
    # ██╔══██║╚════██║╚════██║██╔══╝     ██║   ██║     ██║╚════██║   ██║   ╚════██║██║     ██╔══██╗██╔══╝  ██╔══╝  ██║╚██╗██║
    # ██║  ██║███████║███████║███████╗   ██║   ███████╗██║███████║   ██║   ███████║╚██████╗██║  ██║███████╗███████╗██║ ╚████║
    # ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝   ╚═╝   ╚══════╝╚═╝╚══════╝   ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝

    def on_asset_list_screen_asset_selected(self, event: AssetListScreen.AssetSelected):
        self.push_screen(AssetDetailScreen(event.asset_detail))

    def on_asset_list_screen_download_selected(
        self, event: AssetListScreen.DownloadSelected
    ):
        self.ad.add_assets(event.assets)
        self.run_worker(self.ad.start_download, exclusive=True)

    # ██████╗  ██████╗ ██╗    ██╗███╗   ██╗██╗      ██████╗  █████╗ ██████╗ ███████╗██████╗
    # ██╔══██╗██╔═══██╗██║    ██║████╗  ██║██║     ██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
    # ██║  ██║██║   ██║██║ █╗ ██║██╔██╗ ██║██║     ██║   ██║███████║██║  ██║█████╗  ██████╔╝
    # ██║  ██║██║   ██║██║███╗██║██║╚██╗██║██║     ██║   ██║██╔══██║██║  ██║██╔══╝  ██╔══██╗
    # ██████╔╝╚██████╔╝╚███╔███╔╝██║ ╚████║███████╗╚██████╔╝██║  ██║██████╔╝███████╗██║  ██║
    # ╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝

    def on_downloader_file_download_complete(
        self, event: Downloader.FileDownloadComplete
    ):
        if self.is_screen_installed("asset_list"):
            screen = self.get_screen("asset_list")
            screen.update_asset(event.asset)

    def on_downloader_download_complete(self, event: Downloader.DownloadComplete):
        self.refresh_mods()

    # ███╗   ███╗ ██████╗ ██████╗ ██╗     ██╗███████╗████████╗███████╗ ██████╗██████╗ ███████╗███████╗███╗   ██╗
    # ████╗ ████║██╔═══██╗██╔══██╗██║     ██║██╔════╝╚══██╔══╝██╔════╝██╔════╝██╔══██╗██╔════╝██╔════╝████╗  ██║
    # ██╔████╔██║██║   ██║██║  ██║██║     ██║███████╗   ██║   ███████╗██║     ██████╔╝█████╗  █████╗  ██╔██╗ ██║
    # ██║╚██╔╝██║██║   ██║██║  ██║██║     ██║╚════██║   ██║   ╚════██║██║     ██╔══██╗██╔══╝  ██╔══╝  ██║╚██╗██║
    # ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗██║███████║   ██║   ███████║╚██████╗██║  ██║███████╗███████╗██║ ╚████║
    # ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝╚══════╝   ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝

    def on_mod_list_screen_mod_selected(self, event: ModListScreen.ModSelected):
        self.load_screen(ModDetailScreen(event.filename), "mod_details")

    def on_mod_detail_screen_assets_selected(
        self, event: ModDetailScreen.AssetsSelected
    ):
        self.load_screen(AssetListScreen(event.mod_filename), "asset_list")

    def on_mod_list_screen_download_selected(
        self, event: ModListScreen.DownloadSelected
    ):
        self.write_log(f"Downloading missing assets from `{event.mod_filename}`.")
        self.ad.add_assets(event.mod_filename)
        self.run_worker(self.ad.start_download, exclusive=True)

    def on_mod_list_screen_sha1selected(self, event: ModListScreen.Sha1Selected):
        self.run_worker(self.sha1.scan_sha1s, exclusive=True)

    # ████████╗████████╗███████╗██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗██████╗
    # ╚══██╔══╝╚══██╔══╝██╔════╝██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗
    #    ██║      ██║   ███████╗██║ █╗ ██║██║   ██║██████╔╝█████╔╝ █████╗  ██████╔╝
    #    ██║      ██║   ╚════██║██║███╗██║██║   ██║██╔══██╗██╔═██╗ ██╔══╝  ██╔══██╗
    #    ██║      ██║   ███████║╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗███████╗██║  ██║
    #    ╚═╝      ╚═╝   ╚══════╝ ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝

    def on_ttsworker_update_log(self, event: TTSWorker.UpdateLog):
        params = {
            "prefix": event.prefix,
            "suffix": event.suffix,
        }
        not_none = {k: v for k, v in params.items() if v is not None}
        self.write_log(event.status, **not_none)
        if event.flush:
            self.f_log.flush()

    def on_ttsworker_update_progress(self, event: Downloader.UpdateProgress):
        if event.update_total is not None:
            self.progress_total = event.update_total
            self.progress_advance = 0
        else:
            self.progress_advance = self.progress_advance + event.advance_amount

        try:
            status_center = self.screen_stack[-1].query_one("#worker_center")
            status_center.add_class("unhide")
            progress = self.screen_stack[-1].query_one("#worker_progress")
            progress.add_class("unhide")
            progress.update(total=self.progress_total, progress=self.progress_advance)
        except NoMatches:
            pass

    def on_ttsworker_update_status(self, event: Downloader.UpdateStatus):
        self.last_status = event.status
        try:
            status_center = self.screen_stack[-1].query_one("#worker_center")
            status_center.add_class("unhide")
            status = self.screen_stack[-1].query_one("#worker_status")
            status.add_class("unhide")
            status.update(event.status)
        except NoMatches:
            pass


def get_args() -> Namespace:
    """Parse and return the command line arguments.

    Returns:
        The result of parsing the arguments.
    """

    # Create the parser object.
    parser = ArgumentParser(
        prog=PACKAGE_NAME,
        description=f"{APPLICATION_TITLE} - Tabletop Simulator Mod and Save Utility",
        epilog=f"v{__version__}",
    )

    # Add --version
    parser.add_argument(
        "-v",
        "--version",
        help="Show version information.",
        action="version",
        version=f"%(prog)s {__version__} (Textual v{textual_version})",
    )

    parser.add_argument(
        "-m",
        "--max_mods",
        help="Limit number of mods (for faster debuggin)",
        default=-1,
        type=int,
    )

    parser.add_argument(
        "--no-log",
        help="Disable logging (logfile path specified in config file)",
        dest="log",
        action="store_false",
    )

    parser.add_argument(
        "--overwrite_log",
        help="Overwrite the existing log (don't append)",
        dest="overwrite_log",
        action="store_true",
    )

    parser.add_argument(
        "--force_refresh",
        help="Re-process all mod files (useful if bug fix requires a rescan)",
        dest="force_refresh",
        action="store_true",
    )

    # Finally, parse the command line.
    return parser.parse_args()


def run() -> None:
    """Run the application."""
    TTSMutility(get_args()).run()
