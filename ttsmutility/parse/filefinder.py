import urllib
import os.path
import re


IMGPATH = os.path.join("Mods", "Images")
OBJPATH = os.path.join("Mods", "Models")
BUNDLEPATH = os.path.join("Mods", "Assetbundles")
AUDIOPATH = os.path.join("Mods", "Audio")
PDFPATH = os.path.join("Mods", "PDF")
TXTPATH = os.path.join("Mods", "Text")

AUDIO_EXTS = ['.mp3', '.wav', '.ogv', '.ogg']
IMG_EXTS = ['.png', '.jpg', '.mp4', '.m4v', '.webm', '.mov', '.unity3d']
OBJ_EXTS = ['.obj']
BUNDLE_EXTS = ['.unity3d']
PDF_EXTS = ['.pdf']
TXT_EXTS = ['.txt']

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

# TTS uses UPPER_CASE extensions for these files
UPPER_EXTS = AUDIO_EXTS + PDF_EXTS + TXT_EXTS

def is_obj(trail, url):
    # TODO: None of my mods have NormalURL set (normal maps?). I’m
    # assuming these are image files.
    obj_keys = ("MeshURL", "ColliderURL")
    return trail[-1] in obj_keys


def is_image(trail, url):
    # This assumes that we only have mesh, assetbundle, audio, PDF and image
    # URLs.
    return not (
        is_obj(trail, url)
        or is_assetbundle(trail, url)
        or is_audiolibrary(trail, url)
        or is_pdf(trail, url)
        or is_from_script(trail, url)
        or is_custom_ui_asset(trail, url)
    )


def is_assetbundle(trail, url):
    bundle_keys = ("AssetbundleURL", "AssetbundleSecondaryURL")
    return trail[-1] in bundle_keys


def is_audiolibrary(trail, url):
    audio_keys = ("CurrentAudioURL", "AudioLibrary")
    return trail[-1] in audio_keys


def is_pdf(trail, url):
    return trail[-1] == "PDFUrl"


def is_from_script(trail, url):
    return trail[-1] == "LuaScript"


def is_custom_ui_asset(trail, url):
    return 'CustomUIAssets' in trail


def recodeURL(url):
    """Recode the given URL in the way TTS does, which yields the
    file-system trail to the cached file."""

    return re.sub(r"[\W_]", "", url)


def get_fs_path_from_json_path(path, url, exts):
    recoded_name = recodeURL(url)

    for ext in exts:
        # Search the url for a valid extension
        if url.lower().find(ext.lower()) > 0:
            filename  = recoded_name + ext
            filename = os.path.join(path, filename)
            break
        else:
            # URL didn't give us any hints, so check if this file has already
            # been cached and use the extension from the cached filename
            filename = recoded_name + ext
            filename = os.path.join(path, filename)
            if os.path.exists(filename):
                break
    else:
        filename = get_fs_path_from_url(url)
        if filename is None:
            # This file has not been cached and extension is not included in url
            # so we don't know the extension yet. TBD when we download.
            filename = os.path.join(path, recoded_name)

    return filename


def search_downloaded_files(url):
    recoded_name = recodeURL(url)

    for ttsexts, path in MOD_PATHS:
        for ttsext in ttsexts:
            filename = recoded_name + ttsext
            filename = os.path.join(path, filename)
            if os.path.exists(filename):
                return filename
    else:
        return get_fs_path_from_url(url)


def get_fs_path_from_extension(url, ext):
    recoded_name = recodeURL(url)

    for ttsexts, path in MOD_PATHS:
        if ext.lower() in ttsexts:
            filename = recoded_name + ext
            filename = os.path.join(path, filename)
            return filename
    else:
        return None

def get_fs_path_from_url(url):
    # Use the url to extract the extension, ignoring any trailing ? url parameters
    offset = url.rfind("?")
    if offset > 0:
        ext = os.path.splitext(url[0:url.rfind("?")])[1]
    else:
        ext = os.path.splitext(url)[1]
    
    if ext != "":
        return get_fs_path_from_extension(url, ext)

def get_fs_path(trail, url):
    """Return a file-system path to the object in the cache."""

    recoded_name = recodeURL(url)

    if is_from_script(trail, url):
        # Can be different extensions and mod directories, so search the cache for
        # any matches.  If none are found we'll determine the file path during the
        # download process.
        filename = search_downloaded_files(url)
        return filename

    elif is_custom_ui_asset(trail, url):
        # Can be different extensions and mod directories, so search the cache for
        # any matches.  If none are found we'll determine the file path during the
        # download process.
        filename = search_downloaded_files(url)
        return filename

    elif is_obj(trail, url):
        filename = recoded_name + ".obj"
        return os.path.join(OBJPATH, filename)

    elif is_assetbundle(trail, url):
        filename = recoded_name + ".unity3d"
        return os.path.join(BUNDLEPATH, filename)

    elif is_audiolibrary(trail, url):
        # We know the cache location of the file
        # but the extension may be one of many.
        return get_fs_path_from_json_path(AUDIOPATH, url, AUDIO_EXTS)

    elif is_pdf(trail, url):
        filename = recoded_name + ".PDF"
        return os.path.join(PDFPATH, filename)

    elif is_image(trail, url):
        # We know the cache location of the file
        # but the extension may be one of many.
        return get_fs_path_from_json_path(IMGPATH, url, IMG_EXTS)

    else:
        errstr = (
            "Do not know how to generate path for "
            "URL {url} at {trail}.".format(url=url, trail=trail)
        )
        raise ValueError(errstr)


def find_file(url: str, trail: str) -> str:
    
    # Some mods contain malformed URLs missing a prefix. I’m not
    # sure how TTS deals with these. Let’s assume http for now.
    if not urllib.parse.urlparse(url).scheme:
        fetch_url = "http://" + url
    else:
        fetch_url = url

    try:
        if urllib.parse.urlparse(fetch_url).hostname.find('localhost') >= 0:
            return "", 0
    except:
        # URL was so badly formatted that there is no hostname.
        # missing.append((url, f"Invalid hostname",''))
        return "", 0

    filepath = get_fs_path(trail, url)
    if filepath is None:
        filepath = ""
    
    if os.path.exists(filepath):
        mtime = os.path.getmtime(filepath)
    else:
        mtime = 0

    return filepath, mtime