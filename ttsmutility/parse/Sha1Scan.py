import hashlib
import os
import pathlib

from ..parse.FileFinder import TTS_RAW_DIRS, FILES_TO_IGNORE

# Recursively read each directory
# Load existing dictionary, for each file not found in dictionary:
# Files that match steam pattern, extract SHA-1 values, add to {SHA1, filename}
# For non-steam files generate SHA-1 values, add to dictionary
# For each line is missing url file:
#   Extract SHA-1
#   Check if matching SHA-1 file is found
#   Copy and rename to destination directory


def scan_sha1s(root_dir):
    old_dir = os.getcwd()
    os.chdir(root_dir)
    for root, _, files in os.walk("."):
        dir_name = pathlib.PurePath(root).name

        if dir_name in TTS_RAW_DIRS or dir_name == "":
            continue

        yield (("new_directory", len(files), dir_name))

        for filename in files:
            ext = os.path.splitext(filename)[1]
            if ext.upper() in FILES_TO_IGNORE:
                continue

            # Remove the '.\' at the front of the path
            filepath = str(pathlib.PurePath(os.path.join(root, filename)))
            do_sha1 = yield (("filepath", filepath))
            yield None  # Extra yield required here to stay syncronized with non-send for-loop
            if not do_sha1:
                continue

            sha1 = ""
            steam_sha1 = ""

            if "httpcloud3steamusercontent" in filename:
                hexdigest = os.path.splitext(filename)[0][-40:]
                steam_sha1 = hexdigest.upper()

            with open(filepath, "rb") as f:
                digest = hashlib.file_digest(f, "sha1")
            hexdigest = digest.hexdigest()
            sha1 = hexdigest.upper()

            yield (("sha1", sha1, steam_sha1))
    os.chdir(old_dir)
