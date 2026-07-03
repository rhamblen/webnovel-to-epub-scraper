# 0001 — Tech stack: Python + FastAPI, SQLite, in-process worker

- **Status:** Accepted
- **Date:** 2026-07-03

## Context

We need a browser-based, self-hostable tool that scrapes web novels and produces EPUBs, deployable as a single Docker container on Unraid. The two hard parts — web scraping (incl. JS-rendered sites) and EPUB generation — both have their strongest, most mature libraries in Python. The user expressed no language preference.

## Decision

- **Python 3.12 + FastAPI (Uvicorn)** for the app and API.
- **Jinja2 + HTMX** for the UI — server-rendered, no JS build step, enough for forms and live job progress.
- **httpx** (static) and **Playwright/headless Chromium** (JS-rendered) for fetching.
- **selectolax/BeautifulSoup** + **readability-lxml** for parsing/extraction.
- **EbookLib** for EPUB generation.
- **SQLite** (via SQLModel/SQLAlchemy) for all state.
- **In-process asyncio worker** with a SQLite-persisted job queue for background scraping — no Redis/RQ dependency at v1.
- Packaged as a **Docker image on GHCR** with an **Unraid Community Applications** template.

## Consequences

- **+** Best-in-class scraping + ebook libraries; single container, no external services; simple ops for a homelab.
- **+** HTMX keeps the frontend tiny and dependency-light.
- **−** Single-node, limited job parallelism. Acceptable at homelab scale; the job-queue interface is kept clean so RQ+Redis can be swapped in later if needed.
- **−** Bundling Playwright/Chromium enlarges the image and RAM footprint; mitigated by launching the browser only when an adapter requires rendering.
