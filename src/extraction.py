"""Turns uploaded vendor documents into per-page text, ready for injection
screening and LLM extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class DocumentPage:
    document: str
    page: int
    text: str


def extract_pdf_pages(path: str | Path) -> list[DocumentPage]:
    path = Path(path)
    pages: list[DocumentPage] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(DocumentPage(document=path.name, page=i, text=text))
    return pages
