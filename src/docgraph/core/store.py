"""DocGraph 存储层（PRD 7.3 数据模型；FR-701 项目持久化）——双后端。

存储布局（单项目目录）：
    <project_dir>/
    +-- project.db   # SQLite（便携分支）：projects/groups/documents/... 全部表
    +-- files/       # 文档副本（导入时复制，保证文件名唯一，FR-310）

双后端（v0.6 服务版方向）：
- SQLite（默认，便携 exe 分支）：每个项目一个 project.db，行为与历史版本完全一致；
- PostgreSQL（服务版，传入 DOCGRAPH_DATABASE_URL 时启用）：
    - 元数据库（URL 指定的库）：projects 注册表；
    - 每个项目一个数据库 docgraph_<project_id>：内容表（groups/documents/chunks/...），
      表结构在 SQLite 基础上增加 seq 排序列（BIGSERIAL，替代 rowid 语义）；
  SQL 与 SQLite 完全一致（? 占位符与 rowid 由 _PgDb 适配器翻译），避免双份 SQL 维护。

线程安全：FastAPI 线程池中使用（RLock + 连接内部锁）。
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_RELATION_TYPES,
    GROUP_PRESETS,
    Chunk,
    Document,
    Entity,
    Group,
    Project,
    Relation,
)

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
CREATE TABLE IF NOT EXISTS llm_trace (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL DEFAULT '{}',
    response_text TEXT NOT NULL DEFAULT '',
    raw_response_json TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_trace_project ON llm_trace(project_id, document_id);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
"""

# PostgreSQL 服务版：元数据库 schema（projects 注册表）
_SCHEMA_PG_META = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}'
);
"""

# PostgreSQL 服务版：单项目内容库 schema（= SQLite schema + seq 排序列，替代 rowid）
_SCHEMA_PG_CONTENT = """
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    entity_types TEXT NOT NULL DEFAULT '[]',
    relation_types TEXT NOT NULL DEFAULT '[]',
    extract_config TEXT NOT NULL DEFAULT '{}',
    seq BIGSERIAL NOT NULL
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
    seq BIGSERIAL NOT NULL,
    UNIQUE (project_id, path)
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
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    source_docs_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS llm_trace (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL DEFAULT '{}',
    response_text TEXT NOT NULL DEFAULT '',
    raw_response_json TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    seq BIGSERIAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_trace_project ON llm_trace(project_id, document_id);
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


# ---------- 数据库适配器（SQLite / PostgreSQL 同一方法面） ----------


class _SqliteDb:
    """SQLite 连接（便携分支，行为与历史版本一致）。"""

    def __init__(self, path: str | Path) -> None:
        import sqlite3

        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()

    def execute(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._db.execute(sql, params)

    def executemany(self, sql: str, seq):
        with self._lock:
            return self._db.executemany(sql, seq)

    def executescript(self, script: str) -> None:
        with self._lock:
            self._db.executescript(script)

    def commit(self) -> None:
        with self._lock:
            self._db.commit()

    def close(self) -> None:
        self._db.close()


class _PgDb:
    """PostgreSQL 连接（服务版）。SQL 与 SQLite 同文，仅做两处翻译：

    - 占位符 ? -> %s（psycopg 风格）；
    - ORDER BY rowid -> ORDER BY seq（PG 无 rowid，schema 用 BIGSERIAL seq 表达插入序）。
    """

    def __init__(self, url: str, autocommit: bool = False) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(url, row_factory=dict_row, autocommit=autocommit)
        self._lock = threading.RLock()

    def execute(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(self._q(sql), params)

    def executemany(self, sql: str, seq):
        with self._lock:
            cur = self._conn.cursor()
            cur.executemany(self._q(sql), seq)
            return cur

    def executescript(self, script: str) -> None:
        with self._lock:
            for stmt in script.split(";"):
                s = stmt.strip()
                if s:
                    self._conn.execute(s)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _q(sql: str) -> str:
        return sql.replace("?", "%s").replace("rowid", "seq")


def _pg_with_db(base_url: str, dbname: str) -> str:
    """把连接串中的数据库名替换为指定库（元库 -> 项目库）。"""
    try:
        from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

        parts = urlsplit(base_url)
        query = parse_qs(parts.query)
        if parts.netloc and "/" in parts.path:
            path = "/" + dbname
        else:
            path = "/" + dbname
        return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query, doseq=True), parts.fragment))
    except Exception:
        return base_url.rsplit("/", 1)[0] + "/" + dbname


