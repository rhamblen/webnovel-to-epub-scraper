# Architecture — Webnovel Scraper

## Design principles

1. **Pipeline, not monolith.** Five clean stages — Discover → Scrape → Assemble → Convert → Deliver — each with a narrow interface. A stage can be tested and replaced in isolation.
2. **Adapters are cheap and data-like.** Supporting a new site is a small extractor module (selectors + a couple of functions), never a change to the pipeline. Curated adapters give reliability; a generic fallback gives reach. ([ADR 0003](decisions/0003-scraper-adapter-strategy.md))
3. **No mandatory external services.** SQLite for all state; an in-process asyncio worker for jobs. The whole thing is one container you can `docker run`. Redis/RQ is an *option* if you ever outgrow it, not a requirement.
4. **Resumable and idempotent.** Chapters are persisted as they're fetched. Re-running a book fetches only what's missing. A crash mid-scrape loses nothing already stored.
5. **Polite by default.** Rate limiting, concurrency caps, backoff, and `robots.txt` checks live in the fetch layer so every adapter inherits them. ([ADR 0004](decisions/0004-legal-and-ethical-use.md))
6. **The file share is the contract.** Success = a valid EPUB on disk at the configured path. Downstream tools (Calibre/Kavita) consume that; they are not in the critical path.

## Component map

```
FastAPI app
├── web/            Jinja2 + HTMX pages: Discover, Library, Jobs, Settings
├── api/            JSON + HTMX-fragment endpoints
├── core/
│   ├── discovery/  title search + source ranking/recommendation
│   ├── fetch/      httpx client, Playwright renderer, rate limit, robots, retries
│   ├── adapters/   base interface + curated site modules + generic fallback
│   ├── assemble/   ordering, de-dupe, HTML normalize/clean
│   ├── epub/       EbookLib builder (metadata, cover, TOC, spine)
│   └── deliver/    atomic write to output share (future: calibre/kavita/email)
├── jobs/           async worker, job queue, progress + persistence
├── db/             SQLModel models + migrations (settings, book, chapter, job)
└── main.py         Uvicorn entrypoint, DI wiring, config load
```

## Data model (initial)

- **setting** — key/value config (output path, delays, concurrency, defaults).
- **book** — id, title, author, source_site, toc_url, language, cover, status, created/updated.
- **chapter** — id, book_id, index, title, source_url, raw_html, clean_html, fetched_at, hash.
- **job** — id, book_id, type (build/update/scrape), state, progress, log, error, timestamps.

## Key flows

**Build a book**
1. UI submits `{title, author, source_site, toc_url}` → creates `book` + a `build` job.
2. Worker: adapter `list_chapters(toc_url)` → upsert `chapter` rows (missing only).
3. For each missing chapter: fetch (static or Playwright) → clean → store; update job progress.
4. Assemble ordered clean chapters → EbookLib EPUB → atomic write to output path.
5. Job → done; Library row shows EPUB location + counts.

**Incremental update** — same as above but `list_chapters` diffed against stored chapters; only new indices fetched, then EPUB rebuilt.

## Fetch strategy

- **Static first.** Try httpx; parse with selectolax/BeautifulSoup. Fast and cheap.
- **Render when needed.** Adapters (or the generic path) flag JS-required sites → Playwright headless Chromium renders, then the same extraction runs on the DOM.
- **Guardrails everywhere.** Global + per-host concurrency, min delay between requests, exponential backoff on 429/5xx, capped retries, honest User-Agent, `robots.txt` respected.

## Deployment (Unraid — Compose Manager)

See [ADR 0005](decisions/0005-unraid-deploy-workflow.md) for the division of labour.

- **Compose Manager stack.** Deployed via the Unraid **Compose Manager** plugin, not a Community Applications template (single container, but this keeps the workflow consistent with the user's other stacks).
- **Source location.** The deployable unit is the repo's self-contained **`docker/`** folder (Dockerfile, compose, `requirements.txt`, `app/`). Its contents are copied by the user to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`; deployed via **Compose Manager → Compose Up**. Build context = `docker/`.
- **Base image** includes Chromium for Playwright. Compose pins an explicit `image:` tag and a named network so image tags/network are stable regardless of the invoking project name (the folder-name-as-project-name footgun).
- **Volumes:** `/config` (SQLite + settings + cache) and `/output` (mapped to your books share, e.g. `/mnt/user/books`).
- **Port:** one HTTP port (default 8080) for the UI.
- **Build workflow:** Claude edits the Docker source locally; the user copies to appdata and runs Compose Up. Never raw `docker compose` CLI from the appdata folder.

## Trade-offs consciously accepted

| Choice | Upside | Downside | Mitigation |
|--------|--------|----------|------------|
| SQLite + in-process worker | Zero extra services, dead-simple ops | Single-node, limited parallelism | Fine for homelab scale; queue interface leaves room for RQ later |
| Jinja2 + HTMX (no SPA) | No JS build, tiny, fast to ship | Less rich interactivity | Enough for forms + live progress; revisit only if UX demands it |
| Curated + generic adapters | Reliable where it matters, broad reach elsewhere | Two code paths to maintain | Shared extraction/cleaning core; fixture self-tests catch drift |
| Playwright bundled | Handles JS sites | Bigger image, more RAM | Only launched when an adapter needs it |
| EPUB only (v1) | Simplest, native on modern Paperwhite | Older Kindles want AZW3/MOBI | Send-to-Kindle converts EPUB; AZW3 is a deferred option |
