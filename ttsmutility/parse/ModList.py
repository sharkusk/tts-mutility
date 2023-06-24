import json
import os.path
from glob import glob
import sqlite3
import re

from ttsmutility import *


class ModList:
    def __init__(self, dir_path: str, is_save=False) -> None:
        self.dir_path = dir_path
        self.is_save = is_save

    def get_mod_name(self, filename: str) -> str:
        file_path = os.path.join(self.dir_path, filename)
        if False:
            # This is really slow as the entire JSON file is processed.
            with open(file_path, "r", encoding="utf-8") as infile:
                save = json.load(infile)
            return save["SaveName"]
        else:
            with open(file_path, "r", encoding="utf-8") as infile:
                for line in infile:
                    if "SaveName" in line:
                        # "SaveName": "Defenders of the Realm",
                        return re.findall('"SaveName": "(.*)"', line)[0]
        return ""

    def get_mods_needing_asset_refresh(self):
        with sqlite3.connect(DB_NAME) as db:
            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                WHERE (mod_total_assets=-1 OR mod_missing_assets=-1 OR mod_size=-1)""",
            )
            result = cursor.fetchall()
            # Results are returned as a list of tuples, unzip to a list of mod_filename's
            if len(result) > 0:
                part1 = list(list(zip(*result))[0])
            else:
                part1 = []

            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                WHERE id IN (
                    SELECT mod_id_fk
                    FROM tts_mod_assets
                    WHERE asset_id_fk IN (
                        SELECT id
                        FROM tts_assets
                        WHERE asset_new=1
                    )
                )
                """,
            )
            result = cursor.fetchall()
            if len(result) > 0:
                part2 = list(list(zip(*result))[0])
            else:
                part2 = []

            db.executemany(
                """
                UPDATE tts_mods
                SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1
                WHERE mod_filename=?
                """,
                result,
            )

            combined = list(set(part1 + part2))

            db.execute(
                """
                UPDATE tts_assets
                SET asset_new=0
                """,
            )

            db.commit()

        return combined

    def update_mod_counts(self, mod_filename, forced=False):
        need_total = False
        need_missing = False
        need_size = False
        if forced:
            need_total = True
            need_missing = True
            need_size = True
        else:
            with sqlite3.connect(DB_NAME) as db:
                cursor = db.execute(
                    """
                    SELECT mod_total_assets, mod_missing_assets, mod_size
                    FROM tts_mods
                    WHERE mod_filename=?
                    """,
                    (mod_filename,),
                )
                result = cursor.fetchone()
                if result is None:
                    return
                if result[0] == -1:
                    need_total = True
                if result[1] == -1:
                    need_missing = True
                if result[2] == -1:
                    need_size = True
        if need_total:
            self.count_total_assets(mod_filename)
        if need_missing:
            self.count_missing_assets(mod_filename)
        if need_size:
            self.calc_asset_size(mod_filename)

    def calc_asset_size(self, filename: str) -> int:
        with sqlite3.connect(DB_NAME) as db:
            cursor = db.execute(
                """
            SELECT SUM(asset_size)
            FROM tts_assets
            WHERE id IN (
                SELECT asset_id_fk
                FROM tts_mod_assets
                WHERE mod_id_fk IN (
                    SELECT id FROM tts_mods
                    WHERE mod_filename=?
                )
            )
            """,
                (filename,),
            )
            result = cursor.fetchone()
            if result[0] is None:
                mod_size = 0
            else:
                mod_size = result[0]
            db.execute(
                """
                UPDATE tts_mods
                SET mod_size=?
                WHERE mod_filename=?
                """,
                (mod_size, filename),
            )
            db.commit()
        return mod_size

    def count_total_assets(self, filename: str) -> int:
        with sqlite3.connect(DB_NAME) as db:
            cursor = db.execute(
                """
            SELECT COUNT(asset_id_fk)
            FROM tts_mod_assets
            WHERE mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
            """,
                (filename,),
            )
            result = cursor.fetchone()
            db.execute(
                """
                UPDATE tts_mods
                SET mod_total_assets=?
                WHERE mod_filename=?
                """,
                (result[0], filename),
            )
            db.commit()
        return result[0]

    def count_missing_assets(self, filename: str) -> int:
        with sqlite3.connect(DB_NAME) as db:
            query = """
            SELECT COUNT(asset_id_fk)
            FROM tts_mod_assets
                WHERE (
                    mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
                    AND 
                    asset_id_fk IN (SELECT id FROM tts_assets WHERE asset_mtime=?)
                )
            """
            cursor = db.execute(query, (filename, 0))
            result = cursor.fetchone()
            db.execute(
                """
                UPDATE tts_mods
                SET mod_missing_assets=?
                WHERE mod_filename=?
                """,
                (result[0], filename),
            )
            db.commit()
        return result[0]

    def get_mod_from_db(self, filename: str) -> dict or None:
        mod = None
        with sqlite3.connect(DB_NAME) as db:
            cursor = db.execute(
                """
                SELECT mod_name, mod_mtime, mod_size, mod_total_assets, mod_missing_assets
                FROM tts_mods
                WHERE mod_filename=?""",
                (filename,),
            )
            result = cursor.fetchone()
            if result is not None:
                mod = {
                    "filename": filename,
                    "name": result[0],
                    "mtime": result[1],
                    "size": result[2],
                    "total_assets": result[3],
                    "missing_assets": result[4],
                }
        return mod

    def get_mods(self, parse_only=False, sort_by="name") -> list:
        """
        Returns list of dictionary in following format:
        [{
            "filename": filename,
            "name": name,
            "mtime": mtime,
            etc (TBD)...
        },]
        """
        if os.path.exists(self.dir_path):
            mods = []
            updated_db = False
            # We want the mod filenames to be formatted: Saves/xxxx.json or Workshop/xxxx.json
            if self.is_save:
                base_dir = "Saves"
            else:
                base_dir = "Workshop"

            with sqlite3.connect(DB_NAME) as db:
                max_mods = -1  # Debug with fewer mods...
                for i, f in enumerate(
                    glob(os.path.join(base_dir, "*.json"), root_dir=self.dir_path)
                ):
                    if "WorkshopFileInfos.json" in f or "SaveFileInfos.json" in f or "TS_AutoSave" in f:
                        continue
                    if max_mods != -1 and i >= max_mods:
                        break

                    name = self.get_mod_name(f)

                    # We could have the same mod filename in both the Save and Workshop
                    # directories.
                    mod = self.get_mod_from_db(f)
                    if mod is None:
                        # Default values will come from table definition...
                        db.execute(
                            """
                            INSERT INTO tts_mods
                                (mod_filename, mod_name)
                            VALUES
                                (?, ?) 
                            """,
                            (f, name),
                        )
                        db.commit()
                        # Now that the mod is in the db, extract the data...
                        if parse_only == False:
                            mod = self.get_mod_from_db(f)

                    if parse_only:
                        mods.append((f, name))
                    else:
                        mods.append(mod)

            if parse_only:
                return tuple(zip(*sorted(mods, key=lambda mod: mod[1])))[0]
            else:
                if sort_by is not None:
                    return sorted(mods, key=lambda x: x[sort_by])
                else:
                    return mods
        return None
