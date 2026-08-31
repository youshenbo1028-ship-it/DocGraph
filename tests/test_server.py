"""服务层集成测试：导入 -> 解析 -> 抽取（假抽取器）-> 图谱查询。"""

from __future__ import annotations

import io

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

import docgraph.server.app as app_mod
from docgraph.core.models import Entity, Relation
from docgraph.extractors.base import ExtractionResult

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FakeExtractor:
    """固定返回 GNN -> Transformer 关系的假抽取器（不联网）。"""

    def extract(self, chunk_text, known_entities=None, chunk_id=""):
        return ExtractionResult(
            entities=[
                Entity(id="", canonical_name="GNN", type="概念/方法/理论", confidence=0.9),
                Entity(id="", canonical_name="Transformer", type="概念/方法/理论", confidence=0.8),
            ],
            relations=[
                Relation(
                    id="",
                    source_entity_id="GNN",
                    target_entity_id="Transformer",
                    type="提出",
                    evidence=["原文摘录"],
                    confidence=0.9,
                )
            ],
            chunk_id=chunk_id,
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "DATA_DIR", tmp_path / "data")
    app_mod.registry.clear()
    monkeypatch.setattr(
        app_mod,
        "make_extractor_factory",
        lambda store, api: (lambda group_id=None: FakeExtractor()),
    )
    return TestClient(app_mod.app)


def _make_docx_bytes() -> bytes:
    buf = io.BytesIO()
    doc = DocxDocument()
    doc.add_paragraph("Graph Neural Network 是一种用于图结构数据的深度学习模型。")
    doc.add_paragraph("Transformer 架构使用注意力机制。GNN 借鉴了 Transformer 的思想。")
    doc.save(buf)
    return buf.getvalue()


def test_full_pipeline(client):
    # 1) 创建项目
    r = client.post("/api/projects", json={"name": "集成测试"})
    assert r.status_code == 200
    pid = r.json()["project"]["id"]
    gid = r.json()["groups"][0]["id"]

    # 2) 导入 DOCX
    r = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("paper.docx", _make_docx_bytes(), DOCX_MIME)},
        data={"group_id": gid},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]

    # 3) 解析
    r = client.post(f"/api/projects/{pid}/documents/{doc_id}/parse")
    assert r.status_code == 200
    assert r.json()["status"] == "parsed"

    # 4) 抽取（假抽取器）
    r = client.post(
        f"/api/projects/{pid}/extract",
        json={"group_id": gid, "api": {"base_url": "http://x", "api_key": "k", "model": "m"}},
    )
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["documents"] == 1
    assert summary["entities"] >= 2
    assert summary["relations"] >= 1

    # 5) 图谱查询
    r = client.get(f"/api/projects/{pid}/graph", params={"group_id": gid})
    assert r.status_code == 200
    graph = r.json()
    assert len(graph["nodes"]) >= 2
    assert len(graph["edges"]) >= 1
    labels = {n["data"]["label"] for n in graph["nodes"]}
    assert {"GNN", "Transformer"} <= labels


def test_duplicate_import_conflict(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    gid = client.post(f"/api/projects/{pid}/groups", json={"name": "g"}).json()["id"]
    r1 = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("a.docx", _make_docx_bytes(), DOCX_MIME)},
        data={"group_id": gid},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("a.docx", _make_docx_bytes(), DOCX_MIME)},
        data={"group_id": gid},
    )
    assert r2.status_code == 409  # FR-310：同名文档拒绝


def test_unsupported_format(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/documents", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400  # FR-102：MVP 仅 PDF/DOCX


def test_extract_requires_api_config(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(
        f"/api/projects/{pid}/extract",
        json={"group_id": None, "api": {"base_url": "", "api_key": "", "model": ""}},
    )
    assert r.status_code == 400  # FR-801：缺少 API 配置时给出引导
