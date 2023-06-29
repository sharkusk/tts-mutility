import sqlite3
from contextlib import closing
from pathlib import Path

DB_SCHEMA_VERSION = 0

def create_new_db(db_path: Path) -> int:
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                """
            CREATE TABLE tts_assets(
                id                  INTEGER PRIMARY KEY,
                asset_url           VARCHAR(255)    UNIQUE,
                asset_path          VARCHAR(32)     COLLATE NOCASE      DEFAULT "",
                asset_filename      VARCHAR(255)    UNIQUE COLLATE NOCASE,
                asset_ext           VARCHAR(16)     COLLATE NOCASE      DEFAULT "",
                asset_sha1          CHAR(40)                            DEFAULT "",
                asset_steam_sha1    CHAR(40)                            DEFAULT "",
                asset_mtime         TIMESTAMP                           DEFAULT 0,
                asset_sha1_mtime    TIMESTAMP                           DEFAULT 0,
                asset_size          INTEGER                             DEFAULT 0,
                asset_dl_status     VARCHAR(255)                        DEFAULT "",
                asset_content_name  VARCHAR(255)                        DEFAULT "",
                asset_new           INT2
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_mods (
                id                  INTEGER PRIMARY KEY,
                mod_filename        VARCHAR(128)    NOT NULL UNIQUE,
                mod_name            VARCHAR(128),
                mod_epoch           TIMESTAMP,
                mod_date            VARCHAR(64),
                mod_version         VARCHAR(32),
                mod_game_mode       VARCHAR(128),
                mod_game_type       VARCHAR(64),
                mod_game_complexity VARCHAR(32),
                mod_min_players     INT,
                mod_max_players     INT,
                mod_min_play_time   INT,
                mod_max_play_time   INT,
                mod_mtime           TIMESTAMP                   DEFAULT 0,
                mod_fetch_time      TIMESTAMP                   DEFAULT 0,
                mod_backup_time     TIMESTAMP                   DEFAULT 0,
                mod_size            INT             NOT NULL    DEFAULT -1,
                mod_total_assets    INT             NOT NULL    DEFAULT -1,
                mod_missing_assets  INT             NOT NULL    DEFAULT -1
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_mod_assets (
                id              INTEGER PRIMARY KEY,
                asset_id_fk     INT             NOT NULL REFERENCES tts_assets (id),
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (id),
                mod_asset_trail VARCHAR(128)    NOT NULL,
                UNIQUE(asset_id_fk, mod_id_fk)
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_tags (
                id              INTEGER PRIMARY KEY,
                tag_name        VARCHAR(64)     NOT NULL UNIQUE
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_mod_tags (
                id              INTEGER PRIMARY KEY,
                tag_id_fk       INT             NOT NULL REFERENCES tts_tags (id),
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (id),
                UNIQUE(tag_id_fk, mod_id_fk)
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_app (
                id                      INTEGER PRIMARY KEY,
                asset_last_scan_time    TIMESTAMP,
                mod_last_scan_time      TIMESTAMP,
                db_schema_version       INT
                )
            """
            )

            cursor.execute(
                """
                INSERT INTO tts_app
                    (asset_last_scan_time, mod_last_scan_time, db_schema_version)
                VALUES
                    (0, 0, ?)
            """, (DB_SCHEMA_VERSION,)
            )

        conn.commit()
        return DB_SCHEMA_VERSION
