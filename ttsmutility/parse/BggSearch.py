import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlencode
from urllib.request import urlopen


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
        ("revisde", ""),
        ("!", ""),
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
        " cs",
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

    def __ini__(self):
        pass

    def _parse_games(self, root):
        games = {}
        for e in root:
            name = ""
            id = ""
            if e.tag == "item" and e.attrib["type"] == "boardgame":
                # We found our games!
                id = e.attrib["id"]
                for g in e:
                    if g.tag == "name" and g.attrib["type"] == "primary":
                        name = g.attrib["value"]
                    elif g.tag == "yearpublished":
                        year = g.attrib["value"]
                games[name] = (id, year)
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
        with urlopen(url) as f:
            data = f.read().decode("utf-8")
        root = ET.fromstring(data)
        return self._parse_games(root)

    def _parse_game(self, root):
        game_info = {}
        for e in root:
            if e.tag == "item" and e.attrib["type"] == "boardgame":
                game_info["id"] = e.attrib["id"]
                for d in e:
                    # Only store the primary name
                    if d.tag == "name" and d.attrib["type"] == "primary":
                        game_info["name"] = d.attrib["value"]
                    elif d.tag in self.BGG_TEXT_FIELDS:
                        game_info[d.tag] = unescape(d.text)
                    elif d.tag in self.BGG_FIELDS:
                        game_info[d.tag] = d.attrib["value"]
                    elif d.tag == "statistics":
                        for s in d[0][0]:
                            if s.tag in self.BGG_STATS:
                                game_info[s.tag] = unescape(s.text)
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
                    elif d.tag in self.BGG_LISTS:
                        if d.tag in game_info:
                            game_info[d.tag].append(unescape(d.text))
                        else:
                            game_info[d.tag] = [
                                unescape(d.text),
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
                        for r in d:
                            if r.tag == "results":
                                if len(r.attrib) > 0:
                                    results_key = list(r.attrib.keys())[0]
                                    if results_key not in p:
                                        p[results_key] = {}
                                    if r.attrib[results_key] not in p[results_key]:
                                        p[results_key][r.attrib[results_key]] = []
                                    for s in r:
                                        v = {}
                                        if s.tag == "result":
                                            for key in s.attrib.keys():
                                                v[key] = s.attrib[key]
                                        p[results_key][r.attrib[results_key]].append(v)
                                else:
                                    name = p["name"]
                                    p[name] = {}
                                    for s in r:
                                        if s.tag == "result":
                                            p[name][s.attrib["value"]] = {}
                                            for key in s.attrib.keys():
                                                if key != "value":
                                                    p[name][s.attrib["value"]][
                                                        key
                                                    ] = s.attrib[key]
                        game_info[p["name"]] = p
        return game_info

    def get_game_info(self, bgg_id):
        params = urlencode(
            {
                "id": bgg_id,
                "stats": "1",
            }
        )
        url = self.BGG_GAME % params
        with urlopen(url) as f:
            data = f.read().decode("utf-8")
        root = ET.fromstring(data)
        return self._parse_game(root)

    def get_game_url(self, bgg_id):
        return self.BGG_GAME_URL % bgg_id
