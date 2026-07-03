# Project Plan — Webnovel Scraper

A self-hosted web app that finds a web novel, scrapes its chapters, assembles them into a
single clean **EPUB**, and writes it to an Unraid file share for reading on a Kindle Paperwhite.

## Status

| Phase | Version | Status | One-line |
|-------|---------|--------|----------|
| 0 — Skeleton        | v0.1.0 | ☑ | Container + web UI shell + settings + SQLite |
| 1 — Scraper core    | v0.2.0 | ☑ | Fetch layer + first curated adapter (freewebnovel) |
| 2 — EPUB + books    | v0.3.0 | ☑ | Build EPUB + PDF per "book" (chapter range) + write to share |
| 3 — Discovery       | v0.4.0 | ☑ | Search by title across a configurable site list (freewebnovel first) |
| 4 — Coverage        | v0.5.0 | ☐ | Generic fallback + JS sites + more adapters |
| 5 — Library & jobs  | v0.6.0 | ☐ | Library mgmt, live progress, incremental updates |
| 6 — Hardening       | v1.0.0 | ☐ | Tests, Unraid CA template, docs, error handling |

Legend: ☐ not started · ◐ in progress · ☑ done

---

## Guiding constraints

- **One container, homelab-simple.** No external services required to run (no mandatory Redis/Postgres). SQLite + an in-process async worker is the baseline.
- **Deploy workflow (see [ADR 0005](decisions/0005-unraid-deploy-workflow.md)).** Claude edits the Docker source (Dockerfile, `docker-compose.yml`, app code) **locally only**. The user copies the stack to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/` and deploys via **Compose Manager → Compose Up**. Never raw `docker compose` CLI (folder-name project footgun). Every change that needs deploying ends with an explicit **▶ YOUR TURN** block.
- **Personal use, polite scraping.** Rate limits, `robots.txt` awareness, and concurrency caps are first-class settings, not afterthoughts. See [ADR 0004](decisions/0004-legal-and-ethical-use.md).
- **File share is the delivery contract.** The tool's job ends when a valid EPUB lands in the configured output directory. Calibre/Kavita/Send-to-Kindle are *optional* downstream consumers (a later phase), not dependencies.
- **Adapters are data, not forks.** Adding a site should mean adding one small extractor module + CSS selectors, never touching the core pipeline. See [ADR 0003](decisions/0003-scraper-adapter-strategy.md).

---

## Chosen stack (see [ADR 0001](decisions/0001-tech-stack.md))

| Concern | Choice |
|---------|--------|
| Language / API | Python 3.12 + FastAPI (Uvicorn) |
| Web UI | Server-rendered Jinja2 + HTMX (lightweight, no build step) |
| Static fetch | httpx (async) |
| JS-rendered fetch | Playwright (headless Chromium) |
| HTML parsing | selectolax / BeautifulSoup; readability-lxml for generic fallback |
| EPUB generation | EbookLib |
| State / library / jobs | SQLite (via SQLModel/SQLAlchemy) |
| Background work | In-process asyncio worker + SQLite-persisted job queue |
| Packaging | Docker Compose stack, deployed via the Unraid **Compose Manager** plugin (sources copied to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`) |

---

## Phase 0 — Skeleton · v0.1.0

- **Objective:** a runnable, installable container that serves an empty-but-real web UI and persists settings.
- **What we build:**
  - FastAPI app, Uvicorn entrypoint, health endpoint.
  - Jinja2 + HTMX layout with nav: **Discover · Library · Jobs · Settings** (stubs).
  - SQLite schema + migrations for `settings`, `book`, `chapter`, `job`.
  - Settings page that reads/writes: concurrency, per-request delay, defaults, cover style,
    output formats (the output *location* is fixed at `/output` and mapped by compose, not a setting).
  - Dockerfile (Playwright-capable base), `docker-compose.yml` with explicit `image:` pin + named network (Compose-Manager-safe), `/config` + `/output` volumes.
