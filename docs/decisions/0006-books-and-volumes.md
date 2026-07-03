# 0006 — Multi-book output via Volume (chapter-range "books")

- **Status:** Accepted
- **Date:** 2026-07-03

## Context

Long web serials are frequently published as multiple books/volumes (e.g. Shadow Slave is
10+ books). The user wants to produce one EPUB per book by entering a **start chapter, end
chapter, and book number** — and to do this on the first pull, splitting chapter sets into
different books rather than one giant file.

## Decision

- Introduce a **`Volume`** table (labelled a "Book" in the UI) = a chapter range of a source
  novel: `book_id`, `number`, `title?`, `start_chapter`, `end_chapter`, `status`, `epub_path`.
  A whole-novel EPUB is simply a Volume spanning `1..N`.
- **Add the table, don't restructure.** `Volume` is a new table, so `SQLModel.create_all`
  adds it to the existing SQLite DB with no migration and no loss of already-downloaded
  chapters. The source novel stays the `Book` table (UI: "Novel"); `Chapter` is unchanged.
- **Range-limited download + per-book build.** Building a book downloads only its chapter
  range (idempotent), assembles the downloaded chapters, builds the EPUB, and writes it to
  the output share. Each book is independent and rebuildable.
- **Series metadata.** Each EPUB sets `calibre:series` = novel title and `series_index` =
  book number, so Calibre/Kavita group the books of a novel together.
- **File naming:** `<Novel> - Book NN[ - Title].epub` (sanitized).

## Consequences

- **+** Matches how long serials are read; avoids one unwieldy EPUB; lets the user pull just
  the ranges they want.
- **+** No migration pain and existing data preserved (additive schema change).
- **+** Series metadata makes the multi-book set tidy in downstream readers.
- **−** The user must know/enter the chapter boundaries for each book. Auto-detecting volume
  boundaries from chapter titles is deferred (fragile, site-specific) and can be layered on
  top of the manual model later.
- **−** Naming clash: the DB `Book` is the *novel* while the UI "Book" is a `Volume`. Mitigated
  by consistent UI wording ("Novel" vs "Book") and code comments.
