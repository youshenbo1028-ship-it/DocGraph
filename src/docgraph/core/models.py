"""核心数据模型（对齐 PRD 7.3 数据模型）。

设计约束（FR-310 文档身份规则）：
- 项目内文档名（文件名）唯一，不允许重名；
- 所有文档视为独立文档，sha256 仅作内容指纹元数据，不驱动去重/合并；
- 一个文档属于一个分组（group_id）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# ---- 文档状态机（FR-103）----
DOC_STATUS_PENDING = "pending"  # 待处理
DOC_STATUS_PARSING = "parsing"  # 解析中
DOC_STATUS_PARSED = "parsed"  # 已解析
DOC_STATUS_EXTRACTING = "extracting"  # 抽取中
DOC_STATUS_EXTRACTED = "extracted"  # 已抽取
DOC_STATUS_FAILED = "failed"  # 失败

# ---- 默认实体/关系类型表（FR-302 / FR-303，学术场景）----
# 每组可独立覆盖（FR-310：组级抽取配置）
DEFAULT_ENTITY_TYPES = ["概念/方法/理论", "人物", "组织/机构", "论文/文献", "数据集/工具", "事件", "指标"]
DEFAULT_RELATION_TYPES = ["提出", "基于", "改进", "比较", "引用", "验证", "评价", "应用于", "属于"]

# ---- 法律法规场景预设（FR-310 组级类型表）----
# 法律文档的语义是规范性（规定/禁止/保护/依据…），与学术关系类型（提出/基于/属于…）本质不同；
# 用学术表抽法律文档会把「女职工——属于——劳动法」这种无信息量关系硬套出来。
# 预设表不追求穷尽，只保证语义匹配、可读性通顺（见 prompts.py 防垃圾规则）。
LEGAL_ENTITY_TYPES = [
    "法律/法规文件",
    "机构/组织",
    "人员/角色",
    "权利/义务",
    "行为/事项",
    "程序/制度",
    "处罚/责任",
    "概念/术语",
]
LEGAL_RELATION_TYPES = [
    "规定",
    "确立",
    "保护",
    "禁止",
    "监督",
    "实施",
    "依据",
    "授权",
    "处罚",
    "保障",
    "适用",
    "承担",
]

GROUP_PRESETS: dict[str, tuple[list[str], list[str]]] = {
    "academic": (DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES),
    "legal": (LEGAL_ENTITY_TYPES, LEGAL_RELATION_TYPES),
}


@dataclass
class Project:
    id: str
    name: str
    created_at: str
    config_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class Group:
    """文件分组（FR-310）：每组独立维护实体/关系类型表与抽取参数。"""

    id: str
    project_id: str
    name: str
    entity_types: list[str] = field(default_factory=lambda: list(DEFAULT_ENTITY_TYPES))
    relation_types: list[str] = field(default_factory=lambda: list(DEFAULT_RELATION_TYPES))
    extract_config: dict[str, Any] = field(default_factory=dict)  # temperature/并发/预算等


@dataclass
class Document:
    id: str
    project_id: str
    group_id: str  # 一个文档属于一个分组；未分组归入「默认组」
    path: str  # 文件路径；文件名在项目内唯一，不允许重名（FR-310）
    title: str = ""
    authors: str = ""
    year: str = ""
    format: str = ""  # pdf / docx / md / txt / html
    status: str = DOC_STATUS_PENDING
    sha256: str = ""  # 内容指纹元数据，不用于去重/合并

    @property
    def file_name(self) -> str:
        return os.path.basename(self.path)


@dataclass
class Chunk:
    """分块（FR-202）：携带来源定位（文档 ID + 页码 + 块序号）。"""

    id: str
    document_id: str
    page: int = 0
    seq: int = 0
    text: str = ""
    token_count: int = 0


@dataclass
class Entity:
    id: str
    canonical_name: str
    type: str = ""
    description: str = ""
    confidence: float = 0.0
    aliases: list[str] = field(default_factory=list)
    source_docs: list[str] = field(default_factory=list)


@dataclass
class Relation:
    id: str
    source_entity_id: str
    target_entity_id: str
    type: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)  # 原文摘录（FR-307）
    source_docs: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    id: str
    chunk_id: str
    document_id: str
    page: int = 0
    quote: str = ""
