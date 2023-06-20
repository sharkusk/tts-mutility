from contextlib import suppress
import http.client
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

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


def download_file(
    url,
    fetch_url,
    outfile_name,
    headers,
    timeout,
    content_expected,
    ignore_content_type,
    default_ext_from_path,
    ps,
    retry_num,
    verbose,
):
    missing = None
    request = urllib.request.Request(url=fetch_url, headers=headers)

    try:
        response = urllib.request.urlopen(request, timeout=timeout)

    except urllib.error.HTTPError as error:
        ps.print("Error {code} ({reason})".format(code=error.code, reason=error.reason))
        missing = (url, f"HTTPError {error.code} ({error.reason})")

    except urllib.error.URLError as error:
        ps.print("Error ({reason})".format(reason=error.reason))
        missing = (url, f"URLError ({error.reason})")

    except http.client.HTTPException as error:
        ps.print("HTTP error ({reason})".format(reason=error))
        missing = (url, f"HTTPException ({error})")

    try:
        if os.path.basename(response.url) == "removed.png":
            # Imgur sends bogus png when files are missing, ignore them
            ps.print("Removed")
            missing = (url, f"Removed")
    except UnboundLocalError:
        pass

    if missing is not None:
        return missing

    # Only for informative purposes.
    length = response.getheader("Content-Length", 0)
    length_kb = "???"
    if length:
        with suppress(ValueError):
            length_kb = int(length) / 1000
    size_msg = "({length} kb)".format(length=length_kb)

    # Some content_type arrives as: 'text/plain; charset=utf-8', we only care about
    # the first part...
    content_type = response.getheader("Content-Type", "").split(";")[0].strip()
    is_expected = not content_type or content_expected(content_type)
    if not (is_expected or ignore_content_type):
        # Google drive sends html error page when file is removed/missing
        ps.print("Error: Wrong Content type {type}.".format(type=content_type))
        return (url, f"Wrong context type ({content_type})")

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

    if outfile_name is None:
        ext = filename_ext
        outfile_name = get_fs_path_from_extension(url, ext)

        if outfile_name is None:
            ps.print("Cannot detect filepath for filetype '{type}'.".format(type=ext))
            return (url, f"Cannot detect filepath ({ext})")
    else:
        # Check if we know the extension of our filename.  If not, use
        # the data in the response to determine the appropriate extension.
        ext = os.path.splitext(outfile_name)[1]
        if ext == "":
            ext = filename_ext
            outfile_name = outfile_name + ext

    if ext == "":
        print_err("Warning: Cannot find extension for {name}.")

    mod_dir = os.path.split(os.path.split(outfile_name)[0])[1]
    if verbose:
        ps.print(f"{ext} -> {mod_dir} {size_msg}: ", end="", flush=True)
    else:
        # We want to print progress bar status immediately...
        ps.print(f"{ext} -> {mod_dir} {size_msg}")

    try:
        with open(outfile_name, "wb") as outfile:
            num_segs = int(int(length) / (8 * 1024))
            desc = f"{ext}->{mod_dir} {size_msg}"
            if retry_num > 0:
                desc = f"Retry {retry_num} - {desc}"
            with tqdm(total=num_segs, leave=False, desc=desc) as pbar:
                pbar.update(1)
                data = response.read(1024 * 8)
                while data:
                    outfile.write(data)
                    data = response.read(1024 * 8)
                    pbar.update(1)

    except FileNotFoundError as error:
        print_err("Error writing object to disk: {}".format(error))
        raise

    # Don’t leave files with partial content lying around.
    except Exception:
        with suppress(FileNotFoundError):
            ps.print(f"..cleanup.. ", end="", flush=True)
            os.remove(outfile_name)
        raise

    except SystemExit:
        with suppress(FileNotFoundError):
            ps.print(f"..cleanup.. ", end="", flush=True)
            os.remove(outfile_name)
        raise

    else:
        if verbose:
            ps.print("ok")

    if not is_expected:
        errmsg = "Warning: Content type {} did not match " "expected type.".format(
            content_type
        )
        print_err(errmsg)

    return None


