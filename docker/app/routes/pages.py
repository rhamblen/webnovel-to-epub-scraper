"""HTML pages: Discover, Library, Novel detail, Jobs, Settings.

Phase 2 adds the Novel detail page: define "books" (volumes) by chapter range and build
each into an EPUB written to the output share. Builds run as fire-and-forget asyncio
tasks for now — Phase 5 replaces them with a persistent job queue + live progress.
"""
import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import settings_store
from ..core import build, scrape
from ..db import get_engine
from ..models import Book, Chapter, Job, Volume

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

# Volume ids currently building (in-memory; superseded by the Phase 5 job system).
_building: set[int] = set()


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
def novel_detail(request: Request, book_id: int, error: str | None = None):
    with Session(get_engine()) as s:
        book = s.get(Book, book_id)
        if book is None:
            return RedirectResponse(url="/library", status_code=303)
        total, done = _counts(s, book_id)
        max_ch = max((c.number for c in s.exec(select(Chapter).where(Chapter.book_id == book_id)).all()), default=0)
        volumes = s.exec(select(Volume).where(Volume.book_id == book_id).order_by(Volume.number)).all()
        vols = []
        for v in volumes:
            v_total, v_done = _counts(s, book_id, v.start_chapter, v.end_chapter)
            vols.append({"v": v, "total": v_total, "done": v_done, "building": v.id in _building})
        # Defaults for the "add a book" form: next book number, and start = one past the
        # furthest chapter any existing book covers (so books stay sequential).
        next_number = max((v.number for v in volumes), default=0) + 1
        next_start = min(max((v.end_chapter for v in volumes), default=0) + 1, max_ch) if max_ch else 1
    return templates.TemplateResponse(
        request, "novel.html",
        {"active": "library", "book": book, "total": total, "done": done,
         "max_ch": max_ch, "vols": vols, "error": error,
         "next_number": next_number, "next_start": next_start},
    )


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
async def build_volume_route(volume_id: int):
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        book_id = vol.book_id if vol else None
    if book_id is not None and volume_id not in _building:
        _building.add(volume_id)

        async def _run():
            try:
                await build.build_volume(get_engine(), volume_id)
            finally:
                _building.discard(volume_id)

        asyncio.create_task(_run())
    return RedirectResponse(url=f"/novels/{book_id}", status_code=303)


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
