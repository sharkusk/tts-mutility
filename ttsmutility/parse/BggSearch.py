from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from html import unescape
from markdownify import markdownify
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from ..data.config import load_config
from ..parse.FileFinder import recodeURL


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
            if e.tag == "item" and e.attrib["type"] == "boardgame":
                # We found our games!
                id = e.attrib["id"]
                for g in e:
                    if g.tag == "name" and g.attrib["type"] == "primary":
                        name = g.attrib["value"]
                    elif g.tag == "name" and name == "":
                        # Only use alternative name if we haven't already found
                        # a name.
                        name = g.attrib["value"]
                    elif g.tag == "yearpublished":
                        year = g.attrib["value"]
                if name != "" and id != "" and year != "":
                    games.append((name, id, year))
        return games

    def search(self, name: str) -> dict:
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
        return f"[{elem.attrib['value']}]({self.BGG_URL}/{elem.attrib['type']}/{elem.attrib['id']})"

    def _parse_game_element(self, game):
        game_info = {}
        game_info["id"] = game.attrib["id"]
        for d in game:
            # Only store the primary name
            if d.tag == "name" and d.attrib["type"] == "primary":
                game_info["name"] = d.attrib["value"]
            elif d.tag in self.BGG_TEXT_FIELDS:
                # For some reason BGG lists do not contain anything other
                # than 4 or 5 spaces.  Replace with appropriate markdown
                # compatible lists.
                game_info[d.tag] = (
                    unescape(d.text).replace("     ", "- ").replace("    ", "- ")
                )
            elif d.tag in self.BGG_FIELDS:
                game_info[d.tag] = d.attrib["value"]
            elif d.tag == "link" and d.attrib["type"] in self.BGG_FIELDS:
                # game_info[d.attrib["type"]] = d.attrib["value"]
                game_info[d.attrib["type"]] = self._make_link(d)
            elif d.tag == "statistics":
                for s in d[0]:
                    if s.tag in self.BGG_STATS:
                        game_info[s.tag] = s.attrib["value"]
                    elif s.tag in self.BGG_STATS_LISTS:
                        game_info[s.tag] = []
                        """
                        <ranks>
                            <rank type="subtype" id="1" name="boardgame" friendlyname="Board Game Rank" value="168" bayesaverage="7.3665"/>
                            <rank type="family" id="5497" name="strategygames" friendlyname="Strategy Game Rank" value="125" bayesaverage="7.40438"/>
                        </ranks>
                        """
                        for r in s:
                            d = {}
                            for key in r.attrib.keys():
                                d[key] = r.attrib[key]
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
                """
                p = {}
                for key in d.attrib.keys():
                    p[key] = d.attrib[key]
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
                                        v[key] = s.attrib[key]
                                p[name][r.attrib[results_key]].append(v)
                        else:
                            # suggested_playerage style poll
                            p[name] = {}
                            for s in r:
                                if s.tag == "result":
                                    p[name][s.attrib["value"]] = {}
                                    for key in s.attrib.keys():
                                        if key != "value":
                                            p[name][s.attrib["value"]][key] = s.attrib[
                                                key
                                            ]
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
            return None

    def get_game_info(self, bgg_id):
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
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                data = f.read()
        else:
            with urlopen(url) as f:
                data = f.read().decode("utf-8")
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(data)
        root = ET.fromstring(data)
        return self._parse_game_tree(root)

    def get_game_url(self, bgg_id):
        return self.BGG_GAME_URL % bgg_id

    def get_steam_description(self, steam_id):
        # <div class="workshopItemDescription" id="highlightContent">This mod updates the Battlestar Galactica scripted mod created by |51st|.Capt.MarkvA and adds an unofficial expansion called BSG 2.0 that seeks to fix rules and add content.<br><br>This project is a work in progress!</div>
        description = ""
        if steam_id.isdigit():
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={steam_id}"

            cache_path = (Path(self.config.bgg_cache_dir) / recodeURL(url)).with_suffix(
                ".xml"
            )
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = f.read()
            else:
                with urlopen(url) as f:
                    data = f.read().decode("utf-8")
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(data)
            soup = BeautifulSoup(data, "html.parser")

            description = soup.find("div", class_="workshopItemDescription")
        if description.text == "":
            return ""
        else:
            return markdownify("## Steam Description\n" + str(description))