- **Prerequisites:** none (greenfield).
- **Deliverables:** image builds and runs; Settings persist across restart; `/healthz` green.
- **Why:** get the deployment + persistence + config surface right before any scraping logic, so every later phase has a home.
- **Exit criteria:** `docker run` → open UI → change output path → restart → value survives.

## Phase 1 — Scraper core · v0.2.0

- **Objective:** reliably pull an ordered list of chapters and clean chapter bodies from **one** real site.
- **What we build:**
  - Fetch layer: async httpx client with rate limiting, retries/backoff, configurable UA, `robots.txt` check.
  - Adapter interface: `list_chapters(toc_url) -> [ChapterRef]` and `extract_chapter(url) -> ChapterContent`.
  - First curated adapter for a popular, well-structured host.
  - Chapter store: raw + cleaned HTML persisted per book in SQLite (so scraping is resumable and idempotent).
- **Prerequisites:** Phase 0.
- **Deliverables:** given a novel's TOC URL, the app enumerates chapters and stores cleaned bodies.
- **Why:** the fetch+extract+persist loop is the technical heart; proving it on one site de-risks everything downstream.
- **Exit criteria:** point at a TOC URL → all chapters listed in order → bodies stored, re-run fetches nothing new.

## Phase 2 — EPUB + books · v0.3.0

- **Objective:** first true end-to-end run — URL in, one or more EPUBs on the share.
- **What we build:**
  - **"Books" (volumes):** a novel can be split into user-defined books, each a chapter
    range (`start`, `end`) with a book number + optional title. A whole novel is just one
    book spanning 1..N. Handles multi-book series (e.g. Shadow Slave Book 1–10). See
    [ADR 0006](decisions/0006-books-and-volumes.md).
  - EPUB builder (EbookLib): metadata (title, author, language), `calibre:series` metadata so
    books group in Calibre/Kavita, navigable TOC, one XHTML per chapter.
  - **Cover art (☑ done):** download the cover image from the source novel page and embed it
    in the EPUB (`_fetch_cover` → EbookLib `set_cover`). Skipped only if the source has no cover
    or `cover_style = none`. *Gap:* no generated placeholder yet when a source lacks a cover
    (see open decision D7).
  - Optional **PDF** per book (fpdf2, pure-Python) written alongside the EPUB; toggle
    `format_epub` / `format_pdf` in Settings. See [ADR 0007](decisions/0007-also-emit-pdf.md).
  - Range-limited download so each book fetches only its own chapters (idempotent).
  - Delivery writer: atomically write `<Novel> - Book NN[ - Title].epub` to the configured
    output path (`/output` → `/mnt/user/media/reading/webnovels`); safe filename handling.
  - Novel detail page: define books, build/rebuild each, see status + output filename.
- **Prerequisites:** Phases 0–1.
- **Deliverables:** a validated EPUB (correct structure, cover, series metadata) per book,
  readable on a Kindle Paperwhite.
- **Why:** delivers the core user value; multi-book support matches how long web serials are
  actually published and read.
- **Exit criteria:** define a book by range → build → EPUB appears on the share → sideloads
  and reads correctly on-device.

## Phase 3 — Discovery · v0.4.0

- **Objective:** find a novel by title from within the app instead of hunting for URLs.
- **Scope (this iteration):** search the **freewebnovel** site only, with the searchable sites
  configured as a **list in Settings** (`search_sites`) so more can be added later.
- **What we build:**
  - `Adapter.search(query)` capability (+ `searchable` flag); freewebnovel implements it via its
    POST `/search` endpoint, returning title / chapter count / novel URL.
  - `search_sites` multi-select setting (auto-populated from adapters that are searchable).
  - Discover page: a search box → results table with one-click **Import** (reuses the existing
    import-by-URL flow) → Novel detail, where books are defined and built.
- **Deferred to a later phase (needs >1 site):** cross-site source **ranking/recommendation**
  (best source by completeness/recency) and richer metadata (author/cover/synopsis in results).
- **Prerequisites:** Phases 0–2.
- **Deliverables:** type a title → see results → one click imports the novel ready to build.
- **Why:** removes the need to hand-paste source URLs — a core requested feature.
- **Exit criteria:** search a known title → import a result → build a book from it.

