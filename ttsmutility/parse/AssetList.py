import os
import os.path
import sqlite3
import atexit
import json
import re
import sys
import pathlib
import time

from ttsmutility import *
from ttsmutility.parse.FileFinder import (
    ALL_VALID_EXTS,
    find_file,
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
    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.mod_dir = mod_dir
        self.save_dir = save_dir

    def urls_from_save(self, mod_dir):
        with open(mod_dir, "r", encoding="utf-8") as infile:
            try:
                save = json.load(infile, strict=False)
            except UnicodeDecodeError:
                raise IllegalSavegameException

        if not isinstance(save, dict):
            raise IllegalSavegameException

        return self.seekURL(save)

    def seekURL(self, dic, trail=[], done=None):
        """Recursively search through the save game structure and return URLs
        and the paths to them.

        """
        if done is None:
            done = set()

        for k, v in dic.items():
            newtrail = trail + [k]

            if k == "AudioLibrary":
                for elem in v:
                    try:
                        # It appears that AudioLibrary items are mappings of form
                        # “Item1” → URL, “Item2” → audio title.
                        url = elem["Item1"]
                        recode = recodeURL(url)
                        if recode in done:
                            continue
                        done.add(recode)
                        yield (newtrail, url)
                    except KeyError:
                        raise NotImplementedError(
                            "AudioLibrary has unexpected structure: {}".format(v)
                        )

            elif isinstance(v, dict):
                yield from self.seekURL(v, newtrail, done)

            elif isinstance(v, list):
                for elem in v:
                    if not isinstance(elem, dict):
                        continue
                    yield from self.seekURL(elem, newtrail, done)

            elif k.lower().endswith("url"):
                # We don’t want tablet URLs.
                if k == "PageURL":
                    continue

                # Some URL keys may be left empty.
                if not v:
                    continue

                # Deck art URLs can contain metadata in curly braces
                # (yikes).
                v = re.sub(r"{.*}", "", v)
                recode = recodeURL(v)
                if recode in done:
                    continue
                done.add(recode)
                yield (newtrail, v)

            elif k == "LuaScript":
                NO_EXT_SITES = [
                    "steamusercontent.com",
                    "pastebin.com",
                    "paste.ee",
                    "drive.google.com",
                    "steamuserimages-a.akamaihd.net",
                ]
                # Parse lauscript for potential URLs
                url_matches = re.findall(
                    r"((?:http|https):\/\/(?:[\w\-_]+(?:(?:\.[\w\-_]+)+))(?:[\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?)",
                    v,
                )
                for url in url_matches:
                    valid_url = False

                    # Detect if URL ends in a valid extension or is from a site which doesn't use extension
                    for site in NO_EXT_SITES:
                        if url.lower().find(site) >= 0:
                            valid_url = True
                            break
                    else:
                        for ext in ALL_VALID_EXTS:
                            if url.lower().find(ext.lower()) >= 0:
                                valid_url = True
                                break

                    if valid_url:
                        recode = recodeURL(url)
                        if recode in done:
                            continue
                        done.add(recode)
                        yield (newtrail, url)

    def get_sha1_info(self, filepath: str) -> None:
        # return sha1, steam_sha1, sha1_mtime
        path, filename = os.path.split(filepath)
        if filename != "":
            filename, _ = os.path.splitext(filename)

        with sqlite3.connect(DB_NAME) as db:
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
        with sqlite3.connect(DB_NAME) as db:
            db.execute(
                """
                UPDATE tts_assets
                SET asset_sha1=?, asset_steam_sha1=?, asset_sha1_mtime=?
                WHERE asset_filename=? and asset_path=?
                """,
                (sha1, steam_sha1, sha1_mtime, filename, path),
            )

    def get_sha1_mismatches(self):
        with sqlite3.connect(DB_NAME) as db:
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
        with sqlite3.connect(DB_NAME) as db:
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

    def get_missing_assets(self, mod_filename: str) -> list:
        with sqlite3.connect(DB_NAME) as db:
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
        with sqlite3.connect(DB_NAME) as db:
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
                    mtime = os.path.getmtime(os.path.join(root, filename))
                    if mtime < prev_scan_time:
                        continue
                    size = os.path.getsize(os.path.join(root, filename))
                    filename, ext = os.path.splitext(filename)
                    if ext.upper() in FILES_TO_IGNORE:
                        continue
                    assets.append((path, filename, ext, mtime, size, 1))
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

    def update_mod_assets(self, mod_filename: str) -> int:
        if mod_filename.find("Workshop") == 0:
            mod_path = os.path.join(self.mod_dir, mod_filename)
        else:
            mod_path = os.path.join(self.save_dir, mod_filename)

        mod_assets = [
            (recodeURL(url), url, trail) for trail, url in self.urls_from_save(mod_path)
        ]

        new_asset_count = 0

        with sqlite3.connect(DB_NAME) as db:
            if len(mod_assets) > 0:
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
                    SET mod_mtime=?, mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1
                    WHERE mod_filename=?
                    """,
                    (os.path.getmtime(mod_path), mod_filename),
                )
            db.commit()
        return new_asset_count

    def get_mods_using_asset(self, url: str) -> list:
        results = []
        with sqlite3.connect(DB_NAME) as db:
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

    def get_mod_assets(self, mod_filename: str, parse_only=False) -> list:
        assets = []
        if mod_filename.find("Workshop") == 0:
            mod_path = os.path.join(self.mod_dir, mod_filename)
        else:
            mod_path = os.path.join(self.save_dir, mod_filename)

        prev_mod_mtime = 0
        mod_mtime = 0

        with sqlite3.connect(DB_NAME) as db:
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
            refresh_mod = False
            if result == None:
                refresh_mod = True
            else:
                prev_mod_mtime = result[0]
                mod_mtime = os.path.getmtime(mod_path)
                if mod_mtime > prev_mod_mtime:
                    refresh_mod = True

            if refresh_mod:
                self.update_mod_assets(mod_filename)

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
