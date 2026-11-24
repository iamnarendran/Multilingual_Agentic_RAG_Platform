"""Chunking, language detection and sparse tokenization."""

from __future__ import annotations

import unicodedata

import pytest

from app.rag.chunking import chunk_pages, clean_text, split_text
from app.rag.language import detect_language
from app.rag.sparse import encode_document, encode_query, tokenize


def test_split_text_respects_size_and_overlaps():
    text = " ".join(f"Sentence number {i} talks about Stoic philosophy." for i in range(200))
    chunks = split_text(text, chunk_size=300, overlap=60)
    assert len(chunks) > 10
    assert all(len(c) <= 300 for c in chunks)
    # consecutive chunks share some text (overlap)
    assert any(chunks[i][-30:].split()[-1] in chunks[i + 1] for i in range(len(chunks) - 1))


def test_split_text_prefers_danda_sentence_boundaries():
    text = "भारत एक विशाल देश है। इसकी राजधानी नई दिल्ली है। " * 30
    chunks = split_text(text, chunk_size=150, overlap=30)
    assert all(len(c) <= 150 for c in chunks)
    assert all(c.endswith("।") for c in chunks[:-1])  # every cut lands on a danda


def test_split_text_hard_splits_unbroken_text():
    chunks = split_text("x" * 1000, chunk_size=300, overlap=50)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks).count("x") >= 1000


def test_split_text_rejects_bad_overlap():
    with pytest.raises(ValueError):
        split_text("abc", chunk_size=100, overlap=100)


def test_clean_text_normalizes():
    decomposed = unicodedata.normalize("NFD", "café")
    cleaned = clean_text(f"philo-\nsophy  is\x00 good\n\n\n\n{decomposed}")
    assert "philosophy is good" in cleaned
    assert "\x00" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "café" in cleaned and unicodedata.is_normalized("NFC", cleaned)


def test_chunk_pages_keeps_page_numbers_and_merges_small_chunks():
    pages = [(1, "Short intro."), (2, "Tiny."), (3, "A long page. " * 80)]
    chunks = chunk_pages(pages, chunk_size=300, overlap=50)
    assert chunks[0].page == 1 and chunks[0].page_end == 2  # pages 1 and 2 merged
    assert "Tiny." in chunks[0].text
    assert all(c.page == 3 for c in chunks[1:])


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("What is the capital of India and why was it chosen?", "en"),
        ("भारत की राजधानी क्या है?", "hi"),
        ("माझे नाव राहुल आहे आणि मी पुण्यात राहतो आणि मला पुस्तके वाचायला आवडतात", "mr"),
        ("இந்தியாவின் தலைநகரம் என்ன?", "ta"),
        ("ఇండియా రాజధాని ఏమిటి?", "te"),
        ("ಭಾರತದ ರಾಜಧಾನಿ ಯಾವುದು?", "kn"),
        ("ഇന്ത്യയുടെ തലസ്ഥാനം ഏതാണ്?", "ml"),
        ("ভারতের রাজধানী কী?", "bn"),
        ("ભારતની રાજધાની શું છે?", "gu"),
        ("ਭਾਰਤ ਦੀ ਰਾਜਧਾਨੀ ਕੀ ਹੈ?", "pa"),
        ("ଭାରତର ରାଜଧାନୀ କଣ?", "or"),
        ("hi", "en"),
    ],
)
def test_detect_language(text: str, code: str):
    assert detect_language(text).code == code


def test_tokenize_keeps_indic_words_whole():
    assert tokenize("भारत की राजधानी नई दिल्ली है।") == ["भारत", "की", "राजधानी", "नई", "दिल्ली", "है"]
    assert tokenize("இந்தியாவின் தலைநகரம் என்ன?") == ["இந்தியாவின்", "தலைநகரம்", "என்ன"]
    assert tokenize("The Emperor's MEDITATIONS") == ["emperor", "meditations"]  # stopwords + 1-char dropped


def test_sparse_vectors_are_stable_and_weighted():
    doc = encode_document("stoic stoic emperor")
    assert doc.indices == sorted(doc.indices)
    assert len(doc.indices) == 2
    q = encode_query("Stoic emperor")
    assert set(q.indices) == set(doc.indices)
    assert q.values == [1.0, 1.0]
    weights = dict(zip(doc.indices, doc.values, strict=True))
    assert weights[encode_query("stoic").indices[0]] > weights[encode_query("emperor").indices[0]]
