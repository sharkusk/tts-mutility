import os
import sqlite3
from contextlib import closing


DB_NAME = "ttsmutility.sqlite"

if os.path.exists(DB_NAME):
    _init_table = False
else:
    _init_table = True

if _init_table:
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("""CREATE TABLE tts_assets (
                url VARCHAR(255) PRIMARY KEY,
                asset_filename VARCHAR(128),
                sha1 CHAR(40),
                mtime TIMESTAMP
                )""")

            cursor.execute("""CREATE TABLE tts_mods (
                mod_filename VARCHAR(128) PRIMARY KEY,
                mod_name VARCHAR(128),
                mod_path VARCHAR(256),
                mtime TIMESTAMP,
                fetch_time TIMESTAMP,
                backup_time TIMESTAMP
                )""")

            cursor.execute("""CREATE TABLE tts_mod_assets (
                url VARCHAR(256),
                mod_filename VARCHAR(128),
                trail VARCHAR(128)
                )""")
    
        conn.commit()