def prefetch_file(
    filename,
    refetch=False,
    ignore_content_type=False,
    dry_run=False,
    gamedata_dir=GAMEDATA_DEFAULT,
    timeout=10,
    timeout_retries=10,
    semaphore=None,
    user_agent="TTS prefetch",
    verbose=False,
):
    try:
        save_name = get_save_name(filename)
    except Exception:
        save_name = "???"

    # get_fs_path is relative, so need to change to the gamedir directory
    # so existing file extensions can be properly detected
    os.chdir(gamedata_dir)

    readable_filename = f"{os.path.basename(filename)} [{save_name}]"

    if verbose:
        print(readable_filename)

    try:
        urls = urls_from_save(filename)
    except (FileNotFoundError, IllegalSavegameException) as error:
        print_err(
            "Error retrieving URLs from {filename}: {error}".format(
                error=error, filename=filename
            )
        )
        raise

    missing = []
    skipped = False
    urls = list(urls)  # Need for progress bar count

    # with alive_bar(len(urls), dual_line=True, title=readable_filename, unit=' files') if not verbose else nullcontext() as bar:
    with tqdm(total=len(urls), desc=save_name, miniters=1) as pbar:
        ps = PrintStatus(None, verbose=verbose)
        for path, url in urls:
            if semaphore and semaphore.acquire(blocking=False):
                ps.print("Aborted.")
                return

            if not verbose:
                pbar.update(1)
                # bar(skipped=skipped)
                skipped = False

            # Some mods contain malformed URLs missing a prefix. I’m not
            # sure how TTS deals with these. Let’s assume http for now.
            if not urllib.parse.urlparse(url).scheme:
                fetch_url = "http://" + url
            else:
                fetch_url = url

            try:
                if urllib.parse.urlparse(fetch_url).hostname.find("localhost") >= 0:
                    skipped = True
                    continue
            except:
                # URL was so badly formatted that there is no hostname.
                missing.append((url, f"Invalid hostname", ""))
                skipped = True
                continue

            # type in the response.
            if is_obj(path, url):
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

            elif is_assetbundle(path, url):
                default_ext = ".unity3d"

                def content_expected(mime):
                    return any(
                        map(
                            mime.startswith,
                            ("application/binary", "application/octet-stream"),
                        )
                    )

            elif is_image(path, url):
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

            elif is_audiolibrary(path, url):
                default_ext = ".WAV"

                def content_expected(mime):
                    return mime in (
                        "application/octet-stream",
                        "application/binary",
                    ) or mime.startswith("audio/")

            elif is_pdf(path, url):
                default_ext = ".PDF"

                def content_expected(mime):
                    return mime in (
                        "application/pdf",
                        "application/binary",
                        "application/octet-stream",
                    )

            elif is_from_script(path, url) or is_custom_ui_asset(path, url):
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
                errstr = "Do not know how to retrieve URL {url} at {path}.".format(
                    url=url, path=path
                )
                raise ValueError(errstr)

            outfile_name = get_fs_path(path, url)
            if outfile_name is not None:
                # Check if the object is already cached.
                if os.path.isfile(outfile_name) and not refetch:
                    skipped = True
                    continue

            if dry_run:
                ps.print("{} ".format(url), end="", flush=True)
                ps.print("dry run")
                continue

            headers = {"User-Agent": user_agent}

            for i in range(timeout_retries):
                if i == 0:
                    retry_message = ""
                else:
                    retry_message = f"Retry {i}: "
                ps.print("{}{} ".format(retry_message, url), end="", flush=True)
                try:
                    results = download_file(
                        url,
                        fetch_url,
                        outfile_name,
                        headers,
                        timeout,
                        content_expected,
                        ignore_content_type,
                        default_ext,
                        ps,
                        i,
                        verbose,
                    )
                except socket.timeout as error:
                    ps.print("Error ({reason}). Retrying...".format(reason=error))
                    continue
                except http.client.IncompleteRead as error:
                    ps.print("Error ({reason}). Retrying...".format(reason=error))
                    continue
                if results is not None:
                    # See if we have some trailing URL options and retry if so
                    offset = fetch_url.rfind("?")
                    if offset > 0:
                        ps.print(
                            "Error ({reason}). Retrying without URL params...".format(
                                reason=results[1]
                            )
                        )
                        fetch_url = fetch_url[0 : fetch_url.rfind("?")]
                        continue
                break
            else:
                print_err("All timeout retries exhausted.")
                sys.exit(1)

            if results is not None:
                skipped = True
                missing.append((results[0], results[1], outfile_name))

    workshop_id = os.path.splitext(os.path.basename(filename))[0]
    dest = os.path.dirname(filename)
    safe_save_name = make_safe_filename(save_name)
    missing_filename = f"{workshop_id} [{safe_save_name}] missing.txt"
    missing_path = os.path.join(dest, missing_filename)

    if len(missing) > 0:
        print(f"...{len(missing)} URLs missing!")
        print(f"Saving missing file list to {missing_path}.")

        with open(missing_path, "w") as f:
            for url, error, outfile_name in missing:
                f.write(f"{url} ({outfile_name}): {error}\n")
    else:
        if os.path.isfile(missing_path):
            print(f"Missing files no longer detected. Deleting {missing_filename}.")
            os.remove(missing_path)

    if dry_run:
        completion_msg = "Dry-run for {} completed."
    else:
        completion_msg = "Prefetching {} completed."
    if verbose:
        print(completion_msg.format(filename))
