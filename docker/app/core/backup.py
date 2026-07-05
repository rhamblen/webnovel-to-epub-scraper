"""Daily SQLite backup + restore.

Backups are point-in-time copies of ``app.db`` taken with SQLite's online backup API
(safe against concurrent writes — unlike a raw file copy of a live database). They are
written OUTSIDE ``/config`` on purpose: the whole reason this module exists is that the
config folder was once wiped by a stray file-sync during a deploy, and backups stored
next to the database would have died with it. The default destination is a dot-folder
under ``/output`` (the media share), which deploys never touch and which is itself
covered by the user's wider share backups/sync.

A background scheduler (started from ``main.lifespan``) runs one backup per day at the
time configured in Settings (default 01:00, container-local time); each run is recorded
as a ``Job`` (type="backup") so it shows up on the Jobs page. Retention keeps the newest
N files. Restore swaps a chosen backup in over the live DB — refusing while any job is
running, taking a pre-restore safety copy first, and resetting the engine so pooled
connections don't keep serving the old file.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from .. import settings_store
from ..config import config
from ..models import Job
from . import progress

_BACKUP_NAME = re.compile(r"^app-[A-Za-z0-9-]+\.db$")


def _dir() -> Path:
    d = config.backup_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup_now(prefix: str = "") -> Path:
    """Take an online backup of the live DB; returns the new file's path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"app-{prefix + '-' if prefix else ''}{stamp}.db"
    dest = _dir() / name
    src = sqlite3.connect(str(config.db_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest


def prune(keep: int) -> int:
    """Delete all but the newest ``keep`` backups; returns how many were removed."""
    files = sorted(_dir().glob("app-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in files[max(keep, 1):]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def list_backups() -> list[dict]:
    """Available backups, newest first: name / size / modified time."""
    out = []
    for p in sorted(_dir().glob("app-*.db"), key=lambda q: q.stat().st_mtime, reverse=True):
        st = p.stat()
        out.append({
            "name": p.name,
            "size_mb": round(st.st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(st.st_mtime),
        })
    return out


def backup_path(name: str) -> Path | None:
    """Resolve a backup by filename, strictly within the backup dir (no path tricks)."""
    if not _BACKUP_NAME.match(name):
        return None
    p = _dir() / name
    return p if p.is_file() else None


def restore_backup(engine, name: str) -> str:
    """Replace the live DB with the named backup. Returns the safety-copy's filename.

    Refuses while any job is active — a build writing chapters mid-swap would corrupt
    or resurrect state unpredictably. The current DB is backed up first (prefix
    "pre-restore"), so a mistaken restore is itself reversible.
    """
    from ..db import init_db, reset_engine

    src = backup_path(name)
    if src is None:
        raise ValueError(f"No such backup: {name}")
    with Session(engine) as s:
        active = s.exec(
            select(Job).where(Job.state.in_(("pending", "running", "cancelling")))
        ).first()
        if active is not None:
            raise RuntimeError("A job is currently running — wait for it to finish (or cancel it) first")
    safety = backup_now(prefix="pre-restore")
    reset_engine()
    shutil.copy2(src, config.db_path)
    init_db()  # re-create engine + apply any additive schema migrations to the restored file
    return safety.name


def _next_run(now: datetime, hhmm: str) -> datetime:
    try:
        hour, minute = (int(x) for x in hhmm.strip().split(":", 1))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        hour, minute = 1, 0  # fall back to 01:00 on a malformed setting
    run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run <= now:
        run += timedelta(days=1)
    return run


async def scheduler() -> None:
    """Daily backup loop. Sleeps in short slices so Settings changes (time, enabled,
    retention) take effect without a restart. Re-resolves the engine every cycle so a
    restore (which resets the engine) can't leave it holding a stale reference."""
    from ..db import get_engine

    while True:
        with Session(get_engine()) as s:
            cfg = settings_store.get_all(s)
        if cfg.get("backup_enabled", "true") != "true":
            await asyncio.sleep(300)
            continue
        target = _next_run(datetime.now(), cfg.get("backup_time", "01:00"))
        wait = (target - datetime.now()).total_seconds()
        if wait > 300:
            await asyncio.sleep(300)
            continue
        await asyncio.sleep(max(wait, 0))
        job_id = progress.start(job_type="backup", message="Backing up database…")
        try:
            dest = await asyncio.to_thread(backup_now)
            keep = int(cfg.get("backup_retention", "14") or 14)
            removed = await asyncio.to_thread(prune, keep)
            msg = f"Backed up to {dest.name}" + (f" (pruned {removed} old)" if removed else "")
            progress.finish(job_id, "done", msg)
        except Exception as e:
            progress.finish(job_id, "error", f"Backup failed: {type(e).__name__}: {e}")
        # Skip past the minute we just ran in, so one firing can't double-run.
        await asyncio.sleep(61)
