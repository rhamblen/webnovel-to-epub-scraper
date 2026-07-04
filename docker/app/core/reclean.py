"""Re-run the standard-phrase cleanup (clean.py Layers 0+2) over a volume's chapters and
record what was found, without re-fetching from the source site.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..models import Book, Chapter, Volume
from .adapters import get_adapter_by_name
from .clean import apply_standard_cleanup


def _now():
    return datetime.now(timezone.utc)


def clean_volume(engine, volume_id: int, progress_cb=None) -> dict:
    """Re-derive `Chapter.clean_html` for a volume's chapter range using the standard-phrase
    cleanup pass, and persist an aggregate label->count report onto the Volume."""
    with Session(engine) as s:
        vol = s.get(Volume, volume_id)
        if vol is None:
            raise ValueError(f"Volume {volume_id} not found")
        book = s.get(Book, vol.book_id)
        adapter = get_adapter_by_name(book.source_site) if book and book.source_site else None
        site_terms = adapter.site_terms if adapter else ()

        chapters = s.exec(
            select(Chapter).where(
                Chapter.book_id == vol.book_id,
                Chapter.number >= vol.start_chapter, Chapter.number <= vol.end_chapter,
                Chapter.clean_html.is_not(None),
            ).order_by(Chapter.number)
        ).all()

        total_counts: Counter = Counter()
        for i, ch in enumerate(chapters, start=1):
            new_html, counts = apply_standard_cleanup(ch.clean_html, site_terms=site_terms)
            total_counts.update(counts)
            if new_html != ch.clean_html:
                ch.clean_html = new_html
                ch.content_hash = hashlib.sha1(new_html.encode("utf-8")).hexdigest()
                s.add(ch)
            if progress_cb is not None:
                try:
                    progress_cb(i)
                except Exception:
                    pass

        vol.clean_report = json.dumps(dict(total_counts))
        vol.clean_report_at = _now()
        s.add(vol)
        s.commit()
        return {
            "chapters": len(chapters), "counts": dict(total_counts),
            "total": sum(total_counts.values()),
        }
