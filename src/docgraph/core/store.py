"""SQLite 存储层（PRD 7.3 数据模型；FR-701 项目持久化）。

存储布局（单项目目录）：
    <project_dir>/
    +-- project.db   # SQLite：projects/groups/documents/chunks/entities/relations/evidence
    +-- files/       # 文档副本（导入时复制，保证文件名唯一，FR-310）
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES, Chunk, Document, Entity, Group, Project, Relation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    entity_types TEXT NOT NULL DEFAULT '[]',
    relation_types TEXT NOT NULL DEFAULT '[]',
    extract_config TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '',
    year TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    sha256 TEXT NOT NULL DEFAULT '',
    UNIQUE (project_id, path)   -- FR-310：项目内文件名唯一
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    page INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL DEFAULT '',
    token_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    source_docs_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    source_docs_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    page INTEGER NOT NULL DEFAULT 0,
    quote TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS user_edits (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
"""


class DuplicateNameError(ValueError):
    """项目内已存在同名文档（FR-310：不允许重名）。"""


def _extract_sentence(text: str, index: int, max_len: int = 160) -> str:
    """提取包含 index 的句子片段，作为证据原文。"""
    if index < 0:
        return text[:max_len]
    start = max(text.rfind("。", 0, index), text.rfind("！", 0, index), text.rfind("？", 0, index), text.rfind(".", 0, index))
    end_candidates = [
        t for t in (text.find("。", index), text.find("！", index), text.find("？", index), text.find(".", index))
        if t != -1
    ]
    end = min(end_candidates) + 1 if end_candidates else index + max_len
    start = start + 1 if start != -1 else max(0, index - 40)
    return text[start:end].strip()[:max_len]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectStore:
    """单个项目的 SQLite 存储。线程安全（FastAPI 线程池中使用）。"""

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir = self.project_dir / "files"
        self.files_dir.mkdir(exist_ok=True)
        self._db = sqlite3.connect(str(self.project_dir / "project.db"), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ---------- 项目 / 分组 ----------

    def create_project(self, name: str, project_id: str | None = None) -> Project:
        pid = project_id or uuid.uuid4().hex
        with self._lock:
            self._db.execute(
                "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                (pid, name, _now()),
            )
            self.create_group(pid, "默认组")  # FR-310：未分组文档归入默认组
            self._db.commit()
        project = self.get_project(pid)
        assert project is not None
        return project

    def list_projects(self) -> list[Project]:
        rows = self._db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [self._project_from_row(r) for r in rows]

    def get_project(self, project_id: str) -> Project | None:
        row = self._db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return self._project_from_row(row) if row else None

    def create_group(
        self,
        project_id: str,
        name: str,
        entity_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        extract_config: dict | None = None,
    ) -> Group:
        gid = uuid.uuid4().hex
        et = list(entity_types) if entity_types else list(DEFAULT_ENTITY_TYPES)
        rt = list(relation_types) if relation_types else list(DEFAULT_RELATION_TYPES)
        with self._lock:
            self._db.execute(
                "INSERT INTO groups (id, project_id, name, entity_types, relation_types, extract_config) VALUES (?,?,?,?,?,?)",
                (
                    gid,
                    project_id,
                    name,
                    json.dumps(et, ensure_ascii=False),
                    json.dumps(rt, ensure_ascii=False),
                    json.dumps(extract_config or {}, ensure_ascii=False),
                ),
            )
            self._db.commit()
        group = self.get_group(gid)
        assert group is not None
        return group

    def list_groups(self, project_id: str) -> list[Group]:
        rows = self._db.execute("SELECT * FROM groups WHERE project_id=? ORDER BY rowid", (project_id,)).fetchall()
        return [self._group_from_row(r) for r in rows]

    def get_group(self, group_id: str) -> Group | None:
        row = self._db.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
        return self._group_from_row(row) if row else None

    # ---------- 文档（FR-310：文件名唯一） ----------

    def add_document(
        self,
        project_id: str,
        group_id: str,
        path: str,
        title: str = "",
        authors: str = "",
        year: str = "",
        format: str = "",
        sha256: str = "",
    ) -> Document:
        file_name = Path(path).name
        exists = self._db.execute(
            "SELECT 1 FROM documents WHERE project_id=? AND path=?",
            (project_id, path),
        ).fetchone()
        if exists:
            raise DuplicateNameError(f"项目内已存在同名文档：{file_name}")
        doc_id = uuid.uuid4().hex
        with self._lock:
            self._db.execute(
                "INSERT INTO documents (id, project_id, group_id, path, title, authors, year, format, status, sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (doc_id, project_id, group_id, path, title, authors, year, format, "pending", sha256),
            )
            self._db.commit()
        doc = self.get_document(doc_id)
        assert doc is not None
        return doc

    def get_document(self, doc_id: str) -> Document | None:
        row = self._db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return self._document_from_row(row) if row else None

    def list_documents(self, project_id: str, group_id: str | None = None) -> list[Document]:
        if group_id:
            rows = self._db.execute(
                "SELECT * FROM documents WHERE project_id=? AND group_id=? ORDER BY rowid",
                (project_id, group_id),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM documents WHERE project_id=? ORDER BY rowid", (project_id,)).fetchall()
        return [self._document_from_row(r) for r in rows]

    def set_document_status(self, doc_id: str, status: str) -> None:
        with self._lock:
            self._db.execute("UPDATE documents SET status=? WHERE id=?", (status, doc_id))
            self._db.commit()

    def delete_document(self, doc_id: str) -> None:
        """级联删除：分块、证据；实体/关系中不再引用该文档的删除（FR-105）。"""
        doc = self.get_document(doc_id)
        if doc is None:
            return
        with self._lock:
            self._db.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
            self._db.execute("DELETE FROM evidence WHERE document_id=?", (doc_id,))
            # 从实体/关系的 source_docs 中移除该文档，空则删除
            for table in ("entities", "relations"):
                for row in self._db.execute(f"SELECT id, source_docs_json FROM {table}").fetchall():
                    docs = json.loads(row["source_docs_json"])
                    if doc_id in docs:
                        docs.remove(doc_id)
                        if docs:
                            self._db.execute(
                                f"UPDATE {table} SET source_docs_json=? WHERE id=?",
                                (json.dumps(docs, ensure_ascii=False), row["id"]),
                            )
                        else:
                            self._db.execute(f"DELETE FROM {table} WHERE id=?", (row["id"],))
            self._db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            self._db.commit()

    # ---------- 分块 ----------

    def save_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        with self._lock:
            self._db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            self._db.executemany(
                "INSERT INTO chunks (id, document_id, page, seq, text, token_count) VALUES (?,?,?,?,?,?)",
                [(c.id, c.document_id, c.page, c.seq, c.text, c.token_count) for c in chunks],
            )
            self._db.commit()

    def list_chunks(self, document_id: str) -> list[Chunk]:
        rows = self._db.execute("SELECT * FROM chunks WHERE document_id=? ORDER BY seq", (document_id,)).fetchall()
        return [Chunk(id=r["id"], document_id=r["document_id"], page=r["page"], seq=r["seq"], text=r["text"], token_count=r["token_count"]) for r in rows]

    # ---------- 抽取结果（实体/关系 upsert + 来源文档聚合） ----------

    def save_extraction(self, document_id: str, entities: list[Entity], relations: list[Relation]) -> None:
        with self._lock:
            for e in entities:
                existing = self._db.execute("SELECT source_docs_json FROM entities WHERE id=?", (e.id,)).fetchone()
                docs = json.loads(existing["source_docs_json"]) if existing else []
                if document_id not in docs:
                    docs.append(document_id)
                self._db.execute(
                    "INSERT INTO entities (id, canonical_name, type, description, confidence, aliases_json, source_docs_json) VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET canonical_name=excluded.canonical_name, type=excluded.type, "
                    "description=excluded.description, confidence=excluded.confidence, aliases_json=excluded.aliases_json, "
                    "source_docs_json=excluded.source_docs_json",
                    (
                        e.id,
                        e.canonical_name,
                        e.type,
                        e.description,
                        e.confidence,
                        json.dumps(e.aliases, ensure_ascii=False),
                        json.dumps(docs, ensure_ascii=False),
                    ),
                )
            for r in relations:
                existing = self._db.execute("SELECT source_docs_json FROM relations WHERE id=?", (r.id,)).fetchone()
                docs = json.loads(existing["source_docs_json"]) if existing else []
                if document_id not in docs:
                    docs.append(document_id)
                self._db.execute(
                    "INSERT INTO relations (id, source_entity_id, target_entity_id, type, confidence, evidence_json, source_docs_json) VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET source_entity_id=excluded.source_entity_id, target_entity_id=excluded.target_entity_id, "
                    "type=excluded.type, confidence=excluded.confidence, evidence_json=excluded.evidence_json, source_docs_json=excluded.source_docs_json",
                    (
                        r.id,
                        r.source_entity_id,
                        r.target_entity_id,
                        r.type,
                        r.confidence,
                        json.dumps(r.evidence, ensure_ascii=False),
                        json.dumps(docs, ensure_ascii=False),
                    ),
                )
            self._db.commit()

    # ---------- 图谱查询（Cytoscape.js 格式，FR-401/FR-508 按组过滤） ----------

    def get_graph(self, project_id: str, group_id: str | None = None) -> dict:
        group_docs = {d.id for d in self.list_documents(project_id, group_id)} if group_id else None
        nodes: list[dict] = []
        edges: list[dict] = []
        for row in self._db.execute("SELECT * FROM entities"):
            docs = set(json.loads(row["source_docs_json"]))
            if group_docs is not None and not (docs & group_docs):
                continue
            nodes.append(
                {
                    "data": {
                        "id": row["id"],
                        "label": row["canonical_name"],
                        "type": row["type"],
                        "confidence": row["confidence"],
                    }
                }
            )
        for row in self._db.execute("SELECT * FROM relations"):
            docs = set(json.loads(row["source_docs_json"]))
            if group_docs is not None and not (docs & group_docs):
                continue
            edges.append(
                {
                    "data": {
                        "id": row["id"],
                        "source": row["source_entity_id"],
                        "target": row["target_entity_id"],
                        "type": row["type"],
                        "label": row["type"],
                        "confidence": row["confidence"],
                    }
                }
            )
        return {"nodes": nodes, "edges": edges}

    # ---------- 行 -> 模型 ----------

    def _project_from_row(self, row: sqlite3.Row) -> Project:
        return Project(id=row["id"], name=row["name"], created_at=row["created_at"], config_json=json.loads(row["config_json"]))

    def _group_from_row(self, row: sqlite3.Row) -> Group:
        return Group(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            entity_types=json.loads(row["entity_types"]),
            relation_types=json.loads(row["relation_types"]),
            extract_config=json.loads(row["extract_config"]),
        )

    def _document_from_row(self, row: sqlite3.Row) -> Document:
        return Document(
            id=row["id"],
            project_id=row["project_id"],
            group_id=row["group_id"],
            path=row["path"],
            title=row["title"],
            authors=row["authors"],
            year=row["year"],
            format=row["format"],
            status=row["status"],
            sha256=row["sha256"],
        )


    # ---------- 实体 / 关系详情与证据（来源依据） ----------

    def doc_name(self, doc_id: str) -> str:
        row = self._db.execute("SELECT path FROM documents WHERE id=?", (doc_id,)).fetchone()
        return Path(row["path"]).name if row else doc_id

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self._db.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
        if row is None:
            return None
        return Entity(
            id=row["id"],
            canonical_name=row["canonical_name"],
            type=row["type"],
            description=row["description"],
            confidence=row["confidence"],
            aliases=json.loads(row["aliases_json"]),
            source_docs=json.loads(row["source_docs_json"]),
        )

    def get_relation(self, relation_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM relations WHERE id=?", (relation_id,)).fetchone()
        if row is None:
            return None
        src = self._db.execute("SELECT canonical_name FROM entities WHERE id=?", (row["source_entity_id"],)).fetchone()
        tgt = self._db.execute("SELECT canonical_name FROM entities WHERE id=?", (row["target_entity_id"],)).fetchone()
        return {
            "id": row["id"],
            "source": src["canonical_name"] if src else row["source_entity_id"],
            "target": tgt["canonical_name"] if tgt else row["target_entity_id"],
            "type": row["type"],
            "confidence": row["confidence"],
            "evidence": json.loads(row["evidence_json"]),
            "source_docs": [self.doc_name(d) for d in json.loads(row["source_docs_json"])],
        }

    def get_entity_detail(self, entity_id: str) -> dict | None:
        """实体详情：含来源文档与原文摘录（依据）。"""
        e = self.get_entity(entity_id)
        if e is None:
            return None
        return {
            "id": e.id,
            "canonical_name": e.canonical_name,
            "type": e.type,
            "description": e.description,
            "confidence": e.confidence,
            "aliases": e.aliases,
            "source_docs": [self.doc_name(d) for d in e.source_docs],
            "evidence": self.find_entity_evidence(entity_id),
        }

    def find_entity_evidence(self, entity_id: str, limit: int = 5) -> list[dict]:
        """在实体来源文档的分块中检索包含其名称/别名的句子作为依据。"""
        e = self.get_entity(entity_id)
        if e is None:
            return []
        names = [e.canonical_name] + e.aliases
        results: list[dict] = []
        for doc_id in e.source_docs:
            for chunk in self.list_chunks(doc_id):
                text = chunk.text
                hit_name = next((n for n in names if n and n.lower() in text.lower()), None)
                if not hit_name:
                    continue
                idx = text.lower().find(hit_name.lower())
                quote = _extract_sentence(text, idx)
                results.append({"doc_id": doc_id, "document": self.doc_name(doc_id), "page": chunk.page, "quote": quote})
                if len(results) >= limit:
                    return results
        return results

    def close(self) -> None:
        self._db.close()
