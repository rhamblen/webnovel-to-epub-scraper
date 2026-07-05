"""In-process build queue: pending Jobs in SQLite, one dispatcher, a concurrency cap.

This is the "in-process asyncio worker + SQLite-persisted job queue" ADR 0001 called
for. Build requests no longer spawn a task directly — they enqueue a ``Job`` row as
``pending`` and the dispatcher (one task, started from ``main.lifespan``) promotes the
oldest pending jobs to ``running``, at most ``max_concurrent_builds`` (Settings) at a
time. Without this, N Build clicks meant N parallel scrape loops each with its own
rate-limiter — multiplying polite per-build limits into an impolite site-wide load.

Because pending jobs are just rows, the queue survives restarts: the startup sweep
errors out jobs that were mid-flight (their tasks died with the process) but leaves
pending ones alone, so a queued backlog resumes on its own. Builds are idempotent
(already-fetched chapters are skipped), which is what makes that resume safe.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from .. import settings_store
from ..db import get_engine
from ..models import Job, Volume
from . import build, progress

# How long the dispatcher waits between looks at the queue when nothing wakes it.
# A finished build frees a slot without setting the event, so this is also the worst-case
# delay before the next queued job starts. Tests shrink it.
POLL_SECONDS = 2.0

_wake = asyncio.Event()


def _now():
    return datetime.now(timezone.utc)


def enqueue_build(volume_id: int, book_id: int, do_clean: bool = False) -> int:
    """Queue a build; returns the new Job id. The dispatcher picks it up."""
    with Session(get_engine()) as s:
        job = Job(
            volume_id=volume_id, book_id=book_id, type="build", state="pending",
            message="Queued…", payload=json.dumps({"clean": do_clean}),
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id
    _wake.set()
    return job_id


def _cap(cfg: dict) -> int:
    try:
        return max(1, int(cfg.get("max_concurrent_builds", "2") or 2))
    except ValueError:
        return 2


def sweep_interrupted(engine) -> int:
    """Startup housekeeping: error out jobs whose tasks died with the previous process
    (running/cancelling), but leave pending ones queued — the dispatcher resumes them.
    Returns how many were marked interrupted."""
    with Session(engine) as s:
        stuck = s.exec(select(Job).where(Job.state.in_(("running", "cancelling")))).all()
        for job in stuck:
            job.state = "error"
            job.message = "Interrupted by restart"
            job.error = "Interrupted by restart"
            job.updated_at = _now()
            s.add(job)
        if stuck:
            s.commit()
        return len(stuck)


async def _execute(job_id: int, volume_id: int, do_clean: bool) -> None:
    engine = get_engine()
    try:
        await build.build_volume(engine, volume_id, job_id, do_clean=do_clean)
    except Exception as e:
        progress.finish(job_id, "error", f"Build failed: {type(e).__name__}")
        with Session(engine) as s:
            v = s.get(Volume, volume_id)
            if v is not None:
                v.status = "error"
                v.note = f"Build failed: {type(e).__name__}: {e}"[:300]
                s.add(v)
                s.commit()


async def dispatcher() -> None:
    """Promote pending builds to running while slots are free. Runs forever."""
    while True:
        try:
            await asyncio.wait_for(_wake.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
        _wake.clear()

        ready: list[tuple[int, int, bool]] = []
        with Session(get_engine()) as s:
            cfg = settings_store.get_all(s)
            running = len(s.exec(
                select(Job).where(Job.type == "build", Job.state.in_(("running", "cancelling")))
            ).all())
            slots = _cap(cfg) - running
            if slots > 0:
                pending = s.exec(
                    select(Job).where(Job.type == "build", Job.state == "pending")
                    .order_by(Job.created_at).limit(slots)
                ).all()
                for job in pending:
                    job.state = "running"
                    job.message = "Starting…"
                    job.updated_at = _now()
                    s.add(job)
                    payload = json.loads(job.payload or "{}")
                    ready.append((job.id, job.volume_id, bool(payload.get("clean"))))
                if pending:
                    s.commit()
        for job_id, volume_id, do_clean in ready:
            asyncio.create_task(_execute(job_id, volume_id, do_clean))
