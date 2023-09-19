import time
from argparse import ArgumentParser, Namespace
from pathlib import Path

from textual import __version__ as textual_version  # pylint: disable=no-name-in-module
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Header, LoadingIndicator, Static
from textual.worker import Worker, get_current_worker
from textual import work

from . import __version__
from .data import load_config, save_config, config_override
from .data.db import create_new_db, update_db_schema
from .parse import AssetList, ModList
from .screens.AssetDetailScreen import AssetDetailScreen
from .screens.AssetListScreen import AssetListScreen
from .screens.MissingAssetScreen import MissingAssetScreen
from .screens.ModDetailScreen import ModDetailScreen
from .screens.ModListScreen import ModListScreen
from .utility.advertising import APPLICATION_TITLE, PACKAGE_NAME
from .utility.messages import UpdateLog
from .workers.backup import ModBackup
from .workers.downloader import FileDownload
from .workers.sha1 import Sha1Scanner
from .workers.TTSWorker import TTSWorker
from .workers.names import NameScanner


class TTSMutility(App):
    CSS_PATH = "ttsmutility.css"

    TITLE = APPLICATION_TITLE
    SUB_TITLE = __version__

    class UpdateCounts(Message):
        def __init__(self, mod_filename, counts) -> None:
            super().__init__()
            self.mod_filename = mod_filename
            self.counts = counts

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
        self.sha1 = Sha1Scanner()
        self.backup = ModBackup()
        self.name_scanner = NameScanner()

        self.mods_queued_dl = {}

        if cli_args.force_refresh:
            self.force_refresh = True
        else:
            self.force_refresh = False

        if cli_args.overwrite_log:
            log_flags = "w"
        else:
            log_flags = "a"

        if cli_args.log:
            self.f_log = open(config.log_path, log_flags, encoding="utf-8")
        else:
            self.f_log = None

        if cli_args.skip_asset_scan:
            self.skip_asset_scan = True
        else:
            self.skip_asset_scan = False

        if cli_args.config_file is not None:
            config_override(cli_args.config_file)

        self.force_md_update = cli_args.force_md_update

        self.write_log(f"\n# TTSMutility v{__version__}", prefix="")
        self.write_log(
            f"Started at {time.ctime(self.start_time)}", prefix="", suffix="\n\n"
        )

    def __del__(self):
        if self.f_log is not None:
            self.f_log.close()

    def compose(self) -> ComposeResult:
        yield Header()
        yield LoadingIndicator(id="loading")
        yield Static(id="status")

    def write_log(self, output: str, prefix: str = "- ", suffix: str = "\n") -> None:
        if self.f_log is not None:
            if prefix == "":
                self.f_log.write(f"{output}{suffix}")
            else:
                self.f_log.write(
                    f"{prefix}{time.time() - self.start_time:.3f}:"
                    + f"{output}{suffix}"
                )

    def on_mount(self):
        # Mount the worker screens so our messages bubbled
        self.mount(self.sha1)
        self.mount(self.backup)
        self.mount(self.name_scanner)
        self.initialize_database()

    @work(thread=True)
    def initialize_database(self) -> None:
        config = load_config()
        worker = get_current_worker()

        self.write_log("## Init", prefix="")

        # Wait for DB to be created on first pass
        if not Path(config.db_path).exists():
            self.post_message(self.InitProcessing("Creating Database"))
            db_schema = create_new_db(config.db_path)
            self.write_log(f"Created DB with schema version {db_schema}.")
        else:
            db_schema = update_db_schema(config.db_path)
            self.write_log(f"Using DB schema version {db_schema}.")

        self.post_message(self.InitProcessing("Loading Workshop Mods"))
        mod_list = ModList.ModList(max_mods=self.max_mods)
        mod_list.get_mods(parse_only=True, force_refresh=self.force_refresh)
        self.write_log("Loaded Mods.")

        mod_asset_list = AssetList.AssetList(post_message=self.post_message)

        if self.skip_asset_scan:
            self.post_message(self.InitProcessing("Skipping Asset Scan"))
        else:
            prev_path = ""
            self.post_message(self.InitProcessing("Scanning Cached Assets"))
            for (
                path,
                new_assets,
                scanned_assets,
                assets_in_path,
            ) in mod_asset_list.scan_cached_assets():
                if path != prev_path:
                    if prev_path != "":
                        self.write_log(f"Found {new_assets} new assets.")
                    self.write_log(f"Scanning {path}.")
                    prev_path = path
                if path == "Complete":
                    self.post_message(
                        self.InitProcessing(
                            f"Scanning Complete. Found {new_assets} new assets."
                        )
                    )
                else:
                    if assets_in_path == 0:
                        perc_done = 1.00
                    else:
                        perc_done = scanned_assets / assets_in_path
                    self.post_message(
                        self.InitProcessing(
                            (f"Scanning Cached Assets in {path} " f"({perc_done:0.0%})")
                        )
                    )
                if worker.is_cancelled:
                    self.post_message(self.UpdateLog("Scan cancelled."))
                    return

        if self.force_refresh:
            mods = mod_list.get_all_mod_filenames()
        else:
            mods = mod_list.get_mods_needing_asset_refresh()

        self.write_log(f"Refreshing {len(mods)} Mods.")
        for i, mod_filename in enumerate(mods):
            if worker.is_cancelled:
                self.post_message(self.UpdateLog("Init cancelled."))
                return

            self.post_message(
                self.InitProcessing(
                    f"Finding assets in {mod_filename} ({i+1}/{len(mods)})"
                )
            )
            mod_asset_list.get_mod_assets(
                mod_filename, parse_only=True, force_refresh=True
            )
            mod_list.set_mod_details(
                {mod_filename: mod_asset_list.get_mod_info(mod_filename)}
            )
            mod_list.update_mod_counts(mod_filename)
            self.write_log(f"'{mod_filename}' refreshed.")

        self.post_message(self.InitProcessing("Init complete. Loading UI."))
        self.write_log("Initialization complete.")
        self.f_log.flush()
        self.post_message(self.InitComplete())

    def force_refresh_mod(self, mod_filename: str) -> None:
        mod_list = ModList.ModList()
        mod_asset_list = AssetList.AssetList()

        mod_asset_list.get_mod_assets(mod_filename, parse_only=True, force_refresh=True)
        counts = mod_list.update_mod_counts(mod_filename)

        if self.is_screen_installed("mod_list"):
            screen = self.get_screen("mod_list")
            screen.update_counts(
                mod_filename, counts["total"], counts["missing"], counts["size"]
            )

        if self.is_screen_installed("mod_details"):
            screen = self.get_screen("mod_details")
            screen.action_refresh_mod_details()

    async def on_ttsmutility_update_counts(self, event: UpdateCounts):
        if self.is_screen_installed("mod_list"):
            screen = self.get_screen("mod_list")
            await screen.update_counts_a(
                event.mod_filename,
                event.counts["total"],
                event.counts["missing"],
                event.counts["size"],
            )
        if False:
            if self.is_screen_installed("mod_details"):
                screen = self.get_screen("mod_details")
                screen.action_refresh_mod_details()

    @work(exclusive=True)
    async def refresh_mods(self) -> None:
        mod_list = ModList.ModList()
        mod_asset_list = AssetList.AssetList()

        mods = await mod_list.get_mods_needing_asset_refresh_a()
        for mod_filename in mods:
            await mod_asset_list.get_mod_assets_a(mod_filename)
            counts = await mod_list.update_mod_counts_a(mod_filename)

            self.post_message(self.UpdateCounts(mod_filename, counts))

    def load_screen(self, new_screen: Screen, name: str):
        if self.is_screen_installed(name):
            self.uninstall_screen(name)
        new_screen.mount(TTSWorker())
        self.install_screen(new_screen, name)
        self.push_screen(name)

    def on_ttsmutility_init_complete(self):
        self.run_worker(
            self.backup.backup_daemon,
            thread=True,
            group="backup",
            description="Backup Task",
        )
        self.load_screen(ModListScreen(), "mod_list")

    def on_ttsmutility_init_processing(self, event: InitProcessing):
        static = next(self.query("#status").results(Static))
        static.update(event.status)

    def on_key(self, event: Key):
        if event.key == "ctrl+t":
            from textual.screen import ModalScreen
            from textual.widgets import Footer, Static

            class CssTree(ModalScreen):
                BINDINGS = [
                    ("escape", "app.pop_screen", "Cancel"),
                ]

                def __init__(self, info: str = "") -> None:
                    super().__init__()
                    self.info = info

                def compose(self) -> ComposeResult:
                    yield Footer()
                    yield Static(self.info, id="id_static")

            self.push_screen(CssTree(self.screen_stack[-1].css_tree))

        if event.key == "escape":
            try:
                for s in reversed(self.screen_stack):
                    status_center = s.query_one("#worker_center")
                    status_center.remove_class("unhide")
            except NoMatches:
                pass

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        self.f_log.flush()

    """
    #  █████╗ ███████╗███████╗███████╗████████╗██╗     ██╗███████╗████████╗███████╗ ██████╗██████╗ ███████╗███████╗███╗   ██╗
    # ██╔══██╗██╔════╝██╔════╝██╔════╝╚══██╔══╝██║     ██║██╔════╝╚══██╔══╝██╔════╝██╔════╝██╔══██╗██╔════╝██╔════╝████╗  ██║
    # ███████║███████╗███████╗█████╗     ██║   ██║     ██║███████╗   ██║   ███████╗██║     ██████╔╝█████╗  █████╗  ██╔██╗ ██║
    # ██╔══██║╚════██║╚════██║██╔══╝     ██║   ██║     ██║╚════██║   ██║   ╚════██║██║     ██╔══██╗██╔══╝  ██╔══╝  ██║╚██╗██║
    # ██║  ██║███████║███████║███████╗   ██║   ███████╗██║███████║   ██║   ███████║╚██████╗██║  ██║███████╗███████╗██║ ╚████║
    # ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝   ╚═╝   ╚══════╝╚═╝╚══════╝   ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝
    """  # noqa

    def on_asset_list_screen_asset_selected(self, event: AssetListScreen.AssetSelected):
        self.push_screen(AssetDetailScreen(event.url, event.mod_filename, event.trail))

    def on_asset_list_screen_download_selected(
        self, event: AssetListScreen.DownloadSelected
    ):
        urls = []
        trails = []
        for asset in event.assets:
            urls.append(asset["url"])
            trails.append(asset["trail"])

        if event.mod_filename in self.mods_queued_dl:
            self.mods_queued_dl[event.mod_filename] += urls
        else:
            self.mods_queued_dl[event.mod_filename] = urls
        screen = self.get_screen("mod_list")
        screen.set_files_remaining(
            event.mod_filename, None, len(self.mods_queued_dl[event.mod_filename]), -1
        )
        screen.dl_urls(urls, trails)

    def on_asset_list_screen_update_counts(self):
        self.refresh_mods()

    """
    # ██████╗  ██████╗ ██╗    ██╗███╗   ██╗██╗      ██████╗  █████╗ ██████╗ ███████╗██████╗
    # ██╔══██╗██╔═══██╗██║    ██║████╗  ██║██║     ██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
    # ██║  ██║██║   ██║██║ █╗ ██║██╔██╗ ██║██║     ██║   ██║███████║██║  ██║█████╗  ██████╔╝
    # ██║  ██║██║   ██║██║███╗██║██║╚██╗██║██║     ██║   ██║██╔══██║██║  ██║██╔══╝  ██╔══██╗
    # ██████╔╝╚██████╔╝╚███╔███╔╝██║ ╚████║███████╗╚██████╔╝██║  ██║██████╔╝███████╗██║  ██║
    # ╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝
    """  # noqa

    async def on_file_download_file_download_progress(
        self, event: FileDownload.FileDownloadProgress
    ):
        screen = self.get_screen("mod_list")
        if self.is_screen_installed("mod_details"):
            detail_screen = self.get_screen("mod_details")
        else:
            detail_screen = None
        for mod_filename in self.mods_queued_dl:
            if event.url in self.mods_queued_dl[mod_filename]:
                screen.set_dl_progress(
                    mod_filename,
                    event.url,
                    event.worker_num,
                    event.filesize,
                    event.bytes_complete,
                )
                if detail_screen is not None:
                    detail_screen.update_size(
                        mod_filename, event.url, event.bytes_complete
                    )

    async def on_mod_list_screen_file_download_complete(
        self, event: ModListScreen.FileDownloadComplete
    ):
        asset_list = AssetList.AssetList()
        screen = self.get_screen("mod_list")
        if self.is_screen_installed("mod_details"):
            detail_screen = self.get_screen("mod_details")
        else:
            detail_screen = None
        await asset_list.download_done(event.asset)
        # Find the mods being downloaded that contain this URL so we can update the status
        for mod_filename in self.mods_queued_dl:
            if event.asset["url"] in self.mods_queued_dl[mod_filename]:
                self.mods_queued_dl[mod_filename].remove(event.asset["url"])
                files_remaining = len(self.mods_queued_dl[mod_filename])
                screen.set_files_remaining(
                    mod_filename, event.asset["url"], files_remaining, event.worker_num
                )
                if files_remaining == 0:
                    self.refresh_mods()
                if detail_screen is not None:
                    detail_screen.update_asset(mod_filename, event.asset)

    async def on_asset_detail_screen_copy_complete(
        self, event: AssetDetailScreen.CopyComplete
    ):
        pass

    """
    # ███╗   ███╗ ██████╗ ██████╗ ██╗     ██╗███████╗████████╗███████╗ ██████╗██████╗ ███████╗███████╗███╗   ██╗
    # ████╗ ████║██╔═══██╗██╔══██╗██║     ██║██╔════╝╚══██╔══╝██╔════╝██╔════╝██╔══██╗██╔════╝██╔════╝████╗  ██║
    # ██╔████╔██║██║   ██║██║  ██║██║     ██║███████╗   ██║   ███████╗██║     ██████╔╝█████╗  █████╗  ██╔██╗ ██║
    # ██║╚██╔╝██║██║   ██║██║  ██║██║     ██║╚════██║   ██║   ╚════██║██║     ██╔══██╗██╔══╝  ██╔══╝  ██║╚██╗██║
    # ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗██║███████║   ██║   ███████║╚██████╗██║  ██║███████╗███████╗██║ ╚████║
    # ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝╚══════╝   ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝
    """  # noqa

    def on_mod_list_screen_mod_refresh(self, event: ModListScreen.ModRefresh):
        self.force_refresh_mod(event.filename)

    def on_mod_list_screen_mod_selected(self, event: ModListScreen.ModSelected):
        self.load_screen(
            ModDetailScreen(event.filename, event.backup_time, self.force_md_update),
            "mod_details",
        )

    def on_mod_list_screen_backup_selected(self, event: ModListScreen.BackupSelected):
        self.backup.add_mods(event.backup_list)

    def on_mod_list_screen_download_selected(
        self, event: ModListScreen.DownloadSelected
    ):
        self.run_worker(
            self.download_selected(event.mod_filenames), thread=True, exclusive=True
        )

    async def download_selected(self, mod_filenames: list[str]) -> None:
        mod_asset_list = AssetList.AssetList()
        screen = self.get_screen("mod_list")

        for mod_filename in mod_filenames:
            turls = await mod_asset_list.get_missing_assets(mod_filename)
            if len(turls) == 0:
                continue
            screen.set_files_remaining(mod_filename, None, len(turls), -1)
            urls, trails = tuple(zip(*turls))
            self.write_log(f"Downloading missing assets from `{mod_filename}`.")
            self.mods_queued_dl[mod_filename] = list(urls)
            screen.dl_urls(urls, trails, mod_filename)

    def on_mod_list_screen_sha1selected(self, event: ModListScreen.Sha1Selected):
        self.run_worker(self.sha1.scan_sha1s, exclusive=True, thread=True)

    def on_mod_list_screen_show_sha1(self, event: ModListScreen.ShowSha1):
        self.app.push_screen(MissingAssetScreen("sha1", "SHA1 Mismatches"))

    def on_mod_list_screen_show_missing(self, event: ModListScreen.ShowMissing):
        self.app.push_screen(MissingAssetScreen("missing", "Missing Assets"))

    def on_mod_list_screen_scan_names(self, event: ModListScreen.ScanNames):
        self.run_worker(self.name_scanner.scan_names, exclusive=True, thread=True)

    def on_mod_detail_screen_bgg_id_updated(self, event: ModDetailScreen.BggIdUpdated):
        if self.is_screen_installed("mod_list"):
            screen = self.get_screen("mod_list")
            screen.update_bgg(event.mod_filename, event.bgg_id)

    """
    # ████████╗████████╗███████╗██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗██████╗
    # ╚══██╔══╝╚══██╔══╝██╔════╝██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗
    #    ██║      ██║   ███████╗██║ █╗ ██║██║   ██║██████╔╝█████╔╝ █████╗  ██████╔╝
    #    ██║      ██║   ╚════██║██║███╗██║██║   ██║██╔══██╗██╔═██╗ ██╔══╝  ██╔══██╗
    #    ██║      ██║   ███████║╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗███████╗██║  ██║
    #    ╚═╝      ╚═╝   ╚══════╝ ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
    """  # noqa

    def on_update_log(self, event: UpdateLog):
        params = {
            "prefix": event.prefix,
            "suffix": event.suffix,
        }
        not_none = {k: v for k, v in params.items() if v is not None}
        self.write_log(event.status, **not_none)
        if event.flush:
            self.f_log.flush()

    def on_mod_backup_update_progress(self, event: ModBackup.UpdateProgress):
        up_prog = TTSWorker.UpdateProgress(
            update_total=event.update_total, advance_amount=event.advance_amount
        )
        self.on_ttsworker_update_progress(up_prog)

    def on_mod_backup_backup_start(self, event: ModBackup.BackupStart):
        screen = self.get_screen("mod_list")
        screen.set_backup_start(event.filename, event.zip_path)
        status = TTSWorker.UpdateStatus(str(event.zip_path))
        self.on_ttsworker_update_status(status)

    def on_mod_backup_backup_complete(self, event: ModBackup.BackupComplete):
        screen = self.get_screen("mod_list")
        screen.set_backup_complete(event.filename)

    def on_ttsworker_update_progress(self, event: TTSWorker.UpdateProgress):
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

        try:
            status = self.screen_stack[-1].query_one("#worker_status")
            status.add_class("unhide")
            status.update(self.last_status)
        except NoMatches:
            pass

    def on_ttsworker_update_status(self, event: TTSWorker.UpdateStatus):
        self.last_status = event.status
        try:
            status_center = self.screen_stack[-1].query_one("#worker_center")
            status_center.add_class("unhide")
            status = self.screen_stack[-1].query_one("#worker_status")
            status.add_class("unhide")
            status.update(self.last_status)
        except NoMatches:
            pass

        try:
            progress = self.screen_stack[-1].query_one("#worker_progress")
            progress.update(total=self.progress_total, progress=self.progress_advance)
        except NoMatches:
            pass


def file_path(filepath):
    if Path(filepath).exists():
        return filepath
    else:
        raise NotADirectoryError(filepath)


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
        "--max-mods",
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
        "--overwrite-log",
        help="Overwrite the existing log (don't append)",
        dest="overwrite_log",
        action="store_true",
    )

    parser.add_argument(
        "--force-refresh",
        help="Re-process all mod files (useful if bug fix requires a rescan)",
        dest="force_refresh",
        action="store_true",
    )

    parser.add_argument(
        "--skip-asset-scan",
        help="Do not scan filesystem for new assets during init",
        dest="skip_asset_scan",
        action="store_true",
    )

    parser.add_argument(
        "--force-steam-md-update",
        help="Reload steam meta data, do not use cached version",
        dest="force_md_update",
        action="store_true",
    )

    parser.add_argument(
        "-c",
        "--config_file",
        help="Override default config file path (including filename)",
        type=file_path,
    )

    # Finally, parse the command line.
    return parser.parse_args()


def run() -> None:
    """Run the application."""
    TTSMutility(get_args()).run()
