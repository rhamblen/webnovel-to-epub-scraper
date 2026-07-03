"""HTML pages: Discover, Library, Jobs, Settings.

Phase 0 renders the nav shell and a working Settings form; the feature pages are
intentional stubs that later phases fill in.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import settings_store
from ..db import get_engine
from ..models import Book, Job

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/")
def index():
    return RedirectResponse(url="/library", status_code=303)


@router.get("/discover")
def discover(request: Request):
    return templates.TemplateResponse(
        request, "discover.html", {"active": "discover"}
    )


@router.get("/library")
def library(request: Request):
    with Session(get_engine()) as s:
        books = s.exec(select(Book).order_by(Book.updated_at.desc())).all()
    return templates.TemplateResponse(
        request, "library.html", {"active": "library", "books": books}
    )


@router.get("/jobs")
def jobs(request: Request):
    with Session(get_engine()) as s:
        job_list = s.exec(select(Job).order_by(Job.created_at.desc())).all()
    return templates.TemplateResponse(
        request, "jobs.html", {"active": "jobs", "jobs": job_list}
    )


@router.get("/settings")
def settings_get(request: Request, saved: bool = False):
    with Session(get_engine()) as s:
        values = settings_store.get_all(s)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active": "settings",
            "fields": settings_store.FIELDS,
            "values": values,
            "saved": saved,
        },
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
