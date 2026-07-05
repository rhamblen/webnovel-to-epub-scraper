"""Job-backed progress registry (core/progress.py).

Regression for a live bug: ``progress.update()`` sets keyword fields directly onto the
``Job`` row, so callers must use real Job column names — the first deploy passed
``done=`` (the old in-memory dict's key) where the column is ``completed``, and SQLModel
raised ``ValueError: "Job" object has no field "done"``, killing every build at 0
chapters. These tests call ``update()`` with exactly the field sets ``build.py`` uses.
"""


def test_update_accepts_the_field_sets_build_uses(app_env):
    from app.core import progress

    job_id = progress.start(volume_id=1, book_id=1, job_type="build", message="Starting…")
    # build_volume's initial totals update:
    progress.update(job_id, total=95, completed=3, message="Downloading chapters… 3/95")
    # the per-chapter callback:
    progress.update(job_id, completed=4, message="Downloading chapters… 4/95")
    # the phase transition before EPUB/PDF assembly:
    progress.update(job_id, phase="building", completed=95, total=95)
    # message-only updates (clean/EPUB/PDF phases):
    progress.update(job_id, message="Building EPUB…")

    st = progress.get_for_volume(1)
    assert st["active"] is True
    assert st["done"] == 95 and st["total"] == 95  # read side keeps the old JSON contract
    assert st["phase"] == "building"

    progress.finish(job_id, "done", "Done — 95/95 chapters in range")
    st = progress.get_for_volume(1)
    assert st["active"] is False and st["state"] == "done"


def test_cancel_flow(app_env):
    from app.core import progress

    job_id = progress.start(volume_id=2, job_type="build", message="Starting…")
    assert progress.active_job_id(2) == job_id
    assert progress.is_cancelled(job_id) is False
    progress.request_cancel(job_id)
    assert progress.is_cancelled(job_id) is True
    progress.finish(job_id, "cancelled", "Build cancelled")
    assert progress.active_job_id(2) is None


def test_get_for_volume_without_jobs_is_empty(app_env):
    from app.core import progress

    assert progress.get_for_volume(999) == {}
