"""Backup + restore round-trip against a temp database and backup dir.

Uses the shared ``app_env`` fixture from conftest.py.
"""
from datetime import datetime

import pytest
from sqlmodel import Session, select


def _add_book(title: str) -> int:
    from app.db import get_engine
    from app.models import Book

    with Session(get_engine()) as s:
        book = Book(title=title)
        s.add(book)
        s.commit()
        s.refresh(book)
        return book.id


def _titles() -> list[str]:
    from app.db import get_engine
    from app.models import Book

    with Session(get_engine()) as s:
        return [b.title for b in s.exec(select(Book)).all()]


def test_backup_restore_roundtrip(app_env):
    from app.core import backup
    from app.db import get_engine

    _add_book("Kept Novel")
    dest = backup.backup_now()
    assert dest.is_file() and dest.stat().st_size > 0

    _add_book("Added After Backup")
    assert sorted(_titles()) == ["Added After Backup", "Kept Novel"]

    safety = backup.restore_backup(get_engine(), dest.name)
    assert _titles() == ["Kept Novel"]  # post-backup change rolled away
    # ...and the replaced state was itself preserved as a pre-restore backup.
    assert any(b["name"] == safety for b in backup.list_backups())


def test_restore_refuses_while_job_active(app_env):
    from app.core import backup, progress
    from app.db import get_engine

    dest = backup.backup_now()
    progress.start(job_type="build", message="busy")
    with pytest.raises(RuntimeError):
        backup.restore_backup(get_engine(), dest.name)


def test_restore_rejects_unknown_and_malicious_names(app_env):
    from app.core import backup
    from app.db import get_engine

    for bad in ("nope.db", "../../config/app.db", "app-x.db.sneaky", ""):
        with pytest.raises(ValueError):
            backup.restore_backup(get_engine(), bad)


def test_prune_keeps_newest(app_env, monkeypatch):
    import time

    from app.core import backup

    names = []
    for i in range(4):
        p = backup.backup_now(prefix=f"t{i}")
        names.append(p.name)
        time.sleep(0.05)  # distinct mtimes
    removed = backup.prune(keep=2)
    assert removed == 2
    kept = {b["name"] for b in backup.list_backups()}
    assert kept == set(names[-2:])


def test_next_run_parses_and_falls_back():
    from app.core.backup import _next_run

    now = datetime(2026, 7, 5, 12, 0, 0)
    assert _next_run(now, "13:30") == datetime(2026, 7, 5, 13, 30)
    assert _next_run(now, "01:00") == datetime(2026, 7, 6, 1, 0)   # already past -> tomorrow
    assert _next_run(now, "garbage") == datetime(2026, 7, 6, 1, 0)  # malformed -> 01:00
