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
- **Incremental updates** — re-run an existing book to fetch only newly-published chapters ("Rescan").
- **Manage a library** — the Library page shows every novel with cover, status badge, and chapter counts; search/sort, bulk rescan/delete, and inline Build/Clean/Delete/Download without leaving the page.
- **A real job queue** — builds and rescans run as background **jobs** with live progress; cancel a running build, retry one that failed (only the missing chapters), and clear finished jobs from the log. A concurrency cap keeps many queued builds from hammering a source site all at once.
- **Automatic backups** — the library database is backed up daily (configurable) to your output share, with one-click restore — so a bad deploy or a stray file-sync can't lose your collection.
- **Browser UI** — Discover, Library, Jobs, and Settings pages. No CLI needed.
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
| v0.6.0  | ☑ released | **Phase 5 complete.** Persistent job queue (cancel, retry-failed, survives restarts) with a build concurrency cap; redesigned Library page (covers, status badges, search/sort, bulk rescan/delete, inline actions); EPUB/PDF download; daily database backup + restore |
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
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Discover │ → │ Scrape   │ → │ Assemble │ → │ Convert  │ → │ Deliver  │
│ find +   │   │ adapter/ │   │ clean +  │   │ EPUB/PDF │   │ write to │
│ rank     │   │ generic  │   │ order    │   │ + TOC    │   │ share    │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
      │              │              │              │              │
      └──── persistent jobs + SQLite state (survive restarts) ────┘
```

Each build or rescan runs as a background **job** and the UI polls live progress. Jobs are
queued (at most *N* run at once, set in Settings) and recorded in the `Job` table, so
history and any queued backlog **survive a restart** — nothing is lost if the container
bounces mid-build. Everything else — settings, the library, chapter cache — persists in
SQLite under `/config`, which is itself **backed up daily** to the output share.

## The four pages

| Page | What it's for |
|------|---------------|
| **Discover** | Search for a novel by title (across the sites enabled in Settings) or paste a table-of-contents URL directly. One click imports it. |
| **Library** | Every imported novel: cover, author, chapter counts, and a status badge. Search/sort the list, select rows for bulk rescan/delete, or expand a novel to Build / Clean / Delete / Download its books inline. |
| **Jobs** | Live and past build/rescan/backup jobs with progress bars. Cancel a running build, retry a failed one, dismiss individual entries, or clear all finished jobs. |
| **Settings** | See below. |

## Settings

The **Settings** page is the single place to tune scraping behaviour, output formats, and
backups — no config files to edit. All values persist in SQLite and take effect
immediately (the container's `/output` and `/config` volume *locations* are the only things
fixed by Docker, not set here).

| Section | Setting | What it does |
|---------|---------|--------------|
| **Scraping** | Max concurrent requests | How many chapters download at once within a build. Keep low (2–4) to stay polite to the source. |
| | Delay between requests | Minimum pause between requests to the same site. |
| | Builds running at once | How many build jobs run in parallel; the rest queue. Prevents many builds from hammering a site simultaneously. |
| | Custom User-Agent | Optional override; blank uses a browser-like default. |
| **Output** | Build EPUB / Build PDF | Which formats each book produces (EPUB recommended for Kindle). |
| | PDF page size | A5 (larger text, better for reading) or A4. |
| | Embed book cover | Download the source cover and embed it in the EPUB. |
| **Discovery** | Sites to search | Which site adapters the Discover search queries. |
| **Backups** | Daily database backup | Toggle the automatic daily backup of the library database. |
| | Backup time (HH:MM) | Container-local time for the daily run (default 01:00). |
| | Backups to keep | Retention count; older backups are pruned after each run. |

The Backups section also has a **Back up now** button and a list of existing backups, each
with **Restore** (replaces the current library with that snapshot — safely, saving a
pre-restore copy first) and **Download**. Backups are written to `/output/.app-backups`
(the media share), deliberately *not* alongside the database, so an appdata mishap can't
take them too.

## Documentation

- [Project plan](docs/project-plan.md) — phased roadmap, deliverables, exit criteria
- [Architecture](docs/architecture.md) — design principles and trade-offs
- [AI context](docs/ai-context.md) — cold-start map for the next AI session
- [Decisions](docs/decisions/) — ADRs for the load-bearing choices

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
