"""Scrape orchestration: URL -> Book + ordered Chapters (bodies persisted).

Idempotent by design: importing a novel again only adds missing chapters, and scraping
bodies only fetches chapters that don't yet have cleaned content. A crash mid-scrape
loses nothing already stored.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlmodel import Session, select

from .. import settings_store
from ..models import Book, Chapter
from .adapters import get_adapter
from .fetch import DEFAULT_UA, Fetcher


def _now():
    return datetime.now(timezone.utc)


def _fetcher_from_settings(s: Session) -> Fetcher:
    cfg = settings_store.get_all(s)
    return Fetcher(
        user_agent=cfg.get("user_agent") or DEFAULT_UA,
        delay=float(cfg.get("request_delay_seconds", "1.0") or 1.0),
        concurrency=int(cfg.get("concurrency", "2") or 2),
    )


async def import_novel(engine, url: str) -> int:
    """Fetch novel metadata + chapter list; create/refresh the Book and chapter stubs."""
    adapter = get_adapter(url)
    if adapter is None:
        raise ValueError(f"No adapter supports this URL yet: {url}")

    with Session(engine) as s:
        fetcher = _fetcher_from_settings(s)
        try:
            result = await adapter.fetch_novel(fetcher, url)
        finally:
            await fetcher.aclose()

        meta = result.meta
        book = s.exec(select(Book).where(Book.toc_url == meta.source_url)).first()
        if book is None:
            book = Book(title=meta.title, toc_url=meta.source_url)
        book.title = meta.title
        book.author = meta.author
        book.source_site = adapter.name
        book.cover_path = meta.cover_url
        book.language = meta.language
        book.status = "scraping"
        book.updated_at = _now()
        s.add(book)
        s.commit()
        s.refresh(book)

        existing = {c.number for c in s.exec(select(Chapter).where(Chapter.book_id == book.id)).all()}
        for ref in result.chapters:
            if ref.number not in existing:
                s.add(Chapter(book_id=book.id, number=ref.number, title=ref.title, source_url=ref.url))
        s.commit()
        return book.id


async def scrape_bodies(engine, book_id: int, limit: int | None = None) -> dict:
    """Fetch cleaned bodies for chapters that don't have them yet. Returns a summary."""
    from .adapters.base import ChapterRef

    with Session(engine) as s:
        book = s.get(Book, book_id)
        if book is None:
            raise ValueError(f"Book {book_id} not found")
        adapter = get_adapter(book.toc_url)
        if adapter is None:
            raise ValueError(f"No adapter for {book.toc_url}")

        pending = s.exec(
            select(Chapter)
            .where(Chapter.book_id == book_id, Chapter.clean_html.is_(None))
            .order_by(Chapter.number)
        ).all()
        if limit is not None:
            pending = pending[:limit]

        strip_notes = settings_store.get_all(s).get("strip_translator_notes") == "true"
        fetcher = _fetcher_from_settings(s)
        fetched = errors = 0
        try:
            for ch in pending:
                try:
                    content = await adapter.fetch_chapter(
                        fetcher, ChapterRef(number=ch.number, url=ch.source_url, title=ch.title)
                    )
                    ch.title = content.title or ch.title
                    ch.clean_html = content.html
                    ch.content_hash = hashlib.sha1((content.html or "").encode("utf-8")).hexdigest()
                    ch.fetched_at = _now()
                    s.add(ch)
                    s.commit()
                    fetched += 1
                except Exception:
                    errors += 1
        finally:
            await fetcher.aclose()

        remaining = s.exec(
            select(Chapter).where(Chapter.book_id == book_id, Chapter.clean_html.is_(None))
        ).all()
        book.status = "ready" if not remaining else "scraping"
        book.updated_at = _now()
        s.add(book)
        s.commit()
        return {"fetched": fetched, "errors": errors, "remaining": len(remaining)}
