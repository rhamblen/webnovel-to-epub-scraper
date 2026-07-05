"""Jobs-page cleanup routes: per-job dismiss (✕) and clear-all-finished.

Finished = done/error/cancelled. Queued and running jobs must survive both routes —
dismissing an active job would orphan its task's progress writes.

The route handlers are called directly (no TestClient): running the app's lifespan here
would start the real dispatcher in a background-thread loop, and enqueuing from the test
thread would trip cross-thread asyncio on the queue's module-global wake Event — an
arrangement production never has (enqueues always happen inside the loop).
"""
from sqlmodel import Session, select


def _states() -> dict[int, str]:
    from app.db import get_engine
    from app.models import Job

    with Session(get_engine()) as s:
        return {j.id: j.state for j in s.exec(select(Job)).all()}


def test_dismiss_single_finished_job(app_env):
    from app.core import progress
    from app.routes import pages

    j_err = progress.start(volume_id=1, job_type="build")
    progress.finish(j_err, "error", "boom")
    j_run = progress.start(volume_id=2, job_type="build")

    assert pages.delete_job(j_err).status_code == 303
    assert j_err not in _states(), "finished job should be removed"

    # an active job refuses dismissal
    pages.delete_job(j_run)
    assert _states()[j_run] == "running"


def test_clear_removes_only_finished(app_env):
    from app.core import progress, queue
    from app.routes import pages

    j_done = progress.start(volume_id=1, job_type="build")
    progress.finish(j_done, "done", "ok")
    j_cancelled = progress.start(volume_id=2, job_type="build")
    progress.finish(j_cancelled, "cancelled", "stopped")
    j_backup_err = progress.start(job_type="backup")
    progress.finish(j_backup_err, "error", "disk full")
    j_run = progress.start(volume_id=3, job_type="build")
    j_pending = queue.enqueue_build(volume_id=4, book_id=1)  # no dispatcher running here

    assert pages.clear_jobs().status_code == 303
    assert set(_states()) == {j_run, j_pending}, "only active jobs survive a clear"
