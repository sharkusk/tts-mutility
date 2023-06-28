"""Provides a function for working out the data directory location."""

from pathlib import Path

from xdg_base_dirs import xdg_data_home


def data_directory() -> Path:
    """Get the location of the data directory.

    Returns:
        The location of the data directory.

    Note:
        As a side effect, if the directory doesn't exist it will be created.
    """
    (target_directory := xdg_data_home() / "ttsmutility").mkdir(
        parents=True, exist_ok=True
    )
    return target_directory