## Phase 4 — Coverage · v0.5.0

- **Objective:** work on sites without a hand-written adapter, including JS-heavy ones.
- **What we build:**
  - Generic fallback extractor (readability-style) for TOC and chapter bodies with heuristics.
  - Playwright rendering path for sites that need a real browser; auto-selected per adapter/site.
  - 2–3 more curated adapters for the most common hosts.
  - Adapter self-test harness (fixtures of saved HTML) to catch site drift.
- **Prerequisites:** Phases 0–3.
- **Deliverables:** "just paste a URL" works on most sites, best-effort, with clear warnings when quality is uncertain.
- **Why:** maximizes the set of readable novels without unbounded per-site maintenance.
- **Exit criteria:** an un-adapted static site and a JS-rendered site both produce usable EPUBs.

## Phase 5 — Library & jobs · v0.6.0

- **Objective:** manage a growing collection and keep books current.
- **What we build:**
  - Library page: covers, status, chapter counts, last-updated; re-build / delete / open-in-share.
  - Live job UI: per-chapter progress, logs, cancel, retry-failed-chapters.
  - Incremental update: re-scrape only new chapters and append/rebuild the EPUB.
  - Optional scheduled "check for new chapters" (cron-style) per book.
- **Prerequisites:** Phases 0–4.
- **Deliverables:** a real library you maintain over time, not just one-shot builds.
- **Why:** web novels are ongoing; updating without a full re-scrape is the day-2 value.
- **Exit criteria:** add a book, later run "update", only new chapters fetched, EPUB refreshed.

## Phase 6 — Hardening · v1.0.0

- **Objective:** production-quality for a homelab: reliable, documented, easy to install.
- **What we build:**
  - Test suite (unit for adapters/assembler, integration on saved fixtures), CI on GitHub Actions.
  - Robust error handling + user-facing messages; structured logging.
  - Finalised `docker-compose.yml` + a documented Compose Manager install (copy to appdata → Compose Up); optionally an image published to GHCR so the compose file just pulls a tag.
  - Complete INSTALLATION.md, updated README, ai-context refresh.
- **Prerequisites:** Phases 0–5.
- **Deliverables:** v1.0.0 release, deployable via Compose Manager with a documented, repeatable procedure.
- **Why:** turns a working prototype into something you can rely on and redeploy cleanly.
- **Exit criteria:** copy stack to appdata → Compose Up → working build with no manual fixes.

---

## Open decisions

| # | Decision | Notes |
|---|----------|-------|
| D1 | Which sites get the first curated adapters? | Pick by what you actually read + structural cleanliness. Needed before Phase 1 code. |
| D2 | Discovery metadata source | e.g. a novel index/aggregator for search + source ranking. Legality/ToS to confirm — Phase 3. |
| D3 | Optional delivery integrations | Calibre `calibredb`, Kavita watch-folder, or Send-to-Kindle email — deferred past v1.0 unless wanted sooner. File share is the v1 contract. |
| D4 | AZW3/MOBI output | Only if Send-to-Kindle isn't your workflow; needs Calibre in-container. Deferred. |
| D5 | Auth'd/paywalled sources | Out of scope by policy — see [ADR 0004](decisions/0004-legal-and-ethical-use.md). |
| D7 | Placeholder cover | When a source has no cover image, should we generate a simple title/author placeholder cover? Currently the EPUB just has no cover in that case. `cover_style=simple` is a stub for this. |
| D6 | Product name | GitHub repo is [`rhamblen/webnovel-to-epub-scraper`](https://github.com/rhamblen/webnovel-to-epub-scraper); a friendlier display name (e.g. "PaperNovel") can still be adopted before first release. |

## Future / nice-to-have (post-1.0)

- Delivery plugins: Calibre-Web, Kavita, Send-to-Kindle email.
- AZW3/MOBI + PDF export.
- Per-book cover art fetching and custom styling/themes.
- Multi-user / basic auth in front of the UI.
- OPDS feed served directly from the app.
