import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from webbrowser import open as open_url

import requests
from PIL import Image
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Markdown, TabbedContent, TabPane

from ..data.config import load_config
from ..dialogs.InfoDialog import InfoDialog
from ..dialogs.InputDialog import InputDialog
from ..dialogs.SelectOptionDialog import SelectOptionDialog
from ..parse.AssetList import AssetList
from ..parse.BggSearch import BggSearch
from ..parse.ModList import ModList
from ..parse.ModParser import INFECTION_URL
from ..utility.util import format_time
from .AssetListScreen import AssetListScreen


class ModDetailScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
        ("b", "bgg_lookup", "BGG Lookup"),
        ("n", "bgg_lookup_input", "BGG Lookup (Edit)"),
        ("ctrl+r", "refresh_mod_details", "Reload BGG/Steam"),
    ]

    def __init__(self, filename: str, force_md_update: bool = False) -> None:
        self.filename = filename
        self.in_workshop = True
        if self.filename.find("Saves") == 0:
            self.in_workshop = False
        elif not Path(self.filename).stem.isdigit():
            self.in_workshop = False
        self.ad_uri_prefix = "//asset_detail/"
        self.dl_image_uri_prefix = "//dl_image/"
        config = load_config()
        self.mod_dir = Path(config.tts_mods_dir)
        self.save_dir = Path(config.tts_saves_dir)
        self.mod_list = ModList()
        self.bs = BggSearch()
        self.force_update = force_md_update
        self.mod_detail = self.mod_list.get_mod_details(self.filename).copy()
        self.tab_names = [
            "md_pane_mod",
            "md_pane_steam",
            "md_pane_assets",
        ]
        if not self.in_workshop:
            self.tab_names.remove("md_pane_steam")
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Header()
        yield Label(id="title")
        yield Label(id="infection_warning")
        i = 0
        with TabbedContent(initial=self.tab_names[i]):
            with TabPane("Mod Details", id=self.tab_names[i]):
                with VerticalScroll(id=self.tab_names[i].replace("pane", "scroll")):
                    yield Markdown(
                        id="md_markdown_mod",
                    )
            if self.in_workshop:
                i = i + 1
                with TabPane("Steam Description", id=self.tab_names[i]):
                    with VerticalScroll(id=self.tab_names[i].replace("pane", "scroll")):
                        yield Markdown(
                            id="md_markdown_steam",
                        )
            i = i + 1
            with TabPane("Asset List", id=self.tab_names[i]):
                yield AssetListScreen(
                    self.filename, self.mod_detail["name"], al_id="md_scroll_assets"
                )

    def insert_bgg_tab(self, tab_name="BoardGameGeek"):
        i = self.tab_names.index("md_pane_assets")
        self.tab_names.insert(i, "md_pane_bgg")
        pane = TabPane(
            tab_name,
            VerticalScroll(
                Markdown(
                    id="md_markdown_bgg",
                ),
                id=self.tab_names[i].replace("pane", "scroll"),
            ),
            id=self.tab_names[i],
        )
        tc = self.query_one(TabbedContent)
        tc.add_pane(pane, before="md_pane_assets")

    def on_mount(self):
        self.query_one("#md_markdown_mod").update(self.get_markdown())
        if self.in_workshop:
            self.query_one("#md_markdown_steam").update(self.get_markdown_steam())
        if self.mod_detail["bgg_id"] is not None:
            self.insert_bgg_tab()
            self.query_one("#md_markdown_bgg").update(self.get_markdown_bgg())
        self.query_one("#title").update(self.mod_detail["name"])
        if self.is_infected():
            iw = self.query_one("#infection_warning")
            iw.update(
                (
                    "WARNING!  A TTS viral infection has been detected in this mod. "
                    "Do not copy objects from this mod!"
                )
            )
            iw.add_class("unhide")

    def format_list(self, my_list):
        return "\n- ".join(my_list).join(["\n- ", "\n"])

    def get_mod_image_path(self) -> Path:
        if self.filename.find("Workshop") == 0:
            image_path = self.mod_dir / Path(self.filename).with_suffix(".png")
        else:
            image_path = self.save_dir / Path(self.filename).with_suffix(".png")
        return image_path

    def is_infected(self) -> bool:
        asset_list = AssetList()
        infected_mods = asset_list.get_mods_using_asset(INFECTION_URL)
        if self.mod_detail["name"] in infected_mods:
            return True
        else:
            return False

    def get_markdown_common(self) -> dict:
        mod_detail = self.mod_detail.copy()

        if self.in_workshop:
            steam_link = f"https://steamcommunity.com/sharedfiles/filedetails/?id={Path(self.filename).stem}"
            mod_detail["steam_link"] = f"- Steam Link: [{steam_link}]({steam_link})"
        else:
            mod_detail["steam_link"] = ""

        return mod_detail

    def get_markdown(self) -> str:
        mod_detail = self.get_markdown_common()

        mod_detail_md = ""
        md_filepath = Path(__file__).with_name("ModDetailScreen.md")
        with md_filepath.open("r") as f:
            mod_detail_md = f.read()

        if (image_path := self.get_mod_image_path()).exists():
            mod_detail["mod_image"] = (
                f"- TTS Image: [Mod Image]"
                f"({image_path.as_uri().replace('file:///', '//localhost/')})"
            )
        else:
            mod_detail["mod_image"] = ""

        mod_detail["asset_detail_url"] = quote(f"{self.ad_uri_prefix}{self.filename}")
        mod_detail["size"] = mod_detail["size"] / (1024)
        mod_detail["mtime"] = time.ctime(mod_detail["mtime"])
        mod_detail["epoch"] = time.ctime(mod_detail["epoch"])
        mod_detail["backup_time"] = format_time(mod_detail["backup_time"], "N/A")
        mod_detail["fetch_time"] = format_time(mod_detail["fetch_time"], "N/A")
        mod_detail["newest_asset"] = format_time(mod_detail["newest_asset"], "N/A")
        if "Workshop" in self.filename:
            mod_detail["uri"] = (self.mod_dir / self.filename).as_uri()
        else:
            mod_detail["uri"] = (self.save_dir / self.filename).as_uri()
        mod_detail["uri_short"] = mod_detail["uri"].replace("file:///", "//localhost/")
        if len(mod_detail["tags"]) > 0:
            mod_detail["tag_list"] = self.format_list(mod_detail["tags"])
        else:
            mod_detail["tag_list"] = "- N/A"

        mod_detail["filename_esc"] = (
            mod_detail["filename"]
            .replace("[", "\\[")
            .replace("(", "\\(")
            .replace("]", "\\]")
            .replace(")", "\\)")
        )

        while True:
            try:
                main_md = mod_detail_md.format(**mod_detail)
            except KeyError as missing:
                mod_detail[missing.args[0]] = ""
            else:
                break
        return main_md

    def get_markdown_steam(self, force_update=False) -> str:
        mod_detail = self.get_markdown_common()

        mod_detail_steam = ""
        md_filepath = Path(__file__).with_name("SteamDetailScreen.md")
        with md_filepath.open("r") as f:
            mod_detail_steam = f.read()

        mod_detail.update(
            self.bs.get_steam_details(Path(self.filename).stem, force_update)
        )

        mod_detail["time_created"] = format_time(mod_detail["time_created"])
        mod_detail["time_updated"] = format_time(mod_detail["time_updated"])

        if len(mod_detail["tags"]) > 0:
            mod_detail["tag_list"] = self.format_list(
                [d["tag"] for d in mod_detail["tags"]]
            )
        else:
            mod_detail["tag_list"] = "- N/A"

        while True:
            try:
                steam_md = mod_detail_steam.format(**mod_detail)
            except KeyError as missing:
                mod_detail[missing.args[0]] = ""
            else:
                break
        return steam_md

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

    def get_markdown_bgg(self, force_update=False) -> str:
        mod_detail = self.get_markdown_common()

        if (bgg_id := mod_detail["bgg_id"]) is None:
            mod_detail["bgg_link"] = ""
            return "# No BoardGameGeek ID is associated with this game."

        mod_detail["bgg_link"] = self.bs.get_game_url(mod_detail["bgg_id"])

        bgg_detail_md = ""
        md_filepath = Path(__file__).with_name("BGGDetailScreen.md")
        with md_filepath.open("r") as f:
            bgg_detail_md = f.read()

        mod_detail.update(self.bs.get_game_info(bgg_id, force_update))
        for field in self.bs.BGG_LISTS:
            if field in mod_detail:
                mod_detail[f"{field}_list"] = self.format_list(mod_detail[field])
            else:
                mod_detail[f"{field}_list"] = "- N/A"

        for poll in self.bs.BGG_POLLS:
            if poll in mod_detail and int(mod_detail[poll]['totalvotes']) > 0:
                mod_detail[poll + "_chart"] = self.create_chart(mod_detail[poll], 90)

        for stat in self.bs.BGG_STATS_LISTS:
            if stat in mod_detail:
                mod_detail["ranking"] = ""
                for v in mod_detail[stat]:
                    mod_detail["ranking"] += f"| {v['friendlyname']} | {v['value']} |\n"
                # Remove trailing '\n' to make .md more readable, otherwise need to
                # not have a linefeed after inserting the {ranking} tag in table.
                mod_detail["ranking"] = mod_detail["ranking"][0:-1]

        mod_detail["dl_image_url"] = quote(f"{self.dl_image_uri_prefix}/dl_image")

        self.bgg_detail = mod_detail

        while True:
            try:
                bgg_md = bgg_detail_md.format(**mod_detail)
            except KeyError as missing:
                mod_detail[missing.args[0]] = ""
            else:
                break
        return bgg_md

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked):
        if "//localhost/" in event.href:
            link = event.href.replace("//localhost/", "file:///")
            open_url(link)
        elif self.ad_uri_prefix in event.href:
            filename = unquote(urlparse(event.href[len(self.ad_uri_prefix) :]).path)
            self.post_message(self.AssetsSelected(filename, self.mod_detail["name"]))
        elif self.dl_image_uri_prefix in event.href:
            self.action_set_tts_thumb()
        else:
            open_url(event.href)

    def action_refresh_mod_details(self):
        asset_list = AssetList()
        asset_list.get_mod_assets(self.filename, parse_only=True, force_refresh=True)

        self.query_one("#md_markdown_mod").update(self.get_markdown())
        if self.mod_detail["bgg_id"] is not None:
            self.query_one("#md_markdown_bgg").update(
                self.get_markdown_bgg(force_update=True)
            )
        if self.in_workshop:
            self.query_one("#md_markdown_steam").update(
                self.get_markdown_steam(force_update=True)
            )

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
                if self.mod_detail["bgg_id"] is None:
                    self.insert_bgg_tab()
                offset_start = options[index].rfind("[") + 1
                offset_end = options[index].rfind("]")
                self.mod_detail["bgg_id"] = options[index][offset_start:offset_end]
                md = self.query_one("#md_markdown_bgg")
                self.mod_list.set_bgg_id(self.filename, self.mod_detail["bgg_id"])
                md.update(self.get_markdown_bgg())

            self.app.push_screen(SelectOptionDialog(options), set_id)
        else:
            self.action_bgg_lookup_input(
                msg="No matches found. Please update search string:"
            )

    def action_set_tts_thumb(self):
        if self.mod_detail["bgg_id"] is None:
            self.app.push_screen(
                InfoDialog(
                    (
                        "Unable to update thumbnail.\n"
                        "There is no BGG game associated with this MOD."
                    )
                )
            )
        else:
            response = requests.get(self.bgg_detail["image"])
            img = Image.open(BytesIO(response.content))
            save_path = self.get_mod_image_path()
            img.save(save_path)
            self.action_refresh_mod_details()
            self.app.push_screen(InfoDialog("Updated TTS Thumbnail"))

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        scroll_id = event.tab.id.replace("pane", "scroll")
        pane = self.query_one("#" + scroll_id)
        pane.focus()

    def on_key(self, event: Key):
        if event.key == "tab" or event.key == "shift+tab":
            tabbed_content = self.query_one(TabbedContent)
            i = self.tab_names.index(tabbed_content.active)
            if event.key == "tab":
                i = i + 1
                if i >= len(self.tab_names):
                    i = 0
            else:
                i = i - 1
                if i < 0:
                    i = len(self.tab_names) - 1

            id = self.tab_names[i]
            tabbed_content.active = id

            pane = next(self.query("#" + id).results(TabPane))
            new_event = TabbedContent.TabActivated(tabbed_content, pane)
            self.post_message(new_event)
            event.stop()
        if event.key == "escape":
            status_center = self.query_one("#worker_center")
            if status_center.has_class("unhide"):
                status_center.remove_class("unhide")
                event.stop()

    def update_asset(
        self,
        asset,
    ) -> None:
        pane = next(self.query("#md_pane_assets").results(TabPane))
        al = pane.children[0]
        al.update_asset(asset)
