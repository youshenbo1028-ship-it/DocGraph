"""实体/关系抽取的结构化输出约束（FR-304，JSON Schema / function calling）。"""

EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "description": "本块中识别到的实体",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_name": {"type": "string", "description": "规范名称，与已知实体同名时必须复用其规范名称"},
                    "type": {"type": "string", "description": "实体类型，必须取自类型表"},
                    "description": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}, "description": "别名，用于归一合并"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["canonical_name", "type", "confidence"],
            },
        },
        "relations": {
            "type": "array",
            "description": "实体间的有向语义关系",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "源实体 canonical_name"},
                    "target": {"type": "string", "description": "目标实体 canonical_name"},
                    "type": {"type": "string", "description": "关系类型，必须取自关系类型表"},
                    "evidence": {"type": "string", "description": "原文摘录（证据，FR-307）"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["source", "target", "type", "evidence", "confidence"],
            },
        },
    },
    "required": ["entities", "relations"],
}
