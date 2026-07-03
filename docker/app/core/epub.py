"""Build an EPUB from a set of chapters using EbookLib.

Produces a valid EPUB3 with metadata, an optional cover, a navigable TOC, and one XHTML
document per chapter. Calibre series metadata (`calibre:series` / `series_index`) is set
so multi-book novels group nicely in Calibre/Kavita.
"""
from __future__ import annotations

import html
import uuid
from dataclasses import dataclass

from ebooklib import epub


@dataclass
class ChapterDoc:
    number: int
    title: str
    html: str  # cleaned <p>...</p> body


def _xhtml(title: str, body_html: str) -> str:
    return f"<h2>{html.escape(title)}</h2>\n{body_html}"


def build_epub(
    dest_path: str,
    *,
    title: str,
    author: str,
    language: str,
    chapters: list[ChapterDoc],
    series_name: str | None = None,
    series_index: int | None = None,
    cover: tuple[str, bytes] | None = None,  # (filename, bytes)
) -> str:
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{uuid.uuid4()}")
    book.set_title(title)
    book.set_language(language or "en")
    book.add_author(author or "Unknown")

    if series_name:
        book.add_metadata("OPF", "meta", "", {"name": "calibre:series", "content": series_name})
        if series_index is not None:
            book.add_metadata(
                "OPF", "meta", "",
                {"name": "calibre:series_index", "content": str(series_index)},
            )

    has_cover = False
    if cover:
        fname, data = cover
        try:
            # create_page=True adds a cover XHTML page (id "cover"); the OPF also gets the
            # <meta name="cover"> pointer + EPUB3 cover-image property Kindle uses.
            book.set_cover(fname, data, create_page=True)
            has_cover = True
        except Exception:
            pass  # a bad cover shouldn't fail the whole build

    items: list[epub.EpubHtml] = []
    for ch in chapters:
        item = epub.EpubHtml(
            title=ch.title or f"Chapter {ch.number}",
            file_name=f"chap_{ch.number:05d}.xhtml",
            lang=language or "en",
        )
        item.content = _xhtml(ch.title or f"Chapter {ch.number}", ch.html or "<p></p>")
        book.add_item(item)
        items.append(item)

    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    # Put the cover page first in reading order so it opens on the cover, then nav, then chapters.
    book.spine = (["cover"] if has_cover else []) + ["nav", *items]

    epub.write_epub(dest_path, book)
    return dest_path
