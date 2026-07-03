"""Build a Volume ("book") into an EPUB and deliver it to the output folder.

Flow: mark building -> download the volume's chapter range (idempotent) -> assemble the
downloaded chapters -> build the EPUB -> write it atomically to the configured output
directory (the Unraid share) -> record the path + status on the Volume.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from .. import settings_store
from ..models import Book, Chapter, Volume
from . import scrape
from .epub import ChapterDoc, build_epub

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _now():
    return datetime.now(timezone.utc)


def safe_filename(name: str) -> str:
    name = _ILLEGAL.sub("", name).strip().rstrip(".")
    name = re.sub(r"\s+", " ", name)
    return name or "untitled"


async def _fetch_cover(s: Session, url: str | None):
    if not url:
        return None
    fetcher = scrape._fetcher_from_settings(s)
    try:
        r = await fetcher.get(url)
        ct = r.headers.get("content-type", "")
        ext = ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
        return (f"cover{ext}", r.content)
    except Exception:
        return None
    finally:
        await fetcher.aclose()


async def build_volume(engine, volume_id: int) -> dict:
    with Session(engine) as s:
        vol = s.get(Volume, volume_id)
        if vol is None:
            raise ValueError(f"Volume {volume_id} not found")
        vol.status = "building"
        vol.updated_at = _now()
        s.add(vol)
        s.commit()
        book_id, start, end = vol.book_id, vol.start_chapter, vol.end_chapter

    # Download only this volume's range (idempotent — skips already-fetched chapters).
    await scrape.scrape_bodies(engine, book_id, start=start, end=end)

    with Session(engine) as s:
        vol = s.get(Volume, volume_id)
        book = s.get(Book, book_id)
        in_range = s.exec(
            select(Chapter)
            .where(Chapter.book_id == book_id, Chapter.number >= start, Chapter.number <= end)
            .order_by(Chapter.number)
        ).all()
        downloaded = [c for c in in_range if c.clean_html]

        if not downloaded:
            vol.status = "error"
            vol.note = "No downloaded chapters in range"
            vol.updated_at = _now()
            s.add(vol)
            s.commit()
            return {"status": "error", "note": vol.note}

        cfg = settings_store.get_all(s)
        output_dir = cfg.get("output_dir") or "/output"
        cover = None
        if cfg.get("cover_style", "simple") != "none":
            cover = await _fetch_cover(s, book.cover_path)

        vtitle = f"{book.title} - Book {vol.number:02d}"
        if vol.title:
            vtitle += f" - {vol.title}"

        docs = [ChapterDoc(number=c.number, title=c.title, html=c.clean_html) for c in downloaded]
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        final = os.path.join(output_dir, safe_filename(vtitle) + ".epub")
        tmp = final + ".part"
        build_epub(
            tmp,
            title=vtitle,
            author=book.author,
            language=book.language,
            chapters=docs,
            series_name=book.title,
            series_index=vol.number,
            cover=cover,
        )
        os.replace(tmp, final)

        vol.epub_path = final
        vol.status = "ready" if len(downloaded) == len(in_range) else "partial"
        vol.note = f"{len(downloaded)}/{len(in_range)} chapters in range"
        vol.updated_at = _now()
        s.add(vol)
        s.commit()
        return {"status": vol.status, "epub": final, "chapters": len(downloaded), "of": len(in_range)}
