import os
import sqlite3
from contextlib import closing


DB_NAME = "ttsmutility.sqlite"
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
                asset_url           VARCHAR(255)  NOT NULL UNIQUE,
                asset_url_recode    VARCHAR(255)  NOT NULL UNIQUE,
                asset_filepath      VARCHAR(255)  UNIQUE COLLATE NOCASE,
                asset_sha1          CHAR(40),
                asset_steam_sha1    CHAR(40),
                asset_mtime         TIMESTAMP,
                asset_sha1_mtime    TIMESTAMP,
                asset_size          INTEGER,
                asset_dl_status     VARCHAR(255)
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_mods (
                id              INTEGER PRIMARY KEY,
                mod_filename    VARCHAR(128)    NOT NULL UNIQUE,
                mod_name        VARCHAR(128)    NOT NULL,
                mod_mtime       TIMESTAMP,
                mod_fetch_time  TIMESTAMP,
                mod_backup_time TIMESTAMP,
                mod_size        INT             NOT NULL,
                total_assets    INT             NOT NULL,
                missing_assets  INT             NOT NULL
                )
            """
            )

            cursor.execute(
                """
            CREATE TABLE tts_mod_assets (
                id              INTEGER PRIMARY KEY,
                asset_id_fk     INT             NOT NULL REFERENCES tts_assets (id),
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (id),
                mod_asset_trail VARCHAR(128)    NOT NULL
                )
            """
            )

        conn.commit()
