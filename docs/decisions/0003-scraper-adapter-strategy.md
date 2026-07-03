# 0003 — Scraper strategy: curated adapters + generic fallback

- **Status:** Accepted
- **Date:** 2026-07-03

## Context

Web novels are spread across many host sites with wildly different HTML. Two failure modes to avoid: (a) supporting only hand-written sites → too rigid; (b) relying solely on generic extraction → unreliable per-site. The user chose "curated adapters + generic fallback."

## Decision

- **Curated per-site adapters** for a handful of popular, structurally-clean hosts. Each adapter is a thin module implementing `list_chapters(toc_url)`, `extract_chapter(url)`, and a `needs_render` flag — selectors + a little logic, nothing more.
- **Generic readability-style fallback** for any site without an adapter: heuristic TOC discovery + main-content extraction, best-effort, with a quality warning surfaced to the user.
- **Shared core** for fetching, cleaning, and normalization so both paths behave consistently and politely.
- **Playwright rendering** invoked only when an adapter (or the generic path) flags a site as JS-required.
- **Fixture-based self-tests** (saved HTML snapshots) guard curated adapters against site drift.

## Consequences

- **+** Reliability where it matters (curated) plus broad reach (generic) — the best of both.
- **+** Adding a site is cheap and low-risk; the pipeline never changes.
- **−** Two extraction code paths to maintain; mitigated by the shared cleaning/normalization core.
- **−** Curated adapters break when sites change their markup; mitigated by fixture self-tests and keeping adapters small.
- **−** Generic output quality varies; mitigated by explicit "uncertain quality" warnings and easy manual override of selectors.
