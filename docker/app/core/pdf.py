"""Build a simple, readable PDF from chapters using fpdf2 (pure Python, no system deps).

fpdf2's built-in fonts are latin-1, so typographic characters (smart quotes, dashes,
ellipses) are normalized to ASCII and anything still outside latin-1 is replaced. This
keeps the image dependency-free at the cost of not rendering non-latin scripts — fine for
English web novels. Chapter headings are registered as PDF outline entries (bookmarks) for
navigation.
"""
from __future__ import annotations

from bs4 import BeautifulSoup
from fpdf import FPDF

from .epub import ChapterDoc

_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "--", "…": "...", " ": " ",
    "′": "'", "″": '"', "‑": "-", "​": "",
}


def _latin1(text: str) -> str:
    for k, v in _REPLACEMENTS.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def _paragraphs(clean_html: str) -> list[str]:
    soup = BeautifulSoup(clean_html or "", "html.parser")
    ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    return [p for p in ps if p]


def build_pdf(
    dest_path: str,
    *,
    title: str,
    author: str,
    chapters: list[ChapterDoc],
    page_size: str = "A5",
) -> str:
    page_size = page_size if page_size in ("A4", "A5") else "A5"
    pdf = FPDF(format=page_size)
    pdf.set_title(title)
    pdf.set_author(author or "Unknown")
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title page
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("Times", "B", 22)
    pdf.multi_cell(0, 11, _latin1(title), align="C")
    pdf.ln(4)
    pdf.set_font("Times", "", 13)
    pdf.multi_cell(0, 8, _latin1(f"by {author or 'Unknown'}"), align="C")

    for ch in chapters:
        pdf.add_page()
        heading = ch.title or f"Chapter {ch.number}"
        pdf.start_section(_latin1(heading))  # PDF outline / bookmark
        pdf.set_font("Times", "B", 15)
        pdf.multi_cell(0, 8, _latin1(heading))
        pdf.ln(2)
        pdf.set_font("Times", "", 11)
        for para in _paragraphs(ch.html):
            pdf.multi_cell(0, 6, _latin1(para))
            pdf.ln(1.5)

    pdf.output(dest_path)
    return dest_path
