"""FastAPI entrypoint: wiring, startup, static/templates."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from . import __version__, settings_store
from .config import config
from .db import get_engine, init_db
from .routes import health, pages

BASE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    with Session(get_engine()) as s:
        settings_store.seed_defaults(s)
    yield


app = FastAPI(title="Webnovel to EPUB Scraper", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.include_router(health.router)
app.include_router(pages.router)
