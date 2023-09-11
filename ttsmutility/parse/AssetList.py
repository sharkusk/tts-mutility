import operator
import os
import os.path
import pathlib
import sqlite3
import time
from functools import reduce
from pathlib import Path
from shutil import copy, move

import aiosqlite

from ..data.config import load_config
from ..parse.FileFinder import (
    FILES_TO_IGNORE,
    TTS_RAW_DIRS,
    get_fs_path_from_extension,
    recodeURL,
    trail_to_trailstring,
    trailstring_to_trail,
)
from ..utility.messages import UpdateLog
from ..utility.util import detect_file_type, get_content_name, get_steam_sha1_from_url
from .ModParser import ModParser


class IllegalSavegameException(ValueError):
    def __init__(self):
        super().__init__("not a Tabletop Simulator savegame")


def asset_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key.replace("asset_", ""): value for key, value in zip(fields, row)}


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

    def __init__(self, post_message=None) -> None:
        self.config = load_config()
        self.db_path = Path(self.config.db_path)
        self.mod_dir = Path(self.config.tts_mods_dir)
        self.save_dir = Path(self.config.tts_saves_dir)
        self.mod_infos = {}
        if post_message is None:
            self.post_message = lambda x: None
        else:
            self.post_message = post_message

    def get_mod_info(self, mod_filename: Path) -> dict | None:
        if mod_filename in self.mod_infos:
            return self.mod_infos[mod_filename]
        else:
            return None

    def get_mod_infos(self) -> dict:
        return self.mod_infos

    def get_sha1_info(self, path: str) -> dict:
        def my_factory(cursor, row):
            fields = [column[0] for column in cursor.description]
            return {
                row[0]: {
                    key.replace("asset_", ""): value
                    for key, value in zip(fields[1:], row[1:])
                }
            }

        with sqlite3.connect(self.db_path) as db:
            db.row_factory = my_factory
            cursor = db.execute(
                """
                SELECT
                    asset_filename, asset_sha1, asset_steam_sha1,
                    asset_sha1_mtime, asset_mtime, asset_size
                FROM
                    tts_assets
                WHERE
                    asset_path=?
                """,
                (path,),
            )
            results = cursor.fetchall()
            # We now have a list of dictionaries, combine them into one:
            sha1s = reduce(operator.ior, results, {})
            return sha1s

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
            db.row_factory = asset_factory
            cursor = db.execute(
                (
                    """
                SELECT
                    (asset_path || "/" || asset_filename || asset_ext) as filename,
                    asset_url, asset_mtime, asset_sha1, asset_steam_sha1, mod_asset_trail as trail,
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
            assets = cursor.fetchall()
        return assets

    def get_missing(self):
        assets = []
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = asset_factory
            cursor = db.execute(
                (
                    """
                SELECT
                    (asset_path || "/" || asset_filename || asset_ext) as filename,
                    asset_url, asset_mtime, asset_sha1, asset_steam_sha1, mod_asset_trail as trail,
                    asset_dl_status, asset_size, asset_content_name
                FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.asset_id_fk=tts_assets.id
                    INNER JOIN tts_mods
                        ON tts_mod_assets.mod_id_fk=tts_mods.id
                WHERE asset_size == 0 AND mod_asset_ignore_missing == 0 AND asset_dl_status != ""
                """
                ),
            )
            assets = cursor.fetchall()
        return assets

    async def download_done(self, asset: dict) -> None:
        # Don't overwrite the calculated filepath with something that is empty
        async with aiosqlite.connect(self.db_path) as db:
            if asset["filename"] is None or asset["filename"] == "":
                await db.execute(
                    """
                    UPDATE tts_assets
                    SET
                        asset_dl_status=?, asset_steam_sha1=?, asset_content_name=?
                    WHERE asset_url=?
                    """,
                    (
                        asset["dl_status"],
                        asset["steam_sha1"],
                        asset["content_name"],
                        asset["url"],
                    ),
                )
            else:
                ext = ""
                path, filename = os.path.split(asset["filename"])
                if filename != "":
                    filename, ext = os.path.splitext(filename)

                await db.execute(
                    """
                    UPDATE tts_assets
                    SET
                        asset_filename=?, asset_path=?, asset_ext=?,
                        asset_mtime=?, asset_size=?, asset_dl_status=?,
                        asset_content_name=?, asset_steam_sha1=?
                    WHERE asset_url=?
                    """,
                    (
                        filename,
                        path,
                        ext,
                        asset["mtime"],
                        asset["size"],
                        asset["dl_status"],
                        asset["content_name"],
                        asset["steam_sha1"],
                        asset["url"],
                    ),
                )

            # dl_status is empty if the download was succesfull
            if asset["dl_status"] == "":
                # Set mod asset counts containing this asset to -1
                # to represent an update to the system
                await db.execute(
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
            await db.commit()

    async def get_missing_assets(self, mod_filename: str) -> list:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT
                    asset_url, asset_mtime, asset_sha1,
                    asset_steam_sha1, mod_asset_trail
                FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.asset_id_fk=tts_assets.id
                    INNER JOIN tts_mods
                        ON tts_mod_assets.mod_id_fk=tts_mods.id
                WHERE mod_filename=?
                """,
                (mod_filename,),
            ) as cursor:
                results = await cursor.fetchall()
        urls = []
        for result in results:
            skip = True
            # Has this file already been downloaded, if so we generally skip it
            if result[1] != 0:
                # Check if SHA1 computed from file contents matches steam
                # filename SHA1
                if (
                    result[2] != ""
                    and result[2] != "0"
                    and result[3] != ""
                    and result[3] != "0"
                ):
                    if result[2] != result[3]:
                        # We have a SHA1 mismatch so attempt to re-download
                        skip = False
            else:
                # File doesn't exist, so download it
                skip = False
            if not skip:
                urls.append((result[0], trailstring_to_trail(result[4])))
        return urls

    def scan_cached_assets(self):
        scan_time = time.time()
        new_count = 0

        with sqlite3.connect(self.db_path) as db:
            ignore_paths = ["Mods", "Workshop"]
            ignore_files = ["sha1-verified", "sha1-verified.txt"]

            cursor = db.execute(
                """
                SELECT asset_filename, asset_ext, asset_path
                FROM tts_assets
                WHERE asset_size > 0
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
            for root, dirnames, files in os.walk(self.mod_dir, topdown=True):
                new_count = 0
                path = pathlib.PurePath(root).name

                if path in TTS_RAW_DIRS or path == "" or path in ignore_paths:
                    if path != "Mods":
                        # Do not recurse into directories we are ignoring
                        while len(dirnames) > 0:
                            _ = dirnames.pop()
                    continue

                files_in_path = len(files)

                yield path, new_count, 0, files_in_path

                new_files = set(files).difference(asset_filenames)
                old_count = len(files) - len(new_files)

                for i, filename in enumerate(new_files):
                    filename = Path(filename)
                    if filename.stem in ignore_files:
                        continue
                    if filename.suffix.upper() in FILES_TO_IGNORE:
                        continue

                    if i % 50 == 0:
                        yield path, new_count, old_count + i, files_in_path

                    filepath = Path(root) / filename
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
                            cf = get_fs_path_from_extension(
                                "", correct_ext, filename.stem
                            )
                            if cf is None:
                                # TODO: This shouldn't happen.  Throw error?
                                continue

                            correct_path = pathlib.PurePath(cf).parent

                            src = Path(root) / filename
                            backup_dest = Path(self.config.asset_backup_dir) / filename
                            correct_filepath = (
                                Path(self.config.tts_mods_dir) / correct_path / filename
                            ).with_suffix(correct_ext)
                            asset_filepath = (
                                Path(self.config.tts_mods_dir)
                                / asset_paths[i]
                                / asset_stems[i]
                            ).with_suffix(asset_exts[i])

                            if src.exists() and asset_filepath.exists():
                                # We have two files with same name but different extensions.
                                # We know this one is correct, so move the other to backup
                                # and update the DB accordingly.
                                self.post_message(
                                    UpdateLog(
                                        (
                                            f"Found duplicate files `{asset_stems[i]}` with "
                                            f"extensions: `{asset_exts[i]}` and `{src.suffix}`. "
                                            f"Moving latter to backup directory."
                                        )
                                    )
                                )
                                move(asset_filepath, backup_dest)

                            if asset_exts[i] != filename.suffix:
                                # Asset exists in DB but has a different extension than current file
                                if filename.suffix == correct_ext:
                                    # The file has correct extension, DB is wrong
                                    self.post_message(
                                        UpdateLog(
                                            (
                                                f"Found DB entry (`{asset_filepath}` with wrong ext. "
                                                f"Expected `{correct_ext}`. Updating."
                                            )
                                        )
                                    )
                                    if src != correct_filepath:
                                        # The filename and suffix is correct but in the wrong directory.
                                        # Move it for now, and the DB will get updated on the next pass
                                        move(src, correct_filepath)
                                        self.post_message(
                                            UpdateLog(
                                                (
                                                    f"Moved `{src}` to `{correct_filepath}`"
                                                )
                                            )
                                        )
                                        filepath = correct_filepath
                                    update_asset = True
                                else:
                                    # The file has incorrect extension, DB is correct
                                    self.post_message(
                                        UpdateLog(
                                            (
                                                f"Found asset (`{filename}`) "
                                                f"with wrong ext. "
                                                f"Expected `{correct_ext}`."
                                            )
                                        )
                                    )
                                    if correct_filepath.exists():
                                        self.post_message(
                                            UpdateLog(
                                                (
                                                    f"Correct file already "
                                                    f"exists, moving `{src}`  "
                                                    f"file to `{backup_dest}`"
                                                )
                                            )
                                        )
                                        # Remove the files that have
                                        # the wrong extension
                                        move(src, backup_dest)
                                    else:
                                        move(src, correct_filepath)
                                        self.post_message(
                                            UpdateLog(
                                                (
                                                    f"Moved `{src}` to `{correct_filepath}`"
                                                )
                                            )
                                        )
                                    filepath = correct_filepath

                            if asset_paths[i] != path:
                                # Asset exists in DB but has the wrong path.
                                if Path(path) == correct_path:
                                    self.post_message(
                                        UpdateLog(
                                            (
                                                f"Found DB entry (`{asset_filepath}`) with wrong path"
                                                f"Expected `{correct_path}`. Updating DB."
                                            )
                                        )
                                    )
                                    update_asset = True
                                    # Since the incorrect file is in another path, it will get
                                    # moved later (or possibly on the next scan) as the conflict
                                    # will trigger again.

                    if update_asset:
                        new_count += 1
                        size = os.path.getsize(filepath)
                        mtime = os.path.getmtime(filepath)
                        assets.append(
                            (
                                filepath.parent.stem,
                                filepath.stem,
                                filepath.suffix,
                                mtime,
                                size,
                                1,
                            )
                        )

            yield "Complete", new_count, 0, 0

            cursor = db.executemany(
                """
                INSERT INTO tts_assets
                    (asset_path, asset_filename, asset_ext,
                    asset_mtime, asset_size, asset_new)
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

            db.execute(
                """
                UPDATE tts_app
                SET asset_last_scan_time=?
                WHERE id=1
            """,
                (scan_time,),
            )

            db.commit()

    def update_mod_assets(
        self, mod_filename: str, mod_mtime, force_file_check=False
    ) -> int:
        if mod_filename.find("Workshop") == 0:
            mod_path = Path(self.mod_dir) / mod_filename
        else:
            mod_path = Path(self.save_dir) / mod_filename

        mod_parser = ModParser(str(mod_path))

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

                # Combine the URLs/filenames from the mod with
                # what is already in the DB (from filesystem scan
                # and possible previous mod scan)

                # Since the filesystem is scanned before the mods
                # are processed, filenames may exist in the DB
                # before the associated URLs are discovered in the mod
                # file.  Therefore, when we conflict on the filename,
                # we still need to update the URL.
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
                    INSERT INTO tts_mod_assets
                        (asset_id_fk, mod_id_fk, mod_asset_trail)
                    VALUES (
                        (SELECT tts_assets.id FROM tts_assets
                        WHERE asset_filename=?),
                        (SELECT tts_mods.id FROM tts_mods
                        WHERE mod_filename=?),
                        ?)
                    ON CONFLICT (asset_id_fk, mod_id_fk)
                    DO UPDATE SET
                        mod_asset_trail=excluded.mod_asset_trail
                    """,
                    tuple(
                        zip(filenames, [mod_filename] * len(filenames), trailstrings)
                    ),
                )
                # new_asset_trails = cursor.rowcount

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
                        asset_id_fk = (SELECT tts_assets.id FROM tts_assets
                                        WHERE asset_url=?)
                    AND
                        mod_id_fk = (SELECT tts_mods.id FROM tts_mods
                                        WHERE mod_filename=?)
                    """,
                    tuple(zip(removed_assets, [mod_filename] * len(removed_assets))),
                )

                deleted_files = []
                if force_file_check:
                    cursor = db.execute(
                        """
                        SELECT
                            asset_path, asset_filename, asset_ext
                        FROM
                            tts_assets
                        WHERE asset_url IN ({0})
                        """.format(
                            ",".join("?" for _ in urls)
                        ),
                        urls,
                    )
                    results = cursor.fetchall()
                    for path, filename, ext in results:
                        if (
                            not (Path(self.mod_dir) / path / filename)
                            .with_suffix(ext)
                            .exists()
                        ):
                            deleted_files.append(filename)

                if len(deleted_files) > 0:
                    cursor = db.execute(
                        """
                        UPDATE tts_assets
                        SET asset_sha1="", asset_mtime=0, asset_size=0
                        WHERE asset_filename IN ({0})
                        """.format(
                            ",".join("?" for _ in deleted_files)
                        ),
                        deleted_files,
                    )

                if new_asset_count > 0 or removed_asset_count > 0:
                    db.execute(
                        """
                        UPDATE tts_mods
                        SET mod_total_assets=-1, mod_missing_assets=-1,
                            mod_size=-1, mod_max_asset_mtime=UNIXEPOCH()
                        WHERE mod_filename=?
                        """,
                        (mod_filename,),
                    )
                db.commit()
        return new_asset_count

    def get_mods_using_asset(self, url: str) -> list:
        results = []
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_filename, mod_name
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
        return results

    async def get_mods_using_asset_a(self, url: str) -> list:
        results = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT mod_filename, mod_name
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
            ) as cursor:
                results = await cursor.fetchall()
        return results

    def get_mod_assets(
        self, mod_filename: str, parse_only=False, force_refresh=False, all_nodes=False
    ) -> list:
        assets = []
        if mod_filename == "sha1":
            return self.get_sha1_mismatches()
        elif mod_filename == "missing":
            return self.get_missing()
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
            if result is None:
                refresh_mod = True
            else:
                prev_mod_mtime = result[0]
                try:
                    mod_mtime = os.path.getmtime(mod_path)
                    if mod_mtime > prev_mod_mtime:
                        refresh_mod = True
                except FileNotFoundError:
                    # Mod has been deleted from FS but not DB
                    refresh_mod = False

            if refresh_mod:
                self.update_mod_assets(
                    mod_filename, mod_mtime, force_file_check=force_refresh
                )

            if not parse_only:
                trails = {}
                if all_nodes:
                    mod_parser = ModParser(mod_path)
                    all_assets = [
                        (url, trail) for trail, url in mod_parser.urls_from_mod(True)
                    ]

                    for url, trail in all_assets:
                        trail = trail_to_trailstring(trail)
                        if url in trails:
                            trails[url].append(trail)
                        else:
                            trails[url] = [
                                trail,
                            ]

                db.row_factory = asset_factory
                cursor = db.execute(
                    (
                        """
                    SELECT
                        (asset_path || "/" || asset_filename || asset_ext) as filename,
                        asset_url, asset_mtime, asset_sha1, asset_steam_sha1,
                        mod_asset_trail as trail, asset_dl_status, asset_size,
                        asset_content_name, mod_asset_ignore_missing as ignore_missing
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
                assets = cursor.fetchall()
                if all_nodes:
                    for asset in assets:
                        asset["trail"] = trails[asset["url"]]
        return assets

    async def get_mod_assets_a(self, mod_filename: str) -> list:
        assets = []
        if mod_filename == "sha1":
            # TODO: Not needed yet
            return assets

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = asset_factory
            async with db.execute(
                (
                    """
                SELECT
                    (asset_path || "/" || asset_filename || asset_ext) as filename,
                    asset_url, asset_mtime, asset_sha1, asset_steam_sha1,
                    mod_asset_trail as trail, asset_dl_status, asset_size,
                    asset_content_name, mod_asset_ignore_missing as ignore_missing
                FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.asset_id_fk=tts_assets.id
                    INNER JOIN tts_mods
                        ON tts_mod_assets.mod_id_fk=tts_mods.id
                WHERE mod_filename=?
                """
                ),
                (mod_filename,),
            ) as cursor:
                assets = await cursor.fetchall()

        return assets

    def get_content_names(self) -> list:
        with sqlite3.connect(self.db_path) as db:
            # Check if we have this mod in our DB
            cursor = db.execute(
                """
                SELECT asset_url, asset_content_name, asset_sha1
                FROM tts_assets
                WHERE asset_content_name != ""
                """,
            )
            results = cursor.fetchall()
            return list(zip(*results))

    def get_blank_content_names(self) -> list:
        with sqlite3.connect(self.db_path) as db:
            # Check if we have this mod in our DB
            cursor = db.execute(
                """
                SELECT asset_url
                FROM tts_assets
                WHERE
                    asset_content_name == ""
                    AND
                    asset_url IS NOT NULL
                    AND
                    asset_size > 0
                    AND
                    asset_dl_status == ""
                """,
            )
            results = cursor.fetchall()

            return list(zip(*results))[0]

    def set_content_names(self, urls, content_names) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.executemany(
                """
                UPDATE tts_assets
                SET asset_content_name=?
                WHERE asset_url=?
                """,
                tuple(zip(content_names, urls)),
            )
            db.commit()

    def set_dl_status(self, url, dl_status) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE tts_assets
                SET asset_dl_status=?
                WHERE asset_url=?
                """,
                (dl_status, url),
            )
            db.commit()

    def set_ignore(self, mod_filename, url, ignore):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE tts_mod_assets
                SET mod_asset_ignore_missing=?
                WHERE
                    asset_id_fk = (SELECT tts_assets.id FROM tts_assets
                                    WHERE asset_url=?)
                AND
                    mod_id_fk = (SELECT tts_mods.id FROM tts_mods
                                    WHERE mod_filename=?)
                """,
                (1 if ignore else 0, url, mod_filename),
            )
            db.execute(
                """
                UPDATE tts_mods
                SET mod_missing_assets=-1
                WHERE mod_filename=?
                """,
                (mod_filename,),
            )
            db.commit()

    def copy_asset(self, src_url, dest_url):
        if src_url == dest_url:
            return

        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT asset_path, asset_filename, asset_ext, asset_size, asset_content_name
                FROM tts_assets
                WHERE asset_url=?
                """,
                (src_url,),
            )
            result = cursor.fetchone()
            # No match, or our src url is not on disk
            if result is None or result[3] == 0:
                self.post_message(
                    UpdateLog(
                        f"Cannot copy `{src_url}` because the asset does not exist."
                    )
                )
                return
            src_path = result[0]
            src_ext = result[2]
            src_filepath = (Path(self.mod_dir) / src_path / result[1]).with_suffix(
                src_ext
            )
            content_name = result[4]

            cursor = db.execute(
                """
                SELECT asset_filename, asset_content_name
                FROM tts_assets
                WHERE asset_url=?
                """,
                (dest_url,),
            )
            result = cursor.fetchone()
            if result is None:
                return
            dest_filepath = (Path(self.mod_dir) / src_path / result[0]).with_suffix(
                src_ext
            )
            dest_content_name = result[1]

            if content_name != "" and dest_content_name == "":
                db.execute(
                    """
                    UPDATE tts_assets
                    SET asset_content_name=?
                    WHERE asset_url=?
                    """,
                    (content_name, dest_url),
                )
                db.commit()

        self.post_message(UpdateLog(f"Copying `{src_filepath}` to `{dest_filepath}`"))
        copy(src_filepath, dest_filepath)

    def find_asset(self, url, trail=None, max_matches=20):
        sha_match = ""
        name_matches = []
        fuzzy_matches = []
        total_matches = 0

        with sqlite3.connect(self.db_path) as db:
            content_name = get_content_name(url)
            if content_name == "":
                cursor = db.execute(
                    """
                    SELECT asset_content_name
                    FROM tts_assets
                    WHERE asset_url=?
                    """,
                    (url,),
                )
                result = cursor.fetchone()
                if result is not None:
                    content_name = result[0]

            steam_sha1 = get_steam_sha1_from_url(url)

            if steam_sha1 != "":
                cursor = db.execute(
                    """
                    SELECT asset_url, asset_content_name
                    FROM tts_assets
                    WHERE asset_sha1=?
                    """,
                    (steam_sha1,),
                )
                result = cursor.fetchone()
                if result is not None and result[0] != url:
                    sha_match = result[0], result[1]
                    total_matches += 1

            if content_name != "":
                cursor = db.execute(
                    """
                    SELECT asset_url, asset_content_name
                    FROM tts_assets
                    WHERE asset_content_name LIKE ?
                    """,
                    (content_name,),
                )
                results = cursor.fetchall()
                for result in results:
                    if result[0] != url and result[0] not in sha_match:
                        name_matches.append((result[0], result[1]))
                        total_matches += 1

                content_name, ext = os.path.splitext(content_name)
                cursor = db.execute(
                    """
                    SELECT asset_url, asset_content_name
                    FROM tts_assets
                    WHERE asset_content_name LIKE ? AND asset_ext LIKE ?
                    """,
                    ("%" + recodeURL(content_name) + "%", "%" + ext),
                )
                results = cursor.fetchall()
                for result in results:
                    if total_matches > max_matches:
                        break
                    if (
                        result[0] != url
                        and result[0] != sha_match
                        and result[0] not in name_matches
                    ):
                        fuzzy_matches.append((result[0], result[1]))
                        total_matches += 1

                cursor = db.execute(
                    """
                    SELECT asset_url, asset_content_name
                    FROM tts_assets
                    WHERE asset_content_name LIKE ? AND asset_ext LIKE ?
                    """,
                    ("%" + content_name + "%", "%" + ext),
                )
                results = cursor.fetchall()
                for result in results:
                    if total_matches > max_matches:
                        break
                    if (
                        result[0] != url
                        and result[0] != sha_match
                        and result[0] not in name_matches
                        and result[0] not in fuzzy_matches
                    ):
                        fuzzy_matches.append((result[0], result[1]))
                        total_matches += 1

        matches = []
        if sha_match != "":
            matches += [(sha_match, "SHA1")]

        matches += [(url, "Exact Name") for url in name_matches]
        matches += [(url, "Fuzzy Match") for url in fuzzy_matches]

        return matches

    async def find_asset_a(self, url, trail=None):
        matches = []

        async with aiosqlite.connect(self.db_path) as db:
            content_name = get_content_name(url)
            if content_name == "":
                async with db.execute(
                    """
                    SELECT asset_content_name
                    FROM tts_assets
                    WHERE asset_url=?
                    """,
                    (url,),
                ) as cursor:
                    result = await cursor.fetchone()
                if result is not None:
                    content_name = result[0]

            steam_sha1 = get_steam_sha1_from_url(url)

            if steam_sha1 != "":
                async with db.execute(
                    """
                    SELECT asset_url
                    FROM tts_assets
                    WHERE asset_sha1=?
                    """,
                    (steam_sha1,),
                ) as cursor:
                    result = await cursor.fetchone()
                if result is not None and result[0] != url:
                    matches.append((result[0], "sha1"))

            if content_name != "":
                async with db.execute(
                    """
                    SELECT asset_url
                    FROM tts_assets
                    WHERE asset_content_name=?
                    """,
                    (content_name,),
                ) as cursor:
                    result = await cursor.fetchone()
                if result is not None and result[0] != url:
                    matches.append((result[0], "Exact Name"))

                # Ignore the extension for the fuuzzy searches
                content_name = os.path.splitext(content_name)[0]
                async with db.execute(
                    """
                    SELECT asset_url
                    FROM tts_assets
                    WHERE asset_content_name LIKE ?
                    """,
                    ("%" + recodeURL(content_name) + "%",),
                ) as cursor:
                    result = await cursor.fetchone()
                if result is not None and result[0] != url:
                    matches.append((result[0], "Fuzzy Recode"))

                async with db.execute(
                    """
                    SELECT asset_url
                    FROM tts_assets
                    WHERE asset_content_name LIKE ?
                    """,
                    ("%" + content_name + "%",),
                ) as cursor:
                    result = await cursor.fetchone()
                if result is not None and result[0] != url:
                    matches.append((result[0], "Fuzzy Name"))

        return matches

    def get_asset(self, url: str, mod_filename: str = "") -> dict:
        asset = {}
        mods = self.get_mods_using_asset(url)
        if len(mods) > 0 and (
            mod_filename == "" or mod_filename == "sha1" or mod_filename == "missing"
        ):
            mod_filename = mods[0][0]
        mod_names = [mod_name for _, mod_name in mods]

        with sqlite3.connect(self.db_path) as db:
            db.row_factory = asset_factory
            if mod_filename == "":
                cursor = db.execute(
                    """
                    SELECT
                        (asset_path || "/" || asset_filename || asset_ext) as filename,
                        asset_url, asset_mtime, asset_sha1, asset_steam_sha1,
                        asset_dl_status, asset_size, asset_content_name, "" as trail
                    FROM tts_assets
                    WHERE asset_url=?
                    """,
                    (url,),
                )
            else:
                cursor = db.execute(
                    """
                    SELECT
                        asset_filename, (asset_path || "/" || asset_filename || asset_ext) as filename,
                        asset_url, asset_mtime, asset_sha1, asset_steam_sha1,
                        mod_asset_trail as trail, asset_dl_status, asset_size,
                        asset_content_name
                    FROM tts_assets
                        INNER JOIN tts_mod_assets
                            ON tts_mod_assets.asset_id_fk=tts_assets.id
                        INNER JOIN tts_mods
                            ON tts_mod_assets.mod_id_fk=tts_mods.id
                    WHERE mod_filename=? AND asset_url=?
                    """,
                    (
                        mod_filename,
                        url,
                    ),
                )
            asset = cursor.fetchone()
            asset["mods"] = sorted(mod_names)
        return asset

    def delete_asset(self, url):
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT asset_path, asset_filename, asset_ext, asset_size
                FROM tts_assets
                WHERE asset_url=?
                """,
                (url,),
            )
            result = cursor.fetchone()
            # No match, or our src url is not on disk
            if result is None or result[3] == 0:
                self.post_message(
                    UpdateLog(
                        f"Cannot delete `{url}` because the asset does not exist."
                    )
                )
                return
            src_path = result[0]
            src_ext = result[2]
            src_filepath = (Path(self.mod_dir) / src_path / result[1]).with_suffix(
                src_ext
            )

        self.post_message(UpdateLog(f"Deleting `{src_filepath}`"))
        os.remove(src_filepath)
