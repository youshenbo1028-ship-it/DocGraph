"""PDF 解析器（文本层，FR-102 / FR-201）。"""

from __future__ import annotations

from ..core.models import Chunk
from .base import DocumentParser


class PdfParser(DocumentParser):
    format = "pdf"

    def parse(self, path: str) -> list[Chunk]:
        # TODO(M1): 使用 pdfplumber 提取文本与页码，按标题层级分块（FR-201/FR-202）
        # TODO(M1): 检测扫描版 PDF（文本量极低）并标记「疑似扫描件」（FR-203）
        raise NotImplementedError("M1: 实现 PDF 文本提取与分块")
