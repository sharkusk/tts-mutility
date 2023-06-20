from contextlib import suppress
import http.client
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

from ttsmutility.parse.FileFinder import UPPER_EXTS, get_fs_path_from_extension

from ttsmutility.parse.FileFinder import (
    is_obj,
    is_assetbundle,
    is_audiolibrary,
    is_custom_ui_asset,
    is_from_script,
    is_image,
    is_pdf,
    get_fs_path,
)

DEFAULT_EXT = {
    "text/plain": ".obj",
    "application/json": ".obj",
    "application/x-tgif": ".obj",
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
}


def fix_ext_case(ext):
    if ext.lower() in UPPER_EXTS:
        return ext.upper()
    else:
        return ext.lower()


def download_files(
    urls,
    mod_dir,
    state_callback,
    ignore_content_type=False,
    timeout=10,
    timeout_retries=10,
    user_agent="TTS prefetch",
):
    # get_fs_path is relative, so need to change to the gamedir directory
    # so existing file extensions can be properly detected
    old_dir = os.getcwd()
    os.chdir(mod_dir)

    for url, trail in urls:
        # Some mods contain malformed URLs missing a prefix. I’m not
        # sure how TTS deals with these. Let’s assume http for now.
        if not urllib.parse.urlparse(url).scheme:
            fetch_url = "http://" + url
        else:
            fetch_url = url

        try:
            if urllib.parse.urlparse(fetch_url).hostname.find("localhost") >= 0:
                state_callback("error", url, f"localhost url")
                continue
        except:
            # URL was so badly formatted that there is no hostname.
            state_callback("error", url, f"Invalid hostname")
            continue

        # type in the response.
        if is_obj(trail, url):
            default_ext = ".obj"

            def content_expected(mime):
                return any(
                    map(
                        mime.startswith,
                        (
                            "text/plain",
                            "application/binary",
                            "application/octet-stream",
                            "application/json",
                            "application/x-tgif",
                        ),
                    )
                )

        elif is_assetbundle(trail, url):
            default_ext = ".unity3d"

            def content_expected(mime):
                return any(
                    map(
                        mime.startswith,
                        ("application/binary", "application/octet-stream"),
                    )
                )

        elif is_image(trail, url):
            default_ext = ".png"

            def content_expected(mime):
                return mime in (
                    "image/jpeg",
                    "image/jpg",
                    "image/png",
                    "application/octet-stream",
                    "application/binary",
                    "video/mp4",
                )

        elif is_audiolibrary(trail, url):
            default_ext = ".WAV"

            def content_expected(mime):
                return mime in (
                    "application/octet-stream",
                    "application/binary",
                ) or mime.startswith("audio/")

        elif is_pdf(trail, url):
            default_ext = ".PDF"

            def content_expected(mime):
                return mime in (
                    "application/pdf",
                    "application/binary",
                    "application/octet-stream",
                )

        elif is_from_script(trail, url) or is_custom_ui_asset(trail, url):
            default_ext = ".png"

            def content_expected(mime):
                return mime in (
                    "text/plain",
                    "application/pdf",
                    "application/binary",
                    "application/octet-stream",
                    "application/json",
                    "application/x-tgif",
                    "image/jpeg",
                    "image/jpg",
                    "image/png",
                    "video/mp4",
                )

        else:
            errstr = "Do not know how to retrieve URL {url} at {trail}.".format(
                url=url, trail=trail
            )
            raise ValueError(errstr)

        filepath = get_fs_path(trail, url)
        headers = {"User-Agent": user_agent}

        for i in range(timeout_retries):
            state_callback("download_starting", url, i)
            try:
                results = download_file(
                    url,
                    fetch_url,
                    filepath,
                    headers,
                    timeout,
                    content_expected,
                    ignore_content_type,
                    default_ext,
                    state_callback,
                )
            except socket.timeout as error:
                continue
            except http.client.IncompleteRead as error:
                continue
            if results is not None:
                # See if we have some trailing URL options and retry if so
                offset = fetch_url.rfind("?")
                if offset > 0:
                    fetch_url = fetch_url[0 : fetch_url.rfind("?")]
                    continue
            break
        else:
            state_callback("error", url, f"Retries exhausted")
            continue

        if results is None:
            state_callback("success", url, None)
        else:
            state_callback("error", url, results)

    os.chdir(old_dir)


