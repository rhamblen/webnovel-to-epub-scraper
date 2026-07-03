# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Phases map loosely to minor versions (Phase 0 → v0.1.0).

## [Unreleased]

### Added
- Initial project documentation: README, phased project plan, architecture notes, AI cold-start context, and ADRs 0001–0005 (tech stack, EPUB/file-share delivery, adapter strategy, legal/ethical use, Unraid Compose Manager deploy workflow).
- MIT license and `.gitignore`.
- **Phase 2 EPUB + books (v0.3.0, code complete):** a novel can be split into user-defined **"books"** (the `Volume` table — a chapter range with a book number + optional title; whole-novel = one book spanning 1..N). `app/core/epub.py` builds an EbookLib EPUB3 (metadata, source cover, navigable TOC, one XHTML/chapter, `calibre:series` grouping); `app/core/build.py` downloads a book's range, assembles it, and writes `<Novel> - Book NN[ - Title].epub` atomically to the output share (`/output` → `/mnt/user/media/books/webnovels`). New Novel detail page to define books and build/rebuild each. An optional **PDF** is produced alongside the EPUB (`app/core/pdf.py`, fpdf2; toggle `format_epub`/`format_pdf` and choose page size `pdf_page_size` A5/A4 in Settings) — see [ADR 0007](docs/decisions/0007-also-emit-pdf.md). Verified locally by building and validating a real EPUB + PDF. See [ADR 0006](docs/decisions/0006-books-and-volumes.md) and [docs/phases/phase-2-epub.md](docs/phases/phase-2-epub.md).
- **Phase 1 scraper core (v0.2.0, code complete):** polite async fetch layer (`app/core/fetch.py` — per-host rate limit, concurrency, retries/backoff, robots.txt, configurable User-Agent), adapter interface + registry, first curated adapter for **freewebnovel** (auto-routes the Cloudflare-walled `.com` to the `.vip` mirror; extracts title/author/cover and enumerates all chapters; cleans chapter bodies to `<p>` XHTML), idempotent `import_novel`/`scrape_bodies` orchestration, and a browser flow (Discover "add by URL" → Library with download button + progress counts). Verified against the live site (213-chapter novel). See [docs/phases/phase-1-scraper-core.md](docs/phases/phase-1-scraper-core.md).
- **Phase 0 app skeleton (v0.1.0, code complete):** FastAPI app with Jinja2/HTMX UI shell (Discover · Library · Jobs · Settings), SQLite models (`Setting`, `Book`, `Chapter`, `Job`), a working Settings page persisting output folder + politeness/defaults, `/healthz` probe, `Dockerfile`, Compose-Manager-safe `docker-compose.yml`, and `requirements.txt`. Locally verified: boots, serves all pages, and settings survive a restart. See [docs/phases/phase-0-skeleton.md](docs/phases/phase-0-skeleton.md).

### Changed
- Removed the editable **Output folder** setting. The output location is now fixed at
  `/output` inside the container and controlled solely by the docker-compose bind mount —
  simpler and avoids setting it to a host path that doesn't exist inside the container.

### Notes
- Planning stage only — no application code yet. All phases are ☐ not started.
- Direction locked: Python/FastAPI + Jinja2/HTMX, SQLite, in-process worker; EPUB output written to an Unraid file share; curated adapters + generic fallback scraper.
- Deploy workflow locked: Unraid Compose Manager stack at `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`; Claude edits source locally, user copies + Compose Up (manual copy).
