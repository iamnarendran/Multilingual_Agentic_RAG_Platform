"""Extract text from uploaded files (PDF, DOCX, TXT, MD, CSV).

PDFs get special care: many Indian-language PDFs use legacy fonts without a proper Unicode
mapping, so the embedded "text" is mojibake. We measure how garbled each page is and, when
Tesseract is installed, re-read garbled or scanned pages with OCR.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pymupdf
from docx import Document as DocxDocument

from app.rag.language import SCRIPT_TO_TESSERACT, script_counts

logger = logging.getLogger(__name__)

GARBLED_THRESHOLD = 0.05  # share of non-text glyphs above which a page is considered garbled
MIN_PAGE_CHARS = 25  # below this, a page with images is treated as scanned

_TESSDATA_CANDIDATES = [
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
    "/usr/local/share/tessdata",
    "/opt/homebrew/share/tessdata",
]


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedDocument:
    pages: list[tuple[int | None, str]]
    page_count: int | None = None
    ocr_pages: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(t for _, t in self.pages)


@dataclass(frozen=True)
class OcrConfig:
    enabled: bool = True
    languages: str = "eng+hin+tam"
    dpi: int = 200


# ---------------------------------------------------------------------------
# OCR availability
# ---------------------------------------------------------------------------


@lru_cache
def tessdata_dir() -> str | None:
    env = os.environ.get("TESSDATA_PREFIX")
    for candidate in ([env] if env else []) + _TESSDATA_CANDIDATES:
        if candidate and Path(candidate).is_dir() and any(Path(candidate).glob("*.traineddata")):
            return candidate
    return None


@lru_cache
def installed_ocr_languages() -> frozenset[str]:
    if not shutil.which("tesseract"):
        return frozenset()
    directory = tessdata_dir()
    if not directory:
        return frozenset()
    return frozenset(p.stem for p in Path(directory).glob("*.traineddata") if p.stem != "osd")


def ocr_available() -> bool:
    return bool(installed_ocr_languages())


def _ocr_langs_for(text: str, config: OcrConfig) -> str | None:
    """Pick Tesseract languages from the scripts seen in (possibly garbled) text."""
    installed = installed_ocr_languages()
    wanted = [lang for lang in config.languages.split("+") if lang in installed]
    if not wanted:
        return None
    hinted: list[str] = []
    for script, _ in script_counts(text).most_common(2):
        hinted.extend(lang for lang in SCRIPT_TO_TESSERACT.get(script, []) if lang in wanted)
    langs = list(dict.fromkeys(hinted + (["eng"] if "eng" in wanted else [])))
    if len(langs) <= (1 if "eng" in wanted else 0):
        langs = wanted  # nothing hinted (e.g. a scanned page): try all configured languages
    return "+".join(langs)


# ---------------------------------------------------------------------------
# Quality heuristics
# ---------------------------------------------------------------------------


def garbled_ratio(text: str) -> float:
    """Share of visible characters that are control/private-use/Latin-1-supplement glyphs.

    Clean text in any script scores ~0. Legacy-font Tamil/Hindi PDFs typically score 0.1+.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    bad = sum(
        1 for c in chars if unicodedata.category(c) in ("Cc", "Co", "Cs", "Cn") or c == "�" or 0x80 <= ord(c) <= 0xBF
    )
    return bad / len(chars)


_DIGITS = re.compile(r"\d+")


