"""Job-backed progress tracking (Phase 5).

The `Job` table is the single source of truth for build/rescan status and progress,
surviving restarts. This replaces the old in-memory dict registry; `/volumes/{id}/progress`
still returns the same JSON shape (`active`/`phase`/`done`/`total`/`message`) so
`novel.html`'s existing polling script needs no changes — only the backing store moved.

Build *queueing* (the pending state, the concurrency cap) lives in ``core/queue.py``;
this module only reads/writes job progress and terminal states.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from ..db import get_engine
from ..models import Job


def _now():
    return datetime.now(timezone.utc)


def start(volume_id: int | None = None, book_id: int | None = None, job_type: str = "build",
          total: int = 0, done: int = 0, message: str = "Starting…") -> int:
    """Create a new running Job row and return its id. (Builds don't come through here —
    they're enqueued as pending via ``queue.enqueue_build``.)"""
    with Session(get_engine()) as s:
        job = Job(
            volume_id=volume_id, book_id=book_id, type=job_type, state="running",
            phase="downloading", completed=done, total=max(total, 0), message=message,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


def update(job_id: int, **fields) -> None:
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        s.add(job)
        s.commit()


def finish(job_id: int, state: str, message: str) -> None:
    """Move a job to a terminal state: "done" | "error" | "cancelled"."""
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        job.state = state
        job.phase = state
        job.message = message
        if state == "error":
            job.error = message
        job.updated_at = _now()
        s.add(job)
        s.commit()


def get_for_volume(volume_id: int) -> dict:
    """Latest job for a volume, shaped for `GET /volumes/{id}/progress` (novel.html's poller)."""
    with Session(get_engine()) as s:
        job = s.exec(
            select(Job).where(Job.volume_id == volume_id).order_by(Job.created_at.desc())
        ).first()
        if job is None:
            return {}
        return {
            "active": job.state in ("pending", "running", "cancelling"),
            "phase": job.phase, "done": job.completed, "total": job.total,
            "message": job.message, "job_id": job.id, "state": job.state,
        }


def active_job_id(volume_id: int) -> int | None:
    """The pending/running/cancelling Job id for this volume, if any (concurrency guard)."""
    with Session(get_engine()) as s:
        job = s.exec(
            select(Job).where(
                Job.volume_id == volume_id, Job.state.in_(("pending", "running", "cancelling"))
            )
        ).first()
        return job.id if job else None


def request_cancel(job_id: int) -> None:
    """Ask a job to stop. A queued (pending) job is cancelled outright — the dispatcher
    never picks it up; a running one moves to "cancelling", which the scrape loop checks
    between chapters."""
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        if job.state == "pending":
            job.state = "cancelled"
            job.message = "Cancelled while queued"
        elif job.state == "running":
            job.state = "cancelling"
        else:
            return
        job.updated_at = _now()
        s.add(job)
        s.commit()


def is_cancelled(job_id: int) -> bool:
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        return job is not None and job.state == "cancelling"
