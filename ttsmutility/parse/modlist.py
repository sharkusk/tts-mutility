import json
import os.path
from glob import glob
import sqlite3
import atexit

from ttsmutility import *


class ModList():

    def __init__(self, dir_path: str) -> None:
        self.dir_path = dir_path
        self.conn = (sqlite3.connect(DB_NAME))
        self.cursor = self.conn.cursor()

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
        self.cursor.execute("SELECT mod_filename, mod_name, mtime FROM tts_mods WHERE mod_filename=?", (filename,));
        result = self.cursor.fetchall()
        if len(result) > 0:
            mod = {
                'filename': result[0][0],
                'name': result[0][1],
                'mtime': result[0][2],
            }
            self.cursor.execute("SELECT COUNT(url) FROM tts_mod_assets WHERE mod_filename=?", (filename,));
            result = self.cursor.fetchone()
            total_assets = result[0]

            query = ("""SELECT COUNT(tts_assets.url) FROM tts_assets
                        INNER JOIN tts_mod_assets ON tts_mod_assets.url=tts_assets.url
                        WHERE (tts_mod_assets.mod_filename=? AND tts_assets.mtime=?)""")
            self.cursor.execute(query, (filename,0))
            result = self.cursor.fetchone()

            mod['total_assets'] = total_assets
            mod['missing_assets'] = result[0]
        
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
            for f in glob("*.json", root_dir=self.dir_path):
                if f == "WorkshopFileInfos.json" or f == "SaveFileInfos.json":
                    continue
                if init:
                    mods.append({"filename": f})
                    continue
                mod = self._get_mod_from_db(f)
                if mod is None:
                    file_path = os.path.join(self.dir_path, f)
                    name = self.get_mod_name(file_path)
                    # Set mtime to be zero in the DB, it will get updated when we scan our assets the first time
                    self.cursor.execute("INSERT INTO tts_mods VALUES (?, ?, ?, ?, ?, ?)", (f, name, file_path, 0, 0, 0,))
                    updated_db = True
                    # Now that the mod is in the db, extract the data...
                    mod = self._get_mod_from_db(f)

                mods.append(mod)
            if updated_db:
                self.conn.commit()
        return mods