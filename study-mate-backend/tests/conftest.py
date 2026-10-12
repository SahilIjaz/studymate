"""Shared fixtures: an isolated app with a hashed embedder and a fake Claude."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.llm import Completed, Delta, StreamEvent
from app.services.retrieval import RetrievedChunk


def make_pdf(pages: list[str]) -> bytes:
    """Build a minimal, valid, text-layer PDF without any extra dependency."""

    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def wrap(text: str, width: int = 80) -> list[str]:
        words, lines, current = text.split(), [], ""
        for word in words:
            if len(current) + len(word) + 1 > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
        return lines

    objects: list[bytes] = []
    font_id = 3
    page_ids: list[int] = []
    next_id = 4
    page_objects: list[tuple[int, bytes]] = []
    for text in pages:
        content_lines = ["BT", "/F1 11 Tf", "72 740 Td", "13 TL"]
        for line in wrap(text):
            content_lines.append(f"({escape(line)}) Tj T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", "replace")
        content_id, page_id = next_id, next_id + 1
        next_id += 2
        page_ids.append(page_id)
        page_objects.append(
            (content_id, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        )
        page_objects.append(
            (
                page_id,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (content_id, font_id),
            )
        )

    kids = " ".join(f"{pid} 0 R" for pid in page_ids).encode()
    objects.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objects.append((2, b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)))
    objects.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objects.extend(page_objects)

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for oid, body in objects:
        offsets[oid] = len(out)
        out += b"%d 0 obj\n" % oid + body + b"\nendobj\n"
    xref_pos = len(out)
    count = max(offsets) + 1
    out += b"xref\n0 %d\n" % count
    out += b"0000000000 65535 f \n"
    for oid in range(1, count):
        out += b"%010d 00000 n \n" % offsets.get(oid, 0)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (count, xref_pos)
    return bytes(out)


class FakeClaude:
    """Stands in for Claude: deterministic answers that cite the first source."""

    configured = True
    provider = "claude"
    model = "claude-opus-5-5"
    fast_model = "claude-haiku-5-5"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def stream_answer(
        self, *, question: str, sources: list[RetrievedChunk], history: list[tuple[str, str]]
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append({"question": question, "sources": sources, "history": history})
        yield Delta("The answer is in ")
        yield Delta(f"{sources[0].filename} [1].")
        yield Completed(
            model="fake-model", stop_reason="end_turn", usage={"input_tokens": 10, "output_tokens": 5}
        )

    async def condense_question(self, history: list[tuple[str, str]], question: str) -> str:
        return question

    async def suggest_questions(self, excerpt: str) -> list[str]:
        return [
            "What is photosynthesis?",
            "Where does it happen?",
            "What is produced?",
            "Why is light needed?",
        ]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        embedding_provider="hashed",
        anthropic_api_key=None,
        rate_limit_ask_per_minute=100,
        rate_limit_upload_per_minute=100,
        min_dense_similarity=0.05,
        query_rewrite=False,
        _env_file=None,
    )


@pytest.fixture
def fake_claude() -> FakeClaude:
    return FakeClaude()


@pytest.fixture
def client(settings: Settings, fake_claude: FakeClaude) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        app.state.services.claude = fake_claude
        yield test_client


@pytest.fixture
def workspace() -> dict[str, str]:
    return {"X-Workspace-Id": str(uuid.uuid4())}


PHOTOSYNTHESIS = (
    "Photosynthesis is the process by which green plants convert light energy into chemical energy. "
    "It takes place in the chloroplasts, where chlorophyll absorbs sunlight. "
    "The overall reaction combines carbon dioxide and water to produce glucose and oxygen. "
    "The light-dependent reactions occur in the thylakoid membranes and generate ATP and NADPH. "
    "The Calvin cycle then uses ATP and NADPH to fix carbon dioxide into sugars in the stroma."
)

MITOSIS = (
    "Mitosis is the division of a eukaryotic cell nucleus into two genetically identical nuclei. "
    "Its phases are prophase, metaphase, anaphase and telophase, followed by cytokinesis. "
    "During metaphase the chromosomes align along the equatorial plate of the spindle. "
    "Anaphase separates sister chromatids toward opposite poles of the cell."
)


@pytest.fixture
def photosynthesis_pdf() -> bytes:
    return make_pdf([PHOTOSYNTHESIS, MITOSIS])
