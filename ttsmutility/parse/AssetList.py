import os
import os.path
import sqlite3
import pathlib
import time
from pathlib import Path

from .ModParser import ModParser
from ..data.config import load_config
from ..parse.FileFinder import (
    recodeURL,
    TTS_RAW_DIRS,
    FILES_TO_IGNORE,
    trailstring_to_trail,
    trail_to_trailstring,
)


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
        config = load_config()
        self.db_path = Path(config.db_path)
        self.mod_dir = Path(config.tts_mods_dir)
        self.save_dir = Path(config.tts_saves_dir)
        self.mod_infos = {}

    def get_mod_info(self, mod_filename: Path) -> dict:
        return self.mod_infos[mod_filename]

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
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT asset_url
                FROM tts_assets
                WHERE tts_assets.asset_steam_sha1 != ""
                    AND tts_assets.asset_sha1 != tts_assets.asset_steam_sha1
                """,
            )
            result = cursor.fetchall()
        if len(result) > 0:
            return list(zip(*result))[0]
        else:
            return []

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

    def scan_cached_assets(self) -> int:
        assets = []
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
            ignore_files = ["sha1-verified"]

            for root, _, files in os.walk(self.mod_dir, topdown=True):
                path = pathlib.PurePath(root).name

                if path in TTS_RAW_DIRS or path == "" or path in ignore_paths:
                    continue

                for filename in files:
                    if filename in ignore_files:
                        continue
                    filename = Path(root) / filename
                    if filename.suffix.upper() in FILES_TO_IGNORE:
                        continue
                    stat = filename.stat()
                    mtime = stat.st_mtime
                    if mtime < prev_scan_time:
                        continue
                    size = stat.st_size
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

                if new_asset_count > 0:
                    db.execute(
                        """
                        UPDATE tts_mods
                        SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1
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
            results = list(zip(*cursor.fetchall()))[0]
        return results

    def get_mod_assets(
        self, mod_filename: str, parse_only=False, force_refresh=False
    ) -> list:
        assets = []
        if mod_filename.find("Workshop") == 0:
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
                    SELECT asset_url, asset_path, asset_filename, asset_ext, asset_mtime, asset_sha1, mod_asset_trail, asset_dl_status, asset_size, asset_content_name
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
                            "trail": result[6],
                            "dl_status": result[7],
                            "fsize": result[8],
                            "content_name": result[9],
                        }
                    )

        return assets
