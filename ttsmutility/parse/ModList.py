import json
import os.path
from glob import glob
import sqlite3
import atexit

from ttsmutility import *


class ModList:
    def __init__(self, dir_path: str, is_save=False) -> None:
        self.dir_path = dir_path
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.is_save = is_save

    def __del__(self):
        self.cursor.close()
        self.conn.close()

    def get_mod_name(self, filename: str) -> str:
        file_path = os.path.join(self.dir_path, filename)
        with open(file_path, "r", encoding="utf-8") as infile:
            save = json.load(infile)
        return save["SaveName"]

    def get_mods_needing_asset_refresh(self):
        self.cursor.execute(
            """
            SELECT mod_filename
            FROM tts_mods
            WHERE (total_assets=-1 OR missing_assets=-1 OR mod_size=-1)""",
        )
        result = self.cursor.fetchall()
        # Results are returned as a list of tuples, unzip to a list of mod_filename's
        if len(result) > 0:
            return list(zip(*result))[0]
        else:
            return []

    def calc_asset_size(self, filename: str) -> int:
        self.cursor.execute(
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
        result = self.cursor.fetchone()
        self.cursor.execute(
            """
            UPDATE tts_mods
            SET mod_size=?
            WHERE mod_filename=?
            """,
            (result[0], filename),
        )
        self.conn.commit()
        return result[0]

    def count_total_assets(self, filename: str) -> int:
        self.cursor.execute(
            """
        SELECT COUNT(asset_id_fk)
        FROM tts_mod_assets
        WHERE mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
        """,
            (filename,),
        )
        result = self.cursor.fetchone()
        self.cursor.execute(
            """
            UPDATE tts_mods
            SET total_assets=?
            WHERE mod_filename=?
            """,
            (result[0], filename),
        )
        self.conn.commit()
        return result[0]

    def count_missing_assets(self, filename: str) -> int:
        query = """
        SELECT COUNT(asset_id_fk)
        FROM tts_mod_assets
            WHERE (
                mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
                AND 
                asset_id_fk IN (SELECT id FROM tts_assets WHERE asset_mtime=?)
            )
        """
        self.cursor.execute(query, (filename, 0))
        result = self.cursor.fetchone()
        self.cursor.execute(
            """
            UPDATE tts_mods
            SET missing_assets=?
            WHERE mod_filename=?
            """,
            (result[0], filename),
        )
        self.conn.commit()
        return result[0]

    def _get_mod_from_db(self, filename: str) -> dict or None:
        mod = None
        self.cursor.execute(
            """
            SELECT mod_name, mod_mtime, mod_size, total_assets, missing_assets
            FROM tts_mods
            WHERE mod_filename=?""",
            (filename,),
        )
        result = self.cursor.fetchone()
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

    def get_mods(self) -> list:
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

            max_mods = -1  # Debug with fewer mods...
            for i, f in enumerate(
                glob(os.path.join(base_dir, "*.json"), root_dir=self.dir_path)
            ):
                if "WorkshopFileInfos.json" in f or "SaveFileInfos.json" in f:
                    continue

                if max_mods != -1 and i >= max_mods:
                    break

                # We could have the same mod filename in both the Save and Workshop
                # directories.
                mod = self._get_mod_from_db(f)
                if mod is None:
                    name = self.get_mod_name(f)
                    # Set mtime to be zero in the DB, it will get updated when we scan our assets the first time
                    query = """
                    INSERT INTO tts_mods
                        (mod_filename, mod_name, mod_mtime, mod_size, mod_fetch_time, mod_backup_time, total_assets, missing_assets)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?) 
                    """
                    self.cursor.execute(query, (f, name, 0, 0, 0, 0, -1, -1))
                    updated_db = True
                    # Now that the mod is in the db, extract the data...
                    mod = self._get_mod_from_db(f)

                mods.append(mod)
            if updated_db:
                self.conn.commit()
        return mods
