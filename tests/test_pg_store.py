"""PostgreSQL 服务版存储测试（需要本地 PG 容器：docker compose up -d postgres）。

无 PG 环境时自动跳过（skipif）。
"""

from __future__ import annotations

import os

import pytest

from docgraph.core.models import Entity, Relation
from docgraph.core.store import ProjectStore

PG_URL = os.environ.get("DOCGRAPH_DATABASE_URL", "postgresql://docgraph:docgraph@127.0.0.1:5432/docgraph_meta")


def _pg_reachable() -> bool:
    try:
        import psycopg

        c = psycopg.connect(PG_URL, connect_timeout=2)
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_reachable(), reason="PostgreSQL 不可达（docker compose up -d postgres）")


@pytest.fixture
def pg_store(tmp_path):
    s = ProjectStore(tmp_path / "pgproj", db_url=PG_URL)
    yield s
    s.close()


def test_pg_create_project_and_group(pg_store):
    p = pg_store.create_project("PG 测试项目")
    assert p.id
    g = pg_store.create_group(p.id, "法律法规", preset="legal")
    assert "规定" in g.relation_types
    # 幂等重建
    s2 = ProjectStore(pg_store.project_dir, db_url=PG_URL)
    assert s2.get_project(p.id) is not None
    s2.close()


def test_pg_document_extraction_graph(pg_store):
    p = pg_store.create_project("PG 图测试")
    g = pg_store.create_group(p.id, "默认组")
    d = pg_store.add_document(p.id, g.id, str(pg_store.project_dir / "files" / "a.docx"), format="docx")
    pg_store.save_chunks(d.id, [])
    pg_store.save_extraction(
        d.id,
        [Entity(id="e1", canonical_name="女职工", type="人员/角色", confidence=0.9, aliases=["女工"])],
        [Relation(id="r1", source_entity_id="e1", target_entity_id="e1", type="规定", evidence=["原文"], confidence=0.9)],
    )
    graph = pg_store.get_graph(p.id)
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["data"]["label"] == "女职工"
    assert len(graph["edges"]) == 1
    # 详情与证据
    detail = pg_store.get_entity_detail("e1")
    assert detail["canonical_name"] == "女职工"
    assert "女工" in detail["aliases"]


def test_pg_list_projects_registry(pg_store):
    pg_store.create_project("PG 注册表测试")
    names = {p.name for p in pg_store.list_projects()}
    assert "PG 注册表测试" in names
