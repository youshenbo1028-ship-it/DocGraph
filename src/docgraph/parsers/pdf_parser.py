"""PDF 解析器（文本层，FR-102 / FR-201 / FR-203）。"""

from __future__ import annotations

import pdfplumber

from ..core.models import Chunk
from .base import SCANNED_PDF_MIN_CHARS_PER_PAGE, DocumentParser, ScannedPdfError, build_chunks


class PdfParser(DocumentParser):
    format = "pdf"

    def parse(self, path: str, document_id: str = "") -> list[Chunk]:
        """提取文本（保留页码）并按章节分块；扫描版 PDF 抛 ScannedPdfError。"""
        sections: list[tuple[int, str]] = []
        total_chars = 0
        with pdfplumber.open(path) as pdf:
            n_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                total_chars += len(text)
                if text.strip():
                    sections.append((i, text))

        # FR-203：文本量极低 -> 疑似扫描件
        avg_chars = total_chars / max(n_pages, 1)
        if avg_chars < SCANNED_PDF_MIN_CHARS_PER_PAGE:
            raise ScannedPdfError(path, avg_chars)

        return build_chunks(document_id, sections)
