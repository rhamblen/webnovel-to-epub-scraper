# Webnovel Scraper

> **What + why:** a self-hosted web app that finds a web novel, scrapes its chapters, assembles them into a single clean ebook, and drops an **EPUB** onto your Unraid file share — ready to read on a Kindle Paperwhite. Built to run as one Docker container on Unraid.

This is a personal-use project, built for one reason: reading web novels on a Kindle Paperwhite. Reading them in a browser needs an internet connection for every chapter, and reading on an iPad instead trades that away for a battery that drains quickly and a screen that's unreadable in direct sunlight. E Ink has neither problem — so this tool's whole job is turning scraped chapters into a real EPUB that lands on the Paperwhite instead.

Point it at a novel, pick the recommended source site, click **Build**, and a finished EPUB appears in your library share. No manual chapter-copying, no browser extensions, no desktop conversion dance.

> ⚠️ **Personal-use tool.** Scrape only content you are permitted to read, obey each site's `robots.txt` and rate limits, and keep the output for your own device. See [ADR 0004](docs/decisions/0004-legal-and-ethical-use.md).

---

## Features

- **Identify a novel** — search by title and get back candidate sources with a **recommended site** to scrape from (ranked by reliability and completeness).
- **Scrape chapters** — curated per-site adapters for popular hosts, plus a generic reader-mode fallback for everything else; handles both static and JavaScript-rendered pages.
- **Assemble** — collate every chapter into one normalized master document, in order, de-duplicated and cleaned (optional stripping of translator notes / ads).
- **Split into books** — a long serial can be carved into multiple "books" by chapter range (start/end + book number), each built as its own EPUB with `calibre:series` metadata so they group in Calibre/Kavita. A whole novel is just one book spanning all chapters.
- **Convert to EPUB (+ optional PDF)** — proper metadata (title, author, series, cover), a navigable table of contents, one chapter per section. Native reading on modern Kindle Paperwhite via Send-to-Kindle. A matching PDF can be produced alongside each EPUB (toggleable in Settings).
- **Deliver to your library** — writes the EPUB straight to a configured Unraid share so Calibre/Kavita on UR1 can pick it up.
- **Incremental updates** — re-run an existing book to fetch only newly-published chapters.
- **Browser UI** — Discover, Library, Jobs (live progress), and Settings pages. No CLI needed.
- **Runs on Unraid** — single container, deployed via the Compose Manager plugin.

## Versions

| Version | Status | Features |
|---------|--------|----------|
| v0.1.0  | ☑ done | App skeleton: container, web UI shell, settings, SQLite, health check |
| v0.2.0  | ☑ done | Scraper core + first curated adapter (freewebnovel): import + download chapters |
| v0.3.0  | ☑ done | Build EPUB + PDF per "book" (chapter range) + write to share — end-to-end |
| v0.4.0  | ☑ released | Discovery: search by title (freewebnovel; searchable sites from a settings list). Multi-site + ranking later |
| v0.4.1  | ☑ released | Rescan for new chapters; EPUB opens on cover; default output → `media/reading/webnovels` |
| v0.4.2  | ☑ released | Live build progress; Settings page tidy-up; consistent book cards |
| v0.4.3  | ☑ released | libread.com support; Royal Road adapter; webnovel.com free-chapter adapter |
| v0.4.4  | ☑ released | Content cleaning (first cut): opt-in **Clean** button strips known junk phrases and site-name watermarks (incl. spacing/homoglyph obfuscation), with a per-book report of what was removed |
| v0.4.5  | ☑ released | Adapter self-test harness: pytest + saved-HTML fixtures per curated adapter, catches parsing regressions offline |
| v0.4.6  | ☑ released | Generic fallback adapter: heuristic TOC discovery + readability-lxml content extraction, so importing "just works" on sites with no dedicated adapter |
| v0.5.0  | ☑ released | Playwright rendering for JS-heavy sites, auto-detected by the generic adapter (no manual flag needed); Docker base image now bundles headless Chromium. Completes Phase 4 (Coverage) |
| v0.6.0  | ◐ in progress | Live build progress ✓ + incremental rescan ✓ (shipped in v0.4.1–v0.4.2); a persistent job queue and a real library-management page (covers, direct rebuild/delete) still pending |
| v1.0.0  | ☐ planned | Hardening, tests, Compose Manager install docs |

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Unraid (or any Docker host) | Runs the container |
| A file share for output | Where finished EPUBs land (e.g. `/mnt/user/books`) |
| ~1 GB RAM free | Headless Chromium for JS-rendered sites (launched only when actually needed) |
| ~3 GB disk for the image | The Playwright base image bundles Chromium, Firefox, and WebKit + their OS dependencies |
| (Optional) Calibre / Kavita on UR1 | Point them at the output share to manage/serve the books |

## Installation

Deployed on Unraid via the **Compose Manager** plugin (full steps land in INSTALLATION.md at first release). The entire deployable unit is the repo's **[`docker/`](docker/)** folder (Dockerfile, `docker-compose.yml`, `requirements.txt`, and `app/`). In short: copy the contents of `docker/` to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/` (or clone the repo and point Compose Manager at `docker/docker-compose.yml`), then **Compose Manager → Compose Up**. The `/config` volume holds state; the `/output` mount (mapped to `/mnt/user/media/reading/webnovels`) receives the finished files.

## How it works

```
  ┌─────────┐   ┌──────────┐   ┌───────────┐   ┌───────────┐   ┌──────────┐
  │ Discover │→ │ Scrape   │→ │ Assemble  │→ │ Convert   │→ │ Deliver  │
  │ (find +  │   │ (adapter │   │ (master   │   │ (EPUB +   │   │ (write   │
  │  rank)   │   │ or       │   │  document,│   │  metadata │   │  to      │
  │          │   │ generic) │   │  cleaned) │   │  + TOC)   │   │  share)  │
  └─────────┘   └──────────┘   └───────────┘   └───────────┘   └──────────┘
       │              │              │               │              │
       └──────────────┴──── job queue + SQLite state ┴──────────────┘
```

A background worker runs the long-running scrape as a **job**; the UI polls live progress. Everything (settings, library, job state) persists in SQLite under `/config`.

## Documentation

- [Project plan](docs/project-plan.md) — phased roadmap, deliverables, exit criteria
- [Architecture](docs/architecture.md) — design principles and trade-offs
- [AI context](docs/ai-context.md) — cold-start map for the next AI session
- [Decisions](docs/decisions/) — ADRs for the load-bearing choices

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
