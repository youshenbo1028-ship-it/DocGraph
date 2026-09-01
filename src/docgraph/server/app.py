"""内置 HTTP 服务（FastAPI）。

前端（Vue3）通过 HTTP 调用后端路由：
项目/分组 -> 文档导入 -> 解析 -> 抽取 -> 图谱查询（FR-1xx/2xx/3xx/4xx）。

M1 说明：LLM API 配置在抽取请求中传入（密钥安全存储 FR-802 属 P1）。
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path

import shutil
import sqlite3
import sys
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Windows 上 mimetypes 可能把 .js 误判为 text/plain，导致浏览器拒绝执行模块脚本（黑屏）。
# 在静态资源挂载前注册正确的 MIME 类型。
import mimetypes as _mime

_mime.add_type("text/javascript", ".js")
_mime.add_type("text/javascript", ".mjs")
_mime.add_type("text/css", ".css")
_mime.add_type("application/json", ".json")
_mime.add_type("image/svg+xml", ".svg")
_mime.add_type("font/woff2", ".woff2")

from ..core.settings import (
    get_api_config,
    get_api_key,
    get_last_project_id,
    save_api_config,
    set_last_project_id,
    user_data_dir,
)
from ..core.store import DuplicateNameError, ProjectStore
from ..parsers.base import ScannedPdfError
from .extractor_factory import ApiConfig, make_extractor_factory
from .pipeline import extract_group, parse_document

# ---- 用户数据目录（稳定位置，不依赖启动目录） ----
DATA_DIR = Path(os.environ.get("DOCGRAPH_DATA_DIR", str(user_data_dir() / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_data() -> None:
    """把旧版本（启动目录相对 data/ 与 settings.json）迁移到稳定目录，避免用户数据丢失。"""
    if any(DATA_DIR.iterdir()):
        return  # 已迁移 / 稳定目录已有数据
    src_projects = []
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    for cand in (repo_root / "data",):
        if cand.is_dir():
            src_projects.append(cand)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        if (exe_dir / "data").is_dir():
            src_projects.append(exe_dir / "data")
    for src in src_projects:
        for proj in src.iterdir():
            if proj.is_dir() and not (DATA_DIR / proj.name).exists():
                shutil.copytree(proj, DATA_DIR / proj.name)
    # settings.json
    from ..core import settings

    if not settings.settings_path().exists():
        for sp in (repo_root / "settings.json",):
            if sp.exists():
                shutil.copy2(sp, settings.settings_path())
                break


_migrate_legacy_data()

# MVP 支持格式（FR-102）
SUPPORTED_FORMATS = {"pdf", "docx"}


class _Registry:
    """按项目 id 缓存的 ProjectStore（线程安全由 ProjectStore 内部锁保证）。"""

    def __init__(self) -> None:
        self._stores: dict[str, ProjectStore] = {}

    def open(self, project_id: str) -> ProjectStore:
        store = self._stores.get(project_id)
        if store is None:
            store = ProjectStore(DATA_DIR / project_id)
            if store.get_project(project_id) is None:
                raise HTTPException(status_code=404, detail=f"项目不存在：{project_id}")
            self._stores[project_id] = store
        return store

    def clear(self) -> None:
        for s in self._stores.values():
            s.close()
        self._stores.clear()


registry = _Registry()


# ---------- 请求模型 ----------

class ProjectCreate(BaseModel):
    name: str


class GroupCreate(BaseModel):
    name: str
    entity_types: list[str] | None = None
    relation_types: list[str] | None = None
    preset: str | None = None  # academic | legal（组级抽取类型表预设，FR-310）


class DocGroupRequest(BaseModel):
    group_id: str


class ExportSaveRequest(BaseModel):
    kind: str  # png | svg | graph.json | nodes.csv | edges.csv
    filename: str | None = None
    content_base64: str | None = None  # png/svg 由前端生成后回传
    group_id: str | None = None


class ExtractRequest(BaseModel):
    group_id: str | None = None
    api: ApiConfig = ApiConfig(base_url="", api_key="", model="")


class SettingsUpdate(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


# ---------- 工具 ----------

def _csv_escape(value: object) -> str:
    """CSV 字段转义（含逗号/引号/换行时加引号）。"""
    s = "" if value is None else str(value)
    if any(ch in s for ch in (",", '"', "\n", "\r")):
        return '"' + s.replace('"', '""') + '"'
    return s


def _dist_dir() -> Path | None:
    """打包模式：内嵌 web/dist（PyInstaller sys._MEIPASS）；开发模式：仓库 web/dist。"""
    if getattr(sys, "_MEIPASS", None):
        p = Path(sys._MEIPASS) / "web" / "dist"
        return p if p.exists() else None
    p = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    return p if p.exists() else None


# ---------- 项目枚举 ----------

def list_all_projects() -> list[dict]:
    """扫描数据目录返回所有项目（含文档数），按创建时间倒序。"""
    out = []
    if not DATA_DIR.exists():
        return out
    for d in DATA_DIR.iterdir():
        if d.is_dir() and (d / "project.db").exists():
            try:
                con = sqlite3.connect(f"file:{d / 'project.db'}?mode=ro", uri=True)
                row = con.execute(
                    "SELECT p.id, p.name, p.created_at, "
                    "(SELECT COUNT(*) FROM documents x WHERE x.project_id=p.id) AS doc_count "
                    "FROM projects p"
                ).fetchone()
                con.close()
                if row:
                    out.append({"id": row[0], "name": row[1], "created_at": row[2], "doc_count": row[3]})
            except sqlite3.Error:
                pass
    out.sort(key=lambda p: p["created_at"], reverse=True)
    return out


def resolve_active_project() -> str | None:
    """返回要激活的项目 id：优先 last_project_id，否则最近的、有文档的项目。"""
    pid = get_last_project_id()
    if pid and (DATA_DIR / pid).is_dir():
        return pid
    projs = list_all_projects()
    if not projs:
        return None
    # 优先最近且有文档的项目（避免落到空项目）
    for p in projs:
        if p["doc_count"] > 0:
            return p["id"]
    return projs[0]["id"]


# ---------- 载荷构建 ----------

def _document_payload(d) -> dict:
    return {
        "id": d.id,
        "project_id": d.project_id,
        "group_id": d.group_id,
        "file_name": Path(d.path).name,
        "format": d.format,
        "status": d.status,
        "title": d.title,
        "authors": d.authors,
        "year": d.year,
    }


def _project_detail(store: ProjectStore, pid: str) -> dict:
    p = store.get_project(pid)
    return {
        "project": {"id": p.id, "name": p.name, "created_at": p.created_at},
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "entity_types": g.entity_types,
                "relation_types": g.relation_types,
                "extract_config": g.extract_config,
            }
            for g in store.list_groups(pid)
        ],
        "documents": [_document_payload(d) for d in store.list_documents(pid)],
    }


# ---------- 路由 ----------

def create_app() -> FastAPI:
    app = FastAPI(title="DocGraph", version="0.5.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 本地桌面应用（开发模式前端在 5173）
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": app.version}

    @app.get("/api/projects")
    def list_projects() -> list[dict]:
        return list_all_projects()

    @app.get("/api/projects/active")
    def active_project() -> dict:
        pid = resolve_active_project()
        if pid is None:
            return {"project": None, "groups": [], "documents": []}
        set_last_project_id(pid)
        return _project_detail(registry.open(pid), pid)

    @app.post("/api/projects/{pid}/activate")
    def activate_project(pid: str) -> dict:
        store = registry.open(pid)  # 不存在则 404
        set_last_project_id(pid)
        return _project_detail(store, pid)

    @app.post("/api/projects")
    def create_project(req: ProjectCreate) -> dict:
        pid = uuid.uuid4().hex
        store = ProjectStore(DATA_DIR / pid)
        store.create_project(req.name, project_id=pid)
        registry._stores[pid] = store
        return _project_detail(store, pid)

    @app.get("/api/projects/{pid}")
    def get_project(pid: str) -> dict:
        return _project_detail(registry.open(pid), pid)

    @app.post("/api/projects/{pid}/groups")
    def create_group(pid: str, req: GroupCreate) -> dict:
        store = registry.open(pid)
        try:
            g = store.create_group(
                pid,
                req.name,
                entity_types=req.entity_types,
                relation_types=req.relation_types,
                preset=req.preset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": g.id, "name": g.name, "entity_types": g.entity_types, "relation_types": g.relation_types}

    @app.post("/api/projects/{pid}/documents")
    async def import_document(
        pid: str,
        file: UploadFile = File(...),
        group_id: str | None = Form(None),
    ) -> dict:
        store = registry.open(pid)
        file_name = Path(file.filename or "unnamed").name
        fmt = Path(file_name).suffix.lower().lstrip(".")
        if fmt not in SUPPORTED_FORMATS:
            raise HTTPException(status_code=400, detail=f"暂不支持的格式：.{fmt}（MVP 支持 PDF / DOCX，FR-102）")

        target = store.files_dir / file_name
        if target.exists():
            raise HTTPException(status_code=409, detail=f"项目内已存在同名文档：{file_name}（FR-310）")

        content = await file.read()
        target.write_bytes(content)

        if group_id is None:
            groups = store.list_groups(pid)
            group_id = groups[0].id if groups else store.create_group(pid, "默认组").id
        if store.get_group(group_id) is None:
            raise HTTPException(status_code=404, detail="分组不存在")

        try:
            doc = store.add_document(pid, group_id, str(target), format=fmt)
        except DuplicateNameError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _document_payload(doc)

    @app.post("/api/projects/{pid}/documents/{doc_id}/parse")
    def parse_document_route(pid: str, doc_id: str) -> dict:
        store = registry.open(pid)
        doc = store.get_document(doc_id)
        if doc is None or doc.project_id != pid:
            raise HTTPException(status_code=404, detail="文档不存在")
        try:
            parse_document(store, doc)
        except ScannedPdfError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            store.set_document_status(doc_id, "failed")
            raise HTTPException(status_code=500, detail=f"解析失败：{exc}") from exc
        return _document_payload(store.get_document(doc_id))

    @app.delete("/api/projects/{pid}/documents/{doc_id}")
    def delete_document_route(pid: str, doc_id: str) -> dict:
        store = registry.open(pid)
        doc = store.get_document(doc_id)
        if doc is None or doc.project_id != pid:
            raise HTTPException(status_code=404, detail="文档不存在")
        file_name = Path(doc.path).name
        store.delete_document(doc_id)  # 级联删除分块/证据，并清理实体/关系来源（FR-105）
        return {"deleted": doc_id, "file_name": file_name}

    @app.post("/api/projects/{pid}/documents/{doc_id}/move")
    def move_document_route(pid: str, doc_id: str, req: DocGroupRequest) -> dict:
        """把文档移动到目标分组（拖拽组织，FR-310）。"""
        store = registry.open(pid)
        doc = store.get_document(doc_id)
        if doc is None or doc.project_id != pid:
            raise HTTPException(status_code=404, detail="文档不存在")
        if store.get_group(req.group_id) is None:
            raise HTTPException(status_code=404, detail="目标分组不存在")
        store.move_document(doc_id, req.group_id)
        return _document_payload(store.get_document(doc_id))

    @app.post("/api/projects/{pid}/documents/{doc_id}/copy")
    def copy_document_route(pid: str, doc_id: str, req: DocGroupRequest) -> dict:
        """跨分组复用：自动复制文件并重命名为不重名副本（FR-310）。"""
        store = registry.open(pid)
        doc = store.get_document(doc_id)
        if doc is None or doc.project_id != pid:
            raise HTTPException(status_code=404, detail="文档不存在")
        if store.get_group(req.group_id) is None:
            raise HTTPException(status_code=404, detail="目标分组不存在")
        try:
            new_doc = store.copy_document(doc_id, req.group_id)
        except DuplicateNameError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _document_payload(new_doc)

    @app.post("/api/projects/{pid}/extract")
    def run_extract(pid: str, req: ExtractRequest) -> dict:
        store = registry.open(pid)
        # 请求未携带的字段回退到已保存的设置（FR-801：Key 存凭据库）
        saved = get_api_config()
        base_url = req.api.base_url or saved.get("base_url", "")
        model = req.api.model or saved.get("model", "")
        api_key = req.api.api_key or get_api_key()
        if not (base_url and api_key and model):
            raise HTTPException(
                status_code=400,
                detail="缺少 LLM API 配置（base_url / api_key / model），请在设置中配置（FR-801）",
            )
        group_id = req.group_id
        if group_id is None:
            groups = store.list_groups(pid)
            if not groups:
                raise HTTPException(status_code=400, detail="项目没有分组")
            group_id = groups[0].id
        elif store.get_group(group_id) is None:
            raise HTTPException(status_code=404, detail="分组不存在")

        from .extractor_factory import ApiConfig

        factory = make_extractor_factory(store, ApiConfig(base_url=base_url, api_key=api_key, model=model))
        return extract_group(store, pid, group_id, factory)

    @app.get("/api/projects/{pid}/graph")
    def get_graph(pid: str, group_id: str | None = None) -> dict:
        store = registry.open(pid)
        return store.get_graph(pid, group_id)

    # ---------- 模型 API 调用轨迹（请求/响应日志） ----------

    @app.get("/api/projects/{pid}/traces")
    def list_traces(pid: str, document_id: str | None = None, limit: int = 100) -> list[dict]:
        store = registry.open(pid)
        return store.list_traces(pid, document_id, limit)

    # ---------- 实体/关系详情与证据（来源依据，FR-307） ----------

    @app.get("/api/projects/{pid}/entities/{eid}")
    def entity_detail(pid: str, eid: str) -> dict:
        store = registry.open(pid)
        detail = store.get_entity_detail(eid)
        if detail is None:
            raise HTTPException(status_code=404, detail="实体不存在")
        return detail

    @app.get("/api/projects/{pid}/relations/{rid}")
    def relation_detail(pid: str, rid: str) -> dict:
        store = registry.open(pid)
        detail = store.get_relation(rid)
        if detail is None:
            raise HTTPException(status_code=404, detail="关系不存在")
        return detail

    # ---------- 设置（FR-801 / FR-802） ----------

    @app.get("/api/settings")
    def read_settings() -> dict:
        return get_api_config()

    @app.post("/api/settings")
    def update_settings(req: SettingsUpdate) -> dict:
        save_api_config(req.base_url, req.model, req.api_key or None)
        return get_api_config()

    # ---------- 导出（FR-602） ----------

    @app.get("/api/projects/{pid}/export/nodes.csv")
    def export_nodes_csv(pid: str, group_id: str | None = None) -> Response:
        store = registry.open(pid)
        g = store.get_graph(pid, group_id)
        rows = [["id", "label", "type", "confidence"]]
        rows += [
            [n["data"]["id"], n["data"]["label"], n["data"]["type"], n["data"]["confidence"]]
            for n in g["nodes"]
        ]
        text = "\n".join(",".join(_csv_escape(c) for c in row) for row in rows)
        return Response(
            text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="nodes.csv"'},
        )

    @app.get("/api/projects/{pid}/export/edges.csv")
    def export_edges_csv(pid: str, group_id: str | None = None) -> Response:
        store = registry.open(pid)
        g = store.get_graph(pid, group_id)
        rows = [["source", "target", "type", "confidence", "evidence"]]
        rows += [
            [e["data"]["source"], e["data"]["target"], e["data"]["type"], e["data"]["confidence"], ""]
            for e in g["edges"]
        ]
        text = "\n".join(",".join(_csv_escape(c) for c in row) for row in rows)
        return Response(
            text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="edges.csv"'},
        )

    @app.get("/api/projects/{pid}/export/graph.json")
    def export_graph_json(pid: str, group_id: str | None = None) -> dict:
        store = registry.open(pid)
        g = store.get_graph(pid, group_id)
        return {
            "schema": "docgraph-graph/v1",
            "project_id": pid,
            "group_id": group_id,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stats": {"nodes": len(g["nodes"]), "edges": len(g["edges"])},
            "nodes": g["nodes"],
            "edges": g["edges"],
        }

    @app.post("/api/projects/{pid}/export/save")
    def save_export(pid: str, req: ExportSaveRequest) -> dict:
        """把导出内容写入固定导出目录（%LOCALAPPDATA%\DocGraph\exports\<项目名>），返回绝对路径。

        - png/svg：前端生成内容后以 base64 回传；
        - graph.json / nodes.csv / edges.csv：服务端直接生成。
        """
        store = registry.open(pid)
        p = store.get_project(pid)
        safe_name = "".join(c for c in p.name if c not in '\\/:*?"<>|').strip() or "project"
        export_dir = user_data_dir() / "exports" / safe_name
        export_dir.mkdir(parents=True, exist_ok=True)

        if req.kind in ("graph.json", "nodes.csv", "edges.csv"):
            g = store.get_graph(pid, req.group_id)
            if req.kind == "graph.json":
                content = json.dumps(
                    {
                        "schema": "docgraph-graph/v1",
                        "project_id": pid,
                        "group_id": req.group_id,
                        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "stats": {"nodes": len(g["nodes"]), "edges": len(g["edges"])},
                        "nodes": g["nodes"],
                        "edges": g["edges"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                if req.kind == "nodes.csv":
                    rows = [["id", "label", "type", "confidence"]]
                    rows += [
                        [n["data"]["id"], n["data"]["label"], n["data"]["type"], n["data"]["confidence"]]
                        for n in g["nodes"]
                    ]
                else:
                    rows = [["source", "target", "type", "confidence", "evidence"]]
                    rows += [
                        [e["data"]["source"], e["data"]["target"], e["data"]["type"], e["data"]["confidence"], ""]
                        for e in g["edges"]
                    ]
                content = "\n".join(",".join(_csv_escape(c) for c in row) for row in rows)
        elif req.kind in ("png", "svg"):
            if not req.content_base64:
                raise HTTPException(status_code=400, detail="png/svg 导出需要前端生成的内容")
            content = base64.b64decode(req.content_base64)
        else:
            raise HTTPException(status_code=400, detail="不支持的导出类型：" + str(req.kind))

        filename = req.filename or ("export." + req.kind)
        target = export_dir / filename
        n = 2
        while target.exists():
            stem, suffix = target.stem, target.suffix
            target = export_dir / (stem + " (" + str(n) + ")" + suffix)
            n += 1
        if isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            target.write_bytes(content)
        return {"path": str(target), "dir": str(export_dir)}

    # ---------- 打包模式：内嵌前端静态资源 ----------

    dist = _dist_dir()
    if dist is not None:
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")

    return app


app = create_app()
