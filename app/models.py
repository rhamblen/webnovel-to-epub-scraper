"""Database models (SQLModel).

The schema is deliberately small in Phase 0; later phases fill in the scraping and
build details. Tables are created via ``SQLModel.metadata.create_all`` (see ``db.py``);
a real migration tool (Alembic) can be introduced if/when the schema needs to evolve
in place.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Setting(SQLModel, table=True):
    """A single user-editable application setting (key/value)."""

    key: str = Field(primary_key=True)
    value: str = ""


class Book(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str = "Unknown"
    source_site: Optional[str] = None
    toc_url: Optional[str] = None
    language: str = "en"
    cover_path: Optional[str] = None
    # new | scraping | ready | error
    status: str = "new"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    number: int  # order within the book
    title: str = ""
    source_url: str = ""
    raw_html: Optional[str] = None
    clean_html: Optional[str] = None
    content_hash: Optional[str] = None
    fetched_at: Optional[datetime] = None


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: Optional[int] = Field(default=None, foreign_key="book.id", index=True)
    # build | update | scrape
    type: str = "build"
    # pending | running | done | error | cancelled
    state: str = "pending"
    completed: int = 0
    total: int = 0
    log: str = ""
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
