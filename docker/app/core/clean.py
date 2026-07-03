"""Normalize a chapter body into clean, EPUB-friendly XHTML (a series of <p>).

Kept deliberately conservative in Phase 1: drop scripts/styles/ads and site
watermarks, keep paragraph text. Later phases add per-adapter cleaning rules.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

# Substrings that mark an injected watermark / ad / navigation paragraph.
_JUNK_SUBSTRINGS = (
    "freewebnovel",
    "please reading on",
    "read latest chapters at",
    "this content is taken from",
    "translator:",
    "editor:",
)


def _looks_like_junk(text: str) -> bool:
    low = text.lower()
    return any(sub in low for sub in _JUNK_SUBSTRINGS)


def clean_chapter_html(container: Tag | str, strip_notes: bool = False) -> str:
    """Return sanitized ``<p>...</p>`` markup from a content container."""
    if isinstance(container, str):
        container = BeautifulSoup(container, "html.parser")

    for bad in container.select("script, style, ins, iframe, .adsbox, .ads, noscript"):
        bad.decompose()

    paras: list[str] = []
    blocks = container.find_all("p")
    # Some chapters use <br>-separated text instead of <p>; fall back to that.
    if not blocks:
        raw = container.get_text("\n", strip=True)
        blocks = [BeautifulSoup(f"<p>{line}</p>", "html.parser").p
                  for line in raw.split("\n") if line.strip()]

    for p in blocks:
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        if _looks_like_junk(text):
            continue
        if strip_notes and re.match(r"^\s*(note|a/n|author'?s note)\b", text, re.I):
            continue
        # Escape then re-wrap so we emit safe, minimal markup.
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        paras.append(f"<p>{safe}</p>")

    return "\n".join(paras)
