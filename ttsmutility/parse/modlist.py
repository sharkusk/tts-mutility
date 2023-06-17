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

    def _check_mod_in_db(self, filename: str) -> dict or None:
        mod = None
        self.cursor.execute("SELECT * FROM tts_mods WHERE mod_filename=?", (filename,));
        result = self.cursor.fetchall()
        if len(result) > 0:
            mod = {
                'filename': result[0][MOD_FILENAME_INDEX],
                'name': result[0][MOD_NAME_INDEX],
                'modification_time': result[0][MOD_TIME_INDEX],
            }
        self.cursor.execute("SELECT COUNT(url) FROM tts_mod_assets WHERE mod_filename=?", (filename,));
        result = self.cursor.fetchone()

        if mod is not None:
            mod['total_assets'] = result[0]
        
        return mod

    def get_mods(self) -> list:
        """
        Returns list of dictionary in following format:
        [{
            "filename": filename,
            "name": name,
            "mod_time": mod_time,
            etc (TBD)...
        },]
        """
        if os.path.exists(self.dir_path):
            mods = []
            updated_db = False
            for f in glob("*.json", root_dir=self.dir_path):
                if f == "WorkshopFileInfos.json":
                    continue
                mod = self._check_mod_in_db(f)
                file_path = os.path.join(self.dir_path, f)
                mtime = os.path.getmtime(file_path)
                if mod is None:
                    name = self.get_mod_name(file_path)
                    self.cursor.execute("INSERT INTO tts_mods VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (f, name, file_path, mtime, 0, 0, 0, 0))
                    mod = {
                        "filename": f,
                        "name": name,
                        "modification_time": mtime,
                    }
                    updated_db = True
                elif mod['modification_time'] != mtime:
                    self.cursor.execute("UPDATE tts_mods SET mod_time=? WHERE filename=?", (mtime, f,))
                    updated_db = True

                mods.append(mod)
            if updated_db:
                self.conn.commit()
        return mods