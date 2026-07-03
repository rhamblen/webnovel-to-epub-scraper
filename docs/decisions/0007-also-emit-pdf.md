# 0007 — Also emit PDF alongside EPUB

- **Status:** Accepted
- **Date:** 2026-07-03
- **Amends:** [ADR 0002](0002-epub-output-and-delivery.md) (which set EPUB as the sole v1 format)

## Context

The user asked for a **PDF produced alongside the EPUB** in the output folder. EPUB remains
the best format for the Kindle Paperwhite (reflowable), but a PDF is useful for other
readers/devices and archival.

## Decision

- Build **both EPUB and PDF** per book by default, each toggleable in Settings
  (`format_epub`, `format_pdf`, both default on). Files share a basename:
  `<Novel> - Book NN[ - Title].epub` / `.pdf`.
- **PDF via `fpdf2`** (pure Python) — no system libraries added to the image, so the build
  stays simple and reliable in Docker. Chapter headings become PDF outline bookmarks.
- **Latin-1 limitation accepted.** fpdf2's built-in fonts are latin-1, so typographic
  punctuation is normalized to ASCII and any remaining non-latin-1 character is replaced.
  Fine for English web novels; non-latin scripts would need a bundled Unicode TTF (deferred).
- `Volume` gains a `pdf_path` column (additive).
- **Page size** is a setting (`pdf_page_size`, `A5` default / `A4`). A5 gives larger relative
  text for reading; A4 is standard document size.

## Consequences

- **+** Both formats delivered from the same assembled chapters; no browser/heavy deps.
- **+** Users who want PDF for another device/reader get it without a separate tool.
- **−** PDF is fixed-layout and reads poorly on a 6" Paperwhite — EPUB stays the recommended
  Kindle format; PDF is a convenience, not the primary target.
- **−** Non-latin text won't render in the PDF until a Unicode font is bundled. Revisit if a
  target novel needs it.
