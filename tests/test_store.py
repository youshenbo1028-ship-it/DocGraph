"""存储层测试（FR-310 / FR-701 / FR-105）。"""

from __future__ import annotations

import pytest

from docgraph.core.models import DOC_STATUS_PARSED, Chunk, Document, Entity, Group, Relation
from docgraph.core.store import DuplicateNameError, ProjectStore


@pytest.fixture
def store(tmp_path):
    s = ProjectStore(tmp_path / "proj")
    yield s
    s.close()


def test_create_project_creates_default_group(store):
    p = store.create_project("测试项目")
    groups = store.list_groups(p.id)
    assert len(groups) == 1
    assert groups[0].name == "默认组"  # FR-310：未分组文档归入默认组


def test_group_independent_type_tables(store):
    p = store.create_project("测试项目")
    g = store.create_group(p.id, "医疗文献", entity_types=["疾病", "药物"], relation_types=["治疗"])
    assert g.entity_types == ["疾病", "药物"]
    assert g.relation_types == ["治疗"]
    default = store.list_groups(p.id)[0]
    assert "疾病" not in default.entity_types  # 组间类型表隔离（FR-310）


def test_document_name_unique_per_project(store):
    p = store.create_project("测试项目")
    g = store.list_groups(p.id)[0]
    store.add_document(p.id, g.id, "files/a.pdf", format="pdf")
    with pytest.raises(DuplicateNameError):
        store.add_document(p.id, g.id, "files/a.pdf", format="pdf")


def test_save_extraction_aggregates_source_docs(store):
    p = store.create_project("测试项目")
    g = store.list_groups(p.id)[0]
    d1 = store.add_document(p.id, g.id, "files/a.pdf", format="pdf")
    d2 = store.add_document(p.id, g.id, "files/b.pdf", format="pdf")

    e = Entity(id="e1", canonical_name="GNN", type="概念/方法/理论", confidence=0.9)
    r = Relation(id="r1", source_entity_id="e1", target_entity_id="e2", type="提出", confidence=0.8, evidence=["原文摘录"])
    store.save_extraction(d1.id, [e], [r])
    store.save_extraction(d2.id, [e], [r])

    graph = store.get_graph(p.id)
    assert len(graph["nodes"]) == 1
    assert len(graph["edges"]) == 1
    # 来源文档聚合（FR-311：组内多文档共用同一实体）
    assert set(store._db.execute("SELECT source_docs_json FROM entities").fetchone()["source_docs_json"].split('"')) >= {d1.id, d2.id}


def test_delete_document_cascades(store):
    p = store.create_project("测试项目")
    g = store.list_groups(p.id)[0]
    d1 = store.add_document(p.id, g.id, "files/a.pdf", format="pdf")
    store.set_document_status(d1.id, DOC_STATUS_PARSED)
    store.save_chunks(d1.id, [Chunk(id=f"{d1.id}:c0", document_id=d1.id, page=1, seq=0, text="内容", token_count=1)])
    store.save_extraction(d1.id, [Entity(id="e1", canonical_name="GNN", type="概念/方法/理论")], [])
    assert len(store.list_chunks(d1.id)) == 1

    store.delete_document(d1.id)

    assert store.get_document(d1.id) is None
    assert store.list_chunks(d1.id) == []
    graph = store.get_graph(p.id)
    assert graph["nodes"] == []  # 实体随文档删除消失（FR-105）


def test_get_graph_group_filter(store):
    p = store.create_project("测试项目")
    g1 = store.list_groups(p.id)[0]
    g2 = store.create_group(p.id, "第二组")
    d1 = store.add_document(p.id, g1.id, "files/a.pdf", format="pdf")
    d2 = store.add_document(p.id, g2.id, "files/b.pdf", format="pdf")
    store.save_extraction(d1.id, [Entity(id="e1", canonical_name="GNN", type="概念/方法/理论")], [])
    store.save_extraction(d2.id, [Entity(id="e2", canonical_name="Transformer", type="概念/方法/理论")], [])

    assert len(store.get_graph(p.id, group_id=g1.id)["nodes"]) == 1  # 组内隔离（FR-508）
    assert len(store.get_graph(p.id)["nodes"]) == 2  # 全部聚合视图
