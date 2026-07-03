# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Phases map loosely to minor versions (Phase 0 → v0.1.0).

## [Unreleased]

### Added
- Initial project documentation: README, phased project plan, architecture notes, AI cold-start context, and ADRs 0001–0005 (tech stack, EPUB/file-share delivery, adapter strategy, legal/ethical use, Unraid Compose Manager deploy workflow).
- MIT license and `.gitignore`.

### Notes
- Planning stage only — no application code yet. All phases are ☐ not started.
- Direction locked: Python/FastAPI + Jinja2/HTMX, SQLite, in-process worker; EPUB output written to an Unraid file share; curated adapters + generic fallback scraper.
- Deploy workflow locked: Unraid Compose Manager stack at `/mnt/user/appdata/webnovel-to-epub-scraper-docker/`; Claude edits source locally, user copies + Compose Up (manual copy).
