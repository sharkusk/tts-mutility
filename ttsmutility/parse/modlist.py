import json
import os.path
from glob import glob


def get_save_name(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as infile:
        save = json.load(infile)
    return save["SaveName"]


def mods_in_directory(dir_path: str) -> dict:
    """
    Returns list of dictionary in following format:
    [{
        "filename": filename,
        "name": name,
        "mod_time": mod_time,
        etc (TBD)...
    },]
    """
    mods = []
    if os.path.exists(dir_path):
        for f in glob("*.json", root_dir=dir_path):
            if len(mods) == 50:
                break
            if f == "WorkshopFileInfos.json":
                continue
            file_path = os.path.join(dir_path, f)
            mod = {
                "filename": f,
                "name": get_save_name(file_path),
                "modification_time": os.path.getmtime(file_path)
            }
            mods.append(mod)
    return mods