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
        filepath = os.path.join(self.dir_path, filename)
        with open(filepath, "r", encoding="utf-8") as infile:
            for line in infile:
                if "SaveName" in line:
                    # "SaveName": "Defenders of the Realm",
                    return re.findall('"SaveName": "(.*)"', line)[0]
        return ""

    def get_mod_details(self, filename: str) -> str:
        filepath = os.path.join(self.dir_path, filename)
        fields = [
            "SaveName",
            "EpochTime",
            "Date",
            "VersionNumber",
            "GameMode",
            "GameType",
            "GameComplexity",
        ]
        arrays = ["PlayingTime", "PlayerCounts", "Tags"]
        details = {}
        details["mtime"] = os.path.getmtime(filepath)
        for field in fields:
            details[field] = ""
        for array in arrays:
            details[array] = []
        cur_array = ""
        pattern = re.compile(f'"(.*)": (?:"(.*)"|\[|[\d\.]+)')
        with open(filepath, "r", encoding="utf-8") as infile:
            for line in infile:
                if "{" in line:
                    # Skip first line
                    continue
                if cur_array != "":
                    if "]" in line:
                        cur_array = ""
                    else:
                        value = line.strip(' \n,"')
                        details[cur_array].append(value)
                else:
                    field, value = pattern.findall(line)[0]
                    if field in fields:
                        details[field] = value
                    elif field in arrays:
                        # Empty arrays are contained on same line
                        if "]" not in line:
                            cur_array = field
                    else:
                        # We don't care about the rest of the file..
                        break
        return details

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

    def update_mod_counts(self, mod_filename):
        counts = {}
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
            counts["total"] = result[0]
            counts["missing"] = result[1]
            counts["size"] = result[2]

        if counts["total"] == -1:
            counts["total"] = self._count_total_assets(mod_filename)
        if counts["missing"] == -1:
            counts["missing"] = self._count_missing_assets(mod_filename)
        if counts["size"] == -1:
            counts["size"] = self._calc_asset_size(mod_filename)

        return counts

    def _calc_asset_size(self, filename: str) -> int:
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

    def _count_total_assets(self, filename: str) -> int:
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

    def _count_missing_assets(self, filename: str) -> int:
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

    def get_mods(self) -> dict:
        mods = {}
        mod_list = []
        if os.path.exists(self.dir_path):
            # We want the mod filenames to be formatted: Saves/xxxx.json or Workshop/xxxx.json
            if self.is_save:
                base_dir = "Saves"
            else:
                base_dir = "Workshop"

            max_mods = -1  # Debug with fewer mods...
            for i, f in enumerate(
                glob(os.path.join(base_dir, "*.json"), root_dir=self.dir_path)
            ):
                if (
                    "WorkshopFileInfos.json" in f
                    or "SaveFileInfos.json" in f
                    or "TS_AutoSave" in f
                ):
                    continue

                if max_mods != -1 and i >= max_mods:
                    break

                details = self.get_mod_details(f)
                name = self.get_mod_name(f)
                mod_list.append((f, name))

            if len(mod_list) == 0:
                return mods

            with sqlite3.connect(DB_NAME) as db:
                # Default values will come from table definition...
                db.executemany(
                    """
                    INSERT OR IGNORE INTO tts_mods
                        (mod_filename, mod_name)
                    VALUES
                        (?, ?) 
                    """,
                    mod_list,
                )
                # Now that the mod is in the db, extract the data...
                cursor = db.execute(
                    """
                    SELECT mod_name, mod_mtime, mod_size, mod_total_assets, mod_missing_assets, mod_filename
                    FROM tts_mods
                    """
                )
                results = cursor.fetchall()
                for result in results:
                    mods[result[5]] = {
                        "name": result[0],
                        "mtime": result[1],
                        "size": result[2],
                        "total_assets": result[3],
                        "missing_assets": result[4],
                        "filename": result[5],
                    }
                db.commit()
        return mods
