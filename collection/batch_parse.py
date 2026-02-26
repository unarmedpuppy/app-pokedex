#!/usr/bin/env python3
"""
Pokemon HOME batch vision extractor.

Reads parse_queue.json, sends each screenshot to Claude haiku for structured
extraction, writes results directly to the DB as they complete.

Resumable: already-parsed rows (parsed_at IS NOT NULL) are skipped on re-run.

Usage:
  python batch_parse.py                   # full run
  python batch_parse.py --concurrency 20  # tune parallelism
  python batch_parse.py --limit 50        # test run
  python batch_parse.py --model claude-haiku-4-5-20251001
"""

import argparse
import asyncio
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from collection.schema import get_db, upsert_pokemon, DB_PATH

QUEUE_PATH = Path(__file__).parent / "parse_queue.json"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_CONCURRENCY = 15

EXTRACT_PROMPT_1 = """You are looking at a Pokemon HOME detail screen for a single Pokemon.
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

EXTRACT_PROMPT_2 = """You are looking at the scrolled-down portion of a Pokemon HOME detail screen.
Extract the caught/met information visible and return it as JSON.

Return ONLY valid JSON with these exact keys (use null for any field not visible):

{
  "date_caught": "2023-04-01",
  "met_at_level": 1,
  "met_at_location": "Mesagoza"
}

Notes:
- date_caught: format as YYYY-MM-DD if visible, otherwise null
- met_at_level: integer level at which the Pokemon was met/received
- met_at_location: the location name shown (e.g. "Mesagoza", "Link Trade", "Pokémon HOME")
- Return ONLY the JSON object, no markdown, no explanation"""


def load_image_b64(path: str) -> str:
    return base64.standard_b64encode(Path(path).read_bytes()).decode()


def already_parsed(box: int, slot: int) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT parsed_at FROM pokemon WHERE box_number=? AND box_slot=?",
        (box, slot),
    ).fetchone()
    conn.close()
    return row is not None and row["parsed_at"] is not None


def write_result(item: dict, data: dict):
    NON_DB_KEYS = {"box", "slot", "image_path"}
    update = {
        "box_number": item["box"],
        "box_slot": item["slot"],
        "parsed_at": datetime.now().isoformat(),
        "raw_json": json.dumps(data),
        **{k: v for k, v in data.items() if k not in NON_DB_KEYS and v is not None},
    }
    upsert_pokemon(update)


async def call_claude(client, model: str, images: list[str], prompt: str) -> dict:
    """Send one or two images + prompt to Claude, return parsed JSON."""
    content = []
    for img_b64 in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
        })
    content.append({"type": "text", "text": prompt})

    resp = await client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


async def process_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    item: dict,
    model: str,
    counters: dict,
) -> None:
    box, slot = item["box"], item["slot"]

    if already_parsed(box, slot):
        counters["skipped"] += 1
        return

    img_path = item["image_path"]
    img_path2 = item.get("image_path2")

    if not Path(img_path).exists():
        counters["missing"] += 1
        print(f"  [miss] box={box} slot={slot} — {img_path}", flush=True)
        return

    async with sem:
        for attempt in range(3):
            try:
                img_b64 = load_image_b64(img_path)

                # First screenshot: main detail (species, moves, OT, etc.)
                data = await call_claude(client, model, [img_b64], EXTRACT_PROMPT_1)

                # Second screenshot: caught info (date, met at) — if available
                if img_path2 and Path(img_path2).exists():
                    img_b64_2 = load_image_b64(img_path2)
                    caught_data = await call_claude(client, model, [img_b64_2], EXTRACT_PROMPT_2)
                    data.update({k: v for k, v in caught_data.items() if v is not None})

                write_result(item, data)
                counters["ok"] += 1

                total_done = counters["ok"] + counters["errors"]
                if total_done % 50 == 0 or total_done <= 5:
                    elapsed = time.time() - counters["start"]
                    rate = total_done / elapsed if elapsed > 0 else 0
                    remaining = counters["total"] - counters["skipped"] - total_done
                    eta_s = remaining / rate if rate > 0 else 0
                    eta_min = int(eta_s / 60)
                    print(
                        f"  [{total_done}/{counters['total'] - counters['skipped']}] "
                        f"{data.get('species_name','?')} lv{data.get('level','?')} "
                        f"| {rate:.1f}/s | ETA ~{eta_min}m",
                        flush=True,
                    )
                return

            except json.JSONDecodeError as e:
                counters["errors"] += 1
                print(f"  [json-err] box={box} slot={slot}: {e}", flush=True)
                return
            except anthropic.RateLimitError:
                wait = 2 ** (attempt + 1)
                print(f"  [rate-limit] attempt {attempt+1}, sleeping {wait}s...", flush=True)
                await asyncio.sleep(wait)
            except Exception as e:
                if attempt == 2:
                    counters["errors"] += 1
                    print(f"  [err] box={box} slot={slot}: {e}", flush=True)
                else:
                    await asyncio.sleep(1)


async def run(model: str, concurrency: int, limit: Optional[int]):
    queue = json.loads(QUEUE_PATH.read_text())
    if limit:
        queue = queue[:limit]

    # Enrich queue items with second screenshot path if available in DB
    conn = get_db()
    path2_map = {
        (row["box_number"], row["box_slot"]): row["detail_screenshot2_path"]
        for row in conn.execute(
            "SELECT box_number, box_slot, detail_screenshot2_path FROM pokemon "
            "WHERE detail_screenshot2_path IS NOT NULL"
        )
    }
    conn.close()
    collection_dir = Path(__file__).parent
    for item in queue:
        p2 = path2_map.get((item["box"], item["slot"]))
        if p2:
            item["image_path2"] = str(collection_dir / p2)

    print(f"Queue: {len(queue)} items")
    print(f"Model: {model} | Concurrency: {concurrency}")
    print(f"DB: {DB_PATH}\n")

    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(concurrency)
    counters = {
        "ok": 0,
        "errors": 0,
        "skipped": 0,
        "missing": 0,
        "total": len(queue),
        "start": time.time(),
    }

    tasks = [
        process_one(client, sem, item, model, counters)
        for item in queue
    ]
    await asyncio.gather(*tasks)

    elapsed = time.time() - counters["start"]
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  ok={counters['ok']}  errors={counters['errors']}  "
          f"skipped={counters['skipped']}  missing={counters['missing']}")


def main():
    parser = argparse.ArgumentParser(description="Pokemon HOME batch vision extractor")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--limit", type=int, default=None, help="Cap for testing")
    args = parser.parse_args()

    asyncio.run(run(args.model, args.concurrency, args.limit))


if __name__ == "__main__":
    main()
