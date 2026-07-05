# Phase 5 build log — Library & jobs (v0.6.0)

**Status:** ◐ code complete + verified locally; awaiting UR1 redeploy. The optional
scheduled "check for new chapters" poller is still ☐ pending — deliberately out of scope
for this pass (see Open decisions).
**Scope:** persistent job queue (the `Job` table wired up for real) + a redesigned Library
management page. Both were the two remaining gaps in Phase 5.

## What was built

```
models.py            Job: + volume_id (FK), phase, message; state gains "cancelling".
                      Chapter: + scrape_error (set on fetch failure, cleared on success).
core/progress.py      Rewritten Job-backed (was an in-memory dict): start()/update()/
                      finish() write real Job rows; get_for_volume() backs the existing
                      /volumes/{id}/progress route (unchanged response shape — novel.html's
                      poller needed no edits); active_job_id() is the new concurrency
                      guard (replaces the old in-memory `_building` set); request_cancel()
                      + is_cancelled() implement cooperative cancellation.
core/scrape.py        scrape_bodies(): + job_id param, checked via progress.is_cancelled()
                      once per chapter (loop breaks early, "cancelled" in the return dict);
                      sets/clears Chapter.scrape_error per attempt.
core/build.py         build_volume(): takes job_id instead of calling progress.start()
                      itself; handles the cancelled-early-exit case (Volume -> "partial"/
                      "new", Job -> "cancelled", EPUB/PDF build skipped).
routes/pages.py       _volume_rows() / _delete_book() helpers (shared by Novel detail,
                      Library, and the HTMX partial routes). New routes: POST
                      /jobs/{id}/cancel, GET /volumes/{id}/download/{epub|pdf}, POST
                      /library/bulk-rescan, /library/bulk-delete, POST /novels/{id}/delete.
                      build/edit/delete volume routes branch on the HX-Request header to
                      return the _volumes_list.html partial instead of a redirect. Rescan
                      now records a Job (still synchronous). library()/jobs() routes
                      gather the extra per-row data the redesigned templates need.
templates/_volume_row.html    Extracted from novel.html's per-volume block; now the one
templates/_volumes_list.html   implementation shared by Novel detail and Library.
templates/library.html   Redesign: cover thumbnails, status badges, client-side
                      search/sort, bulk-select + bulk toolbar, expandable per-book
                      volume section (HTMX inline actions).
templates/jobs.html    Redesign: target title, type, state, progress bar, expandable
                      message/error, Cancel (running builds) / Retry (errored builds)
                      buttons, conditional auto-refresh while any job is non-terminal.
templates/novel.html   Now includes the shared partials; real download links replace
                      the old inert path text.
main.py                lifespan(): startup sweep marks any Job still pending/running/
                      cancelling as errored ("Interrupted by restart") — a crash mid-build
                      no longer leaves a Job stuck "running" forever.
static/htmx.min.js     Was a placeholder stub since Phase 0 ("Replace this file with the
                      real minified HTMX build" — its own comment). Vendored htmx 2.0.10
                      for real; this is the first phase that actually needed it.
static/styles.css      + .badge.cancelling / .badge.cancelled.
```

## Design notes

- **Job is the single source of truth**, not a second system running alongside the old
  registry. `core/progress.py`'s public functions kept their names so call sites in
  `build.py`/`pages.py` mostly just swap `volume_id` for `job_id`.
- **Retry needed no new logic.** `scrape_bodies` already only re-fetches chapters missing
  `clean_html`, so re-running a build *is* "retry the failed/missing ones," idempotently
  (this was true before Phase 5 too). The only real gap was visibility — `Chapter.scrape_error`
  plus a "Retry N failed chapters" label solves that without touching the retry path itself.
- **Cancellation is cooperative and coarse**: checked once between chapters, so an
  in-flight fetch for the *current* chapter still completes. Acceptable — chapters are
  fetched one at a time with a polite per-request delay already, so the worst case is
  waiting out one more request.
