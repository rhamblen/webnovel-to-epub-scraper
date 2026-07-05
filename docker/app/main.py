"""FastAPI entrypoint: wiring, startup, static/templates."""
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from . import __version__, settings_store
from .config import config
from .core import backup, queue
from .db import get_engine, init_db
from .routes import health, pages

BASE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    with Session(get_engine()) as s:
        settings_store.seed_defaults(s)
    # Jobs whose tasks died with the previous process are marked interrupted; queued
    # (pending) ones are left alone — the dispatcher below resumes them.
    queue.sweep_interrupted(get_engine())
    background = [
        asyncio.create_task(queue.dispatcher()),
        asyncio.create_task(backup.scheduler()),
    ]
    yield
    for task in background:
        task.cancel()
    for task in background:
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Webnovel to EPUB Scraper", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.include_router(health.router)
app.include_router(pages.router)
