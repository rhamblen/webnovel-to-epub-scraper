# Phase 2 build log — EPUB + books (v0.3.0)

**Status:** ◐ code complete + verified locally (real EPUB built); awaiting UR1 redeploy.

## What was built

Per-"book" (chapter range) EPUB generation and delivery to the output share, plus the
Novel detail UI to drive it.

```
app/models.py              + Volume table (book_id, number, title, start/end_chapter,
                             status, epub_path, note) — additive, no migration
app/core/epub.py           build_epub(): EbookLib EPUB3 — metadata, cover, nav TOC,
                             one XHTML/chapter, calibre:series + series_index
app/core/pdf.py            build_pdf(): fpdf2 (pure-Python) PDF, outline bookmarks,
                             latin-1 normalized (ADR 0007)
app/core/build.py          build_volume(): download range -> assemble -> build -> atomic
                             write to output_dir -> record epub_path + status; safe_filename()
app/core/scrape.py         scrape_bodies() gained start/end range params
app/routes/pages.py        /novels/{id} detail, POST /novels/{id}/volumes (add book),
                             POST /volumes/{id}/build; /library now lists novels -> Manage
app/templates/             novel.html (books table + add-book form), library.html simplified
docker-compose.yml         /output -> /mnt/user/media/books/webnovels
requirements.txt           + ebooklib, fpdf2
```

## Model note (see ADR 0006)

A "book"/volume is the `Volume` table = a chapter range of a novel. Added as a **new table**
so it drops into the existing DB via `create_all` — the 213 chapters already downloaded on
UR1 are preserved. Source novel stays the `Book` table (UI calls it "Novel"; UI "Book" = Volume).

## Verification (local)

- End-to-end: import novel → define Book 01 (ch 1–3, "Test Arc") → `build_volume` →
  `status=ready, 3/3 chapters`.
- EPUB validated by unzip: `mimetype` = `application/epub+zip`, cover embedded, three
  `chap_0000N.xhtml` files, OPF contains the title and `calibre:series`. File written as
  `The Scumbag's Guide To Heroism - Book 01 - Test Arc.epub` (~248 KB).
- PDF validated: `%PDF-` header, written as the matching `.pdf` next to the EPUB; both land
  in the output folder with the same basename.
- Web routes: `/library` lists the novel; `/novels/1` shows the book (ready) + filename +
  add-book form; adding Book 02 (ch 4–6) works; an invalid range (start 9 > end 2) is rejected.

## Delivery

- EPUBs are written atomically (`.part` → rename) to the `output_dir` setting, which defaults
  to `/output` (mapped to `/mnt/user/media/books/webnovels`). This is what was missing when
  "the build ran but no file appeared" — Phase 1 only populated the DB; Phase 2 produces the file.

## Remaining to close the phase

- Redeploy on UR1 (rebuild — `ebooklib` added, new `Volume` table). Confirm `/mnt/user/media/
  books/webnovels` exists, define a book, build, and check the EPUB lands on the share and
  reads on the Paperwhite.
