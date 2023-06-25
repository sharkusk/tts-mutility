from textual.app import ComposeResult
from textual.widgets import Static
from textual.widgets import Footer
from textual.widgets import Markdown, MarkdownViewer
from textual.screen import ModalScreen

from rich.markdown import Markdown

import time
import re
import os
from pathlib import Path

ASSET_DETAIL_MD = """
# {mod_name}

## URL
[{url}]({url})

## Local File URI
[{uri}]({uri})

file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png

> file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png


`file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png`


'file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png'


<a href="file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Plain href</a>


> <a href="file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Block quote href</a>


`<a href="file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">code href</a>`


> `<a href="file:///C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Blockquote code href</a>`


<a href="file://localhost/C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Localhost Plain href</a>


`<a href="file://localhost/C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Localhost Code href</a>`


> <a href="file://localhost/C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Localhost blockquote href</a>


> `<a href="file://localhost/C:/Program%20Files%20%28x86%29/Steam/steamapps/common/Tabletop%20Simulator/Tabletop%20Simulator_Data/Mods/Images/httpcloud3steamusercontentcomugc1816689614996344078BAAC59ECEA0935A6A7200EDF8183892F2079F39.png">Localhost blockquote code href</a>`



## TTS Mod Filepath
{filename}


`{filepath}`


{normpath}


{pathlib}


"{normpath}"

| Asset Details | |
|------------------------------:|:------------------|
| Modified Time                 | {mtime}           |
| File Size                     | {fsize:,}         |
| JSON Trail                    | {trail}           |
| Content Filename              | {content_name}    |
| SHA1 Hexdigest                | {sha1}            |
| Download Error Status         | {dl_status}       |

## All TTS Mods Using Asset
{other_mods}
"""


class AssetDetailScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("f", "toggle_fullscreen", "Fullscreen"),
    ]

    def __init__(self, asset_detail: dict) -> None:
        self.asset_detail = asset_detail
        super().__init__()

    def compose(self) -> ComposeResult:
        yield MarkdownViewer(
            self.get_markdown(),
            id="ad_screen",
            show_table_of_contents=False,
        )
        yield Footer()

    def action_toggle_fullscreen(self) -> None:
        self.query_one("#ad_screen").toggle_class("fs")

    def get_markdown(self) -> str:
        if self.asset_detail["mtime"] == 0:
            self.asset_detail["mtime"] = "File not found"
        else:
            self.asset_detail["mtime"] = time.ctime(self.asset_detail["mtime"])
        self.asset_detail["other_mods"] = "`\n- `".join(self.asset_detail["other_mods"])
        self.asset_detail["other_mods"] = self.asset_detail["other_mods"].join(
            ["\n- `", "`\n"]
        )
        self.asset_detail["uri"] = self.asset_detail["uri"][6:]
        self.asset_detail["normpath"] = os.path.normpath(self.asset_detail["filepath"])
        self.asset_detail["pathlib"] = str(Path(self.asset_detail["filepath"]))
        return ASSET_DETAIL_MD.format(**self.asset_detail)

    def _validate_uri_file_link(self, text, pos):
        tail = text[pos:]

        validate = "^///(\S*)"

        founds = re.search(self.re["not_http"], tail, flags=re.IGNORECASE)
        if founds:
            return len(founds.group(0))

        return 0
