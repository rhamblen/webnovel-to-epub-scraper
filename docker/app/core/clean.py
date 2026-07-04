"""Normalize a chapter body into clean, EPUB-friendly XHTML (a series of <p>).

Kept deliberately conservative in Phase 1: drop scripts/styles/ads and site
watermarks, keep paragraph text. Later phases add per-adapter cleaning rules.
"""
from __future__ import annotations

import re
from collections import Counter

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


# --- Standard-phrase cleanup (Phase 7, Layers 0+2) ------------------------------------
#
# A second, countable pass over already-cleaned <p> markup. Unlike clean_chapter_html's
# exact-substring blocklist above (unchanged, still runs at scrape time), this catches
# spacing/punctuation-obfuscated and homoglyph-obfuscated site names plus mid-sentence
# injected fragments, and reports what it found so it can be surfaced in the UI.

# Site-agnostic boilerplate, expanded from _JUNK_SUBSTRINGS above (minus the site name,
# which is supplied per-book via Adapter.site_terms instead of hardcoded here).
_GENERIC_JUNK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Translator credit", r"\btranslator\s*:"),
    ("Editor credit", r"\beditor\s*:"),
    ("Read-more prompt", r"\bplease\s+reading\s+on\b"),
    ("Read-latest prompt", r"\bread\s+latest\s+chapters?\s+at\b"),
    ("Source-attribution prompt", r"\bthis\s+content\s+is\s+taken\s+from\b"),
)

_SEP = r"[\s._-]{0,2}"  # tolerate spacing/punctuation dropped between letters

# Unicode characters used to visually impersonate an ASCII letter — sites inject a brand
# name like "freewebnovel.com" with 1-3 letters swapped per occurrence to dodge exact-
# substring blocklists (e.g. "frёeωebɳovel.com", "fɾeeweɓnѳveɭ.com"). Drawn from the same
# families (Latin Extended-B hook letters, Greek, Cyrillic, fullwidth, small-capitals)
# confirmed live on a real scraped chapter, extended to the rest of a-z by analogy within
# those same families.
_CONFUSABLE_GROUPS: dict[str, str] = {
    "a": "aаαａᴀ",
    "b": "bƄɓｂʙ",
    "c": "cϲсƈｃᴄ",
    "d": "dԁɗｄᴅ",
    "e": "eеёēｅᴇ",
    "f": "fƒｆꜰ",
    "g": "gɡɠｇɢ",
    "h": "hһｈʜ",
    "i": "iіıｉɪ",
    "j": "jјʝｊᴊ",
    "k": "kκｋᴋ",
    "l": "lℓɭłｌʟ",
    "m": "mɱｍ๓ᴍ",
    "n": "nոɳηｎɴ",
    "o": "oοσѳоｏᴏ",
    "p": "pрρｐᴘ",
    "q": "qｑ",
    "r": "rɾгｒʀ",
    "s": "sѕｓꜱ",
    "t": "tτｔᴛ",
    "u": "uυｕᴜ",
    "v": "vνｖᴠ",
    "w": "wωｗᴡ",
    "x": "xхｘ",
    "y": "yγуｙʏ",
    "z": "zｚᴢ",
}


def _confusable_class(ch: str) -> str:
    """A regex fragment matching `ch` or any known Unicode look-alike of it."""
    group = _CONFUSABLE_GROUPS.get(ch.lower())
    if not group:
        return re.escape(ch)
    return "[" + "".join(re.escape(c) for c in group) + "]"


def _confusable_word(word: str) -> str:
    """A regex fragment for `word` (no spacing tolerance) that also matches per-letter
    homoglyph substitution, e.g. "com" also matches "cσ๓", "cѳm", "ƈom"."""
    return "".join(_confusable_class(ch) for ch in word)


# The obfuscator sometimes swaps letters inside the TLD too, not just the brand name
# (".cσ๓", ".ƈom") — matched with the same per-letter confusable tolerance, so the whole
# decorated suffix comes out in one match instead of leaving an orphaned ".xyz" behind.
_TLD_GROUP = "(?:\\.(?:" + "|".join(_confusable_word(t) for t in ("com", "net", "org", "vip", "app", "info")) + "))?"


def _spaced_token_pattern(token: str) -> re.Pattern[str]:
    """A regex for `token` that also matches spaced (`f r e e w e b n o v e l`), punctuated
    (`free-web-novel`), and homoglyph-obfuscated (`frёeωebɳovel`) variants. Also swallows a
    wrapping "(...)"/"[...]" and a trailing ".com"-style suffix as part of the same match, so
    a decorated watermark like "(freewebnovel.com)" is removed whole instead of leaving an
    orphaned "( .com)" behind."""
    body = _SEP.join(_confusable_class(ch) for ch in token)
    return re.compile(rf"[\(\[]?\s*\b{body}\b{_TLD_GROUP}\s*[\)\]]?", re.I)


def _scrub(text: str, patterns: list[tuple[str, re.Pattern]], counts: Counter) -> str:
    """Repeatedly strip matched junk fragments from a paragraph's text. If a match makes up
    most of what's left, drop the whole paragraph; otherwise remove just that fragment and
    keep looking (a paragraph rarely carries more than 1-2 injected fragments)."""
    for _ in range(5):
        for label, rx in patterns:
            m = rx.search(text)
            if not m:
                continue
            counts[label] += 1
            remainder = (text[:m.start()] + text[m.end():]).strip(" \t\n\r.,;:!?\"'-")
            if len(remainder) < 15 or len(remainder) < 0.2 * len(text):
                return ""  # the match effectively *was* the paragraph
            text = re.sub(r"\s{2,}", " ", text[:m.start()] + " " + text[m.end():]).strip()
            break
        else:
            break  # no pattern matched this round
    return text


def apply_standard_cleanup(html: str, site_terms: tuple[str, ...] = ()) -> tuple[str, Counter]:
    """Second pass over already-cleaned <p> markup: catches spacing-obfuscated site names and
    mid-sentence injected fragments Layer 0's plain substring match misses. Returns
    (new_html, Counter(label -> removals)) so callers can aggregate a report."""
    soup = BeautifulSoup(html or "", "html.parser")
    patterns = [(label, re.compile(pat, re.I)) for label, pat in _GENERIC_JUNK_PATTERNS]
    patterns += [("Site name", _spaced_token_pattern(t)) for t in site_terms]

    counts: Counter = Counter()
    paras: list[str] = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        text = _scrub(text, patterns, counts)
        if not text:
            continue
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        paras.append(f"<p>{safe}</p>")
    return "\n".join(paras), counts
