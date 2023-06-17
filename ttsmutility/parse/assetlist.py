import os.path
import sqlite3
import atexit
import json
import re

from ttsmutility import *

IMGPATH = os.path.join("Mods", "Images")
OBJPATH = os.path.join("Mods", "Models")
BUNDLEPATH = os.path.join("Mods", "Assetbundles")
AUDIOPATH = os.path.join("Mods", "Audio")
PDFPATH = os.path.join("Mods", "PDF")
TXTPATH = os.path.join("Mods", "Text")

AUDIO_EXTS = ['.mp3', '.wav', '.ogv', '.ogg']
IMG_EXTS = ['.png', '.jpg', '.mp4', '.m4v', '.webm', '.mov', '.unity3d']
OBJ_EXTS = ['.obj']
BUNDLE_EXTS = ['.unity3d']
PDF_EXTS = ['.pdf']
TXT_EXTS = ['.txt']

# TTS uses UPPER_CASE extensions for these files
UPPER_EXTS = AUDIO_EXTS + PDF_EXTS + TXT_EXTS

ALL_VALID_EXTS = AUDIO_EXTS + IMG_EXTS + OBJ_EXTS + BUNDLE_EXTS + PDF_EXTS + TXT_EXTS

# Order used to search to appropriate paths based on extension
# IMG comes last (or at least after BUNDLE) as we prefer to store
# unity3d files as bundles (but there are cases where unity3d files
# are used as images -- specifically noticed for decks)
MOD_PATHS = [
    (AUDIO_EXTS, AUDIOPATH),
    (OBJ_EXTS, OBJPATH),
    (BUNDLE_EXTS, BUNDLEPATH),
    (PDF_EXTS, PDFPATH),
    (TXT_EXTS, TXTPATH),
    (IMG_EXTS, IMGPATH),
]

class IllegalSavegameException(ValueError):
    def __init__(self):
        super().__init__("not a Tabletop Simulator savegame")

class AssetList():

    def __init__(self, dir_path: str) -> None:
        self.dir_path = dir_path
        self.conn = (sqlite3.connect(DB_NAME))
        self.cursor = self.conn.cursor()

        # TODO: Get this to work (it doesn't seem to be called)
        #atexit.register(self._close_connection)
    
    def _close_connection(self):
        self.cursor.close()
        self.conn.close()
    
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
                        if url in done:
                            continue
                        done.add(url)
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
                if v in done:
                    continue
                done.add(v)
                yield (newtrail, v)

            elif k == "LuaScript":
                NO_EXT_SITES = ['steamusercontent.com', 'pastebin.com', 'paste.ee', 'drive.google.com', 'steamuserimages-a.akamaihd.net',]
                # Parse lauscript for potential URLs
                url_matches = re.findall(r'((?:http|https):\/\/(?:[\w\-_]+(?:(?:\.[\w\-_]+)+))(?:[\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?)', v)
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
                        if url in done:
                            continue
                        done.add(url)
                        yield (newtrail, url)
    
    def parse_assets(self, filename: str, init=False) -> list:
        assets = []
        mod_path = os.path.join(self.dir_path, filename)
        modified_db = False
        self.cursor.execute("SELECT EXISTS (SELECT 1 FROM tts_mod_assets WHERE mod_filename=?)", (filename,));
        result = self.cursor.fetchone()
        parse_file = False
        if result[0] == 0:
            parse_file = True
        else:
            self.cursor.execute("SELECT * FROM tts_mods WHERE mod_filename=?", (filename,))
            result = self.cursor.fetchone()
            if os.path.getmtime(mod_path) > result[MOD_TIME_INDEX]:
                parse_file = True
        
        if parse_file:
            for trail, url in self.urls_from_save(mod_path):
                # TODO: Add SHA-1 (and filename during parse operation)
                trail_string = '->'.join(['%s']*len(trail)) % tuple(trail)
                modified_db = True
                self.cursor.execute("REPLACE INTO tts_assets VALUES (?, ?, ?, ?)",
                                    (url, "", "", trail_string))
                self.cursor.execute("REPLACE INTO tts_mod_assets VALUES (?, ?)",
                                    (url, filename,))
                if not init:
                    assets.append({
                        "url": url,
                        "asset_filename": "",
                        "sha1": "",
                        "trail": trail_string
                        })
            if modified_db:
                self.conn.commit()
        else:
            if not init:
                self.cursor.execute(("""
                    SELECT
                        * FROM tts_assets
                    INNER JOIN tts_mod_assets
                        ON tts_mod_assets.url=tts_assets.url
                        WHERE tts_mod_assets.mod_filename=?
                    """),(filename,))
                results = self.cursor.fetchall()
                for result in results:
                    assets.append({
                        "url": result[URL_INDEX],
                        "asset_filename": result[ASSET_FILENAME_INDEX],
                        "sha1": result[SHA1_INDEX],
                        "trail": result[TRAIL_INDEX]
                        })
        return assets