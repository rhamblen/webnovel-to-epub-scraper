# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Phases map loosely to minor versions (Phase 0 → v0.1.0).

## [Unreleased]

_Nothing yet._

## [0.4.4] — 2026-07-04

### Added
- **Phase 7 (first cut) — standard-phrase cleanup + counts box.** A new **Clean** button next
  to each book's Build/Rebuild (`app/templates/novel.html`) runs a labeled, countable pass
  (`apply_standard_cleanup()` in `app/core/clean.py`, orchestrated per-volume by new
  `app/core/reclean.py`) over already-scraped chapters: catches known boilerplate
  (translator/editor credits, read-more/read-latest prompts) plus the book's own source-site
  name via new `Adapter.site_terms` on each adapter, tolerant of spacing/punctuation
  obfuscation (`f r e e w e b n o v e l`) **and per-letter Unicode homoglyph substitution**
  (`frёeωebɳovel.com`) — the latter added after a real book (*The Scumbag's Guide To
  Heroism* on freewebnovel.vip) turned out to actively rotate through Cyrillic/Greek/
  Latin-Extended-B/small-capital look-alike characters to dodge exact-substring matching.
  Results are tallied per label and shown in a report box next to the book on the Novel page
  (new `Volume.clean_report` / `clean_report_at` columns, additive migration); the button
  relabels to **Re-clean** once a report exists. Scoped to Phase 7's Layers 0+2 only —
  cross-chapter frequency dedup (Layer 1) and the local-AI layers stay explicit follow-ups
  (the homoglyph gap was considered for an AI-based fix but turned out to be a bounded,
  deterministic normalization problem instead); see
  `docs/phases/phase-7-content-cleaning.md` for the full breakdown. Verified live on
  *The Scumbag's Guide To Heroism* (freewebnovel.vip) — confirmed against 10 real obfuscated
  watermark variants, idempotent on re-run, no false positives on genuine accented prose.

## [0.4.3] — 2026-07-04

### Added
- **libread.com URLs now import.** libread turned out to be another frontend of the freewebnovel
  catalogue (its chapter links redirect to freewebnovel.com), so the freewebnovel adapter now
  matches `libread.*` hosts and normalizes `/libread/<slug>-<id>` paths (stripping the numeric
  catalogue id) to the `.vip` mirror. Verified live: import → 219 chapters → chapter body clean.
- **Royal Road adapter** (`app/core/adapters/royalroad.py`) — search (`/fictions/search?title=`),
  full unpaginated TOC from the fiction page's chapter table, chapter bodies from
  `.chapter-inner.chapter-content`, and stripping of Royal Road's injected anti-theft paragraphs
  (elements whose class an inline `<style>` declares `display:none`). Second entry in the
  Discover search-sites list. Verified live on *Mother of Learning* (109 chapters, 44K-char ch.1).
- **webnovel.com adapter** (`app/core/adapters/webnovel.py`) — imports and scrapes *only* the
  free chapter prefix a title has (webnovel.com serves early chapters to anyone, then paywalls
  later ones via an in-app purchase). Both the book page and each chapter page embed their data
  as an unescaped JS object literal, parsed and normalized to JSON rather than regex-scraped.
  Every chapter fetch re-checks the source's own `vipStatus`/`price` before scraping — a chapter
  is never touched once the source itself marks it locked. `Book.note` (new column) surfaces
  "Only N of M chapters are free…" on the Novel page; Discover search results show the same via
  `SearchResult.note`. Verified live: 25 of 269 chapters free, chapter 26 correctly refused.

### Fixed
- **Cover proxy allowlist:** `/cover` only allowed URLs a curated adapter `matches()`, which
  would 404 Royal Road covers (they live on `royalroadcdn.com`). Adapters now declare
  `cover_hosts` CDNs and the proxy checks `cover_url_allowed()`; non-image upstream
  content-types (webnovel's CDN says `octet-stream`) are corrected to `image/jpeg`.

### Notes
- **noveltrust.com investigated and shelved:** only its novel landing page is directly
  reachable — TOC pagination and every chapter URL 302 to `novellive.app`, which sits behind a
  Cloudflare JS challenge. Revisit when the Phase 4 Playwright rendering path exists.

## [0.4.2] — 2026-07-03

### Changed
- **Tidied the Settings page.** Options are now grouped into **Scraping / Output / Discovery** with
  clearer help text. Removed three redundant settings that weren't wired to anything
  (`default_language`, `default_author`, `strip_translator_notes` — the last returns with the
  Phase 7 content-cleaning work). Replaced the confusing `cover_style` (simple/none) select with a
  plain **Embed book cover** checkbox.
- **Consistent book cards on the Novel page.** Each output file (📗 EPUB, 📕 PDF) is now on its own
  line, and the Build/Delete buttons sit on their own line — no more inconsistent wrapping.

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
