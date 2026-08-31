"""Word（DOCX）解析器（FR-102 / FR-201）。"""

from __future__ import annotations

from ..core.models import Chunk
from .base import DocumentParser


class DocxParser(DocumentParser):
    format = "docx"

    def parse(self, path: str) -> list[Chunk]:
        # TODO(M1): 使用 python-docx 提取段落/表格文本，按标题层级分块（FR-201/FR-202）
        raise NotImplementedError("M1: 实现 DOCX 文本提取与分块")
