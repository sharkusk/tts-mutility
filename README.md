# ttsmutility - Early Development Preview

![ModList](https://github.com/sharkusk/tts-mutility/assets/4368882/931fdd5c-ac78-4d17-bc45-a25c47bb6c0b)

This is an all-in-one application for managing Tabletop Simulator mods and save files.  The following features are currently supported:

- Scan mods/saves and identify assets that are downloaded or missing (including assets in LuaScript sections)
- Browse Mod info, with integration with Steam Workshop descriptions and BoardGame Geek
- Browse Asset info, including information regarding how the asset is used in the JSON mod
- Download all missing assets from a mod, or individual assets
- Backup Mods and Saves to zip files
- Detect mods that are infected with the TTS script-virus (infected mods have a red name)
- Use Steam Workshop names to compare SHA1 signature to local file in order to detect corrupted files
- Cross platform, tested on Windows 10/11 and Linux (may work on MacOS but currently untested)
- Recover original file names from steamcloud and other cloud providers (where possible)
- Identify potential matches for missing assets using SHA1, filenames, and original file names
- Clickable links for both local and cloud files

## Installation

ttsmutility is a Python 3.11 application which uses the Textual TUI framework.  After obtaining the source code, it can be installed using the following command (don't include the '$'):

```$ pip install .```

If you want to play around with the code (many of the screens can be customized by modifying the .md file you can do a editable install by doing:

```$ pip install -e .```

NOTE: Pip also supports installing directly from a zip file.  So, instead of the `.` you can substitute the zip filename.

## Running ttsmutility

Once installed the app can be run by typing:

```$ ttsmutility -m [tts mods directory containing 'Workshop'] -s [tts directory containing 'Saves']```

These directories only need to be specified one time, as they will be saved to a configuration file.

## Configuring other ttsmutility Options

After the first run a config file (`configuration.json`) is created in the xdg config directory.  This is typically `~/.config/ttsmutility` (Linux) or `C:\Users\[username]\.config\ttsmutility` (Windows).  Various options can be configured by modifying the .conf file (e.g. number of download threads).

## Commandline options

```
usage: ttsmutility [-h] [-v] [--no-log] [--append-log] [--force-refresh] [--skip-asset-scan] [--force-steam-md-update] [--clean-db] [-c CONFIG_FILE]
                   [-s SAVES_DIR] [-m MODS_DIR]

TTSMutility - Tabletop Simulator Mod and Save Utility

options:
  -h, --help            show this help message and exit
  -v, --version         Show version information.
  --no-log              Disable logging (logfile path specified in config file)
  --append-log          Append to existing log (no not overwrite)
  --force-refresh       Re-process all mod files (useful if bug fix requires a rescan)
  --skip-asset-scan     Do not scan filesystem for new assets during init
  --force-steam-md-update
                        Reload steam meta data, do not use cached version
  --clean-db            Remove stale assets and deleted mods from the DB
  -c CONFIG_FILE, --config_file CONFIG_FILE
                        Override default config file path (including filename)
  -s SAVES_DIR, --saves_dir SAVES_DIR
                        Absolute path to the TTS directory that contains the 'Saves' subdir
  -m MODS_DIR, --mods_dir MODS_DIR
                        Absolute path to the TTS Mods directory that contains the 'Workshop' subdir
```

## Additional ttsmutility Screenshots

### Mod Details
![Screenshot_20230708_100830](https://github.com/sharkusk/tts-mutility/assets/4368882/dfe2ddae-23e9-4e87-a24a-e80bff5c316d)

### Mod Asset List
![AssetList](https://github.com/sharkusk/tts-mutility/assets/4368882/799701e4-15de-48d0-a3da-8944d86794af)

### Asset Detail
![Screenshot_20230708_102647](https://github.com/sharkusk/tts-mutility/assets/4368882/5ba672bf-7d42-4e43-bd30-7f89d7f98d94)

### Virus Alert
![Screenshot 2023-07-10 124257](https://github.com/sharkusk/tts-mutility/assets/4368882/a257b5d4-a2b7-4df0-8484-7d9409ed5864)

### Explorer Tree View
![tree](https://github.com/sharkusk/tts-mutility/assets/4368882/46112527-eee7-4239-bbd5-6e69f8db7bf9)

# Transitioning To The New Steam Cloud URLs

## Background

Recently TTS changed the URLs used to download assets from the steam cloud. The new URL is used by TTS whenever downloading assets from Steam Cloud servers, even if the original mod still uses the old URLs. Unfortunately, TTS encodes the URL into the asset filename. So, TTS will check if a cached asset exists for both the new and old filename, and only download the asset if necessary. This mix of old and new URLs and filenames makes things a bit of a mess when managing and backing up mods.

When scanning a new or modified mod, tts-mutility automatically converts all URLs to the new scheme. Original URLs can still be viewed in the explore window.

## Recommendation

1. [optional] Use the "Save Content Names" command from tts-mutility's command palette.
1. Rename all cached assets to use filenames based on the new URL scheme (use regular expression so only matching string from start of filename matches). (`^httpscloud3steamusercontentcomugc` -> `httpssteamusercontentaakamaihdnetugc`)
1. [optional] Modify the content_names.csv file created in step 1 with new URL scheme (search/replace). (`https://cloud-3.steamusercontent.com/ugc/` -> `https://steamusercontent-a.akamaihd.net/ugc/`)
1. Run tts-mutility with --force-refresh option to rescan all mods and apply new URL scheme
1. [optional] Use the "Load Content Names" command to restore original filenames

Please note, this will flag all mods using renamed assets (likely most of them) to require a new backup.

# ttscleaner.py - TTS Script Virus Removal Tool

A stand alone tool is also available to remove the TTS virus from Mods and Saves.  **Please store a backup of your original mod.**

```
$ python .\ttscleaner.py --help
usage: ttscleaner [-h] [-v] [-s] [--no-sig] mod_path

ttscleaner - Tabletop Simulator mod virus removal tool

positional arguments:
  mod_path

options:
  -h, --help     show this help message and exit
  -v, --version  Show version information.
  -s, --scan     Scan and print virus info
  --no-sig       Do not add signature in place of virus

0.0.2
```

Sample output from default clean option. Note: the tool will not overwrite the mod.  Instead it creates a "clean" copy with the file extension ".cleaned".

```
> python .\ttscleaner.py 'C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2967684892.json'
Cleaning mod 'C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2967684892.json'
Cleaned 5 infected objects
Saving cleaned mod to 'C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2967684892.cleaned'
```

Sample output from scan operation:

```
> python .\ttscleaner.py --scan 'C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2967684892.json'
Scanning mod 'C:\Program Files (x86)\Steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Workshop\2967684892.json'
Virus detected: ObjectStates->"Sample infected cards"->ContainedObjects->"Card"->LuaScript
Virus detected: ObjectStates->"Sample infected cards"->ContainedObjects->"Card"->LuaScript
Virus detected: ObjectStates->"Sample infected cards"->ContainedObjects->"Card"->LuaScript
Virus detected: ObjectStates->"Sample infected cards"->ContainedObjects->"Card"->LuaScript
Virus detected: ObjectStates->"Sample infected cards"->ContainedObjects->"Card"->LuaScript
Detected 5 infected objects
```
