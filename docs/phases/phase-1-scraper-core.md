# Phase 1 build log — Scraper core (v0.2.0)

**Status:** ◐ code complete + verified against the live site; awaiting UR1 redeploy confirmation.

## What was built

The fetch → extract → persist loop, plus the first curated adapter and a minimal browser
trigger.

```
app/core/
  fetch.py                 async Fetcher: per-host rate limit, concurrency semaphore,
                           retries+backoff, robots.txt check, configurable User-Agent
  clean.py                 clean_chapter_html(): scripts/ads/watermarks out, <p> text kept
  adapters/
    base.py                Adapter ABC + NovelMeta / ChapterRef / ChapterContent / NovelResult
    freewebnovel.py        first curated adapter
    __init__.py            registry: get_adapter(url)
  scrape.py                import_novel() + scrape_bodies() (idempotent), reads settings
app/routes/pages.py        + /discover form, POST /novels (import), POST /novels/{id}/download
app/templates/             discover (add-by-URL) + library (counts + download button) updated
settings_store.py          + user_agent setting
requirements.txt           + httpx, beautifulsoup4
```

## freewebnovel adapter — site notes (confirmed 2026-07)

- **`freewebnovel.com` is behind a Cloudflare JS challenge** ("Just a moment…") — plain HTTP
  gets 403. The **`.vip` mirror serves the same catalogue as static HTML**, so the adapter
  normalizes any freewebnovel host to `https://freewebnovel.vip/freenovel/<slug>`.
- Path scheme differs by host: `.com` uses `/novel/<slug>`, `.vip` uses `/freenovel/<slug>`.
  The adapter extracts the slug from either and rebuilds the `.vip` URL.
- Selectors: title `h1.tit`; author `a[href^="/author/"]`; cover `.m-imgtxt img` (relative →
  prepend host); chapter body `#article` (`<p>`); **chapter title `span.chapter`** (note:
  `h1.tit` on a chapter page is the *book* title, not the chapter).
- The novel page's chapter list is **paginated** (~40 shown), so chapters are enumerated
  `1..N` where N is the highest `/chapter-<N>` link on the page.

## Verification (live site, polite: 1s delay, ≤6 chapter fetches total)

- Import: `book#1` title `The Scumbag's Guide To Heroism`, author `JudeTraore`, cover
  resolved to `.vip`, **213 chapters** listed in order.
- Bodies: chapter 1 → `Chapter 1 | The Scumbag System Doesn't Care About Your Hangover`,
  ~9k chars of clean `<p>` markup, UTF-8 smart quotes preserved.
- **Idempotency:** re-running `scrape_bodies` fetched only chapters still missing bodies
  (remaining count decreased by the batch size each run; already-downloaded chapters skipped).
- Browser flow: `/discover` form → POST `/novels` (303) → Library shows `0/213` + a
  **Download chapters** button; an unsupported URL surfaces a clean error.

## Notes / decisions

- **Enumerate-by-number** chapter listing assumes contiguous `/chapter-N`. A fetch that 404s
  is counted as an error and skipped rather than aborting the run. Sites with non-contiguous
  numbering would need a real list walk — revisit per-adapter if it comes up.
- The download trigger is a **fire-and-forget asyncio task** with an in-memory active set —
  a deliberate stepping stone. Phase 5 replaces it with a persistent job queue + live progress.
- Politeness (rate limit, robots, retries) lives in `fetch.py`, inherited by every adapter
  (ADR 0004). `robots.txt` for freewebnovel allows all (`Disallow:` empty).

## Remaining to close the phase

- Redeploy on UR1 (Compose Manager rebuild — dependencies changed) and confirm import +
  download work from the browser against the live site.
