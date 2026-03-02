#!/usr/bin/env python3
"""
Batch coordinator: splits parse_queue.json into batch input files,
and imports completed batch result files to the DB.

Usage:
  python batch_coord.py split --batch-size 40   # create batch_results/input/batch_NNN.json
  python batch_coord.py import-all              # import all output files to DB
  python batch_coord.py status                  # show progress
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from collection.schema import get_db, upsert_pokemon, DB_PATH, IMAGES_DIR

QUEUE_PATH   = Path(__file__).parent / "parse_queue.json"
BATCH_DIR    = Path(__file__).parent / "batch_results"
INPUT_DIR    = BATCH_DIR / "input"
OUTPUT_DIR   = BATCH_DIR / "output"


def cmd_split(batch_size: int):
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    queue = json.loads(QUEUE_PATH.read_text())

    # Filter already-parsed
    conn = get_db()
    parsed = set()
    for row in conn.execute("SELECT box_number, box_slot FROM pokemon WHERE parsed_at IS NOT NULL"):
        parsed.add((row["box_number"], row["box_slot"]))
    conn.close()

    pending = [item for item in queue if (item["box"], item["slot"]) not in parsed]
    print(f"Pending: {len(pending)} (skipping {len(queue) - len(pending)} already parsed)")

    batches = [pending[i:i+batch_size] for i in range(0, len(pending), batch_size)]
    print(f"Splitting into {len(batches)} batches of up to {batch_size}")

    for i, batch in enumerate(batches):
        path = INPUT_DIR / f"batch_{i:04d}.json"
        if not path.exists():  # don't overwrite existing
            path.write_text(json.dumps(batch, indent=2))

    print(f"Written to {INPUT_DIR}/")
    return len(batches)


def cmd_import_all():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(OUTPUT_DIR.glob("batch_*.json"))
    if not files:
        print("No output files found.")
        return

    # Get valid DB columns
    conn = get_db()
    db_cols = {row[1] for row in conn.execute("PRAGMA table_info(pokemon)")}
    conn.close()
    NON_DB_KEYS = {"box", "slot", "image_path", "image_path2"}

    total_ok = 0
    total_skip = 0
    for f in files:
        results = json.loads(f.read_text())
        for item in results:
            update = {
                "box_number": item["box"],
                "box_slot": item["slot"],
                "parsed_at": datetime.now().isoformat(),
                "raw_json": json.dumps(item),
                **{k: v for k, v in item.items()
                   if k not in NON_DB_KEYS and k in db_cols and v is not None},
            }
            upsert_pokemon(update)
            if item.get("species_name"):
                total_ok += 1
            else:
                total_skip += 1
        # Move to imported/
        imported = BATCH_DIR / "imported"
        imported.mkdir(exist_ok=True)
        f.rename(imported / f.name)

    print(f"Imported {total_ok} Pokemon ({total_skip} skipped). DB: {DB_PATH}")


def cmd_status():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM pokemon").fetchone()[0]
    parsed = conn.execute("SELECT COUNT(*) FROM pokemon WHERE parsed_at IS NOT NULL").fetchone()[0]
    with_img = conn.execute("SELECT COUNT(*) FROM pokemon WHERE detail_screenshot_path IS NOT NULL").fetchone()[0]
    conn.close()

    pending_inputs  = len(list(INPUT_DIR.glob("batch_*.json")))  if INPUT_DIR.exists()  else 0
    pending_outputs = len(list(OUTPUT_DIR.glob("batch_*.json"))) if OUTPUT_DIR.exists() else 0
    imported        = len(list((BATCH_DIR / "imported").glob("batch_*.json"))) if (BATCH_DIR / "imported").exists() else 0

    print(f"DB:          {total} total, {with_img} with screenshot, {parsed} parsed")
    print(f"Remaining:   {with_img - parsed} unparsed")
    print(f"Batch files: {pending_inputs} input, {pending_outputs} output ready, {imported} imported")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    p_split = sub.add_parser("split")
    p_split.add_argument("--batch-size", type=int, default=40)

    sub.add_parser("import-all")
    sub.add_parser("status")

    args = parser.parse_args()
    if args.cmd == "split":
        cmd_split(args.batch_size)
    elif args.cmd == "import-all":
        cmd_import_all()
    elif args.cmd == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
