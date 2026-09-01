
"""分组 UX 修复测试：抽取预设、文档移动/复制、导出保存到目录。

覆盖：
- FR-310 preset=legal：分组使用法律语义类型表（修复「女职工 属于 劳动法」类硬套问题）；
- 文档移动到其他分组 / 复制（自动重命名 报告 (2).pdf）；
- 导出保存到固定导出目录并返回绝对路径。
"""

from __future__ import annotations

import base64
import io

from docx import Document as DocxDocument
from fastapi.testclient import TestClient

import docgraph.server.app as app_mod
from docgraph.core.models import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    GROUP_PRESETS,
    LEGAL_ENTITY_TYPES,
    LEGAL_RELATION_TYPES,
)
from docgraph.extractors.base import ExtractionResult
from docgraph.core.models import Entity, Relation

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FakeExtractor:
    def extract(self, chunk_text, known_entities=None, chunk_id=""):
        return ExtractionResult(
            entities=[
                Entity(id="", canonical_name="GNN", type="概念/方法/理论", confidence=0.9),
                Entity(id="", canonical_name="Transformer", type="概念/方法/理论", confidence=0.8),
            ],
            relations=[
                Relation(id="", source_entity_id="GNN", target_entity_id="Transformer", type="提出", evidence=["x"], confidence=0.9),
            ],
            chunk_id=chunk_id,
        )


