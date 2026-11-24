"""Text extraction from real sample files (English PDF, legacy-font Tamil PDF) and other formats."""

from __future__ import annotations

import io

import pymupdf
import pytest
from docx import Document as DocxDocument

from app.rag.extraction import (
    ExtractionError,
    OcrConfig,
    extract_document,
    garbled_ratio,
    ocr_available,
    strip_running_lines,
)
from tests.conftest import SAMPLE_DOCS


def _pdf_pages(name: str, first: int, last: int) -> bytes:
    src = pymupdf.open(SAMPLE_DOCS / name)
    out = pymupdf.open()
    out.insert_pdf(src, from_page=first, to_page=last)
    return out.tobytes()


def test_english_pdf_extracts_clean_text_with_pages():
    doc = extract_document("sample_en.pdf", (SAMPLE_DOCS / "sample_en.pdf").read_bytes())
    assert doc.page_count == 128
    assert doc.ocr_pages == 0
    assert "Marcus Aurelius" in doc.text
    assert garbled_ratio(doc.text) < 0.01
    assert doc.pages[0][0] == 1
    # running header/footer boilerplate printed on every page is stripped
    assert "philaletheians" not in doc.text
    assert "Page 3 of 128" not in doc.text


def test_strip_running_lines_keeps_content():
    pages = [
        (i, f"Annual Report 2024\nChapter {1 + i // 3}\nUnique fact number {i} about rivers.\n{i}") for i in range(1, 9)
    ]
    cleaned = dict(strip_running_lines(pages))
    assert cleaned[5] == "Unique fact number 5 about rivers."  # header, chapter line (#) and page number removed
    assert strip_running_lines(pages[:3]) == pages[:3]  # too few pages to judge


def test_legacy_font_tamil_pdf_is_detected_as_garbled():
    raw = pymupdf.open(stream=_pdf_pages("sample_ta.pdf", 5, 5), filetype="pdf")[0].get_text()
    assert garbled_ratio(raw) > 0.05


def test_garbled_pages_are_skipped_with_a_clear_message_when_ocr_is_off():
    with pytest.raises(ExtractionError, match="font without proper Unicode"):
        extract_document("ta.pdf", _pdf_pages("sample_ta.pdf", 5, 6), OcrConfig(enabled=False))


@pytest.mark.skipif(not ocr_available(), reason="Tesseract OCR is not installed")
def test_garbled_tamil_pages_are_recovered_with_ocr():
    doc = extract_document("ta.pdf", _pdf_pages("sample_ta.pdf", 5, 5), OcrConfig(languages="eng+tam"))
    assert doc.ocr_pages == 1
    assert garbled_ratio(doc.text) < 0.01
    tamil_chars = sum(1 for c in doc.text if 0x0B80 <= ord(c) <= 0x0BFF)
    assert tamil_chars > 100


def test_docx_paragraphs_and_tables():
    d = DocxDocument()
    d.add_paragraph("राजधानी नई दिल्ली है।")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "City", "State"
    table.cell(1, 0).text, table.cell(1, 1).text = "Chennai", "Tamil Nadu"
    buf = io.BytesIO()
    d.save(buf)
    doc = extract_document("notes.docx", buf.getvalue())
    assert "राजधानी" in doc.text
    assert "Chennai | Tamil Nadu" in doc.text


def test_csv_rows_keep_header_context():
    data = "city,population\nMumbai,12442373\nசென்னை,4646732\n".encode()
    doc = extract_document("cities.csv", data)
    assert "Row 1: city: Mumbai; population: 12442373" in doc.text
    assert "Row 2: city: சென்னை" in doc.text


def test_txt_with_bom_and_unsupported_and_empty():
    assert extract_document("a.txt", "﻿नमस्ते दुनिया".encode()).text == "नमस्ते दुनिया"
    with pytest.raises(ExtractionError, match="Unsupported"):
        extract_document("a.exe", b"MZ")
    with pytest.raises(ExtractionError, match="No readable text"):
        extract_document("a.txt", b"   \n  ")
