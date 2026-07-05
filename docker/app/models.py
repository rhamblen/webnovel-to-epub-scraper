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
    note: str = ""  # adapter-supplied caveat, e.g. "only 25 of 269 chapters are free"
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
    # Set when the last fetch attempt failed (exception message); cleared on next success.
    scrape_error: Optional[str] = None


class Volume(SQLModel, table=True):
    """A user-defined "book" = a chapter range of a novel that builds one EPUB.

    A whole-novel EPUB is just a Volume spanning start_chapter=1..end_chapter=N.
    (In the UI this is labelled a "Book"; ``Book`` above is the source novel/series.)
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    number: int  # the "book number" (e.g. Shadow Slave Book 3)
    title: str = ""  # optional volume title
    start_chapter: int
    end_chapter: int
    # new | building | ready | error | partial
    status: str = "new"
    epub_path: Optional[str] = None
    pdf_path: Optional[str] = None
    note: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    # JSON {"label": count, ...} from the last standard-phrase cleanup pass; None = never run.
    clean_report: Optional[str] = None
    clean_report_at: Optional[datetime] = None


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: Optional[int] = Field(default=None, foreign_key="book.id", index=True)
    volume_id: Optional[int] = Field(default=None, foreign_key="volume.id", index=True)
    # build | rescan
    type: str = "build"
    # pending | running | cancelling | done | error | cancelled
    state: str = "pending"
    phase: str = ""
    # JSON job parameters (e.g. {"clean": true} for builds), set at enqueue time.
    payload: Optional[str] = None
    completed: int = 0
    total: int = 0
    message: str = ""
    log: str = ""
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
