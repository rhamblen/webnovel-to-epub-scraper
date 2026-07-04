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
| 4 — Coverage        | v0.5.0 | ☑ | royalroad + webnovel.com (free-prefix) + libread adapters (v0.4.3) + self-test harness (v0.4.5) + generic fallback (v0.4.6) + Playwright rendering (v0.5.0) — phase complete |
| 5 — Library & jobs  | v0.6.0 | ◐ | Live build progress ✓ (v0.4.2) + rescan ✓ (v0.4.1); persistent job queue + real library-management page still pending — `Job` table/`/jobs` page exist but are currently unwired |
| 6 — Hardening       | v1.0.0 | ☐ | Tests, Unraid CA template, docs, error handling |
| 7 — Content cleaning| v1.1.0 | ◐ | Layer 0+2 ✓ (shipped in v0.4.4: labeled, countable, dedicated Clean/Re-clean button) + fuzzy/homoglyph scrub; frequency dedup + local-Ollama AI step still pending |
| — v2.0 (future)     | v2.0.0 | ☐ | Whole pipeline orchestrated in **n8n** (import→scrape→clean→build), app becomes a stateless-ish service. See below. |

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
    or the **Embed book cover** setting is off. *Gap:* no generated placeholder yet when a source
    lacks a cover (see open decision D7).
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
  - Generic fallback extractor (readability-style) for TOC and chapter bodies with heuristics. (☑ done —
    `core/adapters/generic.py`. TOC: largest same-parent link cluster that looks
    chapter-shaped (or is just very large), numbered in DOM order. Body: `readability-lxml`'s
    `Document.summary()`. Always matches any http(s) URL and sits last in the registry, so
    `get_adapter()` never returns `None` for a well-formed URL. Not searchable. A `Book.note`
    surfaces the best-effort caveat, same mechanism webnovel.com's free-prefix note uses.
    Security note: since it matches *any* host, it's excluded from the `/cover` proxy
    allowlist via a new `Adapter.is_fallback` flag — see `cover_url_allowed` — otherwise
    that route would become an open image proxy.)
  - Playwright rendering path for sites that need a real browser; auto-selected per adapter/site. (☑ done —
    `core/render.py` (`Renderer`, lazy-launched headless Chromium, reused for the rest of
    the scrape) + `Fetcher.get_rendered()` (`core/fetch.py`), sharing the same robots.txt/
    pacing/concurrency/retry machinery as the static path. Curated adapters would opt in
    via the existing static `needs_render` flag (none need it yet — all three surveyed
    sites serve plain HTML); the generic adapter auto-detects per-page instead, since it
    can't know in advance: chapter bodies check raw visible-text length before extracting,
    TOC pages extract first and only render-retry if that comes up empty (link-dense TOC
    pages are naturally prose-sparse, so checking text length up front there would
    misfire — a real bug this design went through during testing, see `tests/test_generic.py`).
    Docker base image switched to `mcr.microsoft.com/playwright/python:v1.61.0-noble`
    (pre-installed matching browser binaries, no separate `playwright install` step).
    Verified against both fake-Renderer unit tests and one real local headless-Chromium
    run against a JS-only test page.)
  - 2–3 more curated adapters for the most common hosts. (☑ done — royalroad, webnovel.com, libread; see "Candidate sites surveyed" below)
  - Adapter self-test harness (fixtures of saved HTML) to catch site drift. (☑ done —
    pytest + a `FixtureFetcher` test double in `docker/tests/`; hand-built fixtures per
    curated adapter mirroring each one's documented live-verified selectors, a shared
    parametrized contract test, plus per-adapter quirk regressions — libread
    normalization, Royal Road anti-theft-paragraph stripping, webnovel.com's paywall
    boundary. Frozen snapshots: catches our own parsing regressions instantly, but a
    real site change still needs a manual fixture refresh.)
