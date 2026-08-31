"""抽取器抽象：LLM Provider 可插拔（FR-301）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.models import Entity, Relation


@dataclass
class ExtractionResult:
    """单个文本块的抽取结果（FR-304 / FR-307）。"""

    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    chunk_id: str = ""
    raw: str = ""  # LLM 原始输出（调试/审计）


class Extractor(ABC):
    """对单个文本块执行实体与关系抽取。"""

    @abstractmethod
    def extract(
        self,
        chunk_text: str,
        known_entities: list[str] | None = None,
    ) -> ExtractionResult:
        """抽取实体与关系。

        known_entities: 已知实体上下文（FR-311 组内实体对齐：
            注入同组既有高频实体与相似候选，引导模型复用既有命名）。
        """
