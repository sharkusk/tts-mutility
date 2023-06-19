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
                id              INTEGER PRIMARY KEY,
                asset_url       VARCHAR(255)    NOT NULL UNIQUE,
                asset_filepath  VARCHAR(255)    UNIQUE,
                asset_sha1      CHAR(40),
                asset_mtime     TIMESTAMP
                )
            """)

            cursor.execute("""
            CREATE TABLE tts_mods (
                id              INTEGER PRIMARY KEY,
                mod_filename    VARCHAR(128)    NOT NULL UNIQUE,
                mod_name        VARCHAR(128)    NOT NULL,
                mod_mtime       TIMESTAMP,
                mod_fetch_time  TIMESTAMP,
                mod_backup_time TIMESTAMP
                )
            """)

            cursor.execute("""
            CREATE TABLE tts_mod_assets (
                id              INTEGER PRIMARY KEY,
                asset_id_fk     INT             NOT NULL REFERENCES tts_assets (id),
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (id),
                mod_asset_trail VARCHAR(128)    NOT NULL
                )
            """)
            
            cursor.execute("""
            CREATE TABLE tts_stats (
                id              INTEGER PRIMARY KEY,
                mod_id_fk       INT             NOT NULL REFERENCES tts_mods (id),
                total_assets    UNISIGNED INT   NOT NULL,
                missing_assets  UNSIGNED INT    NOT NULL
                );
            """)
            
            cursor.execute("""
            CREATE TRIGGER insert_total_assets
                AFTER INSERT ON tts_mods
                BEGIN
                    INSERT OR IGNORE INTO tts_stats (mod_id_fk, total_assets, missing_assets)
                    SELECT NEW.id, 0, 0
                    WHERE NOT EXISTS (
                        SELECT 1 FROM tts_stats
                        WHERE mod_id_fk=NEW.id
                    );
                END;
            """)

            cursor.execute("""
            CREATE TRIGGER update_total_assets
                AFTER INSERT ON tts_mod_assets
                BEGIN
                    UPDATE tts_stats
                    SET total_assets = total_assets + 1
                    WHERE mod_id_fk=NEW.mod_id_fk;
                END;
            """)
    
        conn.commit()