"""把 SQLite 便携版项目数据迁移到 PostgreSQL 服务版（幂等，可重复执行）。

用法：
    $env:DOCGRAPH_DATABASE_URL = "postgresql://docgraph:docgraph@127.0.0.1:5432/docgraph_meta"
    python scripts/migrate_sqlite_to_pg.py

逻辑：
- 扫描数据目录下每个含 project.db 的项目目录；
- 元库注册 projects；每个项目创建 docgraph_<pid> 内容库并按 rowid 顺序回填；
- 文档副本（files/）目录保持不变（PG 模式同样使用本地文件目录）；
- 已迁移的项目自动跳过（幂等）。
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from docgraph.core.settings import user_data_dir

META_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}'
);
"""

CONTENT_SCHEMA = """
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
"""

TABLES = [
    "groups",
    "documents",
    "chunks",
    "entities",
    "relations",
    "evidence",
    "user_edits",
    "llm_trace",
]

_ORDER_BY = {
    "groups": " ORDER BY rowid",
    "documents": " ORDER BY rowid",
    "llm_trace": " ORDER BY rowid",
}


def main() -> None:
    import psycopg
    from psycopg.rows import dict_row

    db_url = os.environ.get("DOCGRAPH_DATABASE_URL", "")
    if not db_url:
        print("需要设置 DOCGRAPH_DATABASE_URL（PostgreSQL 元库连接串）")
        sys.exit(1)
    data_dir = Path(os.environ.get("DOCGRAPH_DATA_DIR", str(user_data_dir() / "data")))

    meta = psycopg.connect(db_url, row_factory=dict_row)
    meta.execute(META_SCHEMA)
    meta.commit()

    migrated = 0
    for d in sorted(data_dir.iterdir()) if data_dir.exists() else []:
        if not d.is_dir() or not (d / "project.db").exists():
            continue
        pid = d.name
        sql = sqlite3.connect(f"file:{d / 'project.db'}?mode=ro", uri=True)
        sql.row_factory = sqlite3.Row
        prow = sql.execute("SELECT * FROM projects ORDER BY rowid LIMIT 1").fetchone()
        if prow is None:
            sql.close()
            continue
        # 元库注册（幂等）
        meta.execute(
            "INSERT INTO projects (id, name, created_at, config_json) VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (prow["id"], prow["name"], prow["created_at"], prow["config_json"]),
        )
        meta.commit()
        # 创建项目库
        admin = psycopg.connect(db_url, autocommit=True)
        admin.execute('CREATE DATABASE "docgraph_' + pid + '"')
        admin.close()
        proj = psycopg.connect(_with_db(db_url, "docgraph_" + pid), row_factory=dict_row)
        proj.execute(CONTENT_SCHEMA)
        proj.commit()
        # 逐表回填
        for table in TABLES:
            cols = [c["name"] for c in sql.execute(f"PRAGMA table_info({table})").fetchall()]
            if not cols:
                continue
            rows = sql.execute(f"SELECT * FROM {table}" + _ORDER_BY.get(table, "")).fetchall()
            if not rows:
                continue
            placeholders = ",".join(["%s"] * len(cols))
            insert = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
            for r in rows:
                proj.execute(insert, tuple(r[c] for c in cols))
            proj.commit()
        proj.close()
        sql.close()
        migrated += 1
        print(f"migrated: {pid} ({prow['name']})")
    meta.close()
    print(f"done. migrated {migrated} project(s)")


def _with_db(base_url: str, dbname: str) -> str:
    from urllib.parse import urlencode, urlsplit, urlunsplit

    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + dbname, urlencode({}), parts.fragment))


if __name__ == "__main__":
    main()
