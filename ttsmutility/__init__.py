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
            cursor.execute("""
            CREATE TABLE tts_assets(
                asset_url       VARCHAR(255)    NOT NULL UNIQUE,
                asset_filepath  VARCHAR(255)    NOT NULL UNIQUE,
                asset_sha1      CHAR(40),
                asset_mtime     TIMESTAMP
                )
            """)

            cursor.execute("""
            CREATE TABLE tts_mods (
                mod_filename    VARCHAR(128)    NOT NULL UNIQUE,
                mod_name        VARCHAR(128)    NOT NULL,
                mod_mtime       TIMESTAMP,
                mod_fetch_time  TIMESTAMP,
                mod_backup_time TIMESTAMP
                )
            """)

            cursor.execute("""
            CREATE TABLE tts_mod_assets (
                asset_id_fk     INT             NOT NULL REFERENCES tts_assets (rowid),
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (rowid),
                mod_asset_trail VARCHAR(128)    NOT NULL
                )
            """)
            
            cursor.execute("""
            CREATE TABLE tts_stats (
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (rowid),
                total_assets    UNISIGNED INT,
                missing_assets  UNSIGNED INT
                )
            """)
            

    
        conn.commit()