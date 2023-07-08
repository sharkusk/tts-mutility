# ttsmutility - Early Development Preview

This is an all-in-one application for managing Tabletop Simulator mods and save files.  The following features are currently supported:

- Scans mods/saves and identifies assets that are downloaded or missing (including assets in LuaScript sections)
- Browse Mod info, with integration with Steam Workshop descriptions and BoardGame Geek
- Browse Asset info, including information regarding how the asset is used
- Download all missing assets from a mod, or individual assets
- Backup Mods and Saves to zip files
- Detects mods that are infected with the TTS virus
- Uses Steam Workshop names to compare SHA1 signature to local file in order to detect corrupted files
- Cross platform, tested on Windows 10/11 and Linux (may work on MacOS but currently untested)

## Installation

ttsmutility is a Python 3.11 application which uses the Textual TUI framework.  After obtaining the source code, it can be installed using the following command (don't include the '$'):

```$ pip install .```

If you want to play around with the code (many of the screens can be customized by modifying the .md file you can do a editable install by doing:

```$ pip install -e .```

## Running ttsmutility

Once installed the app can be run by typing:

```$ ttsmutility```

## Configuring ttsmutility Paths

After the first run a config file is created in the xdg config directory.  This is typically `~/.config/ttsmutility`.  TTS paths can be configured there accordingly.

## Commandline options

```
usage: ttsmutility [-h] [-v] [-m MAX_MODS] [--no-log] [--overwrite-log] [--force-refresh] [--skip-asset-scan]

TTSMutility - Tabletop Simulator Mod and Save Utility

options:
  -h, --help            show this help message and exit
  -v, --version         Show version information.
  -m MAX_MODS, --max-mods MAX_MODS
                        Limit number of mods (for faster debuggin)
  --no-log              Disable logging (logfile path specified in config file)
  --overwrite-log       Overwrite the existing log (don't append)
  --force-refresh       Re-process all mod files (useful if bug fix requires a rescan)
  --skip-asset-scan     Do not scan filesystem for new assets during init
```
