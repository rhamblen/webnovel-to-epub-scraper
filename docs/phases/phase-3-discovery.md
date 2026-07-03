# Phase 3 build log — Discovery (v0.4.0)

**Status:** ◐ code complete + verified against the live site; awaiting UR1 redeploy.
**Scope:** freewebnovel-only search, with searchable sites as a configurable list setting.

## What was built

```
core/adapters/base.py       + SearchResult; Adapter.searchable flag + search() hook
core/adapters/freewebnovel.py  search(): POST /search (searchkey) -> parse rows
                              (title, novel URL, chapter count, cover best-effort)
core/adapters/__init__.py   + get_adapter_by_name(), searchable_names()
core/fetch.py               Fetcher.post() (refactored get/post over _request)
core/scrape.py              search_novels(engine, query): fan out over the enabled
                              sites, aggregate SearchResults (one site failing is skipped)
settings_store.py           + search_sites (multiselect, options = searchable adapters,
                              default "freewebnovel"); MULTISELECT_KEYS; get_search_sites()
routes/pages.py             /discover?q= runs search; settings_post handles multiselect
templates/discover.html     search box + results table (Import buttons) + add-by-URL
templates/settings.html     multiselect field rendering (checkbox list)
```

## Design notes

- **Sites-to-search is a list setting** (`search_sites`), rendered as a checkbox group whose
  options come from `adapters.searchable_names()`. When more searchable adapters are added they
  appear automatically. Stored as a comma-separated string.
- **Import reuses the existing flow.** A result's Import button POSTs its novel URL to `/novels`
  (the same import-by-URL path), so no new import logic — the freewebnovel adapter already
  normalizes `.vip` URLs.
- **Ranking/recommendation deferred.** With a single site there's nothing to rank; cross-site
  "best source" recommendation waits until Phase 4 adds more adapters.

## Verification (live site)

- `search_novels(query="scumbag")` → 19 results, each with title, chapter count, and a
  `freewebnovel.vip/freenovel/<slug>` URL.
- Server: `/discover?q=scumbag` renders the results table with Import buttons; Settings shows the
  `search_sites` checkbox list and saves; importing a result → 303 → `/novels/{id}` (book created).

## Remaining to close the phase

- Redeploy on UR1 (Compose Up; no new dependencies) and confirm search → import → build from the
  browser.
