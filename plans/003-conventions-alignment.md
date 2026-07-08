# Plan 003: Align the collection app with homelab conventions (CORS, /health, Dockerfile, AGENTS.md)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 1a43c12..HEAD -- collection/api.py Dockerfile docker-compose.yml`
> On mismatch with the excerpts below, treat as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED — Dockerfile base-image and non-root changes can break the build or file permissions; each step has its own build gate
- **Depends on**: plans/001-reconcile-deploy-config-before-first-tag.md (the home-server compose must expect port 8420 before any tag ships this Dockerfile)
- **Category**: tech-debt
- **Planned at**: commit `1a43c12`, 2026-07-07

## Why this matters

The canonical conventions in `/Users/joshuajenquist/workspace/homelab/homelab-app-template/CONVENTIONS.md` (env-driven CORS allowlist, `/health` endpoint wired to a Docker HEALTHCHECK, Harbor-proxied base images, non-root user, pinned dependencies, resource limits, `AGENTS.md`) exist because the 2026-07-02 audits found the same failures repeated across apps. The pokedex collection app violates most of them: wildcard CORS, no health endpoint, base images pulled straight from Docker Hub (`node:20-alpine`, `python:3.11-slim`), root user, no HEALTHCHECK, unpinned `pip install fastapi uvicorn`, no resource limits in compose, and no `AGENTS.md`. Individually small; together they make this repo the odd one out for every agent and monitoring tool that assumes the convention.

## Current state

- `collection/api.py:23-28`:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_methods=["GET"],
      allow_headers=["*"],
  )
  ```
  (No `allow_credentials=True`, GET-only — low risk, but the convention is an env allowlist.)
- `collection/api.py` — no `/health` route (grep for `health` returns nothing).
- `Dockerfile` — stage 1 `FROM node:20-alpine AS ui-build`; stage 2 `FROM python:3.11-slim`; `RUN pip install --no-cache-dir fastapi "uvicorn[standard]"` (unpinned); no `USER`, no `HEALTHCHECK`; `EXPOSE 8420`.
- `docker-compose.yml` — no `mem_limit`/`pids_limit`.
- No `AGENTS.md` in the repo root. No `.dockerignore` either (`ls .dockerignore` fails).
- Convention exemplar for all of this: `/Users/joshuajenquist/workspace/homelab/homelab-app-template/` (`app/main.py` for CORS/health shape, `Dockerfile` for Harbor base + non-root + HEALTHCHECK, `.dockerignore`, `AGENTS.md`).
- Harbor proxy prefix used ecosystem-wide: `harbor.server.unarmedpuppy.com/docker-hub/library/<image>` (see `/Users/joshuajenquist/workspace/homelab/rental-property/api/Dockerfile:1` for a live example).
- Auth: NOT needed here — the API is GET-only (list/detail/stats/image); the convention keeps read-only GETs open.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Build image | `docker build -t pokedex-align-test .` | exit 0 |
| Smoke health | `docker run --rm -d -p 18420:8420 --name pkx pokedex-align-test && sleep 3 && curl -sf http://localhost:18420/health; docker rm -f pkx` | `{"status":"healthy","service":"pokedex-collection",...}` |
| Compose config | `docker compose config` | exit 0 |
| Syntax check | `python3 -m py_compile collection/api.py` | exit 0 |

## Scope

**In scope**:
- `collection/api.py` (CORS block + new `/health` route only)
- `Dockerfile`
- `docker-compose.yml`
- `collection/requirements.txt` (create)
- `.dockerignore` (create)
- `AGENTS.md` (create)

**Out of scope**:
- `serve_image` (plan 002), everything under `pokedex/` (upstream veekun fork — do not "align" it), `setup.py`, `.gitea/workflows/` (image name/tag flow is plan 001 territory), the home-server repo.

## Git workflow

- Branch: `chore/conventions-alignment`
- Commit style: `chore: <summary>` (see `ac386a2`-style commits in sibling repos)
- Do NOT push unless the operator instructed it.

## Steps

### Step 1: Env-driven CORS + `/health` in `collection/api.py`

Replace the CORS block with the template pattern:

```python
import os
...
_origins = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:8420,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "healthy", "service": "pokedex-collection", "version": "1.0.0"}
```

