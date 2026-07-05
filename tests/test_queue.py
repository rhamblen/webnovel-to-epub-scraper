"""Build queue (core/queue.py): concurrency cap, ordering, cancel-while-queued,
and the restart sweep leaving pending jobs resumable."""
import asyncio

import pytest
from sqlmodel import Session, select


def _set(key: str, value: str) -> None:
    from app import settings_store
    from app.db import get_engine

    with Session(get_engine()) as s:
        settings_store.set_many(s, {key: value})


def _job_states() -> dict[int, str]:
    from app.db import get_engine
    from app.models import Job

    with Session(get_engine()) as s:
        return {j.id: j.state for j in s.exec(select(Job)).all()}


@pytest.mark.asyncio
async def test_dispatcher_respects_concurrency_cap(app_env, monkeypatch):
    from app.core import build, progress, queue

    monkeypatch.setattr(queue, "POLL_SECONDS", 0.02)
    _set("max_concurrent_builds", "2")

    tracker = {"now": 0, "peak": 0, "runs": []}

    async def fake_build(engine, volume_id, job_id, do_clean=False):
        tracker["now"] += 1
        tracker["peak"] = max(tracker["peak"], tracker["now"])
        tracker["runs"].append(volume_id)
        await asyncio.sleep(0.05)
        tracker["now"] -= 1
        progress.finish(job_id, "done", "fake done")

    monkeypatch.setattr(build, "build_volume", fake_build)

    for vid in range(1, 6):  # five queued builds
        queue.enqueue_build(volume_id=vid, book_id=1)

    task = asyncio.create_task(queue.dispatcher())
    try:
        for _ in range(200):  # up to ~2s
            await asyncio.sleep(0.01)
            if all(state == "done" for state in _job_states().values()):
                break
    finally:
        task.cancel()

    assert all(state == "done" for state in _job_states().values())
    assert tracker["peak"] == 2  # never more than the cap, and the cap was actually used
    assert tracker["runs"][:2] == [1, 2]  # oldest first


@pytest.mark.asyncio
async def test_cancel_while_queued_is_never_run(app_env, monkeypatch):
    from app.core import build, progress, queue

    monkeypatch.setattr(queue, "POLL_SECONDS", 0.02)
    _set("max_concurrent_builds", "1")

    ran = []

    async def fake_build(engine, volume_id, job_id, do_clean=False):
        ran.append(volume_id)
        await asyncio.sleep(0.03)
        progress.finish(job_id, "done", "fake done")

    monkeypatch.setattr(build, "build_volume", fake_build)

    first = queue.enqueue_build(volume_id=1, book_id=1)
    second = queue.enqueue_build(volume_id=2, book_id=1)
    progress.request_cancel(second)  # cancelled while still pending

    task = asyncio.create_task(queue.dispatcher())
    try:
        await asyncio.sleep(0.3)
    finally:
        task.cancel()

    states = _job_states()
    assert states[first] == "done"
    assert states[second] == "cancelled"
    assert ran == [1]


def test_sweep_errors_in_flight_but_keeps_pending(app_env):
    from app.core import queue
    from app.db import get_engine
    from app.models import Job

    with Session(get_engine()) as s:
        rows = [
            Job(type="build", state="running"),
            Job(type="build", state="cancelling"),
            Job(type="build", state="pending"),
            Job(type="build", state="done"),
        ]
        for r in rows:
            s.add(r)
        s.commit()
        ids = [r.id for r in rows]

    assert queue.sweep_interrupted(get_engine()) == 2
    states = _job_states()
    assert states[ids[0]] == "error"
    assert states[ids[1]] == "error"
    assert states[ids[2]] == "pending"  # resumes after restart
    assert states[ids[3]] == "done"
