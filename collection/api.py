#!/usr/bin/env python3
"""
Pokemon HOME collection API.

Run: uvicorn collection.api:app --reload --port 8420
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

COLLECTION_DIR = Path(__file__).parent
DB_PATH = COLLECTION_DIR / "pokemon_home.db"
UI_DIST = COLLECTION_DIR / "ui" / "dist"

app = FastAPI(title="Pokemon HOME Collection")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/pokemon")
def list_pokemon(
    q: Optional[str] = Query(None),
    shiny: Optional[bool] = Query(None),
    ot: Optional[str] = Query(None),
    limit: int = Query(60, le=200),
    offset: int = Query(0),
):
    conn = get_conn()

    conditions = ["parsed_at IS NOT NULL"]
    params: list = []

    if q:
        conditions.append(
            "(species_name LIKE ? OR nickname LIKE ? OR original_trainer LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like])

    if shiny is not None:
        conditions.append("is_shiny = ?")
        params.append(1 if shiny else 0)

    if ot:
        conditions.append("original_trainer LIKE ?")
        params.append(f"%{ot}%")

    where = " AND ".join(conditions)

    total = conn.execute(
        f"SELECT COUNT(*) FROM pokemon WHERE {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT id, box_number, box_slot, species_name, dex_number, form_name, "
        f"nickname, level, nature, is_shiny, gender, original_trainer, trainer_id, "
        f"ball_type, detail_screenshot_path "
        f"FROM pokemon WHERE {where} "
        f"ORDER BY box_number, box_slot LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    conn.close()

    items = []
    for r in rows:
        d = dict(r)
        if d["detail_screenshot_path"]:
            d["image_url"] = f"/image/{d['detail_screenshot_path']}"
        else:
            d["image_url"] = None
        items.append(d)

    return {"total": total, "items": items}


@app.get("/api/pokemon/{pokemon_id}")
def get_pokemon(pokemon_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM pokemon WHERE id = ?", (pokemon_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    d = dict(row)
    if d["detail_screenshot_path"]:
        d["image_url"] = f"/image/{d['detail_screenshot_path']}"
    return d


@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM pokemon WHERE parsed_at IS NOT NULL").fetchone()[0]
    shiny = conn.execute("SELECT COUNT(*) FROM pokemon WHERE is_shiny = 1").fetchone()[0]
    ots = conn.execute(
        "SELECT original_trainer, COUNT(*) as n FROM pokemon "
        "WHERE parsed_at IS NOT NULL AND original_trainer IS NOT NULL "
        "GROUP BY original_trainer ORDER BY n DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "shiny": shiny,
        "top_trainers": [dict(r) for r in ots],
    }


@app.get("/image/{path:path}")
def serve_image(path: str):
    img = COLLECTION_DIR / path
    if not img.exists() or not img.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img)


# ── Serve built React UI (production / Docker) ────────────────────────────────
# In dev, Vite handles this. In production, the built dist/ is served here.
# This must come last so it doesn't shadow API routes.

if UI_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=str(UI_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        return FileResponse(str(UI_DIST / "index.html"))