import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "DATA_DIR", tmp_path / "data")
    monkeypatch.setenv("DOCGRAPH_SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setenv("DOCGRAPH_USER_DATA", str(tmp_path / "userdata"))
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
    doc.save(buf)
    return buf.getvalue()


def _import_doc(client, pid, gid, name="p.docx") -> str:
    r = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": (name, _make_docx_bytes(), DOCX_MIME)},
        data={"group_id": gid},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_group_preset_legal(client):
    """FR-310：preset=legal 使用法律语义类型表（不再把法律文档按学术表硬套）。"""
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/groups", json={"name": "法律法规", "preset": "legal"})
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["entity_types"] == LEGAL_ENTITY_TYPES
    assert g["relation_types"] == LEGAL_RELATION_TYPES
    # 与学术默认表必须不同（法律关系里不应有「属于/提出」这类学术类型）
    assert g["relation_types"] != DEFAULT_RELATION_TYPES
    assert "属于" not in g["relation_types"]
    assert "规定" in g["relation_types"]


def test_group_preset_academic_default(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/groups", json={"name": "g", "preset": "academic"})
    g = r.json()
    assert g["entity_types"] == DEFAULT_ENTITY_TYPES
    assert g["relation_types"] == DEFAULT_RELATION_TYPES


def test_group_preset_invalid(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/groups", json={"name": "g", "preset": "bogus"})
    assert r.status_code == 400


def test_move_document_between_groups(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    g1 = client.post(f"/api/projects/{pid}/groups", json={"name": "a"}).json()["id"]
    g2 = client.post(f"/api/projects/{pid}/groups", json={"name": "b"}).json()["id"]
    doc_id = _import_doc(client, pid, g1)
    r = client.post(f"/api/projects/{pid}/documents/{doc_id}/move", json={"group_id": g2})
    assert r.status_code == 200, r.text
    assert r.json()["group_id"] == g2
    # 项目详情中该文档归属新分组
    docs = client.get(f"/api/projects/{pid}").json()["documents"]
    assert next(d for d in docs if d["id"] == doc_id)["group_id"] == g2


def test_move_document_missing_group(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    g1 = client.post(f"/api/projects/{pid}/groups", json={"name": "a"}).json()["id"]
    doc_id = _import_doc(client, pid, g1)
    r = client.post(f"/api/projects/{pid}/documents/{doc_id}/move", json={"group_id": "nope"})
    assert r.status_code == 404


def test_copy_document_auto_rename(client):
    """FR-310：复制到其他分组 -> 自动重命名（报告 (2).pdf），副本独立。"""
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    g1 = client.post(f"/api/projects/{pid}/groups", json={"name": "a"}).json()["id"]
    g2 = client.post(f"/api/projects/{pid}/groups", json={"name": "b"}).json()["id"]
    doc_id = _import_doc(client, pid, g1, "报告.docx")
    r = client.post(f"/api/projects/{pid}/documents/{doc_id}/copy", json={"group_id": g2})
    assert r.status_code == 200, r.text
    copy = r.json()
    assert copy["file_name"] == "报告 (2).docx"
    assert copy["group_id"] == g2
    assert copy["status"] == "pending"  # 副本独立，需重新解析抽取
    assert copy["id"] != doc_id
    # 原文档不受影响
    docs = client.get(f"/api/projects/{pid}").json()["documents"]
    assert len(docs) == 2


def test_copy_document_again_increments(client):
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    g1 = client.post(f"/api/projects/{pid}/groups", json={"name": "a"}).json()["id"]
    g2 = client.post(f"/api/projects/{pid}/groups", json={"name": "b"}).json()["id"]
    doc_id = _import_doc(client, pid, g1, "报告.docx")
    client.post(f"/api/projects/{pid}/documents/{doc_id}/copy", json={"group_id": g2})
    r = client.post(f"/api/projects/{pid}/documents/{doc_id}/copy", json={"group_id": g2})
    assert r.status_code == 200, r.text
    assert r.json()["file_name"] == "报告 (3).docx"


def _import_and_extract(client, pid, gid) -> None:
    doc_id = _import_doc(client, pid, gid)
    client.post(f"/api/projects/{pid}/documents/{doc_id}/parse")
    client.post(
        f"/api/projects/{pid}/extract",
        json={"group_id": gid, "api": {"base_url": "http://x", "api_key": "k", "model": "m"}},
    )


def test_export_save_json(client, tmp_path, monkeypatch):
    """导出保存：graph.json 写入导出目录并返回绝对路径。"""
    monkeypatch.setenv("DOCGRAPH_USER_DATA", str(tmp_path / "userdata"))
    pid = client.post("/api/projects", json={"name": "导出项目"}).json()["project"]["id"]
    gid = client.post(f"/api/projects/{pid}/groups", json={"name": "g"}).json()["id"]
    _import_and_extract(client, pid, gid)
    r = client.post(
        f"/api/projects/{pid}/export/save",
        json={"kind": "graph.json", "filename": "graph.json", "group_id": gid},
    )
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    assert path.endswith("graph.json")
    assert "导出项目" in path
    assert "exports" in path
    content = open(path, encoding="utf-8").read()
    assert "docgraph-graph/v1" in content
    assert "GNN" in content


def test_export_save_csv_and_png(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGRAPH_USER_DATA", str(tmp_path / "userdata"))
    pid = client.post("/api/projects", json={"name": "导出项目"}).json()["project"]["id"]
    gid = client.post(f"/api/projects/{pid}/groups", json={"name": "g"}).json()["id"]
    _import_and_extract(client, pid, gid)
    # CSV（服务端生成）
    r = client.post(f"/api/projects/{pid}/export/save", json={"kind": "nodes.csv", "filename": "nodes.csv", "group_id": gid})
    assert r.status_code == 200
    assert "GNN" in open(r.json()["path"], encoding="utf-8").read()
    # PNG（前端回传 base64）
    fake_png = base64.b64encode(b"\x89PNG-fake-content").decode()
    r2 = client.post(
        f"/api/projects/{pid}/export/save",
        json={"kind": "png", "filename": "graph.png", "content_base64": fake_png, "group_id": gid},
    )
    assert r2.status_code == 200
    assert open(r2.json()["path"], "rb").read() == b"\x89PNG-fake-content"
    # 同名再导出 -> 自动加序号，不覆盖
    r3 = client.post(f"/api/projects/{pid}/export/save", json={"kind": "nodes.csv", "filename": "nodes.csv", "group_id": gid})
    assert r3.status_code == 200
    assert " (2)" in r3.json()["path"]


def test_export_save_unsupported_kind(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGRAPH_USER_DATA", str(tmp_path / "userdata"))
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/export/save", json={"kind": "exe"})
    assert r.status_code == 400


def test_export_save_png_without_content(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGRAPH_USER_DATA", str(tmp_path / "userdata"))
    pid = client.post("/api/projects", json={"name": "t"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/export/save", json={"kind": "png"})
    assert r.status_code == 400


def test_system_prompt_contains_anti_garbage_rules():
    """Prompt 防垃圾规则：法律文档不再出现「女职工 属于 劳动法」类硬套。"""
    from docgraph.extractors.prompts import build_system_prompt

    prompt = build_system_prompt(LEGAL_ENTITY_TYPES, LEGAL_RELATION_TYPES)
    assert "不得硬套不匹配的关系类型" in prompt
    assert "无实质信息的关系" in prompt
    assert "女职工" in prompt  # 规则 6 明确给出了反例
