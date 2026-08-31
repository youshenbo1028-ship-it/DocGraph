"""LLM 抽取器：provider 抽象 + prompt + JSON Schema（FR-301）。"""

from .base import ExtractionResult, Extractor
from .openai_compatible import OpenAICompatibleExtractor

__all__ = ["ExtractionResult", "Extractor", "OpenAICompatibleExtractor"]
