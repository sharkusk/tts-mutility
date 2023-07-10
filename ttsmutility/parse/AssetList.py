import os
import os.path
import pathlib
import sqlite3
import time
from pathlib import Path
from shutil import move

from ..data.config import load_config
from ..parse.FileFinder import (
    FILES_TO_IGNORE,
    TTS_RAW_DIRS,
    recodeURL,
    trail_to_trailstring,
    trailstring_to_trail,
    get_fs_path_from_extension,
)
from .ModParser import ModParser


def detect_file_type(filepath):
    FILE_TYPES = {
        ".unity3d": b"\x55\x6e\x69\x74\x79\x46\x53",  # UnityFS
        ".OGG": b"\x47\x67\x67\x53",
        ".WAV": b"\x52\x49\x46\x46",  # RIFF
        ".MP3": b"\x49\x44\x33",  # ID3
        ".png": b"\x89\x50\x4E\x47",  # ?PNG
        ".jpg": b"\xFF\xD8",  # ??
        ".obj": b"\x23\x20",  # "# "
        ".PDF": b"\x25\x50\x44\x46",  # %PDF
    }
    with open(filepath, "rb") as f:
        f_data = f.read(10)
        for ext, pattern in FILE_TYPES.items():
            if pattern in f_data[0 : len(pattern)]:
                return ext
        else:
            return ""


class IllegalSavegameException(ValueError):
    def __init__(self):
        super().__init__("not a Tabletop Simulator savegame")


