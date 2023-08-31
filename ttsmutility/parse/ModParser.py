import json
import re

from ..parse.FileFinder import (
    ALL_VALID_EXTS,
    recodeURL,
)

# This URL is used to identify the TTS Luascript infection
INFECTION_URL = (
    "https://media.defense.gov/2020/Mar/03/2002258347/825/780/0/200303-D-ZZ999-112M.JPG"
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
        "custom_content",
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

    def __init__(self, modpath: str) -> None:
        self.modpath = modpath
        self.mod_info = {}
        for field in self.MOD_INFO_FIELDS:
            self.mod_info[field] = ""

    def get_mod_info(self) -> dict:
        return self.mod_info

    def urls_from_mod(self, all_nodes=False):
        with open(self.modpath, "r", encoding="utf-8") as infile:
            try:
                save = json.load(infile, strict=False)
            except UnicodeDecodeError:
                raise IllegalSavegameException

        if not isinstance(save, dict):
            raise IllegalSavegameException

        return self.seekURL(save, all_nodes=all_nodes)

    def seekURL(self, dic, trail=[], all_nodes=False, done=None):
        """Recursively search through the save game structure and return URLs
        and the paths to them.

        """
        if done is None:
            done = set()

        name = ""
        nickname = ""
        guid = ""
        for k, v in dic.items():
            if k in self.MOD_INFO_FIELDS:
                if isinstance(v, str):
                    self.mod_info[k] = v.strip()
                elif isinstance(v, dict):
                    self.mod_info[k] = "-".join(v.values())
                elif isinstance(v, list):
                    self.mod_info[k] = []
                    for entry in v:
                        if isinstance(entry, dict):
                            self.mod_info[k].append("-".join(entry.values()))
                        else:
                            self.mod_info[k].append(entry)
                else:
                    self.mod_info[k] = v

            if name == "" and nickname == "" and guid == "":
                newtrail = trail + [k]
            else:
                full_name = ""
                if name != "":
                    full_name += name.strip() + " "
                if nickname != "":
                    full_name += nickname.strip() + " "
                if guid != "":
                    full_name += f"({guid}) "
                newtrail = trail + [f'"{full_name.strip()}"', k]

            if k == "AudioLibrary":
                for elem in v:
                    # Found mod that has an empty audio library, skip it
                    if isinstance(elem, dict):
                        try:
                            # It appears that AudioLibrary items are mappings of form
                            # “Item1” → URL, “Item2” → audio title.
                            url = elem["Item1"]
                            recode = recodeURL(url)
                            if recode in done and not all_nodes:
                                continue
                            done.add(recode)
                            yield (newtrail, url)
                        except KeyError:
                            raise NotImplementedError(
                                "AudioLibrary has unexpected structure: {}".format(v)
                            )

            elif isinstance(v, dict):
                yield from self.seekURL(
                    v, trail=newtrail, all_nodes=all_nodes, done=done
                )

            elif isinstance(v, list):
                for elem in v:
                    if not isinstance(elem, dict):
                        continue
                    yield from self.seekURL(
                        elem, trail=newtrail, all_nodes=all_nodes, done=done
                    )

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
                if recode in done and not all_nodes:
                    continue
                done.add(recode)
                yield (newtrail, v)

            elif k.lower() == "guid":
                guid = v

            elif k.lower() == "name":
                if not v or v.lower() in self.NAMES_TO_IGNORE:
                    name = ""
                else:
                    name = v.replace("Custom_", "")
                    # Strip inline formatting that may not work properly
                    name = re.sub(r"(\[.+?\])", "", name)

            elif k.lower() == "nickname" and v:
                nickname = v
                # Strip inline formatting that may not work properly
                nickname = re.sub(r"(\[.+?\])", "", nickname)
                nickname = nickname.replace("\r\n", " ")
                nickname = nickname.replace("\n", " ")
                nickname = nickname.replace("\r", " ")

            elif k == "LuaScript":
                NO_EXT_SITES = [
                    "steamusercontent.com",
                    "pastebin.com",
                    "paste.ee",
                    "drive.google.com",
                    "steamuserimages-a.akamaihd.net",
                ]
                # Check for TTS virus signature
                if v.find("tcejbo gninwapS") != -1 and v.find(" " * 200) != 1:
                    # Don't add these to the set, report all infected objects/trails...
                    yield (newtrail, INFECTION_URL)

                # Parse lauscript for potential URLs
                url_matches = re.findall(
                    (
                        r"((?:http|https):\/\/(?:[\w\-_]+(?:(?:\.[\w\-_]+)+))"
                        r"(?:[\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?)"
                    ),
                    v,
                )
                for url in url_matches:
                    valid_url = False

                    # Detect if URL ends in a valid extension or is from
                    # a site which doesn't use extension
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
                        if recode in done and not all_nodes:
                            continue
                        done.add(recode)
                        yield (newtrail, url)
