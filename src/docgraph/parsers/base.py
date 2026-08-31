"""解析器抽象：所有文档解析器实现 DocumentParser（可插件化）。"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from ..core.models import Chunk

# FR-203：单页平均字符数低于该值视为疑似扫描版 PDF
SCANNED_PDF_MIN_CHARS_PER_PAGE = 50


class ScannedPdfError(ValueError):
    """疑似扫描版 PDF（无文本层），需要 OCR（MVP 不支持，FR-203）。"""

    def __init__(self, path: str, avg_chars_per_page: float) -> None:
        self.path = path
        self.avg_chars_per_page = avg_chars_per_page
        super().__init__(
            f"疑似扫描版 PDF，无法提取文本层（平均每页 {avg_chars_per_page:.0f} 字符 < {SCANNED_PDF_MIN_CHARS_PER_PAGE}）"
        )


def estimate_tokens(text: str) -> int:
    """token 粗估：中英混排按 2 字符 ≈ 1 token（FR-202 分块预算用）。"""
    return max(1, math.ceil(len(text) / 2))


class DocumentParser(ABC):
    """将单个文档解析为文本块序列（FR-201 / FR-202）。"""

    format: str = ""

    @abstractmethod
    def parse(self, path: str, document_id: str = "") -> list[Chunk]:
        """提取文本并按章节分块，块携带来源定位（文档 ID + 页码 + 块序号）。"""


def build_chunks(
    document_id: str,
    sections: list[tuple[int, str]],
    max_tokens: int = 3000,
    overlap_tokens: int = 200,
) -> list[Chunk]:
    """将 (页码, 文本) 段落切分为块（FR-202）。

    - 按 token 估算贪心累积，超限即断块；
    - 相邻块重叠 overlap_tokens（重复末尾文本，保证上下文连贯）；
    - 单个超长段落独占一块（不强行截断，M1 简化）。
    """
    chunks: list[Chunk] = []
    buffer: list[tuple[int, str]] = []
    buffer_tokens = 0
    seq = 0
    overlap_chars = overlap_tokens * 2  # 字符 ≈ 2× token

    for page, text in sections:
        text = text.strip()
        if not text:
            continue
        t = estimate_tokens(text)
        if buffer and buffer_tokens + t > max_tokens:
            chunk_page = buffer[0][0]
            chunk_text = "\n".join(p for _, p in buffer)
            chunks.append(
                Chunk(
                    id=f"{document_id}:c{seq}",
                    document_id=document_id,
                    page=chunk_page,
                    seq=seq,
                    text=chunk_text,
                    token_count=buffer_tokens,
                )
            )
            seq += 1
            tail = chunk_text[-overlap_chars:]
            buffer = [(page, tail)]
            buffer_tokens = estimate_tokens(tail)
        buffer.append((page, text))
        buffer_tokens += t

    if buffer:
        chunk_page = buffer[0][0]
        chunk_text = "\n".join(p for _, p in buffer)
        chunks.append(
            Chunk(
                id=f"{document_id}:c{seq}",
                document_id=document_id,
                page=chunk_page,
                seq=seq,
                text=chunk_text,
                token_count=buffer_tokens,
            )
        )
    return chunks
