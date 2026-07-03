# 0002 — Output format EPUB; delivery via file share

- **Status:** Accepted
- **Date:** 2026-07-03

## Context

Target device is a Kindle Paperwhite. Modern Paperwhite firmware + the Send-to-Kindle service read **EPUB** natively, converting on ingest. The user has a file share on Unraid and runs Calibre + Kavita on UR1, and wants finished books to land somewhere those tools (or the device) can reach. The user selected "Save to file share" as the delivery method and EPUB as the output format.

## Decision

- **v1 output = EPUB only.** Proper metadata, cover, navigable TOC, one XHTML per chapter (EbookLib).
- **v1 delivery = write the EPUB to a configured output directory** (an Unraid share mapped to `/output`, e.g. `/mnt/user/books`). Success is defined as a valid EPUB on disk.
- **Downstream integrations are deferred and optional:** Calibre (`calibredb`), Kavita watch-folder, and Send-to-Kindle email are post-v1 "delivery plugins" that consume the same output — they are not in the critical path.

## Consequences

- **+** Simplest possible delivery contract; always works; no coupling to Calibre/Kavita availability.
- **+** EPUB is the least-friction format for a modern Paperwhite and is also what Calibre/Kavita ingest cleanly.
- **−** Older, EPUB-incompatible Kindles would need AZW3/MOBI. Deferred: Send-to-Kindle handles conversion for most users; in-container Calibre conversion can be added later (project-plan D4).
- **−** Getting the EPUB onto the device still needs a manual step (Send-to-Kindle, Calibre push, or USB) until a delivery plugin ships. Accepted for v1.
