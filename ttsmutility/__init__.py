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
                asset_url_recode  VARCHAR(255)    NOT NULL UNIQUE,
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
            
            # When we insert a mod, add a new entry for the mod stats (if one doesn't already exist)
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

            # These are too sloooooow when there are a lot of mods/assets.  Need a new plan.
            if False:
                # When we insert a MOD's asset, increment the number of assets associated with the associated mod
                cursor.execute("""
                CREATE TRIGGER update_total_assets
                    AFTER INSERT ON tts_mod_assets
                    BEGIN
                        UPDATE tts_stats
                        SET total_assets = total_assets + 1
                        WHERE mod_id_fk=NEW.mod_id_fk;
                    END;
                """)

                # When we insert a MOD's asset, increment the number of missing assets associated with the associated mod
                # unless that asset has a modification time (in which case it has been downloaded)
                cursor.execute("""
                    CREATE TRIGGER increment_missing_assets_trigger 
                    AFTER INSERT ON tts_mod_assets
                    FOR EACH ROW
                    BEGIN
                        UPDATE tts_stats
                        SET missing_assets = missing_assets + 1
                        WHERE tts_stats.mod_id_fk IN (
                            SELECT mod_id_fk
                            FROM tts_mod_assets
                            WHERE tts_mod_assets.mod_id_fk = NEW.mod_id_fk
                        )
                        AND EXISTS (
                            SELECT 1
                            FROM tts_assets
                            WHERE tts_assets.id = NEW.asset_id_fk
                            AND tts_assets.asset_mtime = 0
                        );
                    END;
                """)
        
                # When an assets modification time is changed from 0, decrement the missing asset count for all mods containing that
                # asset.

                cursor.execute("""
                    CREATE TRIGGER decrement_missing_assets_trigger 
                    AFTER UPDATE ON tts_assets
                    FOR EACH ROW
                    WHEN OLD.asset_mtime = 0 AND NEW.asset_mtime != 0
                    BEGIN
                        UPDATE tts_stats
                        SET missing_assets = missing_assets - 1
                        WHERE mod_id_fk IN (
                            SELECT mod_id_fk
                            FROM tts_mod_assets
                            WHERE asset_id_fk = NEW.id
                        );
                    END;
                """)

        conn.commit()