from io import StringIO

from ttsmutility.parse.ModParser import ModParser

test_mod = """
{
  "SaveName": "Test Field 1",
  "EpochTime": 1,
  "Date": "Test Field 2",
  "VersionNumber": "Test Field 3",
  "GameMode": "Test Field 4",
  "GameType": "Test Field 5",
  "GameComplexity": "Test Field 5",
  "GameComplexity": "Test Field 6",
  "PlayingTime": [
    1,
    2
  ],
  "PlayerCounts": [
    1,
    2
  ],
  "Tags": [
    "1",
    "2",
    "3"
  ],
  "Table": "Test Field 7",
  "TableURL": "http://i.imgur.com/test_url_1.png",
  "Sky": "Test Field 8",
  "SkyURL": "http://cloud-3.steamusercontent.com/ugc/test_url_2/",
  "MusicPlayer": {
    "RepeatSong": false,
    "PlaylistEntry": 0,
    "CurrentAudioTitle": "01",
    "CurrentAudioURL": "http://cloud-3.steamusercontent.com/ugc/test_url_3/",
    "AudioLibrary": [
      {
        "Item1": "http://cloud-3.steamusercontent.com/ugc/test_url_4/",
        "Item2": "01"
      },
      {
        "Item1": "http://cloud-3.steamusercontent.com/ugc/test_url_5/",
        "Item2": "02"
      }
    ]
  },
}
"""


def test_fields():
    # Do we properly extract all fields
    assert 1


def test_tags():
    # Do we extract tags properly
    assert 1


def test_ignore():
    # Do we ignore fields on ignore list
    assert 1


def test_names():
    # Do we properly handle name and nicknames (and combinations)
    assert 1


def test_virus_detection():
    # Do we detect the TTS virus
    assert 1


def test_urls():
    # Do we extract urls
    assert 1


def test_luascript_urls():
    # Do we extract urls from LuaScript sections properly
    assert 1


def test_field_dict():
    # Do we handle the case where fields are populated with dicts
    assert 1