class ProjectStore:
    """单个项目的存储（SQLite 便携 / PostgreSQL 服务版）。线程安全。"""

    def __init__(self, project_dir: str | Path, db_url: str | None = None) -> None:
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir = self.project_dir / "files"
        self.files_dir.mkdir(exist_ok=True)
        self.db_url = db_url
        self._is_pg = bool(db_url)
        self._lock = threading.RLock()
        if self._is_pg:
            self._meta = _PgDb(db_url)
            self._meta.executescript(_SCHEMA_PG_META)  # 元库注册表（幂等）
            self._pg_project_db = "docgraph_" + self.project_dir.name
            self._db: _PgDb | None = None
            try:
                self._db = _PgDb(_pg_with_db(db_url, self._pg_project_db))
                self._db.executescript(_SCHEMA_PG_CONTENT)
            except Exception:
                self._db = None  # 项目库尚未创建（create_project 时创建）
        else:
            self._db = _SqliteDb(self.project_dir / "project.db")
            self._meta = self._db
            self._db.executescript(_SCHEMA)

    def _content(self) -> "_PgDb | _SqliteDb":
        if self._db is None:
            raise ValueError("项目数据库未创建")
        return self._db

    def is_postgres(self) -> bool:
        return self._is_pg

    # ---------- 项目 / 分组 ----------

    def create_project(self, name: str, project_id: str | None = None) -> Project:
        pid = project_id or uuid.uuid4().hex
        with self._lock:
            self._meta.execute(
                "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                (pid, name, _now()),
            )
            self._meta.commit()
            if self._is_pg:
                self._create_pg_database(pid)
                self._db = _PgDb(_pg_with_db(self.db_url, "docgraph_" + pid))
                self._db.executescript(_SCHEMA_PG_CONTENT)
            self.create_group(pid, "默认组")  # FR-310：未分组文档归入默认组
        project = self.get_project(pid)
        assert project is not None
        return project

    def _create_pg_database(self, pid: str) -> None:
        import psycopg

        admin = psycopg.connect(self.db_url, autocommit=True)
        try:
            admin.execute('CREATE DATABASE "docgraph_' + pid + '"')
        except Exception:
            pass  # 已存在则忽略
        finally:
            admin.close()

    def list_projects(self) -> list[Project]:
        rows = self._meta.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [self._project_from_row(r) for r in rows]

    def get_project(self, project_id: str) -> Project | None:
        row = self._meta.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return self._project_from_row(row) if row else None

    def create_group(
        self,
        project_id: str,
        name: str,
        entity_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        extract_config: dict | None = None,
        preset: str | None = None,
    ) -> Group:
        gid = uuid.uuid4().hex
        if preset and preset not in GROUP_PRESETS:
            raise ValueError(f"未知的分组预设：{preset}（可选：{', '.join(GROUP_PRESETS)}）")
        # 预设优先，显式传入的类型表可覆盖预设（FR-310 组级独立配置）
        if preset:
            et, rt = GROUP_PRESETS[preset]
        else:
            et, rt = list(DEFAULT_ENTITY_TYPES), list(DEFAULT_RELATION_TYPES)
        if entity_types is not None:
            et = list(entity_types)
        if relation_types is not None:
            rt = list(relation_types)
        with self._lock:
            self._content().execute(
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
            self._content().commit()
        group = self.get_group(gid)
        assert group is not None
        return group

    def list_groups(self, project_id: str) -> list[Group]:
        rows = self._content().execute("SELECT * FROM groups WHERE project_id=? ORDER BY rowid", (project_id,)).fetchall()
        return [self._group_from_row(r) for r in rows]

    def get_group(self, group_id: str) -> Group | None:
        row = self._content().execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
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
        exists = self._content().execute(
            "SELECT 1 FROM documents WHERE project_id=? AND path=?",
            (project_id, path),
        ).fetchone()
        if exists:
            raise DuplicateNameError(f"项目内已存在同名文档：{file_name}")
        doc_id = uuid.uuid4().hex
        with self._lock:
            self._content().execute(
                "INSERT INTO documents (id, project_id, group_id, path, title, authors, year, format, status, sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (doc_id, project_id, group_id, path, title, authors, year, format, "pending", sha256),
            )
            self._content().commit()
        doc = self.get_document(doc_id)
        assert doc is not None
        return doc

    def move_document(self, doc_id: str, group_id: str) -> None:
        """把文档移动到目标分组（FR-310：一个文档属于一个分组；用于拖到分组组织查看）。"""
        doc = self.get_document(doc_id)
        if doc is None:
            raise ValueError("文档不存在")
        with self._lock:
            self._content().execute("UPDATE documents SET group_id=? WHERE id=?", (group_id, doc_id))
            self._content().commit()

    def copy_document(self, doc_id: str, target_group_id: str) -> Document:
        """跨分组复用同一源文档：自动复制文件并重命名为项目内唯一名（FR-310）。

        - 新副本为独立文档（status=pending，需重新解析抽取），与原件互不影响；
        - 命名规则：报告.pdf -> 报告 (2).pdf（避开项目内已有文档名）。
        """
        src = self.get_document(doc_id)
        if src is None:
            raise ValueError("文档不存在")
        src_path = Path(src.path)
        new_name = self._unique_copy_name(src.project_id, src_path)
        new_path = src_path.parent / new_name
        shutil.copy2(src_path, new_path)
        return self.add_document(
            src.project_id, target_group_id, str(new_path), format=src.format
        )

    def _unique_copy_name(self, project_id: str, src_path: Path) -> str:
        stem, suffix = src_path.stem, src_path.suffix
        candidate = src_path.name
        n = 2
        while True:
            exists = self._content().execute(
                "SELECT 1 FROM documents WHERE project_id=? AND path=?",
                (project_id, str(src_path.parent / candidate)),
            ).fetchone()
            if not exists:
                return candidate
            candidate = stem + " (" + str(n) + ")" + suffix
            n += 1

    def get_document(self, doc_id: str) -> Document | None:
        row = self._content().execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return self._document_from_row(row) if row else None

    def list_documents(self, project_id: str, group_id: str | None = None) -> list[Document]:
        if group_id:
            rows = self._content().execute(
                "SELECT * FROM documents WHERE project_id=? AND group_id=? ORDER BY rowid",
                (project_id, group_id),
            ).fetchall()
        else:
            rows = self._content().execute("SELECT * FROM documents WHERE project_id=? ORDER BY rowid", (project_id,)).fetchall()
        return [self._document_from_row(r) for r in rows]

    def set_document_status(self, doc_id: str, status: str) -> None:
        with self._lock:
            self._content().execute("UPDATE documents SET status=? WHERE id=?", (status, doc_id))
            self._content().commit()

    def count_documents(self, project_id: str) -> int:
        row = self._content().execute("SELECT COUNT(*) AS c FROM documents WHERE project_id=?", (project_id,)).fetchone()
        return int(row["c"]) if row else 0

    def delete_document(self, doc_id: str) -> None:
        """级联删除：分块、证据；实体/关系中不再引用该文档的删除（FR-105）。"""
        doc = self.get_document(doc_id)
        if doc is None:
            return
        db = self._content()
        with self._lock:
            db.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
            db.execute("DELETE FROM evidence WHERE document_id=?", (doc_id,))
            # 从实体/关系的 source_docs 中移除该文档，空则删除
            for table in ("entities", "relations"):
                for row in db.execute(f"SELECT id, source_docs_json FROM {table}").fetchall():
                    docs = json.loads(row["source_docs_json"])
                    if doc_id in docs:
                        docs.remove(doc_id)
                        if docs:
                            db.execute(
                                f"UPDATE {table} SET source_docs_json=? WHERE id=?",
                                (json.dumps(docs, ensure_ascii=False), row["id"]),
                            )
                        else:
                            db.execute(f"DELETE FROM {table} WHERE id=?", (row["id"],))
            db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            db.commit()

    # ---------- 分块 ----------

    def save_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        db = self._content()
        with self._lock:
            db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            db.executemany(
                "INSERT INTO chunks (id, document_id, page, seq, text, token_count) VALUES (?,?,?,?,?,?)",
                [(c.id, c.document_id, c.page, c.seq, c.text, c.token_count) for c in chunks],
            )
            db.commit()

    def list_chunks(self, document_id: str) -> list[Chunk]:
        rows = self._content().execute("SELECT * FROM chunks WHERE document_id=? ORDER BY seq", (document_id,)).fetchall()
        return [Chunk(id=r["id"], document_id=r["document_id"], page=r["page"], seq=r["seq"], text=r["text"], token_count=r["token_count"]) for r in rows]

    # ---------- 抽取结果（实体/关系 upsert + 来源文档聚合） ----------

    def clear_document_extraction(self, doc_id: str) -> None:
        """重抽取前清理该文档独享的实体/关系。"""
        db = self._content()
        with self._lock:
            for table in ("entities", "relations"):
                for row in db.execute(f"SELECT id, source_docs_json FROM {table}").fetchall():
                    docs = json.loads(row["source_docs_json"])
                    if len(docs) == 1 and docs[0] == doc_id:
                        db.execute(f"DELETE FROM {table} WHERE id=?", (row["id"],))
            db.commit()

    def save_extraction(self, document_id: str, entities: list[Entity], relations: list[Relation]) -> None:
        db = self._content()
        with self._lock:
            for e in entities:
                existing = db.execute("SELECT source_docs_json FROM entities WHERE id=?", (e.id,)).fetchone()
                docs = json.loads(existing["source_docs_json"]) if existing else []
                if document_id not in docs:
                    docs.append(document_id)
                db.execute(
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
                existing = db.execute("SELECT source_docs_json FROM relations WHERE id=?", (r.id,)).fetchone()
                docs = json.loads(existing["source_docs_json"]) if existing else []
                if document_id not in docs:
                    docs.append(document_id)
                db.execute(
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
            db.commit()

    # ---------- 图谱查询（Cytoscape.js 格式，FR-401/FR-508 按组过滤） ----------

    def get_graph(self, project_id: str, group_id: str | None = None) -> dict:
        db = self._content()
        group_docs = {d.id for d in self.list_documents(project_id, group_id)} if group_id else None
        nodes: list[dict] = []
        edges: list[dict] = []
        for row in db.execute("SELECT * FROM entities"):
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
        for row in db.execute("SELECT * FROM relations"):
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

    def _project_from_row(self, row) -> Project:
        return Project(id=row["id"], name=row["name"], created_at=row["created_at"], config_json=json.loads(row["config_json"]))

    def _group_from_row(self, row) -> Group:
        return Group(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            entity_types=json.loads(row["entity_types"]),
            relation_types=json.loads(row["relation_types"]),
            extract_config=json.loads(row["extract_config"]),
        )

    def _document_from_row(self, row) -> Document:
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

    # ---------- LLM 调用轨迹（模型 API 请求/响应日志） ----------

    def save_trace(self, trace: dict) -> None:
        """保存一次 LLM 调用的请求/响应/耗时记录。"""
        import time as _t

        db = self._content()
        with self._lock:
            db.execute(
                "INSERT INTO llm_trace (id, project_id, group_id, document_id, chunk_id, model, base_url, "
                "request_json, response_text, raw_response_json, status, latency_ms, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    trace.get("project_id", ""),
                    trace.get("group_id", ""),
                    trace.get("document_id", ""),
                    trace.get("chunk_id", ""),
                    trace.get("model", ""),
                    trace.get("base_url", ""),
                    json.dumps(trace.get("request", {}), ensure_ascii=False),
                    trace.get("response", ""),
                    trace.get("raw_response", ""),
                    trace.get("status", "ok"),
                    int(trace.get("latency_ms", 0)),
                    _now(),
                ),
            )
            db.commit()

    def list_traces(self, project_id: str, document_id: str | None = None, limit: int = 100) -> list[dict]:
        """返回项目的 LLM 调用轨迹（可按文档过滤，倒序）。"""
        db = self._content()
        if document_id:
            rows = db.execute(
                "SELECT * FROM llm_trace WHERE project_id=? AND document_id=? ORDER BY rowid DESC LIMIT ?",
                (project_id, document_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM llm_trace WHERE project_id=? ORDER BY rowid DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "document_id": r["document_id"],
                    "chunk_id": r["chunk_id"],
                    "model": r["model"],
                    "base_url": r["base_url"],
                    "request": json.loads(r["request_json"]),
                    "response": r["response_text"],
                    "raw_response": r["raw_response_json"],
                    "status": r["status"],
                    "latency_ms": r["latency_ms"],
                    "created_at": r["created_at"],
                }
            )
        return out

    # ---------- 实体 / 关系详情与证据（来源依据） ----------

    def doc_name(self, doc_id: str) -> str:
        row = self._content().execute("SELECT path FROM documents WHERE id=?", (doc_id,)).fetchone()
        return Path(row["path"]).name if row else doc_id

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self._content().execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
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
        db = self._content()
        row = db.execute("SELECT * FROM relations WHERE id=?", (relation_id,)).fetchone()
        if row is None:
            return None
        src = db.execute("SELECT canonical_name FROM entities WHERE id=?", (row["source_entity_id"],)).fetchone()
        tgt = db.execute("SELECT canonical_name FROM entities WHERE id=?", (row["target_entity_id"],)).fetchone()
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
        try:
            if self._db is not None:
                self._db.close()
            if getattr(self, "_meta", None) is not None and self._meta is not self._db:
                self._meta.close()
        except Exception:
            pass
