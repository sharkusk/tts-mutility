import json
import os.path
from glob import glob
import sqlite3
import atexit

from ttsmutility import *


class ModList():

    def __init__(self, dir_path: str, is_save=False) -> None:
        self.dir_path = dir_path
        self.conn = (sqlite3.connect(DB_NAME))
        self.cursor = self.conn.cursor()
        self.is_save = is_save

        # TODO: Get this to work (it doesn't seem to be called)
        #atexit.register(self._close_connection)
    
    def _close_connection(self):
        self.cursor.close()
        self.conn.close()

    def get_mod_name(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as infile:
            save = json.load(infile)
        return save["SaveName"]

    def _get_mod_from_db(self, filename: str) -> dict or None:
        mod = None
        self.cursor.execute("""
            SELECT mod_name, mod_mtime, total_assets
            FROM tts_mods
                INNER JOIN tts_stats
                    ON tts_stats.mod_id_fk=tts_mods.id
            WHERE mod_filename=?""",
            (filename,)
        );
        result = self.cursor.fetchone()
        if result is not None:
            mod = {
                'filename': filename,
                'name': result[0],
                'mtime': result[1],
                'total_assets': result[2],
                'missing_assets': 0
            }

            #TODO: These are too slow, use another table to auto increment/decrement
            if False:
                self.cursor.execute("SELECT COUNT(mod_filename) FROM tts_mod_assets WHERE mod_filename=?", (filename,));
                result = self.cursor.fetchone()
                total_assets = result[0]

                query = ("""SELECT COUNT(tts_mod_assets.mod_filename)
                            FROM tts_assets
                            INNER JOIN tts_mod_assets ON tts_mod_assets.url=tts_assets.url
                            WHERE (tts_mod_assets.mod_filename=? AND tts_assets.mtime=?)""")
                self.cursor.execute(query, (filename,0))
                result = self.cursor.fetchone()
                missing_assets = result[0]

        return mod

    def get_mods(self, init=False) -> list:
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

            i = 0
            for f in glob(os.path.join(base_dir, "*.json"), root_dir=self.dir_path):
                i += 1
                if i > 50:
                    break

                if "WorkshopFileInfos.json" in f or "SaveFileInfos.json" in f:
                    continue
                if init:
                    mods.append({"filename": f})
                    continue
                # We could have the same mod filename in both the Save and Workshop
                # directories.
                mod = self._get_mod_from_db(f)
                if mod is None:
                    file_path = os.path.join(self.dir_path, f)
                    name = self.get_mod_name(file_path)
                    # Set mtime to be zero in the DB, it will get updated when we scan our assets the first time
                    query = ("""
                    INSERT INTO tts_mods
                        (mod_filename, mod_name, mod_mtime, mod_fetch_time, mod_backup_time)
                    VALUES
                        (?, ?, ?, ?, ?) 
                    """)
                    self.cursor.execute(query, (f, name, 0, 0, 0,))
                    updated_db = True
                    # Now that the mod is in the db, extract the data...
                    mod = self._get_mod_from_db(f)

                mods.append(mod)
            if updated_db:
                self.conn.commit()
        return mods