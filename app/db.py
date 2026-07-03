"""SQLite engine + session helpers."""
from sqlmodel import Session, SQLModel, create_engine

from .config import config

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{config.db_path}",
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db() -> None:
    # Import models so they register on SQLModel.metadata before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


def get_session():
    with Session(get_engine()) as session:
        yield session
