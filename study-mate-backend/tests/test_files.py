from __future__ import annotations

from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from app.core.files import read_upload, sanitize_filename
from app.core.ids import is_workspace_id
from app.core.rate_limit import TokenBucketLimiter
from app.errors import PayloadTooLargeError, ValidationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("notes.pdf", "notes.pdf"),
        ("Lecture 3 (final).PDF", "Lecture 3 (final).pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\me\\My Notes.pdf", "My Notes.pdf"),
        ("weird\x00name\x07.pdf", "weirdname.pdf"),
        ("résumé.pdf", "résumé.pdf"),
        (".pdf", "document.pdf"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", ["notes.txt", "notes", "", None, "archive.pdf.exe"])
def test_sanitize_filename_rejects_non_pdf(raw: str | None) -> None:
    with pytest.raises(ValidationError):
        sanitize_filename(raw)


async def test_read_upload_enforces_size_and_magic() -> None:
    small = UploadFile(BytesIO(b"%PDF-1.4 hello"), filename="a.pdf")
    assert await read_upload(small, max_bytes=100) == b"%PDF-1.4 hello"

    big = UploadFile(BytesIO(b"%PDF-" + b"x" * 200), filename="a.pdf")
    with pytest.raises(PayloadTooLargeError):
        await read_upload(big, max_bytes=100)

    fake = UploadFile(BytesIO(b"MZ not a pdf"), filename="a.pdf")
    with pytest.raises(ValidationError) as exc:
        await read_upload(fake, max_bytes=100)
    assert exc.value.code == "invalid_pdf"

    empty = UploadFile(BytesIO(b""), filename="a.pdf")
    with pytest.raises(ValidationError):
        await read_upload(empty, max_bytes=100)


def test_workspace_id_validation() -> None:
    assert is_workspace_id("123e4567-e89b-12d3-a456-426614174000")
    assert not is_workspace_id("not-a-uuid")
    assert not is_workspace_id("../etc")


def test_token_bucket_limits_then_refills() -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_minute=60)
    assert limiter.try_acquire("k")[0]
    assert limiter.try_acquire("k")[0]
    allowed, wait = limiter.try_acquire("k")
    assert not allowed
    assert 0 < wait <= 1.0
    # Different keys have independent buckets.
    assert limiter.try_acquire("other")[0]
