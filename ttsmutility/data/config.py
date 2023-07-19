"""Provides code for loading/saving configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from json import dumps, loads
from pathlib import Path

from xdg_base_dirs import xdg_config_home

import platform
from .data_directory import (
    data_directory,
    bgg_cache_directory,
    mod_backup_directory,
    asset_backup_directory,
)

gamedata_map = {
    "Windows": "Documents/My Games/Tabletop Simulator",
    "Darwin": "Library/Tabletop Simulator",  # MacOS
    "Linux": ".local/share/Tabletop Simulator",
}
try:
    active_platform = platform.system()
    GAMEDATA_DEFAULT = Path.home() / gamedata_map[active_platform]
except KeyError:
    GAMEDATA_DEFAULT = Path.home() / gamedata_map["Windows"]

CONFIG_OVERRIDE = ""


@dataclass
class Config:
    """The markdown viewer configuration."""

    tts_mods_dir: Path = str(GAMEDATA_DEFAULT / "Mods")
    tts_mods_dir_help: str = "Location of the Tabletop Simulator 'Mods' directory."

    tts_saves_dir: Path = str(GAMEDATA_DEFAULT)
    tts_saves_dir_help: str = (
        "Location of the Tabletop Simulator user directory"
        "(this directory contains the 'Saves' subdirectory)."
    )

    db_path: Path = str(data_directory() / "ttsmutility.sqlite")
    db_path_help: str = "The complete path (dir and filename) for the sqlite3 database."

    log_path: Path = str(data_directory() / "ttsmutility_log.md")
    log_path_help: str = (
        "The complete path (dir and filename) for the log"
        "file (can be disabled as argument)."
    )

    bgg_cache_dir: Path = str(bgg_cache_directory())
    bgg_path_dir_help: str = "Location to cache BGG and Steam description files."

    mod_backup_dir: Path = str(mod_backup_directory())
    mod_backup_dir_help: str = (
        "Location where mods should be stored during backup operation."
    )

    asset_backup_dir: Path = str(asset_backup_directory())
    asset_backup_dir_help: str = "Location where bad assets should be disposed."

    metadata_invalidate_days: str = "7"
    metadata_invalidate_days_help: str = (
        "How many days before metadata is refreshed from Steam and BGG"
    )

    num_download_threads: str = "3"
    num_download_threads_help: str = (
        "Number of background threads to use when downloading missing assets"
    )

    steam_api_key: str = ""
    steam_api_key_help: str = (
        "Personal Steam API key. Not currently used, so completely optional."
    )


def config_override(config_file: Path) -> None:
    """Overrides the default configfile location.

    Args:
        config_file: The configuration file to use.

    Returns:
        None

    Note:
        No checks are done to ensure the config_file exists.
    """
    global CONFIG_OVERRIDE
    CONFIG_OVERRIDE = config_file


def config_file() -> Path:
    """Get the path to the configuration file.

    Returns:
        The path to the configuration file.

    Note:
        As a side-effect, the configuration directory will be created if it
        does not exist.
    """
    if CONFIG_OVERRIDE == "":
        (config_dir := xdg_config_home() / "ttsmutility").mkdir(
            parents=True, exist_ok=True
        )
        return config_dir / "configuration.json"
    else:
        return CONFIG_OVERRIDE


def save_config(config: Config) -> Config:
    """Save the given configuration to storage.

    Args:
        config: The configuration to save.

    Returns:
        The configuration.
    """
    # Ensure any cached copy of the config is cleaned up.
    load_config.cache_clear()
    # Dump the given config to storage.
    config_file().write_text(dumps(asdict(config), indent=4))
    # Finally, load it up again. This is to make sure that the updated
    # version is in the cache.
    return load_config()


@lru_cache(maxsize=None)
def load_config() -> Config:
    """Load the configuration from storage.

    Returns:
        The configuration.

    Note:
        As a side-effect, if the configuration doesn't exist a default one
        will be saved to storage.

        This function is designed so that it's safe and low-cost to
        repeatedly call it. The configuration is cached and will only be
        loaded from storage when necessary.
    """
    source_file = config_file()
    return (
        Config(**loads(source_file.read_text()))
        if source_file.exists()
        else save_config(Config())
    )
