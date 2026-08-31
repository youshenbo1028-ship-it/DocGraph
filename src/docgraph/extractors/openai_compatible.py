"""OpenAI 兼容 Provider（DeepSeek / OpenAI / 通义 / Kimi 等，FR-301）。"""

from __future__ import annotations

from openai import OpenAI

from .base import ExtractionResult, Extractor
from .schema import EXTRACTION_JSON_SCHEMA


class OpenAICompatibleExtractor(Extractor):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,  # FR-304：固定 0.1~0.3 保证一致性
    ) -> None:
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._temperature = temperature

    def extract(
        self,
        chunk_text: str,
        known_entities: list[str] | None = None,
    ) -> ExtractionResult:
        # TODO(M1): 组装系统提示词
        #   - 实体/关系类型表（按分组加载，FR-310）
        #   - JSON Schema（EXTRACTION_JSON_SCHEMA）+ few-shot 示例
        #   - known_entities 注入「已知实体上下文」，引导对齐既有命名（FR-311）
        # TODO(M1): 调用 chat.completions（response_format 约束），校验并解析输出（FR-304）
        raise NotImplementedError("M1: 实现 LLM 抽取调用")
