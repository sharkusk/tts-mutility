import os
import sqlite3
from contextlib import closing


DB_NAME = "ttsmutility.sqlite"

URL_INDEX = 0
MOD_FILENAME_INDEX=0
ASSET_FILENAME_INDEX=1
MOD_NAME_INDEX=1
SHA1_INDEX=2
PATH_INDEX=2
MOD_TIME_INDEX=3
TRAIL_INDEX=3
FETCH_TIME_INDEX=4
BACKUP_TIME_INDEX=5
TOTAL_ASSETS_INDEX=6
MISSING_ASSETS_INDEX=7


if not os.path.exists(DB_NAME):
    _init_table = True
else:
    _init_table = False

    if _init_table:
        with closing(sqlite3.connect(DB_NAME)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("""CREATE TABLE tts_assets (
                    url VARCHAR(255) PRIMARY KEY,
                    asset_filename VARCHAR(128),
                    sha1 CHAR(40),
                    trail VARCHAR(128)
                    )""")

                cursor.execute("""CREATE TABLE tts_mods (
                    mod_filename VARCHAR(128) PRIMARY KEY,
                    mod_name VARCHAR(128),
                    mod_path VARCHAR(256),
                    mod_time TIMESTAMP,
                    fetch_time TIMESTAMP,
                    backup_time TIMESTAMP,
                    total_assets UNSIGNED SMALLINT,
                    missing_assets UNSIGNED SMALLINT
                    )""")

                cursor.execute("""CREATE TABLE tts_mod_assets (
                    url VARCHAR(256),
                    mod_filename VARCHAR(128)
                    )""")
        
            conn.commit()