Place `/health` ABOVE the SPA catch-all mount at the bottom of the file (`@app.get("/{full_path:path}")` at `collection/api.py:145-147` would shadow it otherwise — routes are matched in registration order).

**Verify**: `python3 -m py_compile collection/api.py` → exit 0; then run the app briefly (`uvicorn collection.api:app --port 18421 &`) and `curl -sf http://localhost:18421/health` → the JSON above.

### Step 2: Pin Python deps

Create `collection/requirements.txt`:
```
fastapi==0.115.*
uvicorn[standard]==0.32.*
```
(Resolve to exact `==` versions by checking what a fresh `pip install fastapi "uvicorn[standard]"` resolves today; write those exact pins.)

**Verify**: `pip install --dry-run -r collection/requirements.txt` → resolves without conflict.

### Step 3: Harden the Dockerfile

- `FROM node:20-alpine AS ui-build` → `FROM harbor.server.unarmedpuppy.com/docker-hub/library/node:20-alpine AS ui-build`
- `FROM python:3.11-slim` → `FROM harbor.server.unarmedpuppy.com/docker-hub/library/python:3.11-slim`
- Replace the inline pip install with `COPY collection/requirements.txt ./collection/requirements.txt` + `RUN pip install --no-cache-dir -r collection/requirements.txt`
- Add before `CMD`:
  ```dockerfile
  RUN useradd --create-home appuser
  USER appuser
  HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python3 -c "import urllib.request;urllib.request.urlopen('http://localhost:8420/health')"
  ```

**Verify**: `docker build -t pokedex-align-test .` → exit 0; smoke-health command from the table → healthy JSON; `docker run --rm pokedex-align-test whoami` → `appuser`.

Note: if the Harbor proxy is unreachable from the build machine, building may fail on the `FROM` pull — that is an environment problem, not a Dockerfile problem; see STOP conditions.

### Step 4: `.dockerignore`, compose limits, `AGENTS.md`

- Copy `.dockerignore` from `homelab-app-template/.dockerignore` and append repo-specific lines: `pokedex/`, `collection/images/`, `collection/*.db`, `collection/ui/node_modules/`.
- In `docker-compose.yml` add to the `pokedex` service: `mem_limit: 512m` and `pids_limit: 256`.
- Write `AGENTS.md` (model on `homelab-app-template/AGENTS.md`): what the repo is (veekun pokedex fork + Pokemon HOME collection app in `collection/`), how to build (`docker compose up -d --build`), the port (8420), where the data lives (host-side `collection/pokemon_home.db` + `collection/images/`, produced by `capture.py`/`parse.py` on a workstation), the deploy flow (tag `vN.N.N` → Gitea CI → Harbor `library/pokedex` → Watchtower; compose lives in `home-server/apps/pokedex/`), and the gotcha from plan 001 (home-server compose must match port 8420).

**Verify**: `docker compose config` → exit 0 and shows `mem_limit`; `test -f AGENTS.md && test -f .dockerignore` → exit 0.

## Test plan

No new unit tests here (plan 002 seeds the test suite). Gates are the build, the `/health` smoke check, and `docker compose config`.

## Done criteria

- [ ] `grep -n 'allow_origins=\["\*"\]' collection/api.py` → no matches
- [ ] `curl -sf http://localhost:18420/health` (against locally built image) → healthy JSON
- [ ] `grep -c "harbor.server.unarmedpuppy.com" Dockerfile` → 2
- [ ] `docker run --rm pokedex-align-test whoami` → `appuser`
- [ ] `AGENTS.md`, `.dockerignore`, `collection/requirements.txt` exist
- [ ] Only in-scope files modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- Harbor proxy pulls fail from your environment (can't validate the base-image change) — commit nothing image-related you couldn't build.
- The non-root user breaks reading the mounted DB/images (host file ownership) after one fix attempt (e.g. matching UID) — report; UID mapping is an owner decision.
- `collection/api.py` no longer matches the excerpts.

## Maintenance notes

- When capture tooling writes new columns/files, keep `.dockerignore` in sync so the DB never enters the build context.
- Follow-up not in this plan: register `/health` in Uptime Kuma once deployed; a data-sync path for `pokemon_home.db` to the server (see plans/README.md deferred items).
