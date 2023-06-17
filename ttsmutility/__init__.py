import os
import sqlite3
from contextlib import closing


DB_NAME = "ttsmutility.sqlite"


if not os.path.exists(DB_NAME):
    _init_table = True
else:
    _init_table = False
with closing(sqlite3.connect(DB_NAME)) as conn:
    with closing(conn.cursor()) as cursor:

        if _init_table:
            cursor.execute("""CREATE TABLE tts_assets (
                filename VARCHAR(128) PRIMARY KEY,
                sha1 CHAR(40),
                path VARCHAR(256)
                )""")

            cursor.execute("""CREATE TABLE tts_mods (
                filename VARCHAR(128) PRIMARY KEY,
                name VARCHAR(128),
                path VARCHAR(256),
                mod_time TIMESTAMP,
                fetch_time TIMESTAMP,
                backup_time TIMESTAMP,
                total_assets UNSIGNED SMALLINT,
                missing_assets UNSIGNED SMALLINT
                )""")

            cursor.execute("""CREATE TABLE tts_mod_assets (
                mod_filename VARCHAR(128),
                asset_filename VARCHAR(128)
                )""")
        
            conn.commit()