- **Prerequisites:** Phases 0–3.
- **Deliverables:** "just paste a URL" works on most sites, best-effort, with clear warnings when quality is uncertain.
- **Why:** maximizes the set of readable novels without unbounded per-site maintenance.
- **Exit criteria:** an un-adapted static site and a JS-rendered site both produce usable EPUBs.
- **Candidate sites surveyed (2026-07-04):**
  - **libread.com — ☑ done (pre-Phase-4).** Same catalogue as freewebnovel (chapter links
    redirect there); handled as URL normalization inside the existing adapter, not a new one.
  - **noveltrust.com — ✗ still shelved (Cloudflare).** Only the novel landing page is directly
    reachable; TOC pagination (`/book/<slug>/2`) and every chapter URL 302 to `novellive.app`,
    which is behind a Cloudflare JS *challenge* (bot-detection, not just JS-rendered content —
    a different, harder problem than what the new Playwright path solves; Cloudflare
    specifically tries to detect and block headless automation, so plain Playwright
    rendering likely still won't get past it without further work this project hasn't
    taken on). For the record: search = POST `/search/` (`searchkey`), selectors are
    freewebnovel-family (`h1.tit`, `.m-imgtxt`), chapter URLs embed title slugs, TOC
    paginated in 40s.
  - **royalroad.com — ☑ done.** Adapter with search + content (`royalroad.py`); full TOC on
    the fiction page (no pagination); strips injected hidden anti-theft paragraphs. Still
    possible later: a "browse rankings" discovery mode (`/fictions/best-rated`), per-fiction RSS.
  - **webnovel.com — ☑ done (free-prefix content adapter).** Turned out *not* to be uniformly
    paywalled: an author-controlled prefix of chapters (often dozens, sometimes zero) is served
    free to any visitor, with the rest gated behind an in-app purchase. `webnovel.py` imports and
    scrapes only that free prefix, parsing the book/chapter pages' own embedded JS state (an
    unescaped object literal, normalized to JSON) rather than regex-scraping HTML. Every chapter
    fetch re-checks the source's live `vipStatus`/`price` before scraping, so a chapter already
    marked locked upstream is never touched regardless of what an earlier scan said. `Book.note`
    / `SearchResult.note` surface "N of M chapters are free" so this is never silently partial.
    First concrete piece of the D2 source-ranking idea (true upstream chapter count vs mirrors).
  - All four blocked a datacenter-proxy fetch but served plain HTML to a browser UA — the
    Fetcher's UA matters, and the fixture self-test harness is what catches tightening.

## Phase 5 — Library & jobs · v0.6.0

- **Objective:** manage a growing collection and keep books current.
- **What we build:**
  - Library page: covers, status, chapter counts, last-updated; re-build / delete / open-in-share.
    (◐ partial — chapter/book counts ✓ (`library.html`); no covers, and rebuild/delete/
    open-in-share require drilling into the Novel detail page rather than acting from this
    page directly)
  - Live job UI: per-chapter progress, logs, cancel, retry-failed-chapters. (◐ partial — live
    per-volume progress bar ✓ (v0.4.2, `core/progress.py`); no logs/cancel/retry yet. The
    `Job` table + `/jobs` page already exist in the schema/routes but are currently dead code —
    nothing ever writes a `Job` row; build progress is tracked separately via the in-memory
    progress registry, not this table)
  - Incremental update: re-scrape only new chapters and append/rebuild the EPUB. (☑ done — v0.4.1 "Rescan")
  - Optional scheduled "check for new chapters" (cron-style) per book. (☐ pending)
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

## Phase 7 — Content cleaning · v1.1.0

- **Objective:** strip repeated ads/comment blocks and injected site-name watermarks (including
  mid-sentence, obfuscated forms) from chapter bodies, well beyond today's static substring
  blocklist in `core/clean.py`.
- **What we build (layered, cheap→expensive, short-circuit early):**
  - **Layer 0 — blocklist (☑ done, exists):** current `_JUNK_SUBSTRINGS` per-paragraph drop.
  - **Layer 1 — cross-chapter frequency dedup (☐ not started, no AI):** hash normalized
    paragraphs across a book; a paragraph appearing in a high fraction of chapters (esp.
    first/last 1–2) is boilerplate → drop. Near-dups via shingling / `difflib`. Runs as a
    post-scrape pass (whole book is already in SQLite).
  - **Layer 2 — fuzzy site-name scrub (☑ done, no AI):** regex removal of known site
    tokens/templates tolerant of spaced-out/punctuated obfuscation (`f r e e w e b n o v e l`)
    **and** per-letter Unicode homoglyph substitution (`frёeωebɳovel.com`, confirmed live on a
    real book) — a curated confusables table (`_CONFUSABLE_GROUPS` in `core/clean.py`) folds
    ~25 look-alike characters per letter, drawn from the Cyrillic/Greek/Latin-Extended-B/
    small-capital families actually seen in the wild. Removes *fragments*, not just whole
    paragraphs. Labeled + countable: each match is tagged (e.g. "Site name", "Translator
    credit") and tallied per volume, shown in a report box on the Novel page. Ships as an
    dedicated **Clean/Re-clean button** next to a volume's Build/Rebuild (see
    `docs/phases/phase-7-content-cleaning.md` for the trigger-design amendment), not the
    standalone "re-clean book" action originally sketched below.
  - **Layer 3 — local-Ollama AI step (UR1, GPU):** send the already-mostly-clean text to a small
    instruct model (`qwen2.5:7b` / `llama3.1:8b`) via **an n8n webhook** (`POST {text}` →
    `{junk_spans:[...]}`, JSON-schema constrained). n8n owns prompt/model/retries so tuning needs
    **no Docker rebuild**; the app owns the DB and never lets n8n write it.
  - **Layer 4 — verify-subset guardrail (no AI):** reject any AI output whose kept text isn't a
    verbatim subset of the source; fall back to Layers 0–2. Non-negotiable with a local 7B.
  - **Pattern promotion:** AI-found junk spans are stored per-book (`Book.boilerplate_patterns`)
    and re-applied deterministically to later chapters, so AI calls taper toward zero.
  - **Enablers:** populate the existing `Chapter.raw_html` column (re-clean without re-fetch);
    add `Book.boilerplate_patterns` (safe additive migration via `_ensure_columns`); Settings:
    `ollama_url`, `ollama_model`, `ai_clean_enabled`; a "re-clean book" action to reprocess
    existing books.
