# Plan 001: Reconcile pokedex deploy config so the first `v*` tag doesn't break the live site

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 1a43c12..HEAD -- Dockerfile docker-compose.yml .gitea/workflows/build.yml`
> Also check `/Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml`
> against the excerpts below. On a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED — touches the production compose for a live service; wrong port/volume config takes the site down (which is exactly what this plan prevents from happening automatically)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `1a43c12`, 2026-07-07

## Why this matters

The pokedex repo's CI (`.gitea/workflows/build.yml`) builds image `library/pokedex:latest` from the repo `Dockerfile`, which runs the **Pokemon HOME collection FastAPI app on port 8420**. But the production compose at `home-server/apps/pokedex/docker-compose.yml` runs `library/pokedex:latest` expecting a web server **on port 80** (`loadbalancer.server.port=80`, `ports: "8103:80"`), mounts **no volumes** for `pokemon_home.db` or images, and has Watchtower auto-update enabled. Today this is latent because **no `v*` tag has ever been pushed** (only `veekun-promotions/*` tags exist — the workflow has never fired), so Harbor still holds the older static National Pokédex image. The **first** `git tag vX.X.X && git push origin vX.X.X` will rebuild `library/pokedex:latest`, Watchtower will roll the container within ~60s, nothing will listen on port 80, and `pokedex.server.unarmedpuppy.com` goes down — and even on the right port the collection app would 500 because its SQLite DB isn't mounted.

## Current state

- `Dockerfile` (pokedex repo) — final stage: `EXPOSE 8420`, `CMD ["python3", "-m", "uvicorn", "collection.api:app", "--host", "0.0.0.0", "--port", "8420"]`
- `.gitea/workflows/build.yml` — on `push: tags: ['v*']`, calls the shared workflow with `image_name: library/pokedex`, `dockerfile: Dockerfile`, `context: .`
- `docker-compose.yml` (pokedex repo, dev) — publishes `8420:8420` and mounts:
  ```yaml
  volumes:
    - ./collection/pokemon_home.db:/app/collection/pokemon_home.db:ro
    - ./collection/images:/app/collection/images:ro
  ```
- `collection/api.py:17-18` — the app resolves the DB relative to its own directory: `DB_PATH = COLLECTION_DIR / "pokemon_home.db"` where `COLLECTION_DIR = Path(__file__).parent` → in the image that is `/app/collection/pokemon_home.db`.
- `/Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml` — `image: harbor.server.unarmedpuppy.com/library/pokedex:latest`, `ports: "8103:80"`, `traefik.http.services.pokedex.loadbalancer.server.port=80`, `com.centurylinklabs.watchtower.enable=true`, **no volumes**, homepage description "National Pokédex - Complete collection of all Pokémon" (describes the OLD image's content, not this repo's collection app).
- Deploy model (homelab convention): repo tag → Gitea CI → Harbor → Watchtower/auto-deploy. Compose changes deploy via the `home-server` repo, not this one.

**Decision this plan implements (recommended default):** keep the image name `library/pokedex` and update the home-server compose to match this repo's app (port 8420, DB/images volumes), because the repo owner already pointed CI at that name. The alternative (rename the image to e.g. `library/pokemon-home` and leave the old static site untouched) is listed as a STOP condition question if evidence contradicts the default.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Build image locally | `docker build -t pokedex-test /Users/joshuajenquist/workspace/homelab/pokedex` | exit 0 |
| Compose config check | `docker compose -f /Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml config` | exit 0, rendered config |
| Container smoke test | `docker run --rm -d -p 18420:8420 --name pokedex-smoke pokedex-test && sleep 3 && curl -sf http://localhost:18420/api/stats; docker rm -f pokedex-smoke` | JSON or a 500 (500 acceptable here — no DB mounted); NOT connection-refused |

## Scope

**In scope** (the only files you should modify):
- `/Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml`

**Out of scope** (do NOT touch):
- `Dockerfile`, `collection/api.py`, `.gitea/workflows/build.yml` in the pokedex repo (plan 003 handles convention alignment there)
- Any other app under `home-server/apps/`
- Do NOT push any `v*` tag — that is the owner's deploy action, and it must happen only after the home-server compose change is deployed.

## Git workflow

- Work on a branch in **home-server**: `fix/pokedex-compose-port-and-volumes`
- Commit message style (from `git log`): `fix: <imperative summary>`
- Do NOT push or tag unless the operator instructed it.

## Steps

### Step 1: Update the production compose to match the image the repo actually builds

In `/Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml`:

1. Change `ports: - "8103:80"` → `- "8103:8420"`.
2. Change `traefik.http.services.pokedex.loadbalancer.server.port=80` → `...server.port=8420`.
3. Add under the `pokedex` service:
   ```yaml
   volumes:
     - ./data/pokemon_home.db:/app/collection/pokemon_home.db:ro
     - ./data/images:/app/collection/images:ro
   ```
4. Update the `homepage.description` label to `Pokemon HOME collection browser`.

**Verify**: `docker compose -f /Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml config | grep -E "8420|pokemon_home"` → shows the new port mapping and both volume mounts.

### Step 2: Smoke-test the image the tag would produce

Run the "Build image locally" and "Container smoke test" commands from the table. The point is confirming the app listens on 8420 (any HTTP response, even 500 for missing DB, proves the port).

**Verify**: `curl -s -o /dev/null -w "%{http_code}" http://localhost:18420/` during the smoke test → an HTTP status code (200/404/500), not `000`.

### Step 3: Document the deploy ordering

Add a comment block at the top of the home-server compose file:

```yaml
# DEPLOY ORDER: this compose change must be live on the server (with
# data/pokemon_home.db + data/images copied there) BEFORE the first
# `v*` tag is pushed in the pokedex repo — the tag rebuilds
# library/pokedex:latest as the collection app (uvicorn :8420) and
# Watchtower rolls it automatically.
```

**Verify**: `head -8 /Users/joshuajenquist/workspace/homelab/home-server/apps/pokedex/docker-compose.yml` → comment present.

## Test plan

No automated tests exist in either repo for this (see pokedex finding on missing verification baseline). The compose-config check plus the local container smoke test are the gates.

## Done criteria

- [ ] `docker compose -f .../apps/pokedex/docker-compose.yml config` exits 0
- [ ] Rendered config maps host 8103 → container 8420 and mounts the two `./data/...` paths
- [ ] Local image smoke test answers HTTP on 8420
- [ ] No files outside the in-scope list modified (`git -C home-server status`)
- [ ] `plans/README.md` (pokedex repo) status row updated

## STOP conditions

- The Harbor image name in `.gitea/workflows/build.yml` no longer says `library/pokedex` (the owner may have renamed it — this plan's premise is gone).
- Evidence that the currently deployed `library/pokedex:latest` container is actively depended on as the static National Pokédex site AND the owner wants to keep it (e.g. a second compose entry or docs saying so): stop and ask whether to rename the new image instead (`library/pokemon-home`).
- The home-server compose file differs materially from the excerpt above.

## Maintenance notes

- The server needs `pokemon_home.db` + `images/` copied to `home-server/apps/pokedex/data/` (capture runs on a workstation, per repo compose comments) — until a sync path exists, the deployed app will show an empty/erroring collection. That data-sync design is deferred (see plans/README.md).
- When plan 003 adds a `/health` endpoint, add a Docker `HEALTHCHECK` + Uptime Kuma entry against it.
