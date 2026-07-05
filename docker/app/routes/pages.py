"""HTML pages: Discover, Library, Novel detail, Jobs, Settings.

Phase 2 adds the Novel detail page: define "books" (volumes) by chapter range and build
each into an EPUB written to the output share. Builds and rescans run as fire-and-forget
asyncio tasks, backed by a persistent `Job` row (see `core/progress.py`) so state and
history survive restarts — see Phase 5 in `docs/project-plan.md`.
"""
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import settings_store
from ..core import backup, progress, queue, scrape
from ..core.adapters import cover_url_allowed, get_adapter
from ..core.fetch import DEFAULT_UA
from ..db import get_engine
from ..models import Book, Chapter, Job, Volume

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

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


def _volume_rows(s: Session, book_id: int) -> list[dict]:
    """Per-volume display rows for a book: counts, live-build state, sequence-gap check,
    clean report, and failed-chapter count. Shared by the Novel detail page, the Library
    page's expandable per-book section, and the HTMX-partial responses that update those
    sections in place after a build/edit/delete."""
    volumes = s.exec(select(Volume).where(Volume.book_id == book_id).order_by(Volume.number)).all()
    rows = []
    prev_end = 0  # expected start of the first book is chapter 1
    for v in volumes:
        v_total, v_done = _counts(s, book_id, v.start_chapter, v.end_chapter)
        expected = prev_end + 1
        report = json.loads(v.clean_report) if v.clean_report else {}
        failed = s.exec(
            select(Chapter).where(
                Chapter.book_id == book_id, Chapter.number >= v.start_chapter,
                Chapter.number <= v.end_chapter, Chapter.scrape_error.is_not(None),
            )
        ).all()
        job_id = progress.active_job_id(v.id)
        rows.append({
            "v": v, "total": v_total, "done": v_done,
            "building": job_id is not None, "job_id": job_id,
            "seq_ok": v.start_chapter == expected, "expected_start": expected,
            "clean_report": report, "clean_total": sum(report.values()),
            "failed_count": len(failed),
        })
        prev_end = v.end_chapter
    return rows


def _delete_book(s: Session, book_id: int) -> None:
    """Delete a novel entirely: its Chapters, Volumes, then the Book row. No cascade is
    configured at the DB level, so each table is cleared explicitly. Does not touch
    already-built EPUB/PDF files on the share."""
    for ch in s.exec(select(Chapter).where(Chapter.book_id == book_id)).all():
        s.delete(ch)
    for vol in s.exec(select(Volume).where(Volume.book_id == book_id)).all():
        s.delete(vol)
    book = s.get(Book, book_id)
    if book is not None:
        s.delete(book)
    s.commit()


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
def library(request: Request, msg: str | None = None, error: str | None = None):
    rows = []
    with Session(get_engine()) as s:
        books = s.exec(select(Book).order_by(Book.updated_at.desc())).all()
        for b in books:
            total, done = _counts(s, b.id)
            vols = _volume_rows(s, b.id)
            statuses = [row["v"].status for row in vols]
            if any(row["building"] for row in vols):
                status_class, status_label = "running", "building"
            elif "error" in statuses:
                status_class, status_label = "error", "error"
            elif statuses and all(s_ == "ready" for s_ in statuses):
                status_class, status_label = "ready", "ready"
            elif "partial" in statuses:
                status_class, status_label = "pending", "partial"
            else:
                status_class, status_label = "pending", "new"
            rows.append({
                "book": b, "total": total, "done": done, "volumes": len(vols), "vols": vols,
                "status_class": status_class, "status_label": status_label,
            })
    return templates.TemplateResponse(
        request, "library.html", {"active": "library", "rows": rows, "msg": msg, "error": error}
    )


@router.get("/novels/{book_id}")
def novel_detail(request: Request, book_id: int, error: str | None = None, msg: str | None = None):
    with Session(get_engine()) as s:
        book = s.get(Book, book_id)
        if book is None:
            return RedirectResponse(url="/library", status_code=303)
        total, done = _counts(s, book_id)
        max_ch = max((c.number for c in s.exec(select(Chapter).where(Chapter.book_id == book_id)).all()), default=0)
        vols = _volume_rows(s, book_id)
        # Defaults for the "add a book" form: next book number, and start = one past the
        # furthest chapter any existing book covers (so books stay sequential).
        next_number = max((row["v"].number for row in vols), default=0) + 1
        next_start = min(max((row["v"].end_chapter for row in vols), default=0) + 1, max_ch) if max_ch else 1
    return templates.TemplateResponse(
        request, "novel.html",
        {"active": "library", "book": book, "total": total, "done": done,
         "max_ch": max_ch, "vols": vols, "error": error, "msg": msg,
         "next_number": next_number, "next_start": next_start},
    )


