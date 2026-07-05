# AI Context — Webnovel Scraper

Dense cold-start orientation for the next AI session. Not for end users.

## Purpose

Self-hosted web app: **find a web novel → scrape chapters → assemble → build an EPUB → write it to an Unraid file share** for reading on a Kindle Paperwhite. One Docker container, browser UI, runs on Unraid.

## How to work in this repo

- **The repo is the source of truth for intent + rationale.** Read [project-plan.md](project-plan.md) and the [ADRs](decisions/) before proposing architectural changes.
- **Phases map to minor versions** (Phase 0 → v0.1.0). Update the status tables in README + project-plan when a phase moves.
- **Update [CHANGELOG.md](../CHANGELOG.md) every phase** (`[Unreleased]` accumulates).
- **Config as code in the repo**; never hand-edit opaque runtime state. Runtime state (SQLite, cache) lives in the `/config` volume and is git-ignored.
- **Only publish a GitHub release when the user explicitly asks** (see the user's global release procedure).

## Decisions already made (do not relitigate without cause)

| Topic | Decision | ADR |
|-------|----------|-----|
| Stack | Python 3.12 + FastAPI + Jinja2/HTMX; SQLite; in-process asyncio worker | [0001](decisions/0001-tech-stack.md) |
| Output & delivery | EPUB only for v1; delivery = write to Unraid file share. Calibre/Kavita/Send-to-Kindle are deferred optional consumers | [0002](decisions/0002-epub-output-and-delivery.md) |
| Scraper strategy | Curated per-site adapters + generic readability fallback; Playwright only when JS is required | [0003](decisions/0003-scraper-adapter-strategy.md) |
| Books / volumes | A novel splits into user-defined "books" (`Volume` = chapter range + number); one EPUB per book; `calibre:series` groups them. Whole novel = one book 1..N | [0006](decisions/0006-books-and-volumes.md) |
| Legal/ethical | Personal use only; respect robots.txt + rate limits; no paywalled/auth'd sources | [0004](decisions/0004-legal-and-ethical-use.md) |

## Environment / target host

- Deploys to **Unraid** (user has UR1 and UR2; Calibre + Kavita run on UR1).
- Volumes: `/config` (state) and `/output` → **`/mnt/user/media/reading/webnovels`** (UR1 has no dedicated books share; this is under the existing `media` share). HTTP port default 8080 (host 8577).
- **Repo layout:** the deployable unit is the repo's **`docker/`** folder (`Dockerfile`, `docker-compose.yml`, `requirements.txt`, `app/`). Docs/README/LICENSE stay at repo root. Build context = `docker/`.
- **Deploy = Unraid Compose Manager plugin.** The *user* copies the contents of `docker/` to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/` (or clones + points Compose Manager at `docker/docker-compose.yml`), then **Compose Up**. See [ADR 0005](decisions/0005-unraid-deploy-workflow.md).
- **Build division of labour:** Claude edits Docker source **locally only**; the user copies to appdata + deploys. Never emit raw `docker compose` CLI for the appdata folder (project-name footgun → wrong tags/network). End deploy-affecting changes with a **▶ YOUR TURN** block.
- User is on Windows 11; shell is PowerShell (Bash tool also available). Repo not yet `git init`'d.

## Pipeline (the mental model)

`Discover → Scrape → Assemble → Convert → Deliver`, coordinated by a background job with SQLite-persisted progress. Chapters persist as fetched → scraping is resumable + idempotent; incremental update fetches only new chapters then rebuilds the EPUB.

## Core interfaces (target)

- Adapter: `fetch_novel(url)` and `fetch_chapter(ref)`, optional `search(query)` (gated by a `searchable` flag), plus `needs_render` and `is_fallback` flags. Registry: `get_adapter(url)` (curated adapters first, `GenericAdapter` catch-all last — always returns something for a well-formed URL), `get_adapter_by_name(name)`, `searchable_names()`, `cover_url_allowed(url)`.
- Discover search: `scrape.search_novels(query)` fans out over the sites in the `search_sites` setting.
- Fetch layer owns rate limiting / robots / retries (GET + POST + `get_rendered`) so adapters stay thin.
- Rendering (Phase 4/v0.5.0): `Fetcher.get_rendered(url)` → `core/render.py`'s `Renderer`
  (lazy-launched headless Chromium via Playwright, reused for the rest of the scrape).
  Curated adapters opt in via the static `needs_render` flag (none need it yet); the
  generic adapter decides per-page at runtime instead — see its module docstring for the
  two different shell-detection checks (chapter body vs. TOC page).
- EPUB builder: EbookLib — metadata, cover, navigable TOC, one XHTML per chapter.

## Gotchas / watch-list

- **Schema changes:** `create_all` never alters existing tables. Adding a column to a model
  is handled at startup by `db._ensure_columns` (additive `ALTER TABLE ADD COLUMN`, nullable
  only). Renaming/removing columns or changing types still needs a manual migration or a DB reset.

- **Site drift** breaks curated adapters — guarded by the fixture self-test harness (`tests/`,
  v0.4.5): from the repo root, `pip install -r requirements-dev.txt && pytest`. (Tests, pytest.ini,
  and requirements-dev.txt all live at the repo root, NOT in `docker/` — that folder is copied
  verbatim to the server on deploys and holds only what the container needs.) Fixtures are frozen
  snapshots (catch our own parsing regressions instantly); a real live-site change still needs a
  manual fixture refresh (save the new page HTML over the fixture, rerun, fix what fails).
- **Any new catch-all adapter must set `is_fallback = True`** (see `core/adapters/generic.py`).
  `cover_url_allowed()` (the `/cover` proxy's only gate — routes/pages.py) deliberately skips
  `is_fallback` adapters; forgetting the flag on a new "matches everything" adapter turns that
  route into an open image proxy for arbitrary URLs.
- **Playwright** inflates image size (base image is now `mcr.microsoft.com/playwright/python`,
  pinned exactly — see `requirements.txt` comment — to match the Dockerfile tag) and adds ~1GB
  RAM when active; the browser process itself is still launched lazily on first actual use, never
  at container startup. A curated adapter that needs it sets `needs_render = True`; the generic
  adapter instead auto-detects per-page (see `core/adapters/generic.py`) since it can't know a
  site's needs in advance.
- **Cloudflare bot-challenges are not the same problem as JS-rendered content.** Playwright solves
  "content is injected by a script after load." It does not reliably solve "the site is actively
  trying to detect and block headless browsers" (e.g. noveltrust.com/novellive.app, still shelved
  in project-plan.md) — treat that as a distinct, harder, not-yet-attempted problem.
- **Filename safety** on the share — sanitize `Author - Title.epub`, write atomically (temp + rename).
- **EPUB validity** — target epubcheck-clean structure so Send-to-Kindle/Calibre don't choke.
- **Politeness is a feature** — never remove/loosen rate limits to "go faster"; it's a design constraint, not a bug.

## Build-phase status

See the status tables in [README](../README.md#versions) and [project-plan](project-plan.md#status).
Phases 0–4 are done (Phase 4 — Coverage — completed at v0.5.0); Phase 5 (Library & jobs) is in
progress; Phase 7 (Content cleaning) has its first cut shipped. Current version: v0.5.0.

After any deploy-affecting edit, hand off with a **▶ YOUR TURN** block: update the stack (copy the repo's `docker/` contents to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`, or `git pull`), then Compose Manager → Compose Up; wait for "built/confirmed" before verifying.