def strip_running_lines(
    pages: list[tuple[int | None, str]], edge: int = 4, min_share: float = 0.5
) -> list[tuple[int | None, str]]:
    """Remove running headers/footers: lines near the top or bottom that repeat on most pages.

    Exact repeats count as boilerplate. Lines that only repeat once digits are ignored ("Page 3 of
    128" / "Page 4 of 128", bare page numbers) count only when short, so body text that merely
    differs by a number is kept. Such boilerplate otherwise lands in every chunk and pollutes
    both search and citations.
    """
    if len(pages) < 4:
        return pages

    def exact(line: str) -> str:
        return " ".join(line.split()).casefold()

    def numbered(line: str) -> str:
        return _DIGITS.sub("#", exact(line))

    def edge_lines(lines: list[str]) -> set[int]:
        return set(range(min(edge, len(lines)))) | set(range(max(0, len(lines) - edge), len(lines)))

    exact_counts: Counter[str] = Counter()
    numbered_counts: Counter[str] = Counter()
    split_pages = []
    for page_no, text in pages:
        lines = [ln for ln in text.split("\n") if ln.strip()]
        edges = edge_lines(lines)
        split_pages.append((page_no, lines, edges))
        exact_counts.update({exact(lines[i]) for i in edges})
        numbered_counts.update({numbered(lines[i]) for i in edges})

    threshold = max(3, int(len(pages) * min_share))

    def is_boilerplate(line: str) -> bool:
        if exact_counts[exact(line)] >= threshold:
            return True
        key = numbered(line)
        return "#" in key and len(key.split()) <= 4 and numbered_counts[key] >= threshold

    return [
        (page_no, "\n".join(ln for i, ln in enumerate(lines) if not (i in edges and is_boilerplate(ln))))
        for page_no, lines, edges in split_pages
    ]


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def _extract_pdf(data: bytes, ocr: OcrConfig) -> ExtractedDocument:
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - pymupdf raises various error types
        raise ExtractionError(f"Could not open PDF: {exc}") from exc
    if pdf.needs_pass:
        raise ExtractionError("PDF is password protected.")

    pages: list[tuple[int | None, str]] = []
    ocr_pages = garbled_without_ocr = 0
    can_ocr = ocr.enabled and ocr_available()

    for index, page in enumerate(pdf, start=1):
        text = page.get_text("text")
        stripped = text.strip()
        garbled = garbled_ratio(stripped) > GARBLED_THRESHOLD
        scanned = len(stripped) < MIN_PAGE_CHARS and bool(page.get_images())

        if garbled or scanned:
            langs = _ocr_langs_for(stripped, ocr) if can_ocr else None
            if langs:
                try:
                    textpage = page.get_textpage_ocr(language=langs, dpi=ocr.dpi, full=True, tessdata=tessdata_dir())
                    text = page.get_text("text", textpage=textpage)
                    ocr_pages += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("OCR failed on page %s: %s", index, exc)
                    garbled_without_ocr += int(garbled)
            else:
                garbled_without_ocr += int(garbled)
                if garbled:
                    text = ""  # don't index mojibake

        pages.append((index, text))

    warnings: list[str] = []
    if garbled_without_ocr:
        warnings.append(
            f"{garbled_without_ocr} page(s) use a font without proper Unicode text and were skipped. "
            "Install Tesseract OCR (see README) to read them."
        )
    return ExtractedDocument(
        pages=strip_running_lines(pages), page_count=pdf.page_count, ocr_pages=ocr_pages, warnings=warnings
    )


def _extract_docx(data: bytes) -> ExtractedDocument:
    try:
        doc = DocxDocument(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Could not open DOCX: {exc}") from exc
    blocks = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))
    return ExtractedDocument(pages=[(None, "\n\n".join(blocks))])


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_csv(data: bytes, rows_per_block: int = 20) -> ExtractedDocument:
    text = _decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return ExtractedDocument(pages=[(None, "")])
    header, body = rows[0], rows[1:]

    def row_text(row: list[str]) -> str:
        parts = []
        for j, value in enumerate(row):
            if value.strip():
                name = header[j].strip() if j < len(header) and header[j].strip() else f"col{j + 1}"
                parts.append(f"{name}: {value.strip()}")
        return "; ".join(parts)

    # Each row becomes "column: value; ..." so chunks keep the header context.
    lines = [f"Row {i}: {row_text(row)}" for i, row in enumerate(body, start=1)]
    blocks = ["\n".join(lines[i : i + rows_per_block]) for i in range(0, len(lines), rows_per_block)]
    return ExtractedDocument(pages=[(None, "\n\n".join(blocks) or ", ".join(header))])


def extract_document(filename: str, data: bytes, ocr: OcrConfig | None = None) -> ExtractedDocument:
    ext = Path(filename).suffix.lower().lstrip(".")
    ocr = ocr or OcrConfig()
    if ext == "pdf":
        result = _extract_pdf(data, ocr)
    elif ext == "docx":
        result = _extract_docx(data)
    elif ext in ("txt", "md"):
        result = ExtractedDocument(pages=[(None, _decode_text(data))])
    elif ext == "csv":
        result = _extract_csv(data)
    else:
        raise ExtractionError(f"Unsupported file type: .{ext}")

    if not result.text.strip():
        if result.warnings:
            raise ExtractionError(" ".join(result.warnings))
        raise ExtractionError(
            "No readable text found in this file."
            + ("" if ocr_available() else " If it is a scanned PDF, install Tesseract OCR to read it.")
        )
    return result
