"""User-editable application settings, persisted in the ``Setting`` table.

``FIELDS`` drives the Settings page UI (label/type/help), so adding a setting is a
one-line change here plus a default in ``_defaults()``.
"""
from sqlmodel import Session, select

from .config import config
from .models import Setting


def _defaults() -> dict[str, str]:
    return {
        "output_dir": str(config.output_dir),
        "concurrency": "2",
        "request_delay_seconds": "1.0",
        "default_language": "en",
        "default_author": "Unknown",
        "strip_translator_notes": "false",
        "cover_style": "simple",
        "user_agent": "",
        "format_epub": "true",
        "format_pdf": "true",
    }


# UI descriptors for the Settings page (data-driven form).
FIELDS = [
    {
        "key": "output_dir",
        "label": "Output folder",
        "type": "text",
        "help": "Where finished files are written, as seen INSIDE the container. Leave this "
        "as /output — docker-compose maps /output to your UR1 share "
        "(/mnt/user/media/books/webnovels). Do not put the UR1 path here.",
    },
    {
        "key": "concurrency",
        "label": "Max concurrent requests",
        "type": "number",
        "step": "1",
        "help": "How many chapter fetches run at once. Keep low to be polite (2–4).",
    },
    {
        "key": "request_delay_seconds",
        "label": "Delay between requests (seconds)",
        "type": "number",
        "step": "0.1",
        "help": "Minimum pause between requests to the same site.",
    },
    {
        "key": "default_language",
        "label": "Default language",
        "type": "text",
        "help": "ISO code for EPUB metadata when a source doesn't specify one (e.g. en).",
    },
    {
        "key": "default_author",
        "label": "Default author",
        "type": "text",
        "help": "Used when a novel's author can't be detected.",
    },
    {
        "key": "strip_translator_notes",
        "label": "Strip translator / pre- & post-chapter notes",
        "type": "checkbox",
        "help": "Remove common translator note blocks from chapter bodies.",
    },
    {
        "key": "cover_style",
        "label": "Generated cover style",
        "type": "select",
        "options": ["simple", "none"],
        "help": "Placeholder cover generated when the source has no cover image.",
    },
    {
        "key": "format_epub",
        "label": "Build EPUB",
        "type": "checkbox",
        "help": "Produce an .epub for each book (best for Kindle Paperwhite).",
    },
    {
        "key": "format_pdf",
        "label": "Build PDF",
        "type": "checkbox",
        "help": "Also produce a .pdf for each book (fixed layout; handy for other readers).",
    },
    {
        "key": "user_agent",
        "label": "User-Agent (optional)",
        "type": "text",
        "help": "Override the HTTP User-Agent sent to sites. Leave blank to use the "
        "built-in default. Some sites only serve a browser-like UA.",
    },
]

CHECKBOX_KEYS = {f["key"] for f in FIELDS if f["type"] == "checkbox"}


def seed_defaults(session: Session) -> None:
    """Insert any missing default settings without overwriting user changes."""
    existing = {s.key for s in session.exec(select(Setting)).all()}
    for key, value in _defaults().items():
        if key not in existing:
            session.add(Setting(key=key, value=value))
    session.commit()


def get_all(session: Session) -> dict[str, str]:
    values = _defaults()
    for s in session.exec(select(Setting)).all():
        values[s.key] = s.value
    return values


def set_many(session: Session, values: dict[str, str]) -> None:
    for key, value in values.items():
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
            session.add(row)
    session.commit()
