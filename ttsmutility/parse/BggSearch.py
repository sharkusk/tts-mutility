import json
import re
import requests
import time
import xml.etree.ElementTree as ET
from html import unescape
from markdownify import markdownify
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from ..data.config import load_config
from ..parse.FileFinder import recodeURL
from ..utility.util import str_to_num


class BggSearch:
    WORDS_TO_REPLACE = (
        ("1st", "first"),
        ("2nd", "second"),
        ("3rd", "third"),
        ("4th", "fourth"),
        ("complete", ""),
        ("betterized", ""),
        ("setup", ""),
        ("all expansions", ""),
        ("expansions", ""),
        ("HD", ""),
        ("Fully", ""),
        ("English", ""),
        ("+", ""),
        ("revised", ""),
    )

    DELETE_AFTER = [
        " (",
        " [",
        " +",
        " with ",
        " complete ",
        " table ",
        "scripted",
        " everything ",
        " expansion ",
        " all ",
        " - ",
    ]

    BGG_TEXT_FIELDS = [
        "description",
        "thumbnail",
        "image",
    ]

    BGG_FIELDS = [
        "yearpublished",
        "minplayers",
        "maxplayers",
        "playingtime",
        "minplaytime",
        "maxplaytime",
        "minage",
    ]

    BGG_LISTS = [
        "boardgamepublisher",
        "boardgamedesigner",
        "boardgameartist",
        "boardgamecategory",
        "boardgamemechanic",
        "boardgamehonor",
        "boardgamefamily",
    ]

    BGG_POLLS = [
        "suggested_numplayers",
        "suggested_playerage",
        "language_dependence",
    ]

    BGG_STATS = [
        "usersrated",
        "average",
        "bayesaverage",
        "stddev",
        "median",
        "owned",
        "trading",
        "wanting",
        "wishing",
        "numcomments",
        "numweights",
        "averageweight",
    ]

    BGG_STATS_LISTS = [
        "ranks",
    ]

    BGG_SEARCH = "https://api.geekdo.com/xmlapi2/search?%s"
    BGG_GAME = "https://api.geekdo.com/xmlapi2/thing?%s"
    BGG_GAME_URL = "https://boardgamegeek.com/boardgame/%s"
    BGG_URL = "https://boardgamegeek.com/"

    def __init__(self):
        self.config = load_config()

    def _parse_games(self, root):
        games = []
        for e in root:
            name = ""
            id = ""
            year = ""
            if e.tag == "item" and e.attrib["type"] == "boardgame":
                # We found our games!
                id = str_to_num(e.attrib["id"])
                for g in e:
                    if g.tag == "name" and g.attrib["type"] == "primary":
                        name = g.attrib["value"]
                    elif g.tag == "name" and name == "":
                        # Only use alternative name if we haven't already found
                        # a name.
                        name = g.attrib["value"]
                    elif g.tag == "yearpublished":
                        year = str_to_num(g.attrib["value"])
                if name != "" and id != "" and year != "":
                    games.append((name, id, year))
        return games

    def search(self, name: str) -> list:
        name = name.lower()
        for d in self.DELETE_AFTER:
            offset = name.find(d)
            if offset > 0:
                name = name[0:offset]
        for s, r in self.WORDS_TO_REPLACE:
            name = name.replace(s, r)
        name = name.strip()

        params = urlencode(
            {
                "query": name,
                "type": "boardgame",
            }
        )
        url = self.BGG_SEARCH % params

        cache_path = (Path(self.config.bgg_cache_dir) / recodeURL(url)).with_suffix(
            ".xml"
        )
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        else:
            with urlopen(url) as f:
                data = f.read().decode("utf-8", errors="replace")
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(data)
        root = ET.fromstring(data)
        return self._parse_games(root)

    def _make_link(self, elem):
        return (
            f"[{elem.attrib['value']}]"
            f"({self.BGG_URL}/{elem.attrib['type']}/{elem.attrib['id']})"
        )

    def _parse_game_element(self, game):
        game_info = {}
        game_info["id"] = game.attrib["id"]
        for d in game:
            # Only store the primary name
            if d.tag == "name" and d.attrib["type"] == "primary":
                game_info["bgg_name"] = d.attrib["value"]
            elif d.tag == "name" and game_info["bgg_name"] == "":
                # Only use alternative name if we haven't already found
                # a name.
                game_info["bgg_name"] = d.attrib["value"]
            elif d.tag in self.BGG_TEXT_FIELDS:
                # For some reason BGG lists do not contain anything other
                # than 4 or 5 spaces.  Replace with appropriate markdown
                # compatible lists.
                if d.tag == "description":
                    game_info[d.tag] = (
                        self.unescape_utf8(d.text)
                        .replace("     ", "- ")
                        .replace("    ", "- ")
                    )
                else:
                    game_info[d.tag] = unescape(d.text)
            elif d.tag in self.BGG_FIELDS:
                game_info[d.tag] = str_to_num(d.attrib["value"])
            elif d.tag == "link" and d.attrib["type"] in self.BGG_FIELDS:
                # game_info[d.attrib["type"]] = d.attrib["value"]
                game_info[d.attrib["type"]] = self._make_link(d)
            elif d.tag == "statistics":
                for s in d[0]:
                    if s.tag in self.BGG_STATS:
                        game_info[s.tag] = str_to_num(s.attrib["value"])
                    elif s.tag in self.BGG_STATS_LISTS:
                        game_info[s.tag] = []
                        """
                        <ranks>
                            <rank type="subtype" id="1" name="boardgame" friendlyname="Board Game Rank" value="168" bayesaverage="7.3665"/>
                            <rank type="family" id="5497" name="strategygames" friendlyname="Strategy Game Rank" value="125" bayesaverage="7.40438"/>
                        </ranks>
                        """  # noqa
                        for r in s:
                            d = {}
                            for key in r.attrib.keys():
                                d[key] = str_to_num(r.attrib[key])
                            game_info[s.tag].append(d)
            elif d.tag == "link" and d.attrib["type"] in self.BGG_LISTS:
                link = self._make_link(d)
                if d.attrib["type"] in game_info:
                    # game_info[d.attrib["type"]].append(d.attrib["value"])
                    game_info[d.attrib["type"]].append(link)
                else:
                    # game_info[d.attrib["type"]] = [d.attrib["value"],]
                    game_info[d.attrib["type"]] = [
                        link,
                    ]
            elif d.tag == "poll" and d.attrib["name"] in self.BGG_POLLS:
                """
                <poll name="suggested_numplayers" title="User Suggested Number of Players" totalvotes="474">
                    <results numplayers="1">
                        <result value="Best" numvotes="0"/>
                        <result value="Recommended" numvotes="0"/>
                        <result value="Not Recommended" numvotes="251"/>
                    </results>
                    <results numplayers="2">
                        <result value="Best" numvotes="16"/>
                        <result value="Recommended" numvotes="157"/>
                        <result value="Not Recommended" numvotes="162"/>
                    </results>
                </poll>

                or
                <poll name="suggested_playerage" title="User Suggested Player Age" totalvotes="82">
                    <results>
                        <result value="2" numvotes="0"/>
                        <result value="3" numvotes="0"/>
                    </results>
                </poll>
                """  # noqa
                p = {}
                for key in d.attrib.keys():
                    p[key] = str_to_num(d.attrib[key])
                name = p["name"]
                for r in d:
                    if r.tag == "results":
                        if len(r.attrib) > 0:
                            # suggested_numplayers style poll
                            results_key = list(r.attrib.keys())[0]
                            if name not in p:
                                p[name] = {}
                            if r.attrib[results_key] not in p[name]:
                                p[name][r.attrib[results_key]] = []
                            for s in r:
                                v = {}
                                if s.tag == "result":
                                    for key in s.attrib.keys():
                                        v[key] = str_to_num(s.attrib[key])
                                p[name][r.attrib[results_key]].append(v)
                        else:
                            # suggested_playerage style poll
                            p[name] = {}
                            for s in r:
                                if s.tag == "result":
                                    p[name][s.attrib["value"]] = {}
                                    for key in s.attrib.keys():
                                        if key != "value":
                                            p[name][s.attrib["value"]][
                                                key
                                            ] = str_to_num(s.attrib[key])
                game_info[p["name"]] = p
        return game_info

    def _parse_game_tree(self, root):
        for e in root:
            if e.tag == "item" and (
                e.attrib["type"] == "boardgame"
                or e.attrib["type"] == "boardgameexpansion"
            ):
                return self._parse_game_element(e)
        else:
            return {}

    def update_metadata(self, path: Path) -> bool:
        mtime = path.stat().st_mtime
        cur_time = time.time()

        if (
            cur_time + int(self.config.metadata_invalidate_days) * (24 * 60 * 60)
            > mtime
        ):
            return False
        else:
            return True

    def get_game_info(self, bgg_id, force_update):
        params = urlencode(
            {
                "id": bgg_id,
                "stats": "1",
            }
        )
        url = self.BGG_GAME % params
        cache_path = (Path(self.config.bgg_cache_dir) / recodeURL(url)).with_suffix(
            ".xml"
        )
        data = ""
        if (
            cache_path.exists()
            and not self.update_metadata(cache_path)
            and not force_update
        ):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = f.read()

        if len(data) == 0:
            with urlopen(url) as f:
                data = f.read().decode("utf-8")
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(data)
        root = ET.fromstring(data)
        return self._parse_game_tree(root)

    def get_game_url(self, bgg_id):
        return self.BGG_GAME_URL % bgg_id

    def steam_to_html(self, steam_text: str) -> str:
        TAG_MAPS = (
            ("[b]", "<b>"),
            ("[/b]", "</b>"),
            ("[code]", "<code>"),
            ("[/code]", "</code>"),
            ("[h1]", "<h2>"),
            ("[/h1]", "</h2>"),
            ("[h2]", "<h3>"),
            ("[/h2]", "</h3>"),
            ("[h3]", "<h4>"),
            ("[/h3]", "</h4>"),
            ("[i]", "<i>"),
            ("[/i]", "</i>"),
            ("[strike]", "<strike>"),
            ("[/strike]", "</strike>"),
            ("[u]", "<u>"),
            ("[/u]", "</u>"),
            ("[table]", "<table>"),
            ("[/table]", "</table>"),
            ("[tr]", "<tr>"),
            ("[/tr]", "</tr>"),
            ("[td]", "<td>"),
            ("[/td]", "</td>"),
            ("[list]", "<ul>"),
            ("[/list]", "</ul>"),
            ("[olist]", "<ol>"),
            ("[/olist]", "</ol>"),
            ("[img]", '<img src="'),
            ("[/img]", '"/>'),
            ("[hr]", "<hr>"),
            ("[/hr]", "</hr>"),
            ("* ", "- "),
        )
        steam_text = steam_text.replace("\r\n", "<br>")
        steam_text = steam_text.replace("\n", "<br>")
        steam_text = steam_text.replace("\r", "<br>")
        steam_text = steam_text.replace("\t", "    ")

        # Handle list elements
        regex = r"(?:\[\*\])(.*?)(?=(?:\[\/list\])|(?:\n)|(?:\[\*\]))"
        subst = "<li>\\1</li>"
        steam_text = re.sub(regex, subst, steam_text, 0, re.MULTILINE)

        # Handle URL links
        regex = r"\[url=(.*?)\](.*?)\[/url\]"
        subst = r'<a href="\1">\2</a>'
        steam_text = re.sub(regex, subst, steam_text, 0, re.MULTILINE)

        for tag in TAG_MAPS:
            steam_text = steam_text.replace(*tag)
        return steam_text

    def get_steam_details(self, steam_id: str, force_update: bool) -> dict:
        steam_info = {
            "steam_desc": "",
            "creator": 0,
            "title": "",
            "preview_url": "",
            "description": "",
            "time_created": 0,
            "time_updated": 0,
            "subscriptions": 0,
            "lifetime_subscriptions": 0,
            "favorited": 0,
            "lifetime_favorited": 0,
            "views": 0,
            "tags": [],
            "md": "",
        }
        if steam_id.isdigit():
            url = (
                "https://api.steampowered.com/"
                "ISteamRemoteStorage/GetPublishedFileDetails/v1/"
            )
            cache_path = (
                Path(self.config.bgg_cache_dir) / recodeURL(url + steam_id)
            ).with_suffix(".json")
            if (
                not force_update
                and cache_path.exists()
                and cache_path.stat().st_size > 0
                and not self.update_metadata(cache_path)
            ):
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = f.read()
            else:
                resp = requests.post(
                    url, data={"itemcount": "1", "publishedfileids[0]": steam_id}
                )
                if resp.status_code == 200:
                    data = resp.text
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(data)
                else:
                    return {}
            data_j = json.loads(data)
            try:
                details = data_j["response"]["publishedfiledetails"][0]
            except KeyError:
                # No description available on steam page
                return steam_info

            for key in steam_info:
                try:
                    steam_info[key] = details[key]
                except KeyError:
                    pass

            steam_info["steam_desc"] = markdownify(
                self.steam_to_html(steam_info["description"])
            )

        return steam_info

    def unescape_utf8(self, s):
        """
        This function treats escaped codes as utf-8 sequences, rather than unicode values.
        BGG descriptions encode utf-8 as a series of encoded utf-8 bytes
        Eg. "&#232;&#128;&#129;&#229;&#184;&#171;&#230;&#149;&#172;&#230;&#156;&#141;"
        This violates HTML/XML specs so Python's unescape() treats these as unicode
        values instead of utf-8 sequences.
        See the following: https://github.com/python/cpython/issues/108802
        """
        d = bytearray()
        i = 0
        while i < len(s):
            # Find potential escaped character
            e = s.find("&#", i)
            if e != i:
                # Copy all characters up to the escaped character
                if e == -1:
                    e = len(s)
                d += s[i:e].encode("latin-1")
                i = e
            if e == i and i != len(s):
                # Find end mark for escaped character
                e = s.find(";", i + 2)
                # Max value of escaped char is '255' (len of 3 or less)
                if e != -1 and e - (i + 2) <= 3 and s[i + 2 : e].isdigit():
                    # Got an escaped utf-8 code
                    code = int(s[i + 2 : e])
                    d.append(code)
                    i = e + 1
                else:
                    # We were fooled by text using &# but this does not seem to be
                    # an actual escaped character
                    d.append(ord(s[i]))
                    i += 1

        return d.decode("utf-8")
