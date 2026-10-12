"""Sentence-aware, page-tracking text chunking.

Chunks are built by packing whole sentences up to a word budget, then
carrying the tail sentences forward as overlap so an answer that straddles a
boundary is still retrievable. Each chunk remembers the page range it came
from, which is what makes page-level citations possible downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.pdf import Page

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|\n{2,}")


@dataclass(slots=True)
class Chunk:
    index: int
    text: str
    page_start: int
    page_end: int
    word_count: int


@dataclass(slots=True)
class _Sentence:
    text: str
    page: int
    words: int


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text)]
    return [p for p in parts if p]


def _sentences(pages: list[Page]) -> list[_Sentence]:
    out: list[_Sentence] = []
    for page in pages:
        for sentence in split_sentences(page.text):
            out.append(_Sentence(sentence, page.number, len(sentence.split())))
    return out


def _flush(buffer: list[_Sentence], index: int) -> Chunk:
    text = " ".join(s.text for s in buffer)
    return Chunk(
        index=index,
        text=text,
        page_start=buffer[0].page,
        page_end=buffer[-1].page,
        word_count=sum(s.words for s in buffer),
    )


def chunk_pages(pages: list[Page], *, chunk_size: int = 300, overlap: int = 60) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    sentences = _sentences(pages)
    chunks: list[Chunk] = []
    buffer: list[_Sentence] = []
    buffered_words = 0

    for sentence in sentences:
        # A single sentence longer than the budget becomes its own chunk,
        # hard-split by words so nothing is silently dropped.
        if sentence.words > chunk_size:
            if buffer:
                chunks.append(_flush(buffer, len(chunks)))
                buffer, buffered_words = [], 0
            words = sentence.text.split()
            for start in range(0, len(words), chunk_size):
                piece = " ".join(words[start : start + chunk_size])
                chunks.append(
                    Chunk(
                        len(chunks),
                        piece,
                        sentence.page,
                        sentence.page,
                        len(piece.split()),
                    )
                )
            continue

        if buffered_words + sentence.words > chunk_size and buffer:
            chunks.append(_flush(buffer, len(chunks)))
            # Carry the tail forward as overlap.
            tail: list[_Sentence] = []
            tail_words = 0
            for prev in reversed(buffer):
                if tail_words + prev.words > overlap:
                    break
                tail.insert(0, prev)
                tail_words += prev.words
            buffer, buffered_words = tail, tail_words

        buffer.append(sentence)
        buffered_words += sentence.words

    if buffer:
        chunks.append(_flush(buffer, len(chunks)))

    return chunks