- **Rescan stays synchronous.** It only re-fetches a novel's TOC/metadata page (not
  chapter bodies), so it's inherently fast; wrapping it in a `Job` for history didn't
  require making it async too.
- **HTMX partial swap**: build/edit/delete volume routes detect `HX-Request` and
  re-render `_volumes_list.html` for that book instead of redirecting, so Library's
  expandable section updates in place. Non-HTMX submits (e.g. JS disabled) still get the
  original full-redirect behavior — this only works as progressive enhancement because
  `htmx.min.js` had to become real first (see below).
- **Found and fixed in verification, not part of the original plan:** `static/htmx.min.js`
  turned out to be a 3-line placeholder comment, not an actual library — so nothing using
  `hx-*` attributes could ever have worked before this. Discovered when a build button's
  HTMX-driven submit fell back to a full page redirect instead of a partial swap; fixed by
  vendoring the real htmx 2.0.10 build from its official distribution.
- **Delete-a-whole-novel is new.** Only per-volume delete existed before; bulk-delete on
  the Library page needed a book-level delete, so `_delete_book` explicitly clears
  Chapters and Volumes before the Book row (no DB-level cascade is configured). Doesn't
  touch already-built EPUB/PDF files on the share, matching the existing volume-delete's
  behavior/copy.

## Verification (local, outside Docker)

- Existing test suite: `32 passed` (`tests/`, at the repo root since the post-Phase-5 hygiene pass), no regressions.
- Ran the app locally (uvicorn, outside Docker) against seeded data:
  - Library renders covers, status badges, and correct per-volume failed-chapter counts;
    client-side search (title/author substring) and column sort both confirmed working.
  - HTMX build/cancel round-trip confirmed via the browser: `POST /volumes/{id}/build`
    returns the partial (200, not a redirect) when HTMX-driven; the live progress bar
    picks up the newly-active job via the existing polling script.
  - Direct `POST /jobs/{id}/cancel` on a synthetic running Job flips it to `cancelling`,
    confirmed via `progress.is_cancelled()`.
  - Restarted the process mid-"cancelling" Job — startup sweep correctly flipped it to
    `error` / "Interrupted by restart".
  - `GET /volumes/{id}/download/{epub,pdf}` serves the file with correct filename/
    content-type; 404s correctly for a missing format, unknown volume, or bad format string.
  - Bulk-rescan and bulk-delete (incl. cascading Chapter/Volume/Book cleanup) confirmed
    against seeded data.
- Not exercised: a real multi-minute build against a live site (would need a real source
  URL, out of scope for a local smoke test) — the underlying per-chapter loop and
  cancellation check are unchanged in structure from the pre-Phase-5 idempotent design,
  just instrumented with `job_id`.
- **Escaped bug, caught on first real deploy:** `build.py` passed `done=` (the old
  in-memory dict's key) to `progress.update()`, which now sets fields directly on the
  `Job` row — whose column is `completed`. SQLModel raised
  `ValueError: "Job" object has no field "done"` on the first progress update, killing
  every real build at 0 chapters. The local smoke test *displayed* this failure
  ("Build failed: ValueError" on the Jobs page) but it was misattributed to the seeded
  fake URL being unfetchable — which raises the same exception *type*. Lesson recorded:
  when a verification shows an expected-looking error, read the message, not just the
  type. Fixed by using the column name at the three call sites; `tests/test_progress.py`
  now pins `update()` to the exact field sets `build.py` uses. A fake-adapter end-to-end
  build test (which would have caught this outright) is noted for the Phase 6 test suite.

## Remaining to close the phase

- Redeploy on UR1 (Compose Manager → Compose Up; no new runtime dependencies, only a
  vendored static JS file) and confirm a real build + cancel + retry from the browser.
- Scheduled "check for new chapters" poller — still ☐ pending, tracked separately.
