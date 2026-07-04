# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Phases map loosely to minor versions (Phase 0 → v0.1.0).

## [Unreleased]

_Nothing yet._

## [0.5.0] — 2026-07-04

Completes Phase 4 (Coverage) — see `docs/project-plan.md`.

### Added
- **Playwright rendering for JS-heavy sites.** `core/render.py` — a `Renderer` wrapping
  headless Chromium, launched lazily on first use and reused for the rest of the scrape
  (spinning up a fresh browser per page would be far too slow for a multi-hundred-chapter
  book). `Fetcher.get_rendered(url)` (`core/fetch.py`) exposes it alongside the existing
  `get`/`post`, sharing the same robots.txt check, per-host pacing, concurrency cap, and
  retry-with-backoff.
- **Generic adapter now auto-detects JS-only pages** (`core/adapters/generic.py`) instead
  of needing a site-specific flag set in advance: chapter bodies are fetched statically
  first, and only re-fetched through `get_rendered` if the visible text is suspiciously
  short (an unrendered `<div id="root">`-style shell). TOC/novel pages use a slightly
  different check — chapter links are extracted from the static HTML *first*, and
  rendering is only retried if that comes up empty *and* the page looks shell-like, since
  a real TOC page is often link-dense but prose-*sparse* and would otherwise be misread
  as unrendered. Curated adapters continue to use the static `needs_render` flag instead,
  for sites already known upfront to require a browser.
- Verified against a real headless Chromium run (not just the fake-Renderer unit tests in
  `tests/test_render.py`): a local JS-only test page whose content is injected by a
  `<script>` tag was correctly detected as unrendered, rendered, and its content extracted
  end-to-end through `GenericAdapter.fetch_chapter`.

### Changed
- **Docker base image** switched from `python:3.12-slim` to
  `mcr.microsoft.com/playwright/python:v1.61.0-noble` — pre-installed Python 3.12,
  headless Chromium, and its OS-level dependencies, version-matched to the `playwright`
  Python package (now pinned exactly in `requirements.txt`, not a range, since the pip
  package and the base image's pre-installed browser binaries must stay in lockstep).
  No separate `playwright install` build step needed. Meaningfully larger image (browsers
  add well over 1GB) — the tradeoff Phase 4 always anticipated (see ADR 0001) — but the
  browser process itself is still only launched lazily, on the first page that actually
  needs it.

## [0.4.6] — 2026-07-04

### Added
- **Generic fallback adapter (Phase 4).** `core/adapters/generic.py` — imports from sites
  with no curated adapter, heuristically rather than via hand-written selectors (ADR 0003):
  - **TOC discovery:** groups every link on the page by parent element and takes the
    largest cluster that looks chapter-shaped (text/href like "Chapter 12" / "Ch. 12" /
    a bare number) or is just very large, since some sites title chapters with no
    "chapter" marker at all. Numbered in DOM order — a caveat surfaced via `Book.note`
    for sites that list newest-first.
  - **Chapter body:** `readability-lxml`'s `Document.summary()` (new prod dependency,
    per [ADR 0001](docs/decisions/0001-tech-stack.md)) picks the highest text-density
    block on the page, same as curated adapters' bodies feed through `clean_chapter_html`.
  - Always matches any absolute http(s) URL and is appended last in the adapter registry,
    so `get_adapter()` — and therefore "paste a URL and import" — now always finds
    something instead of raising "No adapter supports this URL yet" for un-adapted sites.
  - Not searchable (no way to search an arbitrary site by title) — Discover's search-sites
    list is unaffected.

### Fixed
- **`/cover` proxy allowlist hole.** `cover_url_allowed()` used to treat "some adapter's
  `matches()` returned true" as sufficient to let the `/cover?src=` route fetch a URL.
  Adding the generic fallback (which matches *any* host) would have silently turned that
  into an open image proxy for arbitrary URLs. Fixed by adding `Adapter.is_fallback`
  (true only for `GenericAdapter`) and excluding fallback adapters from this check —
  covers for generically-imported novels still embed correctly in the built EPUB (that
  path fetches `Book.cover_path` directly, server-side, never through `/cover`), they
  just won't show a thumbnail in the web UI. Covered by new `tests/test_registry.py`.

## [0.4.5] — 2026-07-04

### Added
- **Adapter self-test harness (Phase 4).** `docker/tests/` — pytest + a `FixtureFetcher`
  test double (`tests/support.py`) that serves saved HTML instead of hitting the network,
  so curated-adapter parsing can be regression-tested offline and instantly. Each adapter
  (freewebnovel/libread, royalroad, webnovel.com) gets hand-built fixtures
  (`tests/fixtures/<adapter>/{novel,chapter,search}.html`) mirroring its documented,
  live-verified selectors, plus:
  - A shared parametrized contract (`test_adapter_contract.py`): `matches()` accepts its
    own URLs and rejects others, `fetch_novel` parses title/author/cover/chapter-count,
    `fetch_chapter` returns a non-empty body, `search` returns the expected result.
  - Per-adapter quirk regressions: libread URLs normalize to the freewebnovel slug/host;
    Royal Road's injected anti-theft paragraphs (hidden via inline `<style>`) are stripped;
    webnovel.com refuses to scrape a chapter the source currently marks locked even if an
    earlier book-page scan said it was free (the ADR 0004 paywall boundary).
  - Test-only deps live in new `docker/requirements-dev.txt` (pytest, pytest-asyncio) —
    not installed in the production image (`Dockerfile` still only installs
    `requirements.txt`). Run via `cd docker && pip install -r requirements-dev.txt && pytest`.
  - These fixtures are frozen snapshots, not live checks — they catch *our* parsing
    regressions immediately; a real site markup change still needs a manual fixture
    refresh (save the new page HTML, rerun, fix whatever selector the failure points at).

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
