"""Upload hygiene: safe filenames, PDF sniffing, bounded reads."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import UploadFile

from app.errors import PayloadTooLargeError, ValidationError

_PDF_MAGIC = b"%PDF-"
_SAFE_CHARS = re.compile(r"[^\w. \-()\[\]]+")
_MAX_NAME = 120


def sanitize_filename(raw: str | None) -> str:
    """Return a display-safe basename ending in `.pdf`.

    Strips directories (both separators), control characters and anything
    outside a conservative allow-list. The stored file never uses this name;
    it is only shown back to the user.
    """
    name = (raw or "").strip()
    name = PureWindowsPath(name).name
    name = PurePosixPath(name).name
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = _SAFE_CHARS.sub("_", name).strip()
    if not name.lower().endswith(".pdf"):
        raise ValidationError("Only PDF files are supported.", code="unsupported_file_type")
    stem = name[:-4].strip(" ._") or "document"
    return f"{stem[:_MAX_NAME]}.pdf"


async def read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    """Read the body with a hard cap and verify the PDF signature.

    The cap is enforced while reading, so an oversized upload is rejected
    without buffering it all in memory first.
    """
    buffer = bytearray()
    while True:
        part = await upload.read(1024 * 1024)
        if not part:
            break
        buffer.extend(part)
        if len(buffer) > max_bytes:
            raise PayloadTooLargeError(
                f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.",
                details={"max_bytes": max_bytes},
            )
    if not buffer:
        raise ValidationError("The uploaded file is empty.", code="empty_file")
    if not bytes(buffer[:1024]).lstrip().startswith(_PDF_MAGIC):
        raise ValidationError("That file isn't a valid PDF.", code="invalid_pdf")
    return bytes(buffer)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
