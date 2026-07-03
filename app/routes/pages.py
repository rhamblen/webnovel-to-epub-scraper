"""HTML pages: Discover, Library, Jobs, Settings.

Phase 0 rendered the shell; Phase 1 adds an "add novel by URL" flow that imports the
chapter list and downloads bodies in the background. The download runs as a fire-and-
forget asyncio task for now — Phase 5 replaces it with a proper job queue + live UI.
"""
import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import settings_store
from ..core import scrape
from ..db import get_engine
from ..models import Book, Chapter, Job

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

# Book ids currently downloading (in-memory; superseded by the Phase 5 job system).
_active: set[int] = set()


@router.get("/")
def index():
    return RedirectResponse(url="/library", status_code=303)


@router.get("/discover")
def discover(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request, "discover.html", {"active": "discover", "error": error}
    )


@router.post("/novels")
async def add_novel(request: Request):
    form = await request.form()
    url = str(form.get("url", "")).strip()
    if not url:
        return RedirectResponse(url="/discover", status_code=303)
    try:
        await scrape.import_novel(get_engine(), url)
    except Exception as e:  # surface the reason on the Discover page
        return templates.TemplateResponse(
            request, "discover.html",
            {"active": "discover", "error": f"{type(e).__name__}: {e}", "url": url},
        )
    return RedirectResponse(url="/library", status_code=303)


@router.post("/novels/{book_id}/download")
async def download(book_id: int):
    if book_id not in _active:
        _active.add(book_id)

        async def _run():
            try:
                await scrape.scrape_bodies(get_engine(), book_id)
            finally:
                _active.discard(book_id)

        asyncio.create_task(_run())
    return RedirectResponse(url="/library", status_code=303)


@router.get("/library")
def library(request: Request):
    rows = []
    with Session(get_engine()) as s:
        books = s.exec(select(Book).order_by(Book.updated_at.desc())).all()
        for b in books:
            total = len(s.exec(select(Chapter.id).where(Chapter.book_id == b.id)).all())
            done = len(
                s.exec(
                    select(Chapter.id).where(
                        Chapter.book_id == b.id, Chapter.clean_html.is_not(None)
                    )
                ).all()
            )
            rows.append({"book": b, "total": total, "done": done, "active": b.id in _active})
    return templates.TemplateResponse(request, "library.html", {"active": "library", "rows": rows})


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
        request,
        "settings.html",
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
        else:
            updates[key] = str(form.get(key, "")).strip()
    with Session(get_engine()) as s:
        settings_store.set_many(s, updates)
    return RedirectResponse(url="/settings?saved=true", status_code=303)
