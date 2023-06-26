import os.path
from glob import glob
import sqlite3
import re
import time
from datetime import datetime

from ..data.config import load_config


class ModList:
    def __init__(self, mod_dir: str, save_dir: str) -> None:
        self.save_dir = save_dir
        self.mod_dir = mod_dir
        config = load_config()
        self.db_path = config.db_path

    def _get_mod_path(self, filename: str) -> str:
        if "Workshop" in filename:
            path = self.mod_dir
        else:
            path = self.save_dir
        return os.path.join(path, filename)

    def _get_mod_details(self, filename: str) -> str:
        fields = [
            "SaveName",
            "EpochTime",
            "Date",
            "VersionNumber",
            "GameMode",
            "GameType",
            "GameComplexity",
        ]
        arrays = ["PlayingTime", "PlayerCounts", "Tags"]
        details = {}
        for field in fields:
            details[field] = ""
        for array in arrays:
            details[array] = []
        cur_array = ""
        # TODO: Fix this so only two values are returned
        end_groups = [
            r"([\d\.]+),",  # "EpochTime": 1687672340,
            r"(?:\[)",  # "PlayingTime": [
            r'(?:"(.*)",)',  # "GameType": "Game",
        ]
        expr = r'"(.*)": ' + r"(?:" + "|".join(end_groups) + ")"
        pattern = re.compile(expr)
        filepath = self._get_mod_path(filename)
        with open(filepath, "r", encoding="utf-8") as infile:
            for line in infile:
                if "{" in line:
                    # Skip first line
                    continue
                if cur_array != "":
                    if "]" in line:
                        cur_array = ""
                    else:
                        value = line.strip(' \n,"')
                        details[cur_array].append(value)
                else:
                    field, value1, value2 = pattern.findall(line)[0]
                    if field in fields:
                        if value1 == "":
                            details[field] = value2
                        else:
                            details[field] = value1
                    elif field in arrays:
                        # Empty arrays are contained on same line
                        if "]" not in line:
                            cur_array = field
                    else:
                        # We don't care about the rest of the file..
                        break
        return details

    def get_mods_needing_asset_refresh(self):
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                WHERE (mod_total_assets=-1 OR mod_missing_assets=-1 OR mod_size=-1)""",
            )
            result = cursor.fetchall()
            # Results are returned as a list of tuples, unzip to a list of mod_filename's
            if len(result) > 0:
                part1 = list(list(zip(*result))[0])
            else:
                part1 = []

            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                WHERE id IN (
                    SELECT mod_id_fk
                    FROM tts_mod_assets
                    WHERE asset_id_fk IN (
                        SELECT id
                        FROM tts_assets
                        WHERE asset_new=1
                    )
                )
                """,
            )
            result = cursor.fetchall()
            if len(result) > 0:
                part2 = list(list(zip(*result))[0])
            else:
                part2 = []

            db.executemany(
                """
                UPDATE tts_mods
                SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1
                WHERE mod_filename=?
                """,
                result,
            )

            combined = list(set(part1 + part2))

            db.execute(
                """
                UPDATE tts_assets
                SET asset_new=0
                """,
            )

            db.commit()

        return sorted(combined)

    def update_mod_counts(self, mod_filename):
        counts = {}
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_total_assets, mod_missing_assets, mod_size
                FROM tts_mods
                WHERE mod_filename=?
                """,
                (mod_filename,),
            )
            result = cursor.fetchone()
            if result is None:
                return
            counts["total"] = result[0]
            counts["missing"] = result[1]
            counts["size"] = result[2]

        if counts["total"] == -1:
            counts["total"] = self._count_total_assets(mod_filename)
        if counts["missing"] == -1:
            counts["missing"] = self._count_missing_assets(mod_filename)
        if counts["size"] == -1:
            counts["size"] = self._calc_asset_size(mod_filename)

        return counts

    def _calc_asset_size(self, filename: str) -> int:
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
            SELECT SUM(asset_size)
            FROM tts_assets
            WHERE id IN (
                SELECT asset_id_fk
                FROM tts_mod_assets
                WHERE mod_id_fk IN (
                    SELECT id FROM tts_mods
                    WHERE mod_filename=?
                )
            )
            """,
                (filename,),
            )
            result = cursor.fetchone()
            if result[0] is None:
                mod_size = 0
            else:
                mod_size = result[0]
            db.execute(
                """
                UPDATE tts_mods
                SET mod_size=?
                WHERE mod_filename=?
                """,
                (mod_size, filename),
            )
            db.commit()
        return mod_size

    def _count_total_assets(self, filename: str) -> int:
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
            SELECT COUNT(asset_id_fk)
            FROM tts_mod_assets
            WHERE mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
            """,
                (filename,),
            )
            result = cursor.fetchone()
            db.execute(
                """
                UPDATE tts_mods
                SET mod_total_assets=?
                WHERE mod_filename=?
                """,
                (result[0], filename),
            )
            db.commit()
        return result[0]

    def _count_missing_assets(self, filename: str) -> int:
        with sqlite3.connect(self.db_path) as db:
            query = """
            SELECT COUNT(asset_id_fk)
            FROM tts_mod_assets
                WHERE (
                    mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
                    AND 
                    asset_id_fk IN (SELECT id FROM tts_assets WHERE asset_mtime=?)
                )
            """
            cursor = db.execute(query, (filename, 0))
            result = cursor.fetchone()
            db.execute(
                """
                UPDATE tts_mods
                SET mod_missing_assets=?
                WHERE mod_filename=?
                """,
                (result[0], filename),
            )
            db.commit()
        return result[0]

    def get_mod_details(self, filename: str) -> dict:
        with sqlite3.connect(self.db_path) as db:
            # Now that all mods are in the db, extract the data...
            cursor = db.execute(
                """
                SELECT
                    mod_filename, mod_name, mod_mtime, mod_size, mod_total_assets, mod_missing_assets,
                    mod_epoch, mod_version, mod_game_mode, mod_game_type, mod_game_complexity, mod_min_players,
                    mod_max_players, mod_min_play_time, mod_max_play_time
                FROM
                    tts_mods
                WHERE
                    mod_filename=?
                """,
                (filename,),
            )
            result = cursor.fetchone()
            mod = {
                "filename": result[0],
                "name": result[1],
                "mtime": result[2],
                "size": result[3],
                "total_assets": result[4],
                "missing_assets": result[5],
                "epoch": result[6],
                "version": result[7],
                "game_mode": result[8],
                "game_type": result[9],
                "game_complexity": result[10],
                "min_players": result[11],
                "max_players": result[12],
                "min_play_time": result[13],
                "max_play_time": result[14],
            }
            cursor = db.execute(
                """
                SELECT tag_name
                FROM tts_tags
                    INNER JOIN tts_mod_tags
                        ON tts_mod_tags.tag_id_fk=tts_tags.id
                    INNER JOIN tts_mods
                        ON tts_mod_tags.mod_id_fk=tts_mods.id
                WHERE mod_filename=?
                """,
                (filename,),
            )
            results = cursor.fetchall()
            if len(results) > 0:
                mod["tags"] = list(zip(*results))[0]
            else:
                mod["tags"] = ()

        return mod

    def get_mods(self) -> dict:
        mod_list = []
        mods = {}
        tags = set()
        mod_tags = []
        scan_time = time.time()

        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_last_scan_time
                FROM tts_app
                WHERE id=1
            """
            )
            # This should not fail as we init to zero as part of DB init
            prev_scan_time = cursor.fetchone()[0]

            for root_dir, base_dir in [
                (self.mod_dir, "Workshop"),
                (self.save_dir, "Saves"),
            ]:
                # We want the mod filenames to be formatted: Saves/xxxx.json or Workshop/xxxx.json

                max_mods = -1  # Debug with fewer mods...
                for i, f in enumerate(
                    glob(os.path.join(base_dir, "*.json"), root_dir=root_dir)
                ):
                    if (
                        "WorkshopFileInfos" in f
                        or "SaveFileInfos" in f
                        or "TS_AutoSave" in f
                        or "TS_Save" in f
                    ):
                        continue

                    if max_mods != -1 and i >= max_mods:
                        break

                    if os.path.getmtime(self._get_mod_path(f)) > prev_scan_time:
                        details = self._get_mod_details(f)
                        try:
                            min_players = int(details["PlayerCounts"][0])
                            max_players = int(details["PlayerCounts"][1])
                        except:
                            min_players = 0
                            max_players = 0

                        try:
                            min_play_time = int(details["PlayingTime"][0])
                            max_play_time = int(details["PlayingTime"][1])
                        except:
                            min_play_time = 0
                            max_play_time = 0

                        if details["EpochTime"] == "":
                            try:
                                # 9/11/2021 4:55:18 AM
                                utc_time = datetime.strptime(
                                    details["Date"], "%m/%d/%Y %I:%M:%S %p"
                                )
                                epoch_time = (
                                    utc_time - datetime(1970, 1, 1)
                                ).total_seconds()
                                details["EpochTime"] = epoch_time
                            except:
                                details["EpochTime"] = 0

                        mod_list.append(
                            (
                                f,
                                details["SaveName"],
                                details["EpochTime"],
                                details["Date"],
                                details["VersionNumber"],
                                details["GameMode"],
                                details["GameType"],
                                details["GameComplexity"],
                                min_players,
                                max_players,
                                min_play_time,
                                max_play_time,
                            )
                        )

                        for tag in details["Tags"]:
                            mod_tags.append((f, tag))
                            tags.add((tag,))

            if len(mod_list) > 0:
                cursor = db.executemany(
                    """
                    INSERT INTO tts_mods
                        (mod_filename, mod_name, mod_epoch, mod_date, mod_version, mod_game_mode,
                        mod_game_type, mod_game_complexity, mod_min_players, mod_max_players,
                        mod_min_play_time, mod_max_play_time)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
                    ON CONFLICT (mod_filename)
                    DO UPDATE SET
                        mod_name=excluded.mod_name,
                        mod_epoch=excluded.mod_epoch,
                        mod_date=excluded.mod_date,
                        mod_version=excluded.mod_version,
                        mod_game_mode=excluded.mod_game_mode,
                        mod_game_type=excluded.mod_game_type,
                        mod_game_complexity=excluded.mod_game_complexity,
                        mod_min_players=excluded.mod_min_players,
                        mod_max_players=excluded.mod_max_players,
                        mod_min_play_time=excluded.mod_min_play_time,
                        mod_max_play_time=excluded.mod_max_play_time
                    """,
                    mod_list,
                )
                mods_added = cursor.rowcount

                cursor = db.executemany(
                    """
                    INSERT OR IGNORE INTO tts_tags
                        (tag_name)
                    VALUES
                        (?)
                    """,
                    tags,
                )
                tags_added = cursor.rowcount

                cursor = db.executemany(
                    """
                    INSERT OR IGNORE INTO tts_mod_tags
                        (mod_id_fk, tag_id_fk)
                    VALUES (
                        (SELECT tts_mods.id FROM tts_mods WHERE mod_filename=?),
                        (SELECT tts_tags.id FROM tts_tags WHERE tag_name=?)
                    )
                    """,
                    mod_tags,
                )
                mod_tags_added = cursor.rowcount

                db.execute(
                    """
                    UPDATE tts_app
                    SET mod_last_scan_time=?
                    WHERE id=1
                """,
                    (scan_time,),
                )

            # Now that all mods are in the db, extract the data...
            cursor = db.execute(
                """
                SELECT mod_filename, mod_name, mod_mtime, mod_size, mod_total_assets, mod_missing_assets
                FROM tts_mods
                """
            )
            results = cursor.fetchall()
            for result in results:
                mods[result[0]] = {
                    "filename": result[0],
                    "name": result[1],
                    "mtime": result[2],
                    "size": result[3],
                    "total_assets": result[4],
                    "missing_assets": result[5],
                }
            db.commit()
        return mods
