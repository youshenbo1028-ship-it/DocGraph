"""OpenAI 兼容 Provider（DeepSeek / OpenAI / 通义 / Kimi 等，FR-301）。"""

from __future__ import annotations

from openai import OpenAI

from ..core.models import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from .base import ExtractionError, ExtractionResult, Extractor, parse_extraction_result
from .prompts import build_system_prompt, build_user_prompt


class OpenAICompatibleExtractor(Extractor):
    """通过 OpenAI 兼容 chat.completions 接口完成结构化抽取。

    - response_format=json_object（DeepSeek/OpenAI/GLM/Kimi 均支持）；
    - 输出解析失败自动重试（最多 max_retries 次，FR-304）；
    - temperature 固定 0.1~0.3 保证一致性（FR-304）。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        # 为响应与连接设置合理超时，避免某次调用挂起数分钟（默认 600s）
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=90.0, max_retries=1)
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries

    def extract(
        self,
        chunk_text: str,
        known_entities: list[str] | None = None,
        chunk_id: str = "",
    ) -> ExtractionResult:
        # TODO(M1+): 类型表按分组加载（FR-310）；当前用默认类型表
        system = build_system_prompt(DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES, known_entities)
        user = build_user_prompt(chunk_text)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        last_error: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                import time

                t0 = time.time()
                resp = self._client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
                latency = int((time.time() - t0) * 1000)
                raw = (resp.choices[0].message.content or "").strip()
                result = parse_extraction_result(raw, chunk_id=chunk_id)
                # 记录调用轨迹（请求/响应/耗时）
                result.request = {"messages": messages}
                result.response = raw
                try:
                    result.raw_response = resp.model_dump_json()
                except Exception:
                    result.raw_response = str(resp)
                result.base_url = self._base_url
                result.model = self._model
                result.latency_ms = latency
                return result
            except ExtractionError as exc:
                last_error = exc  # 输出格式问题 -> 重试
            except Exception as exc:  # 网络/API 错误 -> 直接抛出
                raise ExtractionError(f"LLM 调用失败：{exc}") from exc
        raise ExtractionError(f"抽取输出解析失败（已重试 {self._max_retries} 次）：{last_error}")
