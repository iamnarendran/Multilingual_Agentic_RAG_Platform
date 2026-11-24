"""Text cleaning and Indic-aware recursive chunking.

Chunks are sized in *characters* (scripts differ a lot in tokens-per-word, so characters
are the more predictable unit) and never cross page boundaries, so every chunk can be
cited with a page number.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Sentence enders: Latin . ! ?, Devanagari danda । and double danda ॥, Urdu ۔ and ؟
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।॥۔؟])\s+")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LATIN_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n([a-z])")
_SPACES = re.compile(r"[ \t ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


@dataclass
class Chunk:
    text: str
    page: int | None = None
    page_end: int | None = None


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)  # important for Indic scripts (composed forms)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _LATIN_HYPHEN_BREAK.sub(r"\1\2", text)  # "philo-\nsophy" -> "philosophy"
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MANY_NEWLINES.sub("\n\n", text)
    return text.strip()


def _split_keep(text: str, level: int) -> list[str]:
    """Split text at one separator level, keeping separators so "".join(parts) == text."""
    if level == 0:
        parts = re.split(r"(?<=\n\n)", text)
    elif level == 1:
        parts = re.split(r"(?<=\n)", text)
    elif level == 2:
        parts, last = [], 0
        for m in _SENTENCE_SPLIT.finditer(text):
            parts.append(text[last : m.end()])
            last = m.end()
        parts.append(text[last:])
    else:
        parts = re.split(r"(?<= )", text)
    return [p for p in parts if p]


_LEVELS = 4


def _atomize(text: str, size: int, level: int = 0) -> list[str]:
    """Break text into pieces no longer than `size`, preferring natural boundaries."""
    if len(text) <= size:
        return [text]
    if level >= _LEVELS:
        return [text[i : i + size] for i in range(0, len(text), size)]
    parts = _split_keep(text, level)
    if len(parts) == 1:
        return _atomize(text, size, level + 1)
    out: list[str] = []
    for part in parts:
        out.extend(_atomize(part, size, level + 1) if len(part) > size else [part])
    return out


def split_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    pieces = _atomize(text, chunk_size)
    chunks: list[str] = []
    window: list[str] = []
    window_len = 0
    for piece in pieces:
        if window and window_len + len(piece) > chunk_size:
            chunk = "".join(window).strip()
            if chunk:
                chunks.append(chunk)
            # keep a tail of the previous window as overlap
            while window and (window_len > overlap or window_len + len(piece) > chunk_size):
                window_len -= len(window[0])
                window.pop(0)
        window.append(piece)
        window_len += len(piece)
    # The window always holds the last piece (added after the last emit), so it's never pure overlap.
    tail = "".join(window).strip()
    if tail:
        chunks.append(tail)
    return chunks


def chunk_pages(pages: list[tuple[int | None, str]], chunk_size: int = 1000, overlap: int = 150) -> list[Chunk]:
    """Chunk a list of (page_number, text) units. Tiny neighbouring chunks are merged."""
    raw: list[Chunk] = []
    for page_no, text in pages:
        for piece in split_text(clean_text(text), chunk_size, overlap):
            raw.append(Chunk(text=piece, page=page_no, page_end=page_no))

    merged: list[Chunk] = []
    for chunk in raw:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and len(chunk.text) < chunk_size // 3
            and len(prev.text) + len(chunk.text) + 2 <= chunk_size
        ):
            prev.text = f"{prev.text}\n\n{chunk.text}"
            prev.page_end = chunk.page_end
        else:
            merged.append(chunk)
    return merged
