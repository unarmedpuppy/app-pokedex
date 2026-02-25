#!/usr/bin/env python3
"""
Pokemon HOME metadata extraction.
Vision extraction runs via Claude Code subagents (no separate API key needed).

Workflow:
  1. python parse.py --export-queue          # write parse_queue.json
  2. (Claude Code session processes the queue via Task subagents)
  3. python parse.py --import-results FILE   # write results to DB

Direct dry-run (for debugging a single slot):
  python parse.py --inspect --box 0 --slot 0
"""

import argparse
import json
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from collection.schema import get_db, upsert_pokemon, IMAGES_DIR, DB_PATH

QUEUE_PATH = Path(__file__).parent / "parse_queue.json"

EXTRACT_PROMPT = """You are looking at a Pokemon HOME detail screen for a single Pokemon.
Extract every visible piece of information and return it as JSON.

Return ONLY valid JSON with these exact keys (use null for any field not visible):

{
  "species_name": "Pikachu",
  "dex_number": 25,
  "form_name": null,
  "nickname": null,
  "level": 50,
  "nature": "Timid",
  "ability": "Static",
  "is_shiny": false,
  "gender": "male",
  "held_item": null,
  "mark": null,
  "move1": "Thunderbolt",
  "move2": "Volt Switch",
  "move3": "Grass Knot",
  "move4": "Filler Move",
  "original_trainer": "Joshua",
  "trainer_id": "12345",
  "game_of_origin": null,
  "ball_type": "Poké Ball"
}

Notes:
- is_shiny: true if there is a shiny star indicator (★) in the top-right area
- gender: "male", "female", or "unknown"
- nickname: only if the Pokemon has a custom name different from species name
- Return ONLY the JSON object, no markdown, no explanation"""


# ── Queue export ──────────────────────────────────────────────────────────────

def export_queue(box: Optional[int] = None, slot: Optional[int] = None):
    """Write parse_queue.json — list of {box, slot, image_path} for unparsed Pokemon."""
    conn = get_db()

    if box is not None and slot is not None:
        rows = conn.execute(
            "SELECT box_number, box_slot, detail_screenshot_path FROM pokemon "
            "WHERE box_number=? AND box_slot=?",
            (box, slot)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT box_number, box_slot, detail_screenshot_path FROM pokemon "
            "WHERE detail_screenshot_path IS NOT NULL AND parsed_at IS NULL"
        ).fetchall()

    conn.close()

    queue = []
    for row in rows:
        img = IMAGES_DIR.parent / row["detail_screenshot_path"]
        if img.exists():
            queue.append({
                "box": row["box_number"],
                "slot": row["box_slot"],
                "image_path": str(img),
            })

    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"Queue: {len(queue)} Pokemon → {QUEUE_PATH}")
    return queue


# ── Results import ────────────────────────────────────────────────────────────

def import_results(results_file: str):
    """Read a JSON array of {box, slot, ...metadata} and write to DB."""
    results = json.loads(Path(results_file).read_text())
    success = 0
    for item in results:
        if not item.get("species_name"):
            print(f"  [skip] box {item.get('box')} slot {item.get('slot')}: no species_name")
            continue

        # Keys that are not DB columns (queue metadata, not schema fields)
        NON_DB_KEYS = {"box", "slot", "image_path"}
        update = {
            "box_number": item["box"],
            "box_slot": item["slot"],
            "parsed_at": datetime.now().isoformat(),
            "raw_json": json.dumps(item),
            **{k: v for k, v in item.items()
               if k not in NON_DB_KEYS and v is not None},
        }
        upsert_pokemon(update)
        print(f"  [ok] {item['species_name']} lv{item.get('level')} (box {item['box']} slot {item['slot']})")
        success += 1

    print(f"\nDone. {success}/{len(results)} written to DB: {DB_PATH}")


# ── Inspect (for debugging) ───────────────────────────────────────────────────

def inspect_one(box: int, slot: int):
    """Print the image path and extraction prompt for a single slot."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pokemon WHERE box_number=? AND box_slot=?",
        (box, slot)
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No row found for box={box} slot={slot}")
        return

    row = rows[0]
    path = IMAGES_DIR.parent / row["detail_screenshot_path"] if row["detail_screenshot_path"] else None
    print(f"Image: {path}")
    print(f"Exists: {path.exists() if path else False}")
    print(f"\nPrompt:\n{EXTRACT_PROMPT}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pokemon HOME parse pipeline")
    parser.add_argument("--export-queue", action="store_true",
                        help="Export pending images to parse_queue.json")
    parser.add_argument("--import-results", metavar="FILE",
                        help="Import extracted results JSON into DB")
    parser.add_argument("--inspect", action="store_true",
                        help="Print image path for a single slot (for debugging)")
    parser.add_argument("--box", type=int, default=None)
    parser.add_argument("--slot", type=int, default=None)
    args = parser.parse_args()

    if args.import_results:
        import_results(args.import_results)
    elif args.export_queue:
        export_queue(args.box, args.slot)
    elif args.inspect:
        if args.box is None or args.slot is None:
            print("--inspect requires --box and --slot")
            sys.exit(1)
        inspect_one(args.box, args.slot)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
