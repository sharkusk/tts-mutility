import os
import sqlite3
from contextlib import closing


DB_NAME = os.path.abspath("ttsmutility.sqlite")
FIRST_PASS = False

if os.path.exists(DB_NAME):
    _init_table = False
else:
    _init_table = True

if _init_table:
    FIRST_PASS = True
    with closing(sqlite3.connect(DB_NAME)) as conn:
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
                mod_name            VARCHAR(128)    NOT NULL,
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
            CREATE TABLE tts_app (
                id                  INTEGER PRIMARY KEY,
                app_last_scan_time  TIMESTAMP
                )
            """
            )

            cursor.execute(
                """
                INSERT INTO tts_app
                    (app_last_scan_time)
                VALUES
                    (0)
            """
            )

        conn.commit()
