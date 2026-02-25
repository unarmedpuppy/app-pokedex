#!/usr/bin/env python3
"""
Pokemon HOME metadata extraction via Claude vision.
Runs AFTER capture.py has collected all screenshots.

Usage:
    python parse.py                         # parse all unparsed detail screenshots
    python parse.py --box 0 --slot 5        # parse specific slot
    python parse.py --dry-run               # print extractions without writing to DB
"""

import argparse
import base64
import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from collection.schema import get_db, upsert_pokemon, IMAGES_DIR, DB_PATH

CLIENT = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-4-6"

EXTRACT_PROMPT = """
You are looking at a Pokemon HOME detail screen for a single Pokemon.
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
  "iv_hp": 31,
  "iv_atk": 31,
  "iv_def": 31,
  "iv_spatk": 31,
  "iv_spdef": 31,
  "iv_speed": 31,
  "ev_hp": 0,
  "ev_atk": 0,
  "ev_def": 0,
  "ev_spatk": 252,
  "ev_spdef": 0,
  "ev_speed": 252,
  "move1": "Thunderbolt",
  "move2": "Volt Switch",
  "move3": "Grass Knot",
  "move4": "Filler Move",
  "original_trainer": "Joshua",
  "trainer_id": "12345",
  "game_of_origin": "Sword",
  "ball_type": "Poke Ball"
}

Notes:
- IVs show as stars or numbers (0-31). "No Good"=0, "Decent"=~15, "Best"=31.
- For IVs shown as star ratings (0-3 stars), use: 0=0, 1=~10, 2=~20, 3=31 as best estimate.
- gender: "male", "female", or "unknown"
- is_shiny: true if there is a shiny indicator/sparkle
- If you cannot see IVs/EVs at all (wrong screen), return null for all IV/EV fields
- Return ONLY the JSON object, no markdown, no explanation
"""


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def extract_metadata(image_path: Path) -> Optional[dict]:
    """Call Claude vision to extract Pokemon metadata from a detail screenshot."""
    try:
        b64 = encode_image(image_path)
        response = CLIENT.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    },
                    {"type": "text", "text": EXTRACT_PROMPT},
                ],
            }],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"  [error] Claude extraction failed: {e}")
        return None


def crop_sprite(box_screenshot: Path, slot: int, out_path: Path) -> bool:
    """
    Crop the Pokemon sprite from a box grid screenshot.
    Grid is 6 cols x 5 rows. Crops a single cell.
    """
    try:
        from PIL import Image

        img = Image.open(box_screenshot)
        w, h = img.size

        # Box grid bounds (match get_box_slot_coords() in capture.py)
        grid_left   = int(w * 0.05)
        grid_right  = int(w * 0.95)
        grid_top    = int(h * 0.18)
        grid_bottom = int(h * 0.82)

        cols, rows = 6, 5
        cell_w = (grid_right - grid_left) / cols
        cell_h = (grid_bottom - grid_top) / rows

        col = slot % cols
        row = slot // cols

        x1 = int(grid_left + cell_w * col)
        y1 = int(grid_top  + cell_h * row)
        x2 = int(x1 + cell_w)
        y2 = int(y1 + cell_h)

        sprite = img.crop((x1, y1, x2, y2))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sprite.save(str(out_path))
        return True
    except Exception as e:
        print(f"  [warn] sprite crop failed: {e}")
        return False


def parse_one(row: sqlite3.Row, dry_run: bool = False) -> bool:
    box = row["box_number"]
    slot = row["box_slot"]
    detail_path = IMAGES_DIR.parent / row["detail_screenshot_path"] if row["detail_screenshot_path"] else None

    if not detail_path or not detail_path.exists():
        print(f"  [skip] box {box} slot {slot}: no detail screenshot")
        return False

    print(f"  [parse] box {box} slot {slot}: {detail_path.name}")
    meta = extract_metadata(detail_path)

    if not meta:
        return False

    print(f"    → {meta.get('species_name')} lv{meta.get('level')} ({meta.get('nature')})")

    # Crop sprite from box screenshot
    sprite_path = None
    box_ss_rel = row["box_screenshot_path"]
    if box_ss_rel:
        box_ss = IMAGES_DIR.parent / box_ss_rel
        out = IMAGES_DIR / "sprites" / f"box_{box:03d}_slot_{slot:02d}.png"
        if crop_sprite(box_ss, slot, out):
            sprite_path = str(out.relative_to(IMAGES_DIR.parent))

    if dry_run:
        print(json.dumps(meta, indent=2))
        return True

    update = {
        "box_number": box,
        "box_slot": slot,
        "parsed_at": datetime.now().isoformat(),
        "raw_json": json.dumps(meta),
        "sprite_path": sprite_path,
        **{k: v for k, v in meta.items() if v is not None},
    }
    upsert_pokemon(update)
    return True


def main():
    parser = argparse.ArgumentParser(description="Parse Pokemon HOME screenshots with Claude vision")
    parser.add_argument("--box", type=int, default=None)
    parser.add_argument("--slot", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    conn = get_db()

    if args.box is not None and args.slot is not None:
        rows = conn.execute(
            "SELECT * FROM pokemon WHERE box_number=? AND box_slot=?",
            (args.box, args.slot)
        ).fetchall()
    else:
        # All rows that have a detail screenshot but haven't been parsed
        rows = conn.execute(
            "SELECT * FROM pokemon WHERE detail_screenshot_path IS NOT NULL AND parsed_at IS NULL"
        ).fetchall()

    conn.close()

    print(f"Parsing {len(rows)} Pokemon...")
    success = 0
    for row in rows:
        if parse_one(row, dry_run=args.dry_run):
            success += 1

    print(f"\nDone. {success}/{len(rows)} parsed successfully.")
    if not args.dry_run:
        print(f"DB: {DB_PATH}")


if __name__ == "__main__":
    main()
