"""文档解析器（可插件化扩展，FR-102）。"""

from .base import DocumentParser, build_chunks
from .docx_parser import DocxParser
from .pdf_parser import PdfParser

_REGISTRY: dict[str, type[DocumentParser]] = {
    PdfParser.format: PdfParser,
    DocxParser.format: DocxParser,
    # TODO(V1.1): md / txt / html（FR-106）
}


def get_parser(fmt: str) -> DocumentParser:
    """按格式取解析器；未知格式抛 ValueError。"""
    try:
        return _REGISTRY[fmt]()
    except KeyError:
        raise ValueError(
            f"不支持的文档格式: {fmt}（当前支持: {sorted(_REGISTRY)}）"
        ) from None


__all__ = ["DocumentParser", "build_chunks", "get_parser"]
