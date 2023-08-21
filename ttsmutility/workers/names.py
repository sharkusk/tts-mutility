from urllib.parse import urlparse

import requests
from textual.app import ComposeResult
from textual.worker import get_current_worker

from ..parse.AssetList import AssetList
from ..utility.advertising import USER_AGENT
from ..utility.messages import UpdateLog
from ..utility.util import get_content_name
from .TTSWorker import TTSWorker

# Recursively read each directory
# Load existing dictionary, for each file not found in dictionary:
# Files that match steam pattern, extract SHA-1 values, add to {SHA1, filename}
# For non-steam files generate SHA-1 values, add to dictionary
# For each line is missing url file:
#   Extract SHA-1
#   Check if matching SHA-1 file is found
#   Copy and rename to destination directory


class NameScanner(TTSWorker):
    # Base class is installed in each screen, so we don't want
    # to inherit the same widgets when this subclass is mounted
    def compose(self) -> ComposeResult:
        return []

    def scan_names(self) -> None:
        asset_list = AssetList()

        worker = get_current_worker()

        self.post_message(UpdateLog("Starting Name Detection"))

        urls = asset_list.get_blank_content_names()

        self.post_message(self.UpdateProgress(len(urls), None))

        updated_urls = []
        updated_names = []

        url_name_count = 0
        cd_name_count = 0

        self.post_message(UpdateLog(f"R {len(urls)} missing names to be scanned."))
        self.post_message(self.UpdateProgress(advance_amount=1))
        for i, url in enumerate(urls):
            self.post_message(self.UpdateProgress(advance_amount=1))

            if worker.is_cancelled:
                asset_list.set_content_names(updated_urls, updated_names)
                self.post_message(
                    UpdateLog(
                        f"Name detection cancelled at {i}/{len(urls)}.", flush=True
                    )
                )
                return

            if (content_name := get_content_name(url)) != "":
                updated_urls.append(url)
                updated_names.append(content_name)
                url_name_count += 1

                self.post_message(
                    self.UpdateStatus(
                        f'Scanning {i}/{len(urls)} missing names.\n{url} -> "{content_name}"'
                    )
                )
                continue

            domain = urlparse(url).netloc
            headers = {"User-Agent": USER_AGENT}
            if "pastebin.com" in domain:
                # Pastebin will provide us the original filename if we use the dl link.
                # This requires a referer from the original pastebin link, so we need
                # to extract it.
                pastebin_ref = ""
                if "pastebin.com/raw.php" in url:
                    pastebin_ref = url.split("=")[-1]
                else:
                    pastebin_ref = url.split("/")[-1]

                if len(pastebin_ref) > 0:
                    headers["Referer"] = f"http://pastebin.com/{pastebin_ref}"
                    fetch_url = f"http://pastebin.com/dl/{pastebin_ref}"
                else:
                    self.post_message(
                        self.UpdateStatus(
                            f"Scanning {i}/{len(urls)} missing names.\n{url} -> (Unable to detect pastebin hash)"
                        )
                    )
                    continue
            elif "paste.ee" in domain:
                self.post_message(
                    self.UpdateStatus(
                        f"Scanning {i}/{len(urls)} missing names.\n{url} -> (paste.ee tell no names)"
                    )
                )
                continue
            else:
                fetch_url = url

            # Some links are missing the http:// portion of the address
            if not urlparse(fetch_url).scheme:
                fetch_url = "http://" + fetch_url

            try:
                with requests.get(
                    url=fetch_url, headers=headers, allow_redirects=True, stream=True
                ) as response:
                    if response.status_code != 200:
                        dl_status = f"HTTPError {response.status_code} ({response.reason}) [namescan]"
                        self.post_message(
                            self.UpdateStatus(
                                f"Scanning {i}/{len(urls)} missing names.\n{url} -> <{dl_status}>"
                            )
                        )
                        # In most cases, 404 does mean the asset doesn't exist. This error will get
                        # returned by steamusercontent if the HEAD method is used for some cases.
                        if response.status_code == 404:
                            asset_list.set_dl_status(url, dl_status)
                        continue
                    if "Content-Disposition" in response.headers:
                        content_disposition = response.headers[
                            "Content-Disposition"
                        ].strip()
                    elif "content-disposition" in response.headers:
                        content_disposition = response.headers[
                            "content-disposition"
                        ].strip()
                    else:
                        self.post_message(
                            self.UpdateStatus(
                                f"Scanning {i}/{len(urls)} missing names.\n{url} -> (No Content-Disposition)"
                            )
                        )
                        continue
            except Exception as error:
                # Can be caused by local file urls or embedded <dlc>
                self.post_message(
                    self.UpdateStatus(
                        f"Scanning {i}/{len(urls)} missing names.\n{url} -> {error}"
                    )
                )
                continue

            if (content_name := get_content_name(url, content_disposition)) != "":
                updated_urls.append(url)
                updated_names.append(content_name)
                cd_name_count += 1

                self.post_message(
                    self.UpdateStatus(
                        f'Scanning {i}/{len(urls)} missing names.\n{url} -> "{content_name}"'
                    )
                )
            else:
                self.post_message(
                    self.UpdateStatus(
                        f"Scanning {i}/{len(urls)} missing names.\n{url} -> (No Name Found)"
                    )
                )

            if len(updated_names) > 50:
                asset_list.set_content_names(updated_urls, updated_names)
                updated_urls = []
                updated_names = []

        asset_list.set_content_names(updated_urls, updated_names)

        self.post_message(UpdateLog("Content Name detection complete."))
        self.post_message(
            self.UpdateStatus(
                f"Complete. New names: URL:{url_name_count} & CD:{cd_name_count}"
            )
        )
