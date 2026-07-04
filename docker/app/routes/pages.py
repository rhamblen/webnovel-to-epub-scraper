"""HTML pages: Discover, Library, Novel detail, Jobs, Settings.

Phase 2 adds the Novel detail page: define "books" (volumes) by chapter range and build
each into an EPUB written to the output share. Builds run as fire-and-forget asyncio
tasks for now — Phase 5 replaces them with a persistent job queue + live progress.
"""
import asyncio
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import settings_store
from ..core import build, progress, scrape
from ..core.adapters import cover_url_allowed, get_adapter
from ..core.fetch import DEFAULT_UA
from ..db import get_engine
from ..models import Book, Chapter, Job, Volume

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

# Volume ids currently building (in-memory; superseded by the Phase 5 job system).
_building: set[int] = set()

_img_client: httpx.AsyncClient | None = None


def _image_client() -> httpx.AsyncClient:
    global _img_client
    if _img_client is None:
        _img_client = httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_UA}, timeout=15, follow_redirects=True
        )
    return _img_client


@router.get("/cover")
async def cover_proxy(src: str = ""):
    """Proxy a cover image so the browser doesn't hotlink the source (and to dodge
    referer/hotlink checks). Restricted to hosts a curated adapter recognizes (novel
    hosts + declared cover CDNs), so this is not an open proxy."""
    if not src or not cover_url_allowed(src):
        return Response(status_code=404)
    try:
        r = await _image_client().get(src)
        if r.status_code != 200:
            return Response(status_code=404)
        # Some cover CDNs (e.g. book-pic.webnovel.com) label images octet-stream.
        media_type = r.headers.get("content-type", "")
        if not media_type.startswith("image/"):
            media_type = "image/jpeg"
        return Response(
            content=r.content,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception:
        return Response(status_code=404)


def _counts(s: Session, book_id: int, start: int | None = None, end: int | None = None):
    conds = [Chapter.book_id == book_id]
    if start is not None:
        conds.append(Chapter.number >= start)
    if end is not None:
        conds.append(Chapter.number <= end)
    listed = s.exec(select(Chapter).where(*conds)).all()
    done = sum(1 for c in listed if c.clean_html)
    return len(listed), done


@router.get("/")
def index():
    return RedirectResponse(url="/library", status_code=303)


@router.get("/discover")
async def discover(request: Request, q: str = "", error: str | None = None):
    results = []
    searched = bool(q.strip())
    if searched:
        try:
            results = await scrape.search_novels(get_engine(), q.strip())
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    return templates.TemplateResponse(
        request, "discover.html",
        {"active": "discover", "q": q, "results": results, "searched": searched, "error": error},
    )


@router.post("/novels")
async def add_novel(request: Request):
    form = await request.form()
    url = str(form.get("url", "")).strip()
    if not url:
        return RedirectResponse(url="/discover", status_code=303)
    try:
        book_id = await scrape.import_novel(get_engine(), url)
    except Exception as e:
        return templates.TemplateResponse(
            request, "discover.html",
            {"active": "discover", "error": f"{type(e).__name__}: {e}", "url": url},
        )
    return RedirectResponse(url=f"/novels/{book_id}", status_code=303)


@router.get("/library")
def library(request: Request):
    rows = []
    with Session(get_engine()) as s:
        books = s.exec(select(Book).order_by(Book.updated_at.desc())).all()
        for b in books:
            total, done = _counts(s, b.id)
            n_vols = len(s.exec(select(Volume).where(Volume.book_id == b.id)).all())
            rows.append({"book": b, "total": total, "done": done, "volumes": n_vols})
    return templates.TemplateResponse(request, "library.html", {"active": "library", "rows": rows})


@router.get("/novels/{book_id}")
def novel_detail(request: Request, book_id: int, error: str | None = None, msg: str | None = None):
    with Session(get_engine()) as s:
        book = s.get(Book, book_id)
        if book is None:
            return RedirectResponse(url="/library", status_code=303)
        total, done = _counts(s, book_id)
        max_ch = max((c.number for c in s.exec(select(Chapter).where(Chapter.book_id == book_id)).all()), default=0)
        volumes = s.exec(select(Volume).where(Volume.book_id == book_id).order_by(Volume.number)).all()
        vols = []
        prev_end = 0  # expected start of the first book is chapter 1
        for v in volumes:
            v_total, v_done = _counts(s, book_id, v.start_chapter, v.end_chapter)
            expected = prev_end + 1
            report = json.loads(v.clean_report) if v.clean_report else {}
            vols.append({
                "v": v, "total": v_total, "done": v_done, "building": v.id in _building,
                "seq_ok": v.start_chapter == expected, "expected_start": expected,
                "clean_report": report, "clean_total": sum(report.values()),
            })
            prev_end = v.end_chapter
        # Defaults for the "add a book" form: next book number, and start = one past the
        # furthest chapter any existing book covers (so books stay sequential).
        next_number = max((v.number for v in volumes), default=0) + 1
        next_start = min(max((v.end_chapter for v in volumes), default=0) + 1, max_ch) if max_ch else 1
    return templates.TemplateResponse(
        request, "novel.html",
        {"active": "library", "book": book, "total": total, "done": done,
         "max_ch": max_ch, "vols": vols, "error": error, "msg": msg,
         "next_number": next_number, "next_start": next_start},
    )


@router.post("/novels/{book_id}/rescan")
async def rescan_novel(book_id: int):
    """Re-read the source novel page and add any newly-published chapters (idempotent)."""
    with Session(get_engine()) as s:
        book = s.get(Book, book_id)
        if book is None:
            return RedirectResponse(url="/library", status_code=303)
        toc_url = book.toc_url
        before = len(s.exec(select(Chapter.id).where(Chapter.book_id == book_id)).all())
    try:
        await scrape.import_novel(get_engine(), toc_url)
    except Exception as e:
        return RedirectResponse(
            url=f"/novels/{book_id}?error={quote(f'Rescan failed: {type(e).__name__}: {e}')}",
            status_code=303,
        )
    with Session(get_engine()) as s:
        after = len(s.exec(select(Chapter.id).where(Chapter.book_id == book_id)).all())
    delta = after - before
    msg = (
        f"Rescan complete — {delta} new chapter(s) found ({after} total). "
        "Extend a book's end (or add a new book) to include them."
        if delta else f"Rescan complete — no new chapters ({after} total)."
    )
    return RedirectResponse(url=f"/novels/{book_id}?msg={quote(msg)}", status_code=303)


def _parse_volume_fields(form) -> tuple[int, str, int, int]:
    number = int(str(form.get("number", "")).strip())
    start = int(str(form.get("start", "")).strip())
    end = int(str(form.get("end", "")).strip())
    title = str(form.get("title", "")).strip()
    if number < 1 or start < 1 or end < start:
        raise ValueError("number >= 1, start >= 1, and end >= start")
    return number, title, start, end


@router.post("/novels/{book_id}/volumes")
async def add_volume(request: Request, book_id: int):
    form = await request.form()
    try:
        number, title, start, end = _parse_volume_fields(form)
    except (ValueError, TypeError) as e:
        return RedirectResponse(url=f"/novels/{book_id}?error=Invalid+book:+{e}", status_code=303)
    with Session(get_engine()) as s:
        s.add(Volume(book_id=book_id, number=number, title=title, start_chapter=start, end_chapter=end))
        s.commit()
    return RedirectResponse(url=f"/novels/{book_id}", status_code=303)


@router.post("/volumes/{volume_id}/edit")
async def edit_volume(request: Request, volume_id: int):
    form = await request.form()
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        if vol is None:
            return RedirectResponse(url="/library", status_code=303)
        book_id = vol.book_id
        try:
            number, title, start, end = _parse_volume_fields(form)
        except (ValueError, TypeError) as e:
            return RedirectResponse(url=f"/novels/{book_id}?error=Invalid+book:+{e}", status_code=303)
        vol.number, vol.title, vol.start_chapter, vol.end_chapter = number, title, start, end
        s.add(vol)
        s.commit()
    return RedirectResponse(url=f"/novels/{book_id}", status_code=303)


@router.post("/volumes/{volume_id}/delete")
async def delete_volume(volume_id: int):
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        book_id = vol.book_id if vol else None
        if vol is not None:
            s.delete(vol)
            s.commit()
    return RedirectResponse(url=f"/novels/{book_id}" if book_id else "/library", status_code=303)


@router.post("/volumes/{volume_id}/build")
async def build_volume_route(request: Request, volume_id: int):
    form = await request.form()
    do_clean = form.get("clean") is not None
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        book_id = vol.book_id if vol else None
    if book_id is not None and volume_id not in _building:
        _building.add(volume_id)
        progress.start(volume_id, message="Starting…")

        async def _run():
            try:
                await build.build_volume(get_engine(), volume_id, do_clean=do_clean)
            except Exception as e:
                progress.finish(volume_id, "error", f"Build failed: {type(e).__name__}")
                with Session(get_engine()) as s:
                    v = s.get(Volume, volume_id)
                    if v is not None:
                        v.status = "error"
                        v.note = f"Build failed: {type(e).__name__}: {e}"[:300]
                        s.add(v)
                        s.commit()
            finally:
                _building.discard(volume_id)

        asyncio.create_task(_run())
    return RedirectResponse(url=f"/novels/{book_id}", status_code=303)


@router.get("/volumes/{volume_id}/progress")
def volume_progress(volume_id: int):
    st = progress.get(volume_id)
    st["building"] = volume_id in _building
    return st


@router.get("/jobs")
def jobs(request: Request):
    with Session(get_engine()) as s:
        job_list = s.exec(select(Job).order_by(Job.created_at.desc())).all()
    return templates.TemplateResponse(request, "jobs.html", {"active": "jobs", "jobs": job_list})


@router.get("/settings")
def settings_get(request: Request, saved: bool = False):
    with Session(get_engine()) as s:
        values = settings_store.get_all(s)
    return templates.TemplateResponse(
        request, "settings.html",
        {"active": "settings", "fields": settings_store.FIELDS, "values": values, "saved": saved},
    )


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    updates: dict[str, str] = {}
    for field in settings_store.FIELDS:
        key = field["key"]
        if key in settings_store.CHECKBOX_KEYS:
            updates[key] = "true" if form.get(key) is not None else "false"
        elif key in settings_store.MULTISELECT_KEYS:
            updates[key] = ",".join(form.getlist(key))
        else:
            updates[key] = str(form.get(key, "")).strip()
    with Session(get_engine()) as s:
        settings_store.set_many(s, updates)
    return RedirectResponse(url="/settings?saved=true", status_code=303)
