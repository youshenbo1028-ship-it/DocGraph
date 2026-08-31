"""核心数据模型测试（对齐 PRD 7.3 / FR-310）。"""

from docgraph.core.models import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    DOC_STATUS_PENDING,
    Document,
    Group,
)


def test_default_group_types_follow_prd():
    """分组默认继承全局类型表（FR-310：组级抽取配置）。"""
    g = Group(id="g1", project_id="p1", name="机器学习论文")
    assert g.entity_types == DEFAULT_ENTITY_TYPES
    assert g.relation_types == DEFAULT_RELATION_TYPES


def test_document_default_status_and_file_name():
    """文档默认状态为 pending，file_name 取路径文件名（FR-310 唯一命名）。"""
    d = Document(id="d1", project_id="p1", group_id="g1", path="C:/docs/报告.pdf")
    assert d.status == DOC_STATUS_PENDING
    assert d.file_name == "报告.pdf"