def download_file(
    url,
    fetch_url,
    filepath,
    headers,
    timeout,
    content_expected,
    ignore_content_type,
    default_ext_from_path,
    state_callback,
):
    request = urllib.request.Request(url=fetch_url, headers=headers)

    try:
        response = urllib.request.urlopen(request, timeout=timeout)

    except urllib.error.HTTPError as error:
        return f"HTTPError {error.code} ({error.reason})"

    except urllib.error.URLError as error:
        return f"URLError ({error.reason})"

    except http.client.HTTPException as error:
        return f"HTTPException ({error})"

    try:
        if os.path.basename(response.url) == "removed.png":
            # Imgur sends bogus png when files are missing, ignore them
            return f"Removed"
    except UnboundLocalError:
        pass

    # Only for informative purposes.
    length = response.getheader("Content-Length", 0)
    length_kb = "???"
    if length:
        with suppress(ValueError):
            length_kb = int(length) / 1000
    size_msg = "({length} kb)".format(length=length_kb)

    state_callback("file_size", url, int(length))

    # Some content_type arrives as: 'text/plain; charset=utf-8', we only care about
    # the first part...
    content_type = response.getheader("Content-Type", "").split(";")[0].strip()
    is_expected = not content_type or content_expected(content_type)
    if not (is_expected or ignore_content_type):
        # Google drive sends html error page when file is removed/missing
        return f"Wrong context type ({content_type})"

    filename_ext = ""
    ext = ""

    # Format of content disposition looks like this:
    # 'attachment; filename="03_Die nostrische Hochzeit (Instrumental).mp3"; filename*=UTF-8\'\'03_Die%20nostrische%20Hochzeit%20%28Instrumental%29.mp3'
    content_disposition = response.getheader("Content-Disposition", "").strip()
    offset_std = content_disposition.find('filename="')
    offset_utf = content_disposition.find("filename*=UTF-8")
    if offset_std >= 0:
        name = content_disposition[offset_std:].split('"')[1]
        _, filename_ext = os.path.splitext(name)
    elif offset_utf >= 0:
        name = content_disposition[offset_utf:].split("=UTF-8")[1]
        _, filename_ext = os.path.splitext(name.split(";")[0])
    else:
        # Use the url to extract the extension, ignoring any trailing ? url parameters
        offset = url.rfind("?")
        if offset > 0:
            filename_ext = os.path.splitext(url[0 : url.rfind("?")])[1]
        else:
            filename_ext = os.path.splitext(url)[1]

    if filename_ext == "":
        if content_type in DEFAULT_EXT:
            filename_ext = DEFAULT_EXT[content_type]
        else:
            filename_ext = default_ext_from_path

    # TTS saves some file extensions as upper case
    filename_ext = fix_ext_case(filename_ext)

    if filepath is None:
        ext = filename_ext
        filepath = get_fs_path_from_extension(url, ext)

        if filepath is None:
            return f"Cannot detect filepath ({ext})"
    else:
        # Check if we know the extension of our filename.  If not, use
        # the data in the response to determine the appropriate extension.
        ext = os.path.splitext(filepath)[1]
        if ext == "":
            ext = filename_ext
            filepath = filepath + ext

    asset_dir = os.path.split(os.path.split(filepath)[0])[1]
    state_callback("filepath", url, filepath)
    state_callback("asset_dir", url, asset_dir)

    try:
        with open(filepath, "wb") as outfile:
            data = response.read(1024 * 8)
            while data:
                state_callback("data_read", url, 1024 * 8)
                outfile.write(data)
                data = response.read(1024 * 8)

    except FileNotFoundError as error:
        return f"Error writing object to disk: {error}"

    # Don’t leave files with partial content lying around.
    except Exception:
        with suppress(FileNotFoundError):
            os.remove(filepath)
        raise

    except SystemExit:
        with suppress(FileNotFoundError):
            os.remove(filepath)
        raise

    return None
