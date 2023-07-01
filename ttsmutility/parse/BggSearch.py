import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlencode
import urllib.request


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

    BGG_FIELDS = [
        "yearpublished",
        "minplayers",
        "maxplayers",
        "playingtime",
        "minplaytime",
        "maxplaytime",
        "minage",
        "description",
        "thumbnail",
        "image",
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
        with urllib.request.urlopen(url) as f:
            data = f.read().decode("utf-8")
        root = ET.fromstring(data)
        return self._parse_games(root)

    def _parse_game(self, root):
        game_info = {}
        for e in root:
            if e.tag == "boardgame":
                game_info["id"] = e.attrib["objectid"]
                for d in e:
                    # Only store the primary name
                    if (
                        d.tag == "name"
                        and "primary" in d.attrib
                        and d.attrib["primary"] == "true"
                    ):
                        game_info["name"] = d.text
                    if d.tag == "statistics":
                        for s in d[0][0]:
                            if s.tag in self.BGG_STATS:
                                game_info[s.tag] = s.text
                            elif s.tag in self.BGG_STATS_LISTS:
                                # TODO
                                pass
                    elif d.tag in self.BGG_FIELDS:
                        game_info[d.tag] = d.text
                    elif d.tag in self.BGG_LISTS:
                        if d.tag in game_info:
                            game_info[d.tag].append(d.text)
                        else:
                            game_info[d.tag] = [
                                d.text,
                            ]
                    elif d.tag in self.BGG_POLLS:
                        # TODO
                        pass
        return game_info

    def get_game_info(self, bgg_id):
        params = urlencode(
            {
                "id": bgg_id,
                "stats": "1",
            }
        )
        url = self.BGG_GAME % params
        with urllib.request.urlopen(url) as f:
            data = f.read().decode("utf-8")
        root = ET.fromstring(data)
        return self._parse_game(root)

    def get_game_url(self, bgg_id):
        return self.BGG_GAME_URL % bgg_id
