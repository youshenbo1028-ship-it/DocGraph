"""解析器注册表测试（FR-102）。"""

import pytest

from docgraph.parsers import get_parser


def test_parser_registry_mapping():
    """PDF 与 DOCX 为 M1 必选格式。"""
    assert get_parser("pdf").format == "pdf"
    assert get_parser("docx").format == "docx"


def test_unknown_format_raises():
    with pytest.raises(ValueError):
        get_parser("xyz")
