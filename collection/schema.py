"""
Pokemon HOME collection database schema.
SQLite-backed, lives at collection/pokemon_home.db (gitignored).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "pokemon_home.db"
IMAGES_DIR = Path(__file__).parent / "images"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    IMAGES_DIR.mkdir(exist_ok=True)
    (IMAGES_DIR / "boxes").mkdir(exist_ok=True)
    (IMAGES_DIR / "detail").mkdir(exist_ok=True)
    (IMAGES_DIR / "sprites").mkdir(exist_ok=True)

    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS boxes (
            box_number   INTEGER PRIMARY KEY,
            name         TEXT,
            screenshot_path TEXT,
            captured_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pokemon (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            box_number   INTEGER NOT NULL,
            box_slot     INTEGER NOT NULL,  -- 0-based, row-major, 6 cols x 5 rows = 30 per box

            -- Species
            species_name TEXT,
            dex_number   INTEGER,
            form_name    TEXT,

            -- Individual
            nickname     TEXT,
            level        INTEGER,
            nature       TEXT,
            ability      TEXT,
            is_shiny     BOOLEAN DEFAULT 0,
            gender       TEXT,  -- 'male' | 'female' | 'unknown'
            held_item    TEXT,
            mark         TEXT,

            -- IVs
            iv_hp        INTEGER,
            iv_atk       INTEGER,
            iv_def       INTEGER,
            iv_spatk     INTEGER,
            iv_spdef     INTEGER,
            iv_speed     INTEGER,

            -- EVs
            ev_hp        INTEGER,
            ev_atk       INTEGER,
            ev_def       INTEGER,
            ev_spatk     INTEGER,
            ev_spdef     INTEGER,
            ev_speed     INTEGER,

            -- Moves
            move1        TEXT,
            move2        TEXT,
            move3        TEXT,
            move4        TEXT,

            -- Origin
            original_trainer TEXT,
            trainer_id   TEXT,
            game_of_origin TEXT,
            ball_type    TEXT,

            -- Origin (caught info, from second detail screen)
            date_caught  TEXT,
            met_at_level INTEGER,
            met_at_location TEXT,

            -- Files (relative to collection/)
            box_screenshot_path     TEXT,
            detail_screenshot_path  TEXT,
            detail_screenshot2_path TEXT,
            sprite_path             TEXT,

            -- Meta
            captured_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            parsed_at    TIMESTAMP,
            raw_json     TEXT,

            UNIQUE(box_number, box_slot)
        );

        -- Tracks automation progress so we can resume
        CREATE TABLE IF NOT EXISTS capture_state (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Migrate existing DBs: add columns if they don't exist
    existing = {row[1] for row in conn.execute("PRAGMA table_info(pokemon)")}
    migrations = [
        ("date_caught",           "ALTER TABLE pokemon ADD COLUMN date_caught TEXT"),
        ("met_at_level",          "ALTER TABLE pokemon ADD COLUMN met_at_level INTEGER"),
        ("met_at_location",       "ALTER TABLE pokemon ADD COLUMN met_at_location TEXT"),
        ("detail_screenshot2_path", "ALTER TABLE pokemon ADD COLUMN detail_screenshot2_path TEXT"),
    ]
    for col, sql in migrations:
        if col not in existing:
            conn.execute(sql)
    conn.commit()
    conn.close()
    print(f"DB initialized at {DB_PATH}")


def upsert_pokemon(data: dict) -> int:
    conn = get_db()
    cols = [k for k in data if k != "id"]
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("box_number", "box_slot"))
    sql = f"""
        INSERT INTO pokemon ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(box_number, box_slot) DO UPDATE SET {updates}
    """
    cur = conn.execute(sql, data)
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_state(key: str, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM capture_state WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_state(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO capture_state(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
        (key, value)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
