import urllib
from pathlib import Path
import re
import os.path


IMGPATH = "Images"
OBJPATH = "Models"
BUNDLEPATH = "Assetbundles"
AUDIOPATH = "Audio"
PDFPATH = "PDF"
TXTPATH = "Text"

AUDIO_EXTS = [".mp3", ".wav", ".ogv", ".ogg"]
IMG_EXTS = [".png", ".jpg", ".mp4", ".m4v", ".webm", ".mov", ".unity3d"]
OBJ_EXTS = [".obj"]
BUNDLE_EXTS = [".unity3d"]
PDF_EXTS = [".pdf"]
TXT_EXTS = [".txt"]

# TTS uses UPPER_CASE extensions for these files
UPPER_EXTS = AUDIO_EXTS + PDF_EXTS + TXT_EXTS

ALL_VALID_EXTS = AUDIO_EXTS + IMG_EXTS + OBJ_EXTS + BUNDLE_EXTS + PDF_EXTS + TXT_EXTS

# Order used to search to appropriate paths based on extension
# IMG comes last (or at least after BUNDLE) as we prefer to store
# unity3d files as bundles (but there are cases where unity3d files
# are used as images -- specifically noticed for decks)
MOD_PATHS = [
    (AUDIO_EXTS, AUDIOPATH),
    (OBJ_EXTS, OBJPATH),
    (BUNDLE_EXTS, BUNDLEPATH),
    (PDF_EXTS, PDFPATH),
    (TXT_EXTS, TXTPATH),
    (IMG_EXTS, IMGPATH),
]

# Ignore raw files as they are created by TTS
FILES_TO_IGNORE = [".RAWT", ".RAWM", ".TMP", ".DB"]
TTS_RAW_DIRS = {"Images Raw": ".rawt", "Models Raw": ".rawm", ".": ""}


def trailstring_to_trail(trailstring: str) -> list:
    return trailstring.split("->")


def trail_to_trailstring(trail: list) -> str:
    return "->".join(["%s"] * len(trail)) % tuple(trail)


def is_obj(trail):
    # TODO: None of my mods have NormalURL set (normal maps?). I’m
    # assuming these are image files.
    obj_keys = ("MeshURL", "ColliderURL")
    return trail[-1] in obj_keys


def is_image(trail):
    # This assumes that we only have mesh, assetbundle, audio, PDF and image
    # URLs.
    return not (
        is_obj(trail)
        or is_assetbundle(trail)
        or is_audiolibrary(trail)
        or is_pdf(trail)
        or is_from_script(trail)
        or is_custom_ui_asset(trail)
    )


def is_assetbundle(trail):
    bundle_keys = ("AssetbundleURL", "AssetbundleSecondaryURL")
    return trail[-1] in bundle_keys


def is_audiolibrary(trail):
    audio_keys = ("CurrentAudioURL", "AudioLibrary")
    return trail[-1] in audio_keys


def is_pdf(trail):
    return trail[-1] == "PDFUrl"


def is_from_script(trail):
    return trail[-1] == "LuaScript"


def is_custom_ui_asset(trail):
    return "CustomUIAssets" in trail


def recodeURL(url):
    """Recode the given URL in the way TTS does, which yields the
    file-system trail to the cached file."""

    return re.sub(r"[\W_]", "", url)


def get_fs_path_from_extension(url, ext):
    recoded_name = recodeURL(url)

    for ttsexts, path in MOD_PATHS:
        if ext.lower() in ttsexts:
            filename = recoded_name + ext
            filename = Path(path) / filename
            return filename
    else:
        return None


def get_fs_path_from_url(url):
    # Use the url to extract the extension, ignoring any trailing ? url parameters
    offset = url.rfind("?")
    if offset > 0:
        ext = os.path.splitext(url[0 : url.rfind("?")])[1]
    else:
        ext = os.path.splitext(url)[1]

    if ext != "":
        return get_fs_path_from_extension(url, ext)
    else:
        return None


def get_fs_path(trail, url):
    """Return a file-system path to the object in the cache."""

    # Check if we can determine the filepath strictly from the URL.
    filename = get_fs_path_from_url(url)
    if filename is not None:
        return filename

    recoded_name = recodeURL(url)

    if is_obj(trail):
        filename = recoded_name + ".obj"
        filename = Path(OBJPATH) / filename

    elif is_assetbundle(trail):
        filename = recoded_name + ".unity3d"
        filename = Path(BUNDLEPATH) / filename

    elif is_audiolibrary(trail):
        # We know the cache location of the file
        # but the extension may be one of many.
        filename = recoded_name
        filename = Path(AUDIOPATH) / recoded_name

    elif is_pdf(trail):
        filename = recoded_name + ".PDF"
        filename = Path(PDFPATH) / filename

    elif is_image(trail):
        # We know the cache location of the file
        # but the extension may be one of many.
        filename = recoded_name
        filename = Path(IMGPATH) / recoded_name

    else:
        filename = Path(recoded_name)

    return filename