async def _rescan_one(book_id: int) -> tuple[str, int]:
    """Re-read a novel's source page for newly-published chapters (idempotent), recorded
    as a Job for history. Returns (summary message, count of new chapters found); raises
    on failure (after recording the Job as errored) so callers can report it."""
    with Session(get_engine()) as s:
        book = s.get(Book, book_id)
        if book is None:
            raise ValueError(f"Book {book_id} not found")
        toc_url, title = book.toc_url, book.title
        before = len(s.exec(select(Chapter.id).where(Chapter.book_id == book_id)).all())
    job_id = progress.start(book_id=book_id, job_type="rescan", message=f"Rescanning {title}…")
    try:
        await scrape.import_novel(get_engine(), toc_url)
    except Exception as e:
        progress.finish(job_id, "error", f"Rescan failed: {type(e).__name__}: {e}")
        raise
    with Session(get_engine()) as s:
        after = len(s.exec(select(Chapter.id).where(Chapter.book_id == book_id)).all())
    delta = after - before
    msg = (
        f"Rescan complete — {delta} new chapter(s) found ({after} total)."
        if delta else f"Rescan complete — no new chapters ({after} total)."
    )
    progress.finish(job_id, "done", msg)
    return msg, delta


@router.post("/novels/{book_id}/rescan")
async def rescan_novel(book_id: int):
    """Re-read the source novel page and add any newly-published chapters (idempotent)."""
    try:
        msg, delta = await _rescan_one(book_id)
    except ValueError:
        return RedirectResponse(url="/library", status_code=303)
    except Exception as e:
        return RedirectResponse(
            url=f"/novels/{book_id}?error={quote(f'Rescan failed: {type(e).__name__}: {e}')}",
            status_code=303,
        )
    if delta:
        msg += " Extend a book's end (or add a new book) to include them."
    return RedirectResponse(url=f"/novels/{book_id}?msg={quote(msg)}", status_code=303)


@router.post("/novels/{book_id}/delete")
async def delete_novel(book_id: int):
    """Delete a novel entirely (all its chapters + volumes). Reused by bulk-delete."""
    with Session(get_engine()) as s:
        _delete_book(s, book_id)
    return RedirectResponse(url="/library", status_code=303)


@router.post("/library/bulk-rescan")
async def bulk_rescan(request: Request):
    form = await request.form()
    book_ids = [int(x) for x in form.getlist("book_ids") if str(x).strip()]
    total_new = failed = 0
    for book_id in book_ids:
        try:
            _msg, delta = await _rescan_one(book_id)
            total_new += delta
        except Exception:
            failed += 1
    msg = f"Rescanned {len(book_ids)} novel(s) — {total_new} new chapter(s) found total."
    if failed:
        msg += f" ({failed} failed — see Jobs for details.)"
    return RedirectResponse(url=f"/library?msg={quote(msg)}", status_code=303)


@router.post("/library/bulk-delete")
async def bulk_delete(request: Request):
    form = await request.form()
    book_ids = [int(x) for x in form.getlist("book_ids") if str(x).strip()]
    with Session(get_engine()) as s:
        for book_id in book_ids:
            _delete_book(s, book_id)
    return RedirectResponse(url=f"/library?msg={quote(f'Deleted {len(book_ids)} novel(s).')}", status_code=303)


