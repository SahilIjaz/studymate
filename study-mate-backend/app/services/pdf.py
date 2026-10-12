"""PDF text extraction, one entry per page so citations can carry page numbers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from app.errors import ValidationError

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SINGLE_NEWLINE = re.compile(r"(?<!\n)\n(?!\n)")
_MULTI_SPACE = re.compile(r"[ \t\u00a0]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class Page:
    number: int  # 1-based
    text: str


def clean_page_text(text: str) -> str:
    """Repair the artefacts PDF extraction leaves behind.

    - re-join words hyphenated across line breaks ("infor-\\nmation")
    - turn hard-wrapped lines into flowing paragraphs, keeping blank-line breaks
    - collapse runs of whitespace
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _SINGLE_NEWLINE.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def extract_pages(path: Path, *, max_pages: int) -> list[Page]:
    """Extract text per page. Pages without a text layer are skipped.

    Raises ValidationError when the PDF is unreadable, too long, or carries no
    extractable text at all (a scanned PDF needs OCR, which we don't run).
    """
    pages: list[Page] = []
    try:
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > max_pages:
                raise ValidationError(
                    f"This PDF has {len(pdf.pages)} pages; the limit is {max_pages}.",
                    code="too_many_pages",
                )
            for i, page in enumerate(pdf.pages, start=1):
                raw = page.extract_text() or ""
                cleaned = clean_page_text(raw)
                if cleaned:
                    pages.append(Page(number=i, text=cleaned))
    except ValidationError:
        raise
    except Exception as exc:  # pdfminer raises a zoo of exception types
        raise ValidationError(
            "Couldn't read this PDF. It may be corrupted or encrypted.",
            code="unreadable_pdf",
        ) from exc

    if not pages:
        raise ValidationError(
            "No text layer found. This looks like a scanned PDF; run it through OCR first.",
            code="no_text_layer",
        )
    return pages
