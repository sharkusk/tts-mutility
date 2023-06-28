import json
import re
from pathlib import Path

from ..data.config import load_config
from ..parse.FileFinder import (
    ALL_VALID_EXTS,
    recodeURL,
)


class IllegalSavegameException(ValueError):
    def __init__(self):
        super().__init__("not a Tabletop Simulator savegame")


class ModParser:
    # These names are redundant, so don't keep them in our trail
    NAMES_TO_IGNORE = [
        "custom_model",
        "custom_assetbundle",
        "custom_pdf",
        "custom_token",
        "custom content",
        "deck",
        "cardcustom",
    ]
    MOD_INFO_FIELDS = [
        "SaveName",
        "EpochTime",
        "Date",
        "VersionNumber",
        "GameMode",
        "GameType",
        "GameComplexity",
        "PlayingTime",
        "PlayerCounts",
        "Tags",
    ]

    def __init__(self, modpath: Path) -> None:
        self.modpath = modpath
        self.mod_info = {}
        for field in self.MOD_INFO_FIELDS:
            self.mod_info[field] = ""

    def get_mod_info(self) -> dict:
        return self.mod_info

    def urls_from_mod(self):
        with open(self.modpath, "r", encoding="utf-8") as infile:
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

        name = ""
        for k, v in dic.items():
            if k in self.MOD_INFO_FIELDS:
                self.mod_info[k] = v

            if name == "":
                newtrail = trail + [k]
            else:
                newtrail = trail + [f'"{name.strip()}"', k]

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

            elif k.lower() == "name":
                if not v or v.lower() in self.NAMES_TO_IGNORE:
                    name = ""
                else:
                    # Don't store the same custom name twice in a given trail
                    if v in newtrail:
                        name = ""
                    else:
                        name = v.replace("Custom_", "")
                        # Strip inline formatting that may not work properly
                        name = re.sub(r"(\[.+?\])", "", name)

            # Prioritize storing the nickname over the name...
            elif k.lower() == "nickname" and v:
                # Don't store the same custom name twice in a given trail
                if v not in newtrail:
                    name = v
                    # Strip inline formatting that may not work properly
                    name = re.sub(r"(\[.+?\])", "", name)

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
