"""抽取器工厂：按分组配置构建 Extractor（FR-310 / FR-301）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.store import ProjectStore
from ..extractors.base import Extractor
from ..extractors.openai_compatible import OpenAICompatibleExtractor

# group_id -> Extractor；测试可注入假抽取器
ExtractorFactory = Callable[[str | None], Extractor]


@dataclass
class ApiConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2


def make_extractor_factory(store: ProjectStore, api: ApiConfig) -> ExtractorFactory:
    def build(group_id: str | None = None) -> Extractor:
        # TODO(M1+): 读取分组 extract_config 覆盖 temperature 等（FR-310）
        return OpenAICompatibleExtractor(
            base_url=api.base_url,
            api_key=api.api_key,
            model=api.model,
            temperature=api.temperature,
        )

    return build
