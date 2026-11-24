"""Multilingual BM25 sparse vectors for Qdrant hybrid search.

Why custom: generic tokenizers split Indic words at combining vowel signs (matras), e.g.
"किताब" -> "क", "त", "ब". We tokenize on Unicode letters + marks + digits so whole words
survive in every script. Each token is hashed to a stable 32-bit index; the value is the
BM25 term-frequency part. Qdrant applies the IDF part server-side (Modifier.IDF).
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections import Counter
from dataclasses import dataclass

import regex

_TOKEN = regex.compile(r"[\p{L}\p{M}\p{N}]+")

# Tiny English stopword list (other languages rely on IDF to down-weight common words)
_STOPWORDS = frozenset(
    """a an and are as at be but by for from has have he her his i in is it its me my of on or
    our she so than that the their them they this to us was we were what when where which who
    why will with you your""".split()
)


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).casefold()
    tokens = []
    for tok in _TOKEN.findall(text):
        if tok in _STOPWORDS:
            continue
        if len(tok) == 1 and tok.isascii():
            continue
        tokens.append(tok)
    return tokens


def _index(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest(), "big")


def encode_document(text: str, k1: float = 1.2, b: float = 0.75, avg_len: float = 150.0) -> SparseVector:
    tokens = tokenize(text)
    if not tokens:
        return SparseVector([], [])
    counts = Counter(tokens)
    doc_len = len(tokens)
    weights: dict[int, float] = {}
    for token, tf in counts.items():
        score = tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avg_len))
        idx = _index(token)
        weights[idx] = weights.get(idx, 0.0) + score
    indices = sorted(weights)
    return SparseVector(indices, [round(weights[i], 4) for i in indices])


def encode_query(text: str) -> SparseVector:
    indices = sorted({_index(t) for t in tokenize(text)})
    return SparseVector(indices, [1.0] * len(indices))
