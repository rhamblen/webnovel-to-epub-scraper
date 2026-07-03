"""User-editable application settings, persisted in the ``Setting`` table.

``FIELDS`` drives the Settings page UI (label/type/help), so adding a setting is a
one-line change here plus a default in ``_defaults()``.
"""
from sqlmodel import Session, select

from .core.adapters import searchable_names
from .models import Setting


def _defaults() -> dict[str, str]:
    return {
        "concurrency": "2",
        "request_delay_seconds": "1.0",
        "user_agent": "",
        "format_epub": "true",
        "format_pdf": "true",
        "pdf_page_size": "A5",
        "embed_cover": "true",
        # Comma-separated list of adapter names the Discover search queries.
        "search_sites": "freewebnovel",
    }


# UI descriptors for the Settings page (data-driven form).
# Note: the output location is intentionally NOT a setting — it's fixed at /output inside
# the container and mapped to a host path by docker-compose (see config.output_dir).
FIELDS = [
    # --- Scraping ---
    {
        "key": "concurrency",
        "section": "Scraping",
        "label": "Max concurrent requests",
        "type": "number",
        "step": "1",
        "help": "How many chapters download at once. Keep low (2–4) to be polite to the site.",
    },
    {
        "key": "request_delay_seconds",
        "section": "Scraping",
        "label": "Delay between requests (seconds)",
        "type": "number",
        "step": "0.1",
        "help": "Minimum pause between requests to the same site.",
    },
    {
        "key": "user_agent",
        "section": "Scraping",
        "label": "Custom User-Agent (optional)",
        "type": "text",
        "help": "Leave blank to use the built-in browser-like default. Only set this if a "
        "particular site needs a specific User-Agent.",
    },
    # --- Output ---
    {
        "key": "format_epub",
        "section": "Output",
        "label": "Build EPUB",
        "type": "checkbox",
        "help": "Create an .epub for each book (recommended for Kindle Paperwhite).",
    },
    {
        "key": "format_pdf",
        "section": "Output",
        "label": "Build PDF",
        "type": "checkbox",
        "help": "Also create a .pdf for each book.",
    },
    {
        "key": "pdf_page_size",
        "section": "Output",
        "label": "PDF page size",
        "type": "select",
        "options": ["A5", "A4"],
        "help": "A5 = larger text, better for reading; A4 = standard document size. "
        "Only used when Build PDF is on.",
    },
    {
        "key": "embed_cover",
        "section": "Output",
        "label": "Embed book cover",
        "type": "checkbox",
        "help": "Download the novel's cover from the source and embed it in the EPUB.",
    },
    # --- Discovery ---
    {
        "key": "search_sites",
        "section": "Discovery",
        "label": "Sites to search",
        "type": "multiselect",
        "options": searchable_names(),
        "help": "Which sites the Discover search queries. More appear here as site adapters "
        "are added.",
    },
]

CHECKBOX_KEYS = {f["key"] for f in FIELDS if f["type"] == "checkbox"}
MULTISELECT_KEYS = {f["key"] for f in FIELDS if f["type"] == "multiselect"}


def get_search_sites(session: Session) -> list[str]:
    raw = get_all(session).get("search_sites", "")
    sites = [s.strip() for s in raw.split(",") if s.strip()]
    return sites or searchable_names()


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
