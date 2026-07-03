# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Phases map loosely to minor versions (Phase 0 → v0.1.0).

## [Unreleased]

### Added
- **Live build progress:** while a book builds, the Novel page shows a live progress bar with a
  status message (Downloading chapters X/Y → Building EPUB → Building PDF → Done), polling
  `GET /volumes/{id}/progress` every ~1.5s and auto-refreshing when finished. Backed by an
  in-memory progress registry (`app/core/progress.py`) that the in-process build task updates;
  `scrape_bodies` gained a `progress_cb`. Build tasks now also fail gracefully (marked `error`
  instead of getting stuck on `building`). This is the "live progress" slice of Phase 5.

## [0.4.1] — 2026-07-03

### Added
- **Rescan for new chapters:** a button on the Novel page re-reads the source novel page and adds
  any newly-published chapters (idempotent — existing downloaded chapters are untouched), reporting
  how many were found. Then extend a book's end (or add a new book) to include them.
  Route `POST /novels/{id}/rescan`.

### Changed
- **Default output path is now `/mnt/user/media/reading/webnovels`** (was `.../media/books/webnovels`)
  in `docker-compose.yml`. The container still writes to `/output`; only the host bind mount changed.
- **EPUB opens on its cover.** The cover page is now first in the reading order (spine), in addition
  to the `<meta name="cover">` + EPUB3 `cover-image` metadata that already drives the Kindle library
  thumbnail — so the book both shows a cover in the library and opens on it.

## [0.4.0] — 2026-07-03

First tagged release — the cumulative result of build Phases 0–3. A working, self-hosted
tool that searches web novels, scrapes chapters, and builds EPUB/PDF "books" onto an Unraid
share, deployed via the Unraid Compose Manager plugin.

### Added
- **Phase 0 — app skeleton (v0.1.0):** FastAPI app with Jinja2/HTMX UI shell (Discover ·
  Library · Jobs · Settings), SQLite models, a Settings page persisting politeness/defaults,
  `/healthz`, `Dockerfile`, Compose-Manager-safe `docker-compose.yml`. See
  [docs/phases/phase-0-skeleton.md](docs/phases/phase-0-skeleton.md).
- **Phase 1 — scraper core (v0.2.0):** polite async fetch layer (per-host rate limit,
  concurrency, retries/backoff, robots.txt, configurable User-Agent), adapter interface +
  registry, and the first curated adapter for **freewebnovel** (auto-routes the Cloudflare-walled
  `.com` to the `.vip` mirror; title/author/cover + full chapter enumeration; chapter bodies
  cleaned to `<p>` XHTML). Idempotent import/download. See
  [docs/phases/phase-1-scraper-core.md](docs/phases/phase-1-scraper-core.md).
- **Phase 2 — EPUB + PDF + books (v0.3.0):** a novel can be split into user-defined **"books"**
  (the `Volume` table — a chapter range with a book number + optional title; whole-novel = one
  book spanning 1..N). EbookLib EPUB3 with metadata, source cover, navigable TOC, one XHTML per
  chapter, and `calibre:series` grouping; an optional **PDF** alongside it (fpdf2; `format_epub`/
  `format_pdf` toggles + `pdf_page_size` A5/A4). Files written atomically as
  `<Novel> - Book NN[ - Title].epub`/`.pdf` to `/output` (→ `/mnt/user/media/books/webnovels`).
  See [ADR 0006](docs/decisions/0006-books-and-volumes.md),
  [ADR 0007](docs/decisions/0007-also-emit-pdf.md), and
  [docs/phases/phase-2-epub.md](docs/phases/phase-2-epub.md).
- **Phase 3 — discovery / title search (v0.4.0):** a Discover search box queries the sites in the
  `search_sites` setting (multi-select, auto-populated from searchable adapters; freewebnovel for
  now). Results show cover + title + chapter count with one-click **Import**. Adds `Adapter.search()`,
  `Fetcher.post()`, and `scrape.search_novels()`. Cross-site ranking deferred until more adapters
  exist. See [docs/phases/phase-3-discovery.md](docs/phases/phase-3-discovery.md).
- **Editable books + sequential ranges:** each book on the Novel page is an editable card (correct
  number/title/start/end and Save, or Delete). The Add-a-book form defaults the start to one past
  the furthest existing book (and the next book number) so books stay sequential.
- **Out-of-sequence flag:** a book whose start isn't exactly one past the previous book's end
  (gap or overlap; first book expected to start at 1) is highlighted with a warning and the
  expected start, so ranges needing correction are obvious.
- **Book covers in the UI:** cover thumbnails in Discover results and on the Novel page, served
  through a `/cover` proxy restricted to known adapter hosts (not an open proxy; also dodges
  hotlink/referer issues).
- Project documentation: README, phased project plan, architecture, AI cold-start context, and
  ADRs 0001–0007. MIT license and `.gitignore`.

### Changed
- **Self-contained `docker/` folder** (`Dockerfile`, `docker-compose.yml`, `requirements.txt`,
  `.dockerignore`, `app/`) — the single unit copied to the Unraid appdata stack, kept apart from
  the GitHub-facing README/docs/LICENSE at repo root.
- **Removed the editable Output folder setting** — the output location is fixed at `/output`
  inside the container and controlled solely by the docker-compose bind mount.

### Fixed
- **`no such column: volume.pdf_path`** after upgrading a DB that already had the `volume` table.
  Added a lightweight additive migration (`db._ensure_columns`) that adds any model columns missing
  from existing tables after `create_all`, so schema upgrades no longer require wiping the database.

### Notes / decisions
- Stack: Python/FastAPI + Jinja2/HTMX, SQLite, in-process worker. EPUB (+ optional PDF) output to
  an Unraid file share. Curated adapters + (later) a generic fallback scraper.
- Deploy: Unraid Compose Manager stack at `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`;
  Claude edits source locally, user copies + Compose Up.
