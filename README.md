# ttsmutility - Early Development Preview

![Screenshot_20230708_100645](https://github.com/sharkusk/tts-mutility/assets/4368882/aaf36fe5-2128-4a76-b5dd-a5a2ee18befe)

This is an all-in-one application for managing Tabletop Simulator mods and save files.  The following features are currently supported:

- Scans mods/saves and identifies assets that are downloaded or missing (including assets in LuaScript sections)
- Browse Mod info, with integration with Steam Workshop descriptions and BoardGame Geek
- Browse Asset info, including information regarding how the asset is used
- Download all missing assets from a mod, or individual assets
- Backup Mods and Saves to zip files
- Detects mods that are infected with the TTS script-virus (infected mods have a red name)
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

After the first run a config file is created in the xdg config directory.  This is typically `~/.config/ttsmutility` (Linux) or `C:\Users\[username]\.config\ttsmutility` (Windows).  TTS paths can be configured there accordingly.

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

## Additional ttsmutility Screenshots

### Mod Details
![Screenshot_20230708_100830](https://github.com/sharkusk/tts-mutility/assets/4368882/dfe2ddae-23e9-4e87-a24a-e80bff5c316d)

### Mod Asset List
![Screenshot_20230708_100919](https://github.com/sharkusk/tts-mutility/assets/4368882/c3ec2548-df2a-4573-a805-a5b971bd69e9)

### Asset Detail
![Screenshot_20230708_102647](https://github.com/sharkusk/tts-mutility/assets/4368882/5ba672bf-7d42-4e43-bd30-7f89d7f98d94)

### Virus Alert
![Screenshot 2023-07-10 124257](https://github.com/sharkusk/tts-mutility/assets/4368882/a257b5d4-a2b7-4df0-8484-7d9409ed5864)

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
