from __future__ import annotations

import pytest

from app.services.chunking import chunk_pages, split_sentences
from app.services.pdf import Page, clean_page_text


def _words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n)) + "."


def test_split_sentences_handles_common_punctuation() -> None:
    text = "First sentence. Second one! Third? Fourth (with parens)."
    assert split_sentences(text) == ["First sentence.", "Second one!", "Third?", "Fourth (with parens)."]


def test_chunks_respect_budget_and_track_pages() -> None:
    pages = [
        Page(1, " ".join(_words(50, f"a{i}_") for i in range(4))),
        Page(2, " ".join(_words(50, f"b{i}_") for i in range(4))),
    ]
    chunks = chunk_pages(pages, chunk_size=120, overlap=50)
    assert len(chunks) >= 3
    assert all(c.word_count <= 120 for c in chunks)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_overlap_carries_tail_sentences_forward() -> None:
    sentences = [_words(40, f"S{i}_") for i in range(6)]
    chunks = chunk_pages([Page(1, " ".join(sentences))], chunk_size=100, overlap=45)
    # The first chunk holds sentences 0 and 1; the second must start with sentence 1 again.
    assert chunks[0].text.startswith("S0_0")
    assert "S1_0" in chunks[0].text
    assert chunks[1].text.startswith("S1_0")


def test_oversized_sentence_is_hard_split_not_dropped() -> None:
    long_sentence = " ".join(f"tok{i}" for i in range(700))
    chunks = chunk_pages([Page(3, long_sentence)], chunk_size=300, overlap=30)
    assert [c.word_count for c in chunks] == [300, 300, 100]
    assert all(c.page_start == c.page_end == 3 for c in chunks)


def test_invalid_parameters_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_pages([Page(1, "x")], chunk_size=0)
    with pytest.raises(ValueError):
        chunk_pages([Page(1, "x")], chunk_size=10, overlap=10)


def test_clean_page_text_repairs_extraction_artifacts() -> None:
    raw = "Infor-\nmation retrieval is\nuseful.\n\n\n\nNext   paragraph\there."
    assert clean_page_text(raw) == "Information retrieval is useful.\n\nNext paragraph here."
