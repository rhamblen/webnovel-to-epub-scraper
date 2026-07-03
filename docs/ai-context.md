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
| Legal/ethical | Personal use only; respect robots.txt + rate limits; no paywalled/auth'd sources | [0004](decisions/0004-legal-and-ethical-use.md) |

## Environment / target host

- Deploys to **Unraid** (user has UR1 and UR2; Calibre + Kavita run on UR1).
- Volumes: `/config` (state) and `/output` (books share, e.g. `/mnt/user/books`). HTTP port default 8080.
- **Deploy = Unraid Compose Manager plugin.** Sources copied by the *user* to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`, then **Compose Up**. See [ADR 0005](decisions/0005-unraid-deploy-workflow.md).
- **Build division of labour:** Claude edits Docker source **locally only**; the user copies to appdata + deploys. Never emit raw `docker compose` CLI for the appdata folder (project-name footgun → wrong tags/network). End deploy-affecting changes with a **▶ YOUR TURN** block.
- User is on Windows 11; shell is PowerShell (Bash tool also available). Repo not yet `git init`'d.

## Pipeline (the mental model)

`Discover → Scrape → Assemble → Convert → Deliver`, coordinated by a background job with SQLite-persisted progress. Chapters persist as fetched → scraping is resumable + idempotent; incremental update fetches only new chapters then rebuilds the EPUB.

## Core interfaces (target)

- Adapter: `list_chapters(toc_url) -> [ChapterRef]`, `extract_chapter(url) -> ChapterContent`, plus a `needs_render` flag.
- Fetch layer owns rate limiting / robots / retries so adapters stay thin.
- EPUB builder: EbookLib — metadata, cover, navigable TOC, one XHTML per chapter.

## Gotchas / watch-list

- **Site drift** breaks curated adapters — keep saved-HTML fixtures + a self-test harness (Phase 4).
- **Playwright** inflates image size and RAM; launch it only when an adapter sets `needs_render`.
- **Filename safety** on the share — sanitize `Author - Title.epub`, write atomically (temp + rename).
- **EPUB validity** — target epubcheck-clean structure so Send-to-Kindle/Calibre don't choke.
- **Politeness is a feature** — never remove/loosen rate limits to "go faster"; it's a design constraint, not a bug.

## Build-phase status

See the status tables in [README](../README.md#versions) and [project-plan](project-plan.md#status). All phases currently ☐ not started — this repo is at the planning stage (docs only, no code yet).

## First code steps (when the user says go)

1. `git init`; scaffold the FastAPI app + Dockerfile + Compose-Manager-safe compose (Phase 0).
2. SQLite models + Settings page (persist output path).
3. Fetch layer + first curated adapter (Phase 1).
4. Assembler + EbookLib EPUB + share writer → first end-to-end build (Phase 2).

After any deploy-affecting edit, hand off with a **▶ YOUR TURN** block: copy `webnovel-to-epub-scraper-docker/` to `/mnt/user/appdata/`, then Compose Manager → Compose Up; wait for "built/confirmed" before verifying.
