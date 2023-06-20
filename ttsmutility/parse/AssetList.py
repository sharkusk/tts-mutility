import os
import os.path
import sqlite3
import atexit
import json
import re
import sys

from ttsmutility import *
from ttsmutility.parse.FileFinder import ALL_VALID_EXTS, find_file, recodeURL


class IllegalSavegameException(ValueError):
    def __init__(self):
        super().__init__("not a Tabletop Simulator savegame")


class AssetList:
    def __init__(self, dir_path: str) -> None:
        self.dir_path = dir_path
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()

        # TODO: Get this to work (it doesn't seem to be called)
        # atexit.register(self._close_connection)

    def _close_connection(self):
        self.cursor.close()
        self.conn.close()

    def url_reformat(self, url):
        replacements = [
            ("http://", ""),
            ("https://", ""),
            ("cloud-3.steamusercontent.com/ugc", ".steamuser."),
            ("www.dropbox.com/s", ".dropbox."),
        ]
        for x, y in replacements:
            url = url.replace(x, y)
        return url

    def trail_reformat(self, trail):
        replacements = [
            ("ObjectStates", "O.S"),
            ("Custom", "C."),
            ("ContainedObjects", "Con.O"),
        ]
        for x, y in replacements:
            trail = trail.replace(x, y)
        return trail

    def urls_from_save(self, mod_path):
        with open(mod_path, "r", encoding="utf-8") as infile:
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
                        record = recodeURL(url)
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

    def parse_assets(self, mod_filename: str, parse_only=False) -> list:
        assets = []
        mod_path = os.path.join(self.dir_path, mod_filename)
        modified_db = False
        self.cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.asset_id_fk=tts_assets.id
                    INNER JOIN tts_mods
                        ON tts_mod_assets.mod_id_fk=tts_mods.id
                WHERE mod_filename=?
            )""",
            (mod_filename,),
        )
        result = self.cursor.fetchone()
        parse_file = False
        if result[0] == 0:
            parse_file = True
        else:
            self.cursor.execute(
                """
                SELECT mod_mtime
                FROM tts_mods
                WHERE mod_filename=?
                """,
                (mod_filename,),
            )
            result = self.cursor.fetchone()
            if result is not None:
                if os.path.getmtime(mod_path) > result[0]:
                    parse_file = True

        if parse_file:
            old_dir = os.getcwd()
            os.chdir(self.dir_path)

            assets_i = []
            mod_assets_i = []

            mods_changed = set()

            for trail, url in self.urls_from_save(mod_path):
                asset_filename, mtime = find_file(url, trail)
                trail_string = "->".join(["%s"] * len(trail)) % tuple(trail)

                # This is assumed to be unique, but can be "not found" so in that case make it NULL to
                # avoid a DB unique constraint error
                if asset_filename == "":
                    asset_filename = None

                if not parse_only:
                    assets.append(
                        {
                            "url": url,
                            "asset_filename": asset_filename,
                            "sha1": "",
                            "mtime": mtime,
                            "trail": trail_string,
                        }
                    )

                assets_i.append((url, recodeURL(url), asset_filename, "", mtime))
                mod_assets_i.append((recodeURL(url), mod_filename, trail_string))

                mods_changed.add(mod_filename)

            self.cursor.executemany(
                """
                INSERT OR IGNORE INTO tts_assets
                    (asset_url, asset_url_recode, asset_filepath, asset_sha1, asset_mtime)
                VALUES
                    (?, ?, ?, ?, ?)
                """,
                assets_i,
            )

            self.cursor.executemany(
                """
                INSERT OR IGNORE INTO tts_mod_assets
                    (asset_id_fk, mod_id_fk, mod_asset_trail)
                VALUES (
                    (SELECT tts_assets.id FROM tts_assets WHERE asset_url_recode=?),
                    (SELECT tts_mods.id FROM tts_mods WHERE mod_filename=?),
                    ?)
                """,
                mod_assets_i,
            )

            self.cursor.execute(
                """
                UPDATE tts_mods
                SET mod_mtime=?
                WHERE mod_filename=?
                """,
                (os.path.getmtime(mod_path), mod_filename),
            )

            if len(mods_changed) > 0:
                self.cursor.executemany(
                    """
                    UPDATE tts_mods
                    SET total_assets=-1, missing_assets=-1
                    WHERE mod_filename=?
                    """,
                    [tuple(mods_changed)],
                )

            modified_db = True
            os.chdir(old_dir)
        else:
            if not parse_only:
                old_dir = os.getcwd()
                os.chdir(self.dir_path)
                self.cursor.execute(
                    (
                        """
                    SELECT asset_url, asset_filepath, asset_mtime, asset_sha1, mod_asset_trail
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
                results = self.cursor.fetchall()
                for result in results:
                    if result[1] == "":
                        # Check if this file happens to exist in the filesystem
                        asset_filename, mtime = find_file(
                            result[0], result[4].split("->")
                        )
                        if asset_filename != "":
                            modified_db = True
                            self.cursor.execute(
                                """
                                UPDATE INTO tts_assets
                                SET asset_filepath=?, asset_sha1=?, asset_mtime=?
                                WHERE asset_url=?
                                """,
                                (asset_filename, "", mtime, result[0]),
                            )

                    else:
                        asset_filename = result[1]

                    assets.append(
                        {
                            "url": result[0],
                            "asset_filename": asset_filename,
                            "mtime": result[2],
                            "sha1": result[3],
                            "trail": result[4],
                        }
                    )
                os.chdir(old_dir)

        if modified_db:
            self.conn.commit()
        return assets
