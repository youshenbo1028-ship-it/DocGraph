"""解析器抽象：所有文档解析器实现 DocumentParser（可插件化）。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.models import Chunk


class DocumentParser(ABC):
    """将单个文档解析为文本块序列（FR-201 / FR-202）。"""

    format: str = ""

    @abstractmethod
    def parse(self, path: str) -> list[Chunk]:
        """提取文本并按章节分块，块携带来源定位（文档 ID + 页码 + 块序号）。"""


def build_chunks(
    document_id: str,
    sections: list[tuple[int, str]],
    max_tokens: int = 3000,
    overlap_tokens: int = 200,
) -> list[Chunk]:
    """将 (页码, 文本) 段落切分为块。

    TODO(M1): 按 token 估算切分，相邻块重叠 overlap_tokens（FR-202）。
    """
    raise NotImplementedError("M1: 实现分块逻辑（FR-202）")
