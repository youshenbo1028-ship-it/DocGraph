"""抽取 Prompt 组装（FR-304 / FR-311）。

- 类型表按分组注入（FR-310）；
- known_entities 注入「已知实体上下文」，引导模型复用既有命名（FR-311）；
- 输出约束为严格 JSON（json_object 模式 + 系统提示词约束）。
"""

from __future__ import annotations

from typing import Iterable


def build_system_prompt(
    entity_types: Iterable[str],
    relation_types: Iterable[str],
    known_entities: Iterable[str] | None = None,
) -> str:
    lines = [
        "你是一个文档知识图谱抽取引擎。你的任务是从给定的文档文本块中抽取【实体】与【实体间关系】，并输出严格 JSON。",
        "",
        "## 实体类型表（type 只能取以下值之一）",
        *[f"- {t}" for t in entity_types],
        "",
        "## 关系类型表（relation 的 type 只能取以下值之一）",
        *[f"- {t}" for t in relation_types],
        "",
        "## 输出格式（只输出 JSON，不要任何解释文字）",
        "{",
        '  "entities": [',
        '    {"canonical_name": "规范名称", "type": "实体类型", "description": "一句话描述", "aliases": ["别名"], "confidence": 0.9}',
        "  ],",
        '  "relations": [',
        '    {"source": "源实体规范名称", "target": "目标实体规范名称", "type": "关系类型", "evidence": "原文摘录", "confidence": 0.9}',
        "  ]",
        "}",
        "",
        "## 规则",
        "1. canonical_name 使用规范名称：统一大小写、全半角、括号写法；",
        "2. evidence 必须是原文中的摘录（逐字引用），不得编造；",
        "3. confidence 为 0~1 的浮点数，表示抽取把握；",
        "4. 只抽取明确出现在文本中的实体与关系，宁缺毋滥；",
        "5. 若实体与【已知实体列表】中的实体是同一对象，必须复用其 canonical_name。",
        "6. 关系具有方向性：如「A 从属 B」表示 A 是 B 的下级/组成部分；同一对实体不要同时输出互为反向的同一关系（如既 A 从属 B 又 B 从属 A），只保留语义正确方向；",
        "7. 不抽取互相矛盾的关系，若无法确定方向则不输出该关系。",
    ]
    if known_entities:
        lines += [
            "",
            "## 已知实体列表（与本列表同名的实体必须复用 canonical_name）",
            *[f"- {name}" for name in known_entities],
        ]
    return "\n".join(lines)


def build_user_prompt(chunk_text: str) -> str:
    return f"以下是文档文本块：\n\n{chunk_text}"
