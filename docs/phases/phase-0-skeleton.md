# Phase 0 build log — Skeleton (v0.1.0)

**Status:** ◐ code complete + locally verified; awaiting first Unraid deploy confirmation.

## What was built

A runnable FastAPI app with a browser UI shell, SQLite persistence, and Docker packaging.

```
app/
  main.py              FastAPI entrypoint; lifespan creates data dir, inits DB, seeds settings
  config.py            deploy-level config from env (WN_DATA_DIR=/config, WN_OUTPUT_DIR=/output, port)
  db.py                SQLite engine + create_all + session helper
  models.py            SQLModel tables: Setting, Book, Chapter, Job
  settings_store.py    default settings + FIELDS descriptors + get_all/set_many/seed
  routes/
    health.py          GET /healthz (checks DB)
    pages.py           /, /discover, /library, /jobs, /settings (GET+POST)
  templates/           base + discover/library/jobs/settings (Jinja2)
  static/              styles.css, htmx.min.js (placeholder until Phase 5)
Dockerfile             python:3.12-slim; uvicorn on :8080
docker-compose.yml     Compose-Manager-safe (image + container_name pinned)
requirements.txt       fastapi, uvicorn, jinja2, python-multipart, sqlmodel, pydantic-settings
.dockerignore / .env.example
```

## Key decisions / notes

- **Two config layers.** Infra config (paths, port) comes from env via `pydantic-settings`; user-editable settings (output folder, concurrency, delay, defaults, cover style) live in the `setting` table and are edited on the Settings page. `settings_store.FIELDS` drives the form, so adding a setting is a one-liner.
- **Schema via `create_all`.** No Alembic yet — fine while the schema is additive. Introduce migrations if we ever need in-place column changes.
- **Slim base now, Playwright later.** Dockerfile uses `python:3.12-slim`; the Playwright/Chromium base is deferred to Phase 4 so the skeleton image stays small. (Minor deviation from the plan's "Playwright-capable base" — intentional.)
- **HTMX placeholder.** `base.html` references `/static/htmx.min.js` (empty placeholder) so it won't 404; the real lib arrives in Phase 5 when live job progress needs it.
- **Compose-Manager safety.** `image:` and `container_name:` are pinned; no named network needed for a single container. Never `docker compose` from the appdata shell (folder-name → wrong tag).

## Verification (local, Python 3.14 venv)

- `pip install -r requirements.txt` → imports OK.
- `uvicorn app.main:app` boots; `/healthz` → `{"status":"ok","db":"ok"}`; `/` → 303 → `/library`; all four nav pages 200.
- POST /settings (full form) → 303; values read back correctly.
- **Restart test (exit criterion):** stopped the process, started a fresh one against the same `WN_DATA_DIR`; settings survived. Direct SQLite read confirmed tables `book, chapter, job, setting` and persisted values (`concurrency=3`, `request_delay_seconds=1.5`, `strip_translator_notes=true`, etc.).

## Reproduce locally

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements.txt
WN_DATA_DIR=./.localdata/config WN_OUTPUT_DIR=./.localdata/output \
  ./.venv/Scripts/python -m uvicorn app.main:app --port 8577
# open http://127.0.0.1:8577
```

## Remaining to close the phase

- Deploy on UR1 via Compose Manager and confirm the container serves the UI and persists settings across a container restart (the real exit criterion on the target host).