- **Prerequisites:** Phases 0–2 (works on stored bodies); independent of 4–6.
- **Why:** repeated ads and injected watermarks are the top readability annoyance in scraped
  serials; the deterministic layers alone (1–2) cut most of it at zero cost/latency, with the
  local LLM as a safe, auditable fallback for obfuscated cases.
- **Exit criteria:** on a real book, repeated end-of-chapter ad blocks and mid-text site names are
  gone; no story text lost (subset guardrail holds); re-clean is idempotent.

## v2.0 (future) — n8n pipeline orchestrator

- **Objective:** move the *whole* pipeline into an **n8n orchestrator** (bumblebee-bot style),
  with the app reduced to a stateless-ish service that owns the SQLite DB and exposes discrete,
  idempotent steps.
- **Design (already agreed):**
  - **n8n conducts; the app owns state.** The orchestrator sequences retryable HTTP calls; the
    app remains the *sole writer* to SQLite (single-writer store — n8n must never touch the file
    directly). This is the SQLite-safe form of the bumblebee orchestrator pattern.
  - **Flow:** `import → scrape (stores raw_html) → clean (Layers 0–2) → AI-clean (Ollama node
    + subset guardrail) → build (EPUB/PDF) → [notify]`, each an HTTP call to the app.
  - **Enabling gap:** the app is server-rendered (routes = `pages.py` + health) with no JSON API.
    v2.0 requires a thin **`/api`** surface wrapping the existing functions (`import_novel`,
    `scrape_bodies`, a new `clean_book`, `build`) — this is the orchestrator's control plane.
  - Fits the pipeline's existing idempotency (`core/scrape.py` re-import/re-scrape are no-ops on
    already-done work), so orchestrator retries are safe.
  - **Notifications:** deferred (not in first cut).
- **Prerequisites:** Phase 7 (the AI-clean step) plus the `/api` layer.
- **Status:** designed, bookmarked — build later.

---

## Open decisions

| # | Decision | Notes |
|---|----------|-------|
| D1 | Which sites get the first curated adapters? | Pick by what you actually read + structural cleanliness. Needed before Phase 1 code. |
| D2 | Discovery metadata source | e.g. a novel index/aggregator for search + source ranking. Legality/ToS to confirm — Phase 3. |
| D3 | Optional delivery integrations | Calibre `calibredb`, Kavita watch-folder, or Send-to-Kindle email — deferred past v1.0 unless wanted sooner. File share is the v1 contract. |
| D4 | AZW3/MOBI output | Only if Send-to-Kindle isn't your workflow; needs Calibre in-container. Deferred. |
| D5 | Auth'd/paywalled sources | Out of scope by policy — see [ADR 0004](decisions/0004-legal-and-ethical-use.md). |
| D7 | Placeholder cover | When a source has no cover image, should we generate a simple title/author placeholder cover? Currently the EPUB just has no cover in that case. (The old `cover_style=simple` stub was removed; the **Embed book cover** setting only toggles using the source cover.) |
| D6 | Product name | GitHub repo is [`rhamblen/webnovel-to-epub-scraper`](https://github.com/rhamblen/webnovel-to-epub-scraper); a friendlier display name (e.g. "PaperNovel") can still be adopted before first release. |

## Future / nice-to-have (post-1.0)

- Delivery plugins: Calibre-Web, Kavita, Send-to-Kindle email.
- AZW3/MOBI + PDF export.
- Per-book cover art fetching and custom styling/themes.
- Multi-user / basic auth in front of the UI.
- OPDS feed served directly from the app.
