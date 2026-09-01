"""抽取解析与去重合并测试（FR-304 / FR-306 / FR-311）。"""

from __future__ import annotations

import pytest

from docgraph.core.models import Entity, Relation
from docgraph.extractors.base import ExtractionError, parse_extraction_result
from docgraph.extractors.prompts import build_system_prompt, build_user_prompt
from docgraph.graph.dedupe import entity_id, merge_entities, normalize_name

# ---------- FR-304：JSON 解析与校验 ----------

def test_parse_valid_json():
    raw = """
    {
      "entities": [
        {"canonical_name": "GNN", "type": "概念/方法/理论", "description": "图神经网络", "aliases": ["Graph Neural Network"], "confidence": 0.95},
        {"canonical_name": "Attention", "type": "概念/方法/理论", "confidence": 0.8}
      ],
      "relations": [
        {"source": "GNN", "target": "Attention", "type": "基于", "evidence": "GNN is based on attention.", "confidence": 0.9}
      ]
    }
    """
    result = parse_extraction_result(raw, chunk_id="c1")
    assert len(result.entities) == 2
    assert len(result.relations) == 1
    assert result.chunk_id == "c1"
    r = result.relations[0]
    assert r.evidence == ["GNN is based on attention."]
    assert result.entities[0].aliases == ["Graph Neural Network"]


def test_parse_fenced_json():
    fence = chr(96) * 3
    raw = fence + "json\n{\"entities\": [{\"canonical_name\": \"GNN\", \"type\": \"概念/方法/理论\", \"confidence\": 0.9}], \"relations\": []}\n" + fence
    result = parse_extraction_result(raw)
    assert result.entities[0].canonical_name == "GNN"


def test_parse_invalid_json_raises():
    with pytest.raises(ExtractionError):
        parse_extraction_result("这不是 JSON")


def test_parse_tolerates_missing_optional_fields():
    result = parse_extraction_result('{"entities": [{"canonical_name": "X"}], "relations": [{"source": "A", "target": "B", "type": "T"}]}')
    assert result.entities[0].type == ""
    assert result.entities[0].confidence == 0.0
    assert result.relations[0].evidence == []


def test_parse_skips_invalid_items():
    result = parse_extraction_result(
        '{"entities": [{"canonical_name": ""}, {"canonical_name": "OK", "confidence": "abc"}], "relations": [{"source": "", "target": "B", "type": "T"}]}'
    )
    assert len(result.entities) == 1
    assert result.entities[0].canonical_name == "OK"
    assert result.relations == []


# ---------- FR-311：Prompt 注入 ----------

def test_system_prompt_contains_types_and_known_entities():
    prompt = build_system_prompt(["概念/方法/理论", "人物"], ["提出", "基于"], known_entities=["GNN", "Transformer"])
    assert "概念/方法/理论" in prompt
    assert "提出" in prompt
    assert "已知实体列表" in prompt
    assert "- GNN" in prompt
    assert "复用其 canonical_name" in prompt


def test_user_prompt_contains_chunk():
    assert "内容块" in build_user_prompt("这是内容块")


# ---------- FR-306：去重合并 ----------

def test_normalize_name():
    assert normalize_name("Graph Neural Network") == normalize_name("graph neural network")
    assert normalize_name("（GNN）") == "(gnn)"  # NFKC 全角转半角
    assert normalize_name("  Attention  ") == "attention"


def test_entity_id_stable():
    assert entity_id("GNN") == entity_id("gnn")


def test_merge_same_name_across_chunks():
    candidates = [
        Entity(id="", canonical_name="GNN", type="概念/方法/理论", confidence=0.9, aliases=["Graph Neural Network"]),
        Entity(id="", canonical_name="GNN", type="概念/方法/理论", confidence=0.85),
    ]
    merged = merge_entities(candidates, [])
    assert len(merged.entities) == 1
    assert "Graph Neural Network" in merged.entities[0].aliases
    assert merged.entities[0].confidence == 0.9


def test_merge_alias_matches_canonical():
    candidates = [
        Entity(id="", canonical_name="GNN", confidence=0.9, aliases=["graph neural network"]),
        Entity(id="", canonical_name="Graph Neural Network", confidence=0.8),
    ]
    merged = merge_entities(candidates, [])
    assert len(merged.entities) == 1


def test_merge_similar_names():
    candidates = [
        Entity(id="", canonical_name="Attention Mechanism", confidence=0.9),
        Entity(id="", canonical_name="Attention mechanisms", confidence=0.8),
    ]
    merged = merge_entities(candidates, [], similarity_threshold=0.9)
    assert len(merged.entities) == 1


def test_relations_rewritten_to_ids():
    candidates = [
        Entity(id="", canonical_name="GNN", confidence=0.9),
        Entity(id="", canonical_name="Attention", confidence=0.9),
    ]
    relations = [Relation(id="", source_entity_id="GNN", target_entity_id="Attention", type="基于", evidence=["e1"])]
    merged = merge_entities(candidates, relations)
    assert len(merged.relations) == 1
    r = merged.relations[0]
    assert r.source_entity_id == entity_id("GNN")
    assert r.target_entity_id == entity_id("Attention")
    assert r.evidence == ["e1"]



def test_merge_resolves_directional_conflicts():
    """非对称关系反向矛盾：保留置信度高者，另一条进待确认（bug: 互相从属）。"""
    candidates = [
        Entity(id="", canonical_name="国务院", confidence=0.9),
        Entity(id="", canonical_name="办事机构", confidence=0.9),
    ]
    relations = [
        Relation(id="", source_entity_id="办事机构", target_entity_id="国务院", type="从属", confidence=0.95),
        Relation(id="", source_entity_id="国务院", target_entity_id="办事机构", type="从属", confidence=0.8),
    ]
    merged = merge_entities(candidates, relations)
    assert len(merged.relations) == 1, "应只保留一条从属关系"
    r = merged.relations[0]
    assert r.source_entity_id == entity_id("办事机构")  # 保留高置信度方向
    assert r.target_entity_id == entity_id("国务院")
    assert r.confidence == 0.95
    assert any(p["type"] == "directional_conflict" for p in merged.pending)


def test_merge_keeps_symmetric_bidirectional():
    """对称关系（如 比较）双向共存不视为矛盾。"""
    candidates = [
        Entity(id="", canonical_name="A", confidence=0.9),
        Entity(id="", canonical_name="B", confidence=0.9),
    ]
    relations = [
        Relation(id="", source_entity_id="A", target_entity_id="B", type="比较", confidence=0.7),
        Relation(id="", source_entity_id="B", target_entity_id="A", type="比较", confidence=0.6),
    ]
    merged = merge_entities(candidates, relations)
    assert len(merged.relations) == 2  # 对称关系双向保留

def test_duplicate_relations_merged():
    candidates = [
        Entity(id="", canonical_name="GNN", confidence=0.9),
        Entity(id="", canonical_name="Attention", confidence=0.9),
    ]
    relations = [
        Relation(id="", source_entity_id="GNN", target_entity_id="Attention", type="基于", confidence=0.7, evidence=["e1"]),
        Relation(id="", source_entity_id="GNN", target_entity_id="Attention", type="基于", confidence=0.9, evidence=["e2"]),
    ]
    merged = merge_entities(candidates, relations)
    assert len(merged.relations) == 1
    assert merged.relations[0].confidence == 0.9
    assert merged.relations[0].evidence == ["e1", "e2"]
