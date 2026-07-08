# Plan 002: Contain the `/image/{path}` endpoint to the collection directory

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 1a43c12..HEAD -- collection/api.py`
> If `collection/api.py` changed since this plan was written, compare the
> "Current state" excerpt against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW — pure input-validation addition on one read-only endpoint
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `1a43c12`, 2026-07-07

## Why this matters

`collection/api.py` serves screenshot files with a raw catch-all path parameter and joins it directly onto the app directory with no containment check. A request whose path segment contains `..` sequences (sent raw, e.g. `curl --path-as-is`, or percent-encoded) resolves outside `collection/` and returns arbitrary readable files from the container filesystem (`/etc/passwd`, app source, the SQLite DB). Exposure is bounded today — the service sits behind Traefik (LAN/Tailscale unauthenticated, basicauth externally) and the container holds low-sensitivity data — but this is exactly the class of defect that becomes serious the moment the container gains a secret (an `.env`, a token file). Fix is a few lines plus a regression test.

## Current state

- `collection/api.py:129-134`:
  ```python
  @app.get("/image/{path:path}")
  def serve_image(path: str):
      img = COLLECTION_DIR / path
      if not img.exists() or not img.is_file():
          raise HTTPException(status_code=404, detail="Image not found")
      return FileResponse(img)
  ```
- `collection/api.py:17` — `COLLECTION_DIR = Path(__file__).parent`
- Callers build image URLs as `f"/image/{d['detail_screenshot_path']}"` (`collection/api.py:86,107`); stored paths look like `images/<file>.png` relative to `COLLECTION_DIR`.
- There are **no tests** for the collection app anywhere in the repo (the `pokedex/tests/` suite is the upstream veekun fork's and requires a built database).
- Repo convention: plain FastAPI function endpoints, stdlib only — match this style; do not introduce new dependencies.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install test deps (venv) | `python3 -m venv .venv-plans && .venv-plans/bin/pip install fastapi httpx pytest uvicorn` | exit 0 |
| Run new tests | `.venv-plans/bin/pytest collection/tests/test_api_images.py -q` | all pass |
| Syntax check | `python3 -m py_compile collection/api.py` | exit 0, no output |

(The repo has no established test runner for the collection app; the venv above is disposable — add `.venv-plans/` to nothing, just delete it when done.)

## Scope

**In scope** (the only files you should modify/create):
- `collection/api.py` (the `serve_image` function only)
- `collection/tests/__init__.py` (create, empty)
- `collection/tests/test_api_images.py` (create)

**Out of scope** (do NOT touch):
- The CORS middleware block (`collection/api.py:23-28`) — plan 003 handles it.
- `conftest.py` and `pokedex/tests/` — upstream veekun test infrastructure; adding collection tests there entangles them with the veekun DB fixtures.
- `capture.py`, `parse.py`, `batch_*.py` — host-side tooling, unrelated.

## Git workflow

- Branch: `security/image-path-containment`
- Commit style (from `git log`): `fix: <summary>` / `security: <summary>` (e.g. commit `2be76fc chore(security): ...`)
- Do NOT push unless the operator instructed it.

## Steps

### Step 1: Add containment to `serve_image`

Replace the body of `serve_image` in `collection/api.py` with a resolved-path containment check:

```python
@app.get("/image/{path:path}")
def serve_image(path: str):
    base = COLLECTION_DIR.resolve()
    img = (COLLECTION_DIR / path).resolve()
    if not img.is_relative_to(base):
        raise HTTPException(status_code=404, detail="Image not found")
    if not img.exists() or not img.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img)
```

Notes: `Path.is_relative_to` exists on Python 3.9+ (image runs 3.11-slim — fine). Return 404, not 403, so the endpoint doesn't confirm the existence of out-of-tree files.

**Verify**: `python3 -m py_compile collection/api.py` → exit 0.

### Step 2: Write regression tests

Create `collection/tests/test_api_images.py` using `fastapi.testclient.TestClient`:

- happy path: create a temp file under `COLLECTION_DIR / "images"` (use `tmp_path` + monkeypatch of `collection.api.COLLECTION_DIR` if simpler), GET `/image/images/<name>.png` → 200.
- traversal literal: `client.get("/image/../../etc/passwd")` → 404 (TestClient does not normalize; assert not 200).
- traversal resolved: `client.get("/image/images/../../api.py")` → 404 (a file that DOES exist but sits outside/at the base via `..` — asserts the resolve check, not just existence).
- missing file: `/image/images/nope.png` → 404.

**Verify**: `.venv-plans/bin/pytest collection/tests/test_api_images.py -q` → 4 passed.

## Test plan

The four tests in Step 2 are the test plan; model their structure on plain pytest functions (no fixtures beyond `tmp_path`/`monkeypatch`). They become the seed of the collection app's test suite (currently zero tests).

## Done criteria

- [ ] `.venv-plans/bin/pytest collection/tests/test_api_images.py -q` → all pass
- [ ] `grep -n "is_relative_to" collection/api.py` → one match inside `serve_image`
- [ ] `python3 -m py_compile collection/api.py` exits 0
- [ ] Only in-scope files modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- `serve_image` in the live code no longer matches the excerpt (drifted).
- The stored `detail_screenshot_path` values turn out to be absolute paths or to point outside `COLLECTION_DIR` (the happy path would break) — report; the data model needs a decision first.
- Tests can't import `collection.api` due to the module-level `DB_PATH`/`UI_DIST` side effects in ways monkeypatching can't handle after 2 attempts.

## Maintenance notes

- If image serving is ever switched to `StaticFiles` (which has its own traversal protection), this handler and its tests can be deleted together.
- Reviewer should confirm the 404-on-out-of-tree behavior (no information leak about file existence).
