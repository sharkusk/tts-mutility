import os.path
import sqlite3
import time
from datetime import datetime
from glob import glob
from pathlib import Path

import aiosqlite

from ..data.config import load_config


def mod_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key.replace("mod_", ""): value for key, value in zip(fields, row)}


class ModList:
    def __init__(self, max_mods=-1) -> None:
        config = load_config()
        self.db_path = Path(config.db_path)
        self.mod_dir = Path(config.tts_mods_dir)
        self.save_dir = Path(config.tts_saves_dir)
        self.recurse_save_dir = config.recurse_save_dir
        self.scan_ts_saves = config.scan_ts_saves
        self.max_mods = max_mods

    def _get_mod_path(self, filename: str) -> str:
        if "Workshop" in filename:
            path = self.mod_dir
        else:
            path = self.save_dir
        return os.path.join(path, filename)

    def get_all_mod_filenames(self):
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                """
            )
            results = cursor.fetchall()
            return list(zip(*results))[0]

    def get_mods_needing_asset_refresh(self):
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                WHERE (mod_total_assets=-1 OR mod_missing_assets=-1 OR mod_size=-1)""",
            )
            result = cursor.fetchall()
            # Results are returned as a list of tuples, unzip to a list of mod_filenames
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
                SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1, mod_max_asset_mtime=UNIXEPOCH()
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

    async def get_mods_needing_asset_refresh_a(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
                WHERE (mod_total_assets=-1 OR mod_missing_assets=-1 OR mod_size=-1)""",
            ) as cursor:
                result = await cursor.fetchall()
            # Results are returned as a list of tuples, unzip to a list of mod_filenames
            if len(result) > 0:
                part1 = list(list(zip(*result))[0])
            else:
                part1 = []

            async with db.execute(
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
            ) as cursor:
                result = await cursor.fetchall()
            if len(result) > 0:
                part2 = list(list(zip(*result))[0])
            else:
                part2 = []

            await db.executemany(
                """
                UPDATE tts_mods
                SET mod_total_assets=-1, mod_missing_assets=-1, mod_size=-1, mod_max_asset_mtime=UNIXEPOCH()
                WHERE mod_filename=?
                """,
                result,
            )

            combined = list(set(part1 + part2))

            await db.commit()

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

    async def update_mod_counts_a(self, mod_filename):
        counts = {}
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT mod_total_assets, mod_missing_assets, mod_size
                FROM tts_mods
                WHERE mod_filename=?
                """,
                (mod_filename,),
            ) as cursor:
                result = await cursor.fetchone()
                if result is None:
                    return
                counts["total"] = result[0]
                counts["missing"] = result[1]
                counts["size"] = result[2]

        if counts["total"] == -1:
            counts["total"] = await self._count_total_assets_a(mod_filename)
        if counts["missing"] == -1:
            counts["missing"] = await self._count_missing_assets_a(mod_filename)
        if counts["size"] == -1:
            counts["size"] = await self._calc_asset_size_a(mod_filename)

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

    async def _calc_asset_size_a(self, filename: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
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
            ) as cursor:
                result = await cursor.fetchone()
            if result[0] is None:
                mod_size = 0
            else:
                mod_size = result[0]
            await db.execute(
                """
                UPDATE tts_mods
                SET mod_size=?
                WHERE mod_filename=?
                """,
                (mod_size, filename),
            )
            await db.commit()
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

    async def _count_total_assets_a(self, filename: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
            SELECT COUNT(asset_id_fk)
            FROM tts_mod_assets
            WHERE mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
            """,
                (filename,),
            ) as cursor:
                result = await cursor.fetchone()
            await db.execute(
                """
                UPDATE tts_mods
                SET mod_total_assets=?
                WHERE mod_filename=?
                """,
                (result[0], filename),
            )
            await db.commit()
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
                    AND
                    mod_asset_ignore_missing=0
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

    async def _count_missing_assets_a(self, filename: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            query = """
            SELECT COUNT(asset_id_fk)
            FROM tts_mod_assets
                WHERE (
                    mod_id_fk=(SELECT id FROM tts_mods WHERE mod_filename=?)
                    AND
                    asset_id_fk IN (SELECT id FROM tts_assets WHERE asset_mtime=?)
                    AND
                    mod_asset_ignore_missing=0
                )
            """
            async with db.execute(query, (filename, 0)) as cursor:
                result = await cursor.fetchone()
            await db.execute(
                """
                UPDATE tts_mods
                SET mod_missing_assets=?
                WHERE mod_filename=?
                """,
                (result[0], filename),
            )
            await db.commit()
        return result[0]

    def get_mod_details(self, filename: str) -> dict:
        with sqlite3.connect(self.db_path) as db:
            # Now that all mods are in the db, extract the data...
            cursor = db.execute(
                """
                SELECT
                    mod_filename, mod_name, mod_mtime, mod_size,
                    mod_total_assets, mod_missing_assets, mod_epoch,
                    mod_version, mod_game_mode, mod_game_type,
                    mod_game_complexity, mod_min_players, mod_max_players,
                    mod_min_play_time, mod_max_play_time, mod_bgg_id,
                    mod_max_asset_mtime as newest_asset
                FROM
                    tts_mods
                WHERE
                    mod_filename=?
                """,
                (filename,),
            )
            cursor.row_factory = mod_factory
            mod = cursor.fetchone()
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

    def set_mod_details(self, mod_infos: dict) -> None:
        db_params = []
        mod_tags = []
        tags = set()

        for mod_filename in mod_infos:
            details = mod_infos[mod_filename]

            # If mod wasn't updated it will be None
            if details is None:
                return

            try:
                min_players = int(details["PlayerCounts"][0])
                max_players = int(details["PlayerCounts"][1])
            except (KeyError, IndexError):
                min_players = 0
                max_players = 0

            try:
                min_play_time = int(details["PlayingTime"][0])
                max_play_time = int(details["PlayingTime"][1])
            except (KeyError, IndexError):
                min_play_time = 0
                max_play_time = 0

            if details["EpochTime"] == "":
                if details["Date"] != "":
                    formats = [
                        "%m/%d/%Y %I:%M:%S %p",  # 9/11/2021 4:55:18 AM
                        "%m/%d/%Y %H:%M:%S",  # 02/01/2019 14:40:08
                        "%d/%m/%Y %I:%M:%S %p",  # 28/04/2023 11:11:14 PM
                        "%d/%m/%Y %H:%M:%S",  # 28/04/2023 14:11:14
                    ]
                    for format in formats:
                        try:
                            utc_time = datetime.strptime(details["Date"], format)
                        except ValueError:
                            continue
                        else:
                            epoch_time = (
                                utc_time - datetime(1970, 1, 1)
                            ).total_seconds()
                            details["EpochTime"] = epoch_time
                            break
                    else:
                        details["EpochTime"] = 0
                else:
                    details["EpochTime"] = 0

            for tag in details["Tags"]:
                mod_tags.append((mod_filename, tag))
                tags.add((tag,))

            db_params.append(
                (
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
                    details["mtime"],
                    mod_filename,
                )
            )

        with sqlite3.connect(self.db_path) as db:
            db.executemany(
                """
                UPDATE tts_mods
                SET
                    (mod_name, mod_epoch, mod_date, mod_version,
                    mod_game_mode, mod_game_type, mod_game_complexity,
                    mod_min_players, mod_max_players, mod_min_play_time,
                    mod_max_play_time, mod_mtime) =
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                WHERE
                    mod_filename=?
                """,
                db_params,
            )

            db.executemany(
                """
                INSERT OR IGNORE INTO tts_tags
                    (tag_name)
                VALUES
                    (?)
                """,
                tags,
            )

            db.executemany(
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
            db.commit()

    def get_mods(
        self, parse_only=False, force_refresh=False, include_deleted=False
    ) -> dict:
        mods_on_disk = []  # Mods that exist in the filesystem
        mod_list = []
        mods = {}
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

            cursor = db.execute(
                """
                SELECT mod_filename
                FROM tts_mods
            """
            )
            results = cursor.fetchall()
            if len(results) > 0:
                mod_filenames = list(zip(*results))[0]
            else:
                mod_filenames = []

            for root_dir, base_dir, prefix in [
                (self.mod_dir, "Workshop", ""),
                (self.save_dir, "Saves", "**/" if self.recurse_save_dir else ""),
            ]:
                # We want the mod filenames to be formatted:
                # Saves/xxxx.json or Workshop/xxxx.json
                files_to_skip = [
                    "WorkshopFileInfos",
                    "SaveFileInfos",
                    "TS_AutoSave",
                ]

                if not self.scan_ts_saves:
                    files_to_skip.append("TS_Save")

                def skip_mod(filename):
                    result = False
                    for ignore in files_to_skip:
                        if ignore in filename:
                            result = True
                            break
                    return result

                for i, f in enumerate(
                    glob(
                        os.path.join(base_dir, f"{prefix}*.json"),
                        root_dir=root_dir,
                        recursive=True,
                    )
                ):
                    if skip_mod(f):
                        continue

                    if self.max_mods != -1 and i >= self.max_mods:
                        break

                    mods_on_disk.append(f)

                    if (
                        os.path.getmtime(self._get_mod_path(f)) > prev_scan_time
                        or force_refresh
                        or f not in mod_filenames
                    ):
                        mod_list.append((f,))

            if len(mod_list) > 0:
                # Mod details will be added as part of mod file json scan
                db.executemany(
                    """
                    INSERT INTO tts_mods
                        (mod_filename, mod_total_assets, mod_missing_assets, mod_size)
                    VALUES
                        (?, -1, -1, -1)
                    ON CONFLICT (mod_filename)
                    DO UPDATE SET
                        mod_total_assets=excluded.mod_total_assets,
                        mod_missing_assets=excluded.mod_missing_assets,
                        mod_size=excluded.mod_size
                    """,
                    mod_list,
                )

                db.execute(
                    """
                    UPDATE tts_app
                    SET mod_last_scan_time=?
                    WHERE id=1
                """,
                    (scan_time,),
                )

            if parse_only is False:
                # Now that all mods are in the db, extract the data...
                cursor = db.execute(
                    """
                    SELECT
                        mod_filename, mod_name, mod_mtime, mod_size,
                        mod_total_assets, mod_missing_assets, mod_epoch,
                        mod_version, mod_game_mode, mod_game_type,
                        mod_game_complexity, mod_min_players, mod_max_players,
                        mod_min_play_time, mod_max_play_time, mod_bgg_id,
                        mod_max_asset_mtime as newest_asset
                    FROM
                        tts_mods
                    """,
                )
                cursor.row_factory = mod_factory
                results = cursor.fetchall()
                for mod in results:
                    filename = mod["filename"]
                    if filename not in mods_on_disk and not include_deleted:
                        continue
                    mods[filename] = mod
                    mods[filename]["deleted"] = filename not in mods_on_disk
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
                    tag_results = cursor.fetchall()
                    if len(tag_results) > 0:
                        mods[filename]["tags"] = list(zip(*tag_results))[0]
                    else:
                        mods[filename]["tags"] = ()
            db.commit()
        return mods

    async def set_bgg_id(self, mod_filename: str, bgg_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE
                    tts_mods
                SET
                    mod_bgg_id=?
                WHERE
                    mod_filename=?
                """,
                (bgg_id, mod_filename),
            )
            await db.commit()
