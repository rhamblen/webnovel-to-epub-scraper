"""SQLite engine + session helpers."""
from sqlalchemy import inspect, text
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

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine) -> None:
    """Lightweight additive migration: add model columns missing from existing tables.

    ``create_all`` never alters an existing table, so new nullable columns (e.g. a later
    ``Volume.pdf_path``) won't appear on an already-created DB. This adds them via
    ``ALTER TABLE ADD COLUMN`` so upgrades don't require wiping the database. Columns are
    added nullable (SQLite can't backfill NOT NULL on existing rows); the ORM populates
    them on write.
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    for table_name, table in SQLModel.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table_name)}
        for col in table.columns:
            if col.name in have:
                continue
            coltype = col.type.compile(dialect=engine.dialect)
            ddl = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {coltype}'
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception:
                pass  # best-effort; don't block startup on a single column


def get_session():
    with Session(get_engine()) as session:
        yield session