def _is_hx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def _volumes_partial(request: Request, book_id: int, error: str | None = None):
    """Re-render the volumes-list partial for a book — used by the Library page's
    inline (HTMX) build/edit/delete actions so they update in place without a full
    page navigation."""
    with Session(get_engine()) as s:
        vols = _volume_rows(s, book_id)
    return templates.TemplateResponse(
        request, "_volumes_list.html", {"book_id": book_id, "vols": vols, "error": error}
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
            if _is_hx(request):
                return _volumes_partial(request, book_id, error=f"Invalid book: {e}")
            return RedirectResponse(url=f"/novels/{book_id}?error=Invalid+book:+{e}", status_code=303)
        vol.number, vol.title, vol.start_chapter, vol.end_chapter = number, title, start, end
        s.add(vol)
        s.commit()
    if _is_hx(request):
        return _volumes_partial(request, book_id)
    return RedirectResponse(url=f"/novels/{book_id}", status_code=303)


@router.post("/volumes/{volume_id}/delete")
async def delete_volume(request: Request, volume_id: int):
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        book_id = vol.book_id if vol else None
        if vol is not None:
            s.delete(vol)
            s.commit()
    if book_id is not None and _is_hx(request):
        return _volumes_partial(request, book_id)
    return RedirectResponse(url=f"/novels/{book_id}" if book_id else "/library", status_code=303)


@router.post("/volumes/{volume_id}/build")
async def build_volume_route(request: Request, volume_id: int):
    form = await request.form()
    do_clean = form.get("clean") is not None
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        book_id = vol.book_id if vol else None
    # Enqueue rather than run directly: the dispatcher (core/queue.py) executes at most
    # `max_concurrent_builds` at a time; the rest wait as "pending" on the Jobs page.
    if book_id is not None and progress.active_job_id(volume_id) is None:
        queue.enqueue_build(volume_id, book_id, do_clean=do_clean)
    if book_id is not None and _is_hx(request):
        return _volumes_partial(request, book_id)
    return RedirectResponse(url=f"/novels/{book_id}" if book_id else "/library", status_code=303)


@router.get("/volumes/{volume_id}/progress")
def volume_progress(volume_id: int):
    st = progress.get_for_volume(volume_id)
    st["building"] = st.get("active", False)
    return st


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    """Cooperative cancel: the scrape loop checks this between chapters and stops."""
    progress.request_cancel(job_id)
    return RedirectResponse(url="/jobs", status_code=303)


_FINISHED_STATES = ("done", "error", "cancelled")


@router.post("/jobs/{job_id}/delete")
def delete_job(job_id: int):
    """Remove one finished job from the log. Active jobs are ignored — cancel them first."""
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        if job is not None and job.state in _FINISHED_STATES:
            s.delete(job)
            s.commit()
    return RedirectResponse(url="/jobs", status_code=303)


@router.post("/jobs/clear")
def clear_jobs():
    """Remove every finished job (done/error/cancelled); queued and running ones stay."""
    with Session(get_engine()) as s:
        for job in s.exec(select(Job).where(Job.state.in_(_FINISHED_STATES))).all():
            s.delete(job)
        s.commit()
    return RedirectResponse(url="/jobs", status_code=303)


@router.get("/volumes/{volume_id}/download/{fmt}")
def download_volume(volume_id: int, fmt: str):
    if fmt not in ("epub", "pdf"):
        return Response(status_code=404)
    with Session(get_engine()) as s:
        vol = s.get(Volume, volume_id)
        path = (vol.epub_path if fmt == "epub" else vol.pdf_path) if vol else None
    if not path or not Path(path).is_file():
        return Response(status_code=404)
    return FileResponse(path, filename=Path(path).name)


@router.get("/jobs")
def jobs(request: Request):
    with Session(get_engine()) as s:
        job_list = s.exec(select(Job).order_by(Job.created_at.desc())).all()
        rows = []
        for j in job_list:
            target = "—"
            if j.volume_id is not None:
                vol = s.get(Volume, j.volume_id)
                book = s.get(Book, vol.book_id) if vol else None
                if vol is not None and book is not None:
                    target = f"{book.title} — Book {vol.number:02d}"
            elif j.book_id is not None:
                book = s.get(Book, j.book_id)
                if book is not None:
                    target = book.title
            rows.append({"job": j, "target": target})
    return templates.TemplateResponse(request, "jobs.html", {"active": "jobs", "rows": rows})


@router.get("/settings")
def settings_get(request: Request, saved: bool = False, msg: str | None = None, error: str | None = None):
    with Session(get_engine()) as s:
        values = settings_store.get_all(s)
    return templates.TemplateResponse(
        request, "settings.html",
        {"active": "settings", "fields": settings_store.FIELDS, "values": values, "saved": saved,
         "backups": backup.list_backups(), "msg": msg, "error": error},
    )


@router.post("/settings/backup")
def settings_backup_now():
    """Take an immediate backup (same machinery as the daily run), recorded as a Job."""
    job_id = progress.start(job_type="backup", message="Backing up database…")
    try:
        dest = backup.backup_now()
    except Exception as e:
        progress.finish(job_id, "error", f"Backup failed: {type(e).__name__}: {e}")
        return RedirectResponse(
            url=f"/settings?error={quote(f'Backup failed: {type(e).__name__}: {e}')}", status_code=303
        )
    progress.finish(job_id, "done", f"Backed up to {dest.name}")
    return RedirectResponse(url=f"/settings?msg={quote(f'Backed up to {dest.name}')}", status_code=303)


@router.post("/settings/restore")
async def settings_restore(request: Request):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    try:
        safety = backup.restore_backup(get_engine(), name)
    except Exception as e:
        return RedirectResponse(url=f"/settings?error={quote(str(e))}", status_code=303)
    msg = f"Restored {name}. The library now reflects that backup; the replaced database was saved as {safety}."
    return RedirectResponse(url=f"/settings?msg={quote(msg)}", status_code=303)


@router.get("/settings/backups/{name}/download")
def settings_backup_download(name: str):
    path = backup.backup_path(name)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, filename=path.name)


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
