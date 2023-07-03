from textual.app import ComposeResult
from textual.widgets import Footer
from textual.widgets import Markdown
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.message import Message

import time
from pathlib import Path
from webbrowser import open as open_url
from urllib.parse import unquote, urlparse, quote
from PIL import Image
import requests
from io import BytesIO

from ..data.config import load_config
from ..parse.AssetList import AssetList
from ..parse.ModList import ModList
from ..parse.ModParser import INFECTION_URL
from ..parse.BggSearch import BggSearch
from ..dialogs.SelectOptionDialog import SelectOptionDialog
from ..dialogs.InputDialog import InputDialog
from ..dialogs.InfoDialog import InfoDialog


class ModDetailScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("a", "asset_list", "Asset List"),
        ("b", "bgg_lookup", "BGG Lookup"),
        ("n", "bgg_lookup_input", "BGG Lookup (Edit)"),
        ("t", "set_tts_thumb", "Set TTS Thumbnail"),
    ]

    class AssetsSelected(Message):
        def __init__(self, mod_filename: str) -> None:
            self.mod_filename = mod_filename
            super().__init__()

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.ad_uri_prefix = "//asset_detail/"
        self.dl_image_uri_prefix = "//dl_image/"
        config = load_config()
        self.mod_dir = Path(config.tts_mods_dir)
        self.save_dir = Path(config.tts_saves_dir)
        self.mod_list = ModList()
        self.mod_detail = self.mod_list.get_mod_details(self.filename)
        self.bs = BggSearch()
        super().__init__()

    def compose(self) -> ComposeResult:
        with Container(id="md_screen"):
            yield Footer()
            with VerticalScroll(id="md_scroll"):
                yield Markdown(
                    self.get_markdown(),
                    id="md_markdown",
                )

    def format_list(self, l):
        return "\n- ".join(l).join(["\n- ", "\n"])
        # return "`\n- `".join(l).join(["\n- `", "`\n"])

    def get_mod_image_path(self) -> Path:
        if self.filename.find("Workshop") == 0:
            image_path = self.mod_dir / Path(self.filename).with_suffix(".png")
        else:
            image_path = self.save_dir / Path(self.filename).with_suffix(".png")
        return image_path

    def get_markdown(self) -> str:
        mod_detail_md = ""
        md_filepath = Path(__file__).with_name("ModDetailScreen.md")
        with md_filepath.open("r") as f:
            mod_detail_md = f.read()

        mod_detail = self.mod_detail.copy()

        if (image_path := self.get_mod_image_path()).exists():
            mod_detail[
                "mod_image"
            ] = f"- TTS Image: [Mod Image]({image_path.as_uri().replace('file:///', '//localhost/')})"
        else:
            mod_detail["mod_image"] = ""

        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        if mod_detail["name"] in infected_mods:
            mod_detail[
                "infection_warning"
            ] = "\n\n\n## WARNING!  A TTS viral infection has been detected in this mod.  Do not copy objects from this mod!\n\n\n"
        else:
            mod_detail["infection_warning"] = ""

        mod_detail["asset_detail_url"] = quote(f"{self.ad_uri_prefix}{self.filename}")
        mod_detail["size"] = mod_detail["size"] / (1024)
        mod_detail["mtime"] = time.ctime(mod_detail["mtime"])
        mod_detail["epoch"] = time.ctime(mod_detail["epoch"])
        if "Workshop" in self.filename:
            mod_detail["uri"] = (self.mod_dir / self.filename).as_uri()
        else:
            mod_detail["uri"] = (self.save_dir / self.filename).as_uri()
        mod_detail["uri_short"] = mod_detail["uri"].replace("file:///", "//localhost/")
        if len(mod_detail["tags"]) > 0:
            mod_detail["tag_list"] = self.format_list(mod_detail["tags"])
        else:
            mod_detail["tag_list"] = "- N/A"

        mod_detail[
            "steam_link"
        ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={Path(self.filename).stem}"
        if mod_detail["bgg_id"] is None:
            mod_detail["bgg_link"] = ""
            bgg_md = ""
        else:
            mod_detail["bgg_link"] = self.bs.get_game_url(mod_detail["bgg_id"])
            bgg_md = self.get_bgg_markdown(mod_detail["bgg_id"])

        main_md = mod_detail_md.format(**mod_detail)

        return main_md + bgg_md

    def create_chart(self, results, width):
        TICKS = "▏▎▍▌▋▊▉█"

        # Find min and max values, used determine block size
        # Find max label size, determine start of chart blocks
        # For each row, print spaces, label, then blocks

        # Find largest and smallest number of votes
        max_votes = 0
        min_votes = 10000000
        bar_name_max_size = 0
        multi_bar = False

        chart_name = results["name"]
        chart_title = results["title"]
        total_votes = results["totalvotes"]

        chart = f"## {chart_title}\n"

        for bar_name in results[chart_name]:
            bar_values = results[chart_name][bar_name]
            if isinstance(bar_values, list):
                multi_bar = True
                # Multi-bar per result
                for sub_result in bar_values:
                    value = sub_result["value"]
                    if 3 + len(bar_name) + len(value) > bar_name_max_size:
                        bar_name_max_size = 3 + len(bar_name) + len(value)
                    if int(sub_result["numvotes"]) < min_votes:
                        min_votes = int(sub_result["numvotes"])
                    if int(sub_result["numvotes"]) > max_votes:
                        max_votes = int(sub_result["numvotes"])
            else:
                # Single-bar per result
                if len(bar_name) > bar_name_max_size:
                    bar_name_max_size = len(bar_name)
                if int(bar_values["numvotes"]) < min_votes:
                    min_votes = int(bar_values["numvotes"])
                if int(bar_values["numvotes"]) > max_votes:
                    max_votes = int(bar_values["numvotes"])

        if bar_name_max_size > int(width / 1.5):
            bar_name_max_size = int(width / 1.5)
        votes_per_tick = 1 + int((max_votes - min_votes) / (width - bar_name_max_size))

        line = "```\n"
        chart += line

        for bar_name in results[chart_name]:
            bar_values = results[chart_name][bar_name]
            if len(bar_name) > bar_name_max_size:
                bar_name = bar_name[0:bar_name_max_size]
            if multi_bar:
                line = "─" * width
                line += "  \n"
                chart += line
                for i, sub_result in enumerate(bar_values):
                    value = sub_result["value"]
                    numvotes = sub_result["numvotes"]
                    if i == 1:
                        line = bar_name + " " * (
                            bar_name_max_size - len(bar_name) - len(value) - 1
                        )
                    else:
                        line = " " * (bar_name_max_size - len(value) - 1)
                    line += value + "▕"
                    num_ticks = int(int(numvotes) / votes_per_tick)
                    line += TICKS[-1] * num_ticks
                    remainder = (int(numvotes) / votes_per_tick) % 1
                    if remainder != 0:
                        tick = int(remainder / 0.125)
                        line += TICKS[tick]
                    line += " " + numvotes
                    line += "  \n"
                    chart += line
            else:
                line = " " * (bar_name_max_size - len(bar_name))
                line += bar_name + "▕"
                num_ticks = int(int(bar_values["numvotes"]) / votes_per_tick)
                line += TICKS[-1] * num_ticks
                remainder = (int(bar_values["numvotes"]) / votes_per_tick) % 1
                if remainder != 0:
                    tick = int(remainder / 0.125)
                    line += TICKS[tick]
                line += " " + bar_values["numvotes"]
                line += "\n"
                chart += line

        if multi_bar:
            line = "─" * width
            line += "  \n"
            chart += line

        line = "```\n"
        chart += line
        return chart

    def get_bgg_markdown(self, bgg_id) -> str:
        bgg_detail_md = ""
        md_filepath = Path(__file__).with_name("BGGDetailScreen.md")
        with md_filepath.open("r") as f:
            bgg_detail_md = f.read()

        bgg_detail = self.bs.get_game_info(bgg_id)
        for field in self.bs.BGG_LISTS:
            if field in bgg_detail:
                bgg_detail[f"{field}_list"] = self.format_list(bgg_detail[field])
            else:
                bgg_detail[f"{field}_list"] = "- N/A"

        for poll in self.bs.BGG_POLLS:
            if poll in bgg_detail:
                bgg_detail[poll + "_chart"] = self.create_chart(bgg_detail[poll], 90)

        for stat in self.bs.BGG_STATS_LISTS:
            if stat in bgg_detail:
                bgg_detail["ranking"] = ""
                for v in bgg_detail[stat]:
                    bgg_detail["ranking"] += f"- {v['friendlyname']}: {v['value']}  \n"

        bgg_detail["dl_image_url"] = quote(f"{self.dl_image_uri_prefix}/dl_image")

        self.bgg_detail = bgg_detail

        return bgg_detail_md.format(**bgg_detail)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
            open_url(link)
        elif self.ad_uri_prefix in event.href:
            filename = unquote(urlparse(event.href[len(self.ad_uri_prefix) :]).path)
            self.post_message(self.AssetsSelected(filename))
        elif self.dl_image_uri_prefix in event.href:
            self.action_set_tts_thumb()
        else:
            open_url(event.href)

    def refresh_mod_details(self):
        self.query_one("#md_markdown").update(self.get_markdown())

    def action_asset_list(self):
        self.post_message(self.AssetsSelected(self.filename))

    def action_bgg_lookup_input(self, msg: str = "Please enter search string:"):
        def set_name(name: str) -> None:
            self.action_bgg_lookup(name)

        self.app.push_screen(InputDialog(self.mod_detail["name"], msg=msg), set_name)

    def action_bgg_lookup(self, mod_name: str = ""):
        if mod_name == "":
            mod_name = self.mod_detail["name"]

        bgg_matches = self.bs.search(mod_name)

        options = [f"{name} ({year}) [{id}]" for name, id, year in bgg_matches]

        if len(options) > 0:

            def set_id(index: int) -> None:
                offset_start = options[index].rfind("[") + 1
                offset_end = options[index].rfind("]")
                self.mod_detail["bgg_id"] = options[index][offset_start:offset_end]
                md = self.query_one("#md_markdown")
                md.update(self.get_markdown())
                self.mod_list.set_bgg_id(self.filename, self.mod_detail["bgg_id"])

            self.app.push_screen(SelectOptionDialog(options), set_id)
        else:
            self.action_bgg_lookup_input(
                msg="No matches found. Please update search string:"
            )

    def action_set_tts_thumb(self):
        if self.mod_detail["bgg_id"] is None:
            self.app.push_screen(
                InfoDialog(
                    "Unable to update thumbnail.\nThere is no BGG game associated with this MOD."
                )
            )
        else:
            response = requests.get(self.bgg_detail["image"])
            img = Image.open(BytesIO(response.content))
            save_path = self.get_mod_image_path()
            img.save(save_path)
            self.refresh_mod_details()
            self.app.push_screen(InfoDialog("Updated TTS Thumbnail"))