class AssetList:
    # These names are redundant, so don't keep them in our trail
    NAMES_TO_IGNORE = [
        "custom_model",
        "custom_assetbundle",
        "custom_pdf",
        "custom_token",
        "custom content",
        "deck",
        "cardcustom",
    ]

    def __init__(self) -> None:
        self.config = load_config()
        self.db_path = Path(self.config.db_path)
        self.mod_dir = Path(self.config.tts_mods_dir)
        self.save_dir = Path(self.config.tts_saves_dir)
        self.mod_infos = {}

    def get_mod_info(self, mod_filename: Path) -> dict or None:
        if mod_filename in self.mod_infos:
            return self.mod_infos[mod_filename]
        else:
            return None

    def get_mod_infos(self) -> dict:
        return self.mod_infos

    def get_sha1_info(self, filepath: str) -> None:
        # return sha1, steam_sha1, sha1_mtime
        path, filename = os.path.split(filepath)
        if filename != "":
            filename, _ = os.path.splitext(filename)

        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT asset_sha1, asset_steam_sha1, asset_sha1_mtime, asset_mtime, asset_size
                FROM tts_assets
                WHERE asset_filename=? and asset_path=?
                """,
                (filename, path),
            )
            result = cursor.fetchone()
            if result is not None:
                return {
                    "sha1": result[0],
                    "steam_sha1": result[1],
                    "sha1_mtime": result[2],
                    "mtime": result[3],
                    "fsize": result[4],
                }
            return None

    def sha1_scan_done(
        self, filepath: str, sha1: str, steam_sha1: str, sha1_mtime: float
    ) -> None:
        path, filename = os.path.split(filepath)
        if filename != "":
            filename, _ = os.path.splitext(filename)
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE tts_assets
                SET asset_sha1=?, asset_steam_sha1=?, asset_sha1_mtime=?
                WHERE asset_filename=? and asset_path=?
                """,
                (sha1, steam_sha1, sha1_mtime, filename, path),
            )
            db.commit()

    def get_sha1_mismatches(self):
        assets = []
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                (
                    """
                SELECT
                    asset_url, asset_path, asset_filename, asset_ext,
                    asset_mtime, asset_sha1, asset_steam_sha1, mod_asset_trail,
                    asset_dl_status, asset_size, asset_content_name
                FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.asset_id_fk=tts_assets.id
                    INNER JOIN tts_mods
                        ON tts_mod_assets.mod_id_fk=tts_mods.id
                WHERE tts_assets.asset_steam_sha1 != ""
                    AND tts_assets.asset_sha1 != tts_assets.asset_steam_sha1
                """
                ),
            )
            results = cursor.fetchall()
            for result in results:
                path = result[1]
                filename = result[2]
                ext = result[3]

                asset_filename = os.path.join(path, filename) + ext
                assets.append(
                    {
                        "url": result[0],
                        "filename": asset_filename,
                        "mtime": result[4],
                        "sha1": result[5],
                        "steam_sha1": result[6],
                        "trail": result[7],
                        "dl_status": result[8],
                        "fsize": result[9],
                        "content_name": result[10],
                    }
                )
        return assets

    def download_done(self, asset: dict) -> None:
        # Don't overwrite the calculated filepath with something that is empty
        with sqlite3.connect(self.db_path) as db:
            if asset["filename"] == "":
                db.execute(
                    """
                    UPDATE tts_assets
                    SET asset_mtime=?, asset_size=?, asset_dl_status=?, asset_content_name=?, asset_steam_sha1=?
                    WHERE asset_url=?
                    """,
                    (
                        asset["mtime"],
                        asset["fsize"],
                        asset["dl_status"],
                        asset["content_name"],
                        asset["steam_sha1"],
                        asset["url"],
                    ),
                )
            else:
                path, filename = os.path.split(asset["filename"])
                if filename != "":
                    filename, ext = os.path.splitext(filename)

                db.execute(
                    """
                    UPDATE tts_assets
                    SET asset_filename=?, asset_path=?, asset_ext=?,
                        asset_mtime=?, asset_size=?, asset_dl_status=?, asset_content_name=?, asset_steam_sha1=?
                    WHERE asset_url=?
                    """,
                    (
                        filename,
                        path,
                        ext,
                        asset["mtime"],
                        asset["fsize"],
                        asset["dl_status"],
                        asset["content_name"],
                        asset["steam_sha1"],
                        asset["url"],
                    ),
                )

            # dl_status is empty if the download was succesfull
            if asset["dl_status"] == "":
                # Set mod asset counts containing this asset to -1 to represent an update to the system
                db.execute(
                    """
                    UPDATE tts_mods
                    SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1
                    WHERE id IN (
                        SELECT mod_id_fk
                        FROM tts_mod_assets
                        WHERE asset_id_fk IN (
                            SELECT id FROM tts_assets
                            WHERE asset_url=?
                        )
                    )
                    """,
                    (asset["url"],),
                )
            db.commit()

    def get_missing_assets(self, mod_filename: str) -> list:
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT asset_url, asset_mtime, asset_sha1, asset_steam_sha1, mod_asset_trail
                FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.asset_id_fk=tts_assets.id
                    INNER JOIN tts_mods
                        ON tts_mod_assets.mod_id_fk=tts_mods.id
                WHERE mod_filename=?
                """,
                (mod_filename,),
            )
            results = cursor.fetchall()
        urls = []
        for result in results:
            skip = True
            # Has this file already been downloaded, if so we generally skip it
            if result[1] != 0:
                # Check if SHA1 computed from file contents matches steam filename SHA1
                if result[2] != "" and result[3] != "":
                    if result[2] != result[3]:
                        # We have a SHA1 mismatch so re-download
                        skip = False
            else:
                # File doesn't exist, so download it
                skip = False
            if not skip:
                urls.append((result[0], trailstring_to_trail(result[4])))
        return urls

    def fix_duplicate_files(
        self, root, path, filename, asset_filename, dup_ext, dup_path
    ) -> list:
        # We have file_stems (i.e. filenames without the ext)
        # that match in our DB.  However, the extensions are not the
        # same or there are duplicate files with diff extensions.
        # Detect the correct fileformat and update accordingly.
        no_dupes = []
        # file_exts = [Path(file).suffix for file in files]
        # We likely have duplicate filenames with different extensions.
        # Let's see if we can identify what is the real file.
        for dup_file in new_files:
            dup_stem = Path(dup_file).stem
            dup_files = [x for x in files if Path(x).stem == dup_stem]
            ext = ""
            # For each duplicate file (i.e. files with same stem),
            # we are going to look for the correct ext, then determine
            # what directory that extension belongs in, then rename
            # or move the duplicate file appropriately.
            for file in dup_files:
                filepath = Path(root) / file
                if ext == "":
                    if (ext := detect_file_type(Path(root) / file)) != "":
                        if Path(file).suffix != ext:
                            newpath = get_fs_path_from_extension(
                                "", ext, Path(file).stem
                            )
                            newpath = Path(self.config.tts_mods_dir) / newpath
                            remove_file = True
                            if newpath is not None:
                                if not newpath.exists():
                                    remove_file = False
                            if remove_file:
                                move(
                                    filepath,
                                    Path(self.config.asset_backup_dir) / file,
                                )
                            else:
                                # Is this going to the current path?
                                if filepath.with_suffix("") == newpath.with_suffix(""):
                                    no_dupes.append(dup_stem + ext)
                                    os.rename(filepath, newpath)
                                else:
                                    # Move the file to it's correct location
                                    move(
                                        filepath,
                                        newpath,
                                    )
                            continue
                # Any subsequent duplicate files (with the wrong
                # extension) need to be removed.
                if ext != "":
                    if Path(file).suffix.lower() != ext.lower():
                        # Remove the files that have the wrong extension
                        move(filepath, Path(self.config.asset_backup_dir) / file)
                    else:
                        no_dupes.append(file)
        return no_dupes

    def scan_cached_assets(self) -> int:
        scan_time = time.time()
        count = 0

        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT asset_last_scan_time
                FROM tts_app
                WHERE id=1
            """
            )
            result = cursor.fetchone()
            # This should not fail as we init to zero as part of DB init
            prev_scan_time = result[0]

            ignore_paths = ["Mods", "Workshop"]
            ignore_files = ["sha1-verified", "sha1-verified.txt"]

            cursor = db.execute(
                """
                SELECT asset_filename, asset_ext, asset_path
                FROM tts_assets
                """,
            )
            results = cursor.fetchall()
            if len(results) > 0:
                asset_stems, asset_exts, asset_paths = list(zip(*results))
                asset_filenames = set(map(str.__add__, asset_stems, asset_exts))
            else:
                asset_stems = []
                asset_exts = []
                asset_paths = []
                asset_filenames = set()

            assets = []
            for root, _, files in os.walk(self.mod_dir, topdown=True):
                path = pathlib.PurePath(root).name

                if path in TTS_RAW_DIRS or path == "" or path in ignore_paths:
                    continue

                new_files = set(files).difference(asset_filenames)

                for filename in new_files:
                    filename = Path(filename)
                    if filename.stem in ignore_files:
                        continue
                    if filename.suffix.upper() in FILES_TO_IGNORE:
                        continue

                    update_asset = False
                    # Determine why there is a difference.
                    try:
                        i = asset_stems.index(filename.stem)
                    except ValueError:
                        # This is a brand new asset, not in our DB
                        update_asset = True
                    else:
                        if asset_exts[i] == "" and asset_paths[i] == "":
                            # Asset exists in DB, but is not associated
                            # with a file yet. This is normal case and
                            # we can simply update the DB.
                            update_asset = True
                        else:
                            if (
                                correct_ext := detect_file_type(Path(root) / filename)
                            ) == "":
                                # Unknown file, just leave it alone...
                                continue
                            correct_filepath = get_fs_path_from_extension(
                                "", correct_ext, filename.stem
                            )
                            correct_path = pathlib.PurePath(correct_filepath).parent

                            if asset_exts[i] != filename.suffix:
                                # Asset exists in DB but has a different ext.
                                if filename.suffix == correct_ext:
                                    if asset_exts[i] != correct_ext:
                                        update_asset = True
                                else:
                                    if (
                                        (Path(root) / filename)
                                        .with_suffix(correct_ext)
                                        .exists()
                                    ):
                                        # Remove the files that have the wrong extension
                                        move(
                                            Path(root) / filename,
                                            Path(self.config.asset_backup_dir)
                                            / filename,
                                        )
                                    else:
                                        # Rename file to have correct ext
                                        os.rename(
                                            Path(root) / filename,
                                            (Path(root) / filename).with_suffix(
                                                correct_ext
                                            ),
                                        )
                                        # Need to set new suffix to filename since it may be used later
                                        filename = Path(filename).with_suffix(
                                            correct_ext
                                        )

                            if asset_paths[i] != path:
                                # Asset exists in DB but has a different path.
                                if path == correct_path:
                                    if asset_paths[i] != correct_path:
                                        update_asset = True
                                else:
                                    # Move the files to correct directory or remove if already exists
                                    if (
                                        Path(self.config.tts_mods_dir)
                                        / correct_path
                                        / filename
                                    ).exists():
                                        # Remove the files that are in the wrong spot and already have a file
                                        # in the correct destination that matches
                                        move(
                                            Path(root) / filename,
                                            Path(self.config.asset_backup_dir)
                                            / filename,
                                        )
                                    else:
                                        move(
                                            Path(root) / filename,
                                            Path(self.config.tts_mods_dir)
                                            / correct_path
                                            / filename,
                                        )

                    if update_asset:
                        filepath = Path(root) / filename
                        size = os.path.getsize(filepath)
                        mtime = os.path.getmtime(filepath)
                        assets.append(
                            (path, filename.stem, filename.suffix, mtime, size, 1)
                        )

            cursor = db.executemany(
                """
                INSERT INTO tts_assets
                    (asset_path, asset_filename, asset_ext, asset_mtime, asset_size, asset_new)
                VALUES
                    (?, ?, ?, ?, ?, ?)
                ON CONFLICT (asset_filename)
                DO UPDATE SET
                    asset_path=excluded.asset_path,
                    asset_ext=excluded.asset_ext,
                    asset_mtime=excluded.asset_mtime,
                    asset_size=excluded.asset_size,
                    asset_new=excluded.asset_new;
                """,
                assets,
            )
            count = cursor.rowcount

            db.execute(
                """
                UPDATE tts_app
                SET asset_last_scan_time=?
                WHERE id=1
            """,
                (scan_time,),
            )

            db.commit()
        return count

    def update_mod_assets(self, mod_filename: str, mod_mtime) -> int:
        if mod_filename.find("Workshop") == 0:
            mod_path = Path(self.mod_dir) / mod_filename
        else:
            mod_path = Path(self.save_dir) / mod_filename

        mod_parser = ModParser(mod_path)

        mod_assets = [
            (recodeURL(url), url, trail) for trail, url in mod_parser.urls_from_mod()
        ]

        # Defer updating until we are told
        mod_info = mod_parser.get_mod_info()
        self.mod_infos[mod_filename] = mod_info
        self.mod_infos[mod_filename]["mtime"] = mod_mtime

        new_asset_count = 0

        if len(mod_assets) > 0:
            with sqlite3.connect(self.db_path) as db:
                filenames, urls, trails = zip(*mod_assets)

                # Combine the URLs/filenames from the mod with what is already in the DB
                # (from filesystem scan and possible previous mod scan)

                # Since the filesystem is scanned before the mods are processed, filenames
                # may exist in the DB before the associated URLs are discovered in the mod
                # file.  Therefore, when we conflict on the filename, we still need to update
                # the URL.
                cursor = db.executemany(
                    """
                    INSERT INTO tts_assets
                        (asset_url, asset_filename)
                    VALUES
                        (?, ?)
                    ON CONFLICT (asset_filename)
                    DO UPDATE SET
                        asset_url=excluded.asset_url;
                    """,
                    tuple(zip(urls, filenames)),
                )
                new_asset_count += cursor.rowcount

                trailstrings = [trail_to_trailstring(trail) for trail in trails]
                cursor = db.executemany(
                    """
                    INSERT OR IGNORE INTO tts_mod_assets
                        (asset_id_fk, mod_id_fk, mod_asset_trail)
                    VALUES (
                        (SELECT tts_assets.id FROM tts_assets WHERE asset_filename=?),
                        (SELECT tts_mods.id FROM tts_mods WHERE mod_filename=?),
                        ?)
                    """,
                    tuple(
                        zip(filenames, [mod_filename] * len(filenames), trailstrings)
                    ),
                )
                new_asset_trails = cursor.rowcount

                # Detect assets that are no longer included in the mod
                cursor = db.execute(
                    """
                    SELECT asset_url
                    FROM tts_assets
                        INNER JOIN tts_mod_assets
                            ON tts_mod_assets.asset_id_fk=tts_assets.id
                        INNER JOIN tts_mods
                            ON tts_mod_assets.mod_id_fk=tts_mods.id
                    WHERE mod_filename=?
                    """,
                    (mod_filename,),
                )
                results = cursor.fetchall()

                removed_assets = list(
                    set(list(zip(*results))[0]).symmetric_difference(set(urls))
                )
                removed_asset_count = len(removed_assets)
                cursor = db.executemany(
                    """
                    DELETE FROM tts_mod_assets
                    WHERE
                        asset_id_fk = (SELECT tts_assets.id FROM tts_assets WHERE asset_url=?)
                    AND
                        mod_id_fk = (SELECT tts_mods.id FROM tts_mods WHERE mod_filename=?)
                    """,
                    tuple(zip(removed_assets, [mod_filename] * len(removed_assets))),
                )
                if removed_asset_count != cursor.rowcount:
                    # We didn't remove assets properly!
                    pass

                if new_asset_count > 0 or removed_asset_count > 0:
                    cursor = db.execute(
                        """
                        SELECT
                            asset_mtime
                        FROM
                            tts_assets
                        WHERE
                            asset_mtime = (
                                SELECT MAX(asset_mtime)
                                FROM tts_assets
                                WHERE id IN (
                                    SELECT asset_id_fk
                                    FROM tts_mod_assets
                                    WHERE mod_id_fk = (
                                        SELECT id
                                        FROM tts_mods
                                        WHERE mod_filename = ?
                                    )
                                )
                            )
                        """,
                        (mod_filename,),
                    )
                    result = cursor.fetchone()
                    max_asset_mtime = result[0]

                    db.execute(
                        """
                        UPDATE tts_mods
                        SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1, mod_max_asset_mtime=?
                        WHERE mod_filename=?
                        """,
                        (max_asset_mtime, mod_filename),
                    )
                db.commit()
        return new_asset_count

    def get_mods_using_asset(self, url: str) -> list:
        results = []
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_name
                FROM tts_mods
                WHERE id IN (
                    SELECT mod_id_fk
                    FROM tts_mod_assets
                    WHERE asset_id_fk = (
                        SELECT id
                        FROM tts_assets
                        WHERE asset_url=?
                    )
                )
                """,
                (url,),
            )
            results = cursor.fetchall()
            if len(results) > 0:
                results = list(zip(*results))[0]
        return results

    def get_mod_assets(
        self, mod_filename: str, parse_only=False, force_refresh=False
    ) -> list:
        assets = []
        if mod_filename == "sha1":
            return self.get_sha1_mismatches()
        elif mod_filename.find("Workshop") == 0:
            mod_path = os.path.join(self.mod_dir, mod_filename)
        else:
            mod_path = os.path.join(self.save_dir, mod_filename)

        prev_mod_mtime = 0
        mod_mtime = 0

        with sqlite3.connect(self.db_path) as db:
            # Check if we have this mod in our DB
            cursor = db.execute(
                """
                SELECT mod_mtime
                FROM tts_mods
                WHERE mod_filename=?
                """,
                (mod_filename,),
            )
            result = cursor.fetchone()
            refresh_mod = force_refresh
            if result == None:
                refresh_mod = True
            else:
                prev_mod_mtime = result[0]
                mod_mtime = os.path.getmtime(mod_path)
                if mod_mtime > prev_mod_mtime:
                    refresh_mod = True

            if refresh_mod:
                self.update_mod_assets(mod_filename, mod_mtime)

            if not parse_only:
                cursor = db.execute(
                    (
                        """
                    SELECT
                        asset_url, asset_path, asset_filename, asset_ext,
                        asset_mtime, asset_sha1, asset_steam_sha1, mod_asset_trail,
                        asset_dl_status, asset_size, asset_content_name
                    FROM tts_assets
                        INNER JOIN tts_mod_assets
                            ON tts_mod_assets.asset_id_fk=tts_assets.id
                        INNER JOIN tts_mods
                            ON tts_mod_assets.mod_id_fk=tts_mods.id
                    WHERE mod_filename=?
                    """
                    ),
                    (mod_filename,),
                )
                results = cursor.fetchall()
                for result in results:
                    path = result[1]
                    filename = result[2]
                    ext = result[3]

                    asset_filename = os.path.join(path, filename) + ext
                    assets.append(
                        {
                            "url": result[0],
                            "filename": asset_filename,
                            "mtime": result[4],
                            "sha1": result[5],
                            "steam_sha1": result[6],
                            "trail": result[7],
                            "dl_status": result[8],
                            "fsize": result[9],
                            "content_name": result[10],
                        }
                    )

        return assets

    def get_content_names(self) -> list:
        with sqlite3.connect(self.db_path) as db:
            # Check if we have this mod in our DB
            cursor = db.execute(
                """
                SELECT asset_url, asset_content_name
                FROM tts_assets
                WHERE asset_content_name != ""
                """,
            )
            results = cursor.fetchall()
            return list(zip(*results))

    def set_content_names(self, urls, content_names) -> None:
        with sqlite3.connect(self.db_path) as db:
            cursor = db.executemany(
                """
                UPDATE tts_assets
                SET asset_content_name=?
                WHERE asset_url=?
                """,
                tuple(zip(content_names, urls)),
            )
            count = cursor.rowcount
            db.commit()
