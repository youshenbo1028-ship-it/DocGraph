"""抽取器抽象：LLM Provider 可插拔（FR-301）。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.models import Entity, Relation


class ExtractionError(Exception):
    """抽取失败（LLM 调用错误 / 输出无法解析）。"""


@dataclass
class ExtractionResult:
    """单个文本块的抽取结果（FR-304 / FR-307）。"""

    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    chunk_id: str = ""
    raw: str = ""  # LLM 原始输出（调试/审计）

    # ---- 调用轨迹（供"调用日志"查看请求/响应，FR-3xx DEBUG） ----
    request: dict = field(default_factory=dict)  # 发送给 LLM 的 messages
    response: str = ""  # LLM 返回的内容（文本）
    raw_response: str = ""  # LLM 原始响应（JSON 字符串）
    base_url: str = ""
    model: str = ""
    latency_ms: int = 0


_FENCE = chr(96) * 3


def _strip_fence(text: str) -> str:
    """移除 markdown 代码块包裹（若存在）。"""
    text = text.strip()
    if text.startswith(_FENCE):
        body = text[len(_FENCE):]
        stripped = body.lstrip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        text = stripped
    if text.rstrip().endswith(_FENCE):
        text = text.rstrip()[: -len(_FENCE)]
    return text.strip()


def parse_extraction_result(raw: str, chunk_id: str = "") -> ExtractionResult:
    """解析并校验 LLM 输出的 JSON（FR-304）。

    - 容忍 markdown 代码块包裹；
    - 缺省字段补默认值；非法实体/关系（缺必填字段）直接丢弃。
    """
    text = _strip_fence(raw)
    if not text:
        raise ExtractionError("LLM 输出为空")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"LLM 输出不是合法 JSON：{exc.msg}") from exc
    if not isinstance(data, dict):
        raise ExtractionError("LLM 输出不是 JSON 对象")

    entities: list[Entity] = []
    relations: list[Relation] = []
    for item in data.get("entities") or []:
        name = str(item.get("canonical_name", "")).strip()
        if not name:
            continue
        entities.append(
            Entity(
                id="",  # 由合并阶段按规范化名称派生稳定 id
                canonical_name=name,
                type=str(item.get("type", "")),
                description=str(item.get("description", "")),
                confidence=_to_confidence(item.get("confidence")),
                aliases=[str(a).strip() for a in (item.get("aliases") or []) if str(a).strip()],
            )
        )
    for item in data.get("relations") or []:
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        rtype = str(item.get("type", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        if not (source and target and rtype):
            continue
        relations.append(
            Relation(
                id="",
                source_entity_id=source,  # 合并阶段解析为实体 id
                target_entity_id=target,
                type=rtype,
                confidence=_to_confidence(item.get("confidence")),
                evidence=[evidence] if evidence else [],
            )
        )
    return ExtractionResult(entities=entities, relations=relations, chunk_id=chunk_id, raw=raw)


def _to_confidence(value: object) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, c))


class Extractor(ABC):
    """对单个文本块执行实体与关系抽取。"""

    @abstractmethod
    def extract(
        self,
        chunk_text: str,
        known_entities: list[str] | None = None,
        chunk_id: str = "",
    ) -> ExtractionResult:
        """抽取实体与关系。

        known_entities: 已知实体上下文（FR-311 组内实体对齐：
            注入同组既有高频实体与相似候选，引导模型复用既有命名）。
        """
