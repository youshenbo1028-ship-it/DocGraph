"""内置 HTTP 服务（FastAPI）。

前端（Vue3）通过 HTTP 调用后端路由：
项目/分组 -> 文档导入 -> 解析 -> 抽取 -> 图谱查询（FR-1xx/2xx/3xx/4xx）。

M1 说明：LLM API 配置在抽取请求中传入（密钥安全存储 FR-802 属 P1）。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.store import DuplicateNameError, ProjectStore
from ..parsers.base import ScannedPdfError
from .extractor_factory import ApiConfig, make_extractor_factory
from .pipeline import extract_group, parse_document

# 项目数据目录（可用环境变量覆盖；生产打包时指向用户数据目录）
DATA_DIR = Path(os.environ.get("DOCGRAPH_DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

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


class ExtractRequest(BaseModel):
    group_id: str | None = None
    api: ApiConfig = ApiConfig(base_url="", api_key="", model="")


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
    app = FastAPI(title="DocGraph", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 本地桌面应用（开发模式前端在 5173）
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/projects")
    def list_projects() -> list[dict]:
        # 仅返回当前已打开的项目（M1 简化：项目列表持久化属后续）
        return []

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
        g = store.create_group(
            pid,
            req.name,
            entity_types=req.entity_types,
            relation_types=req.relation_types,
        )
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

    @app.post("/api/projects/{pid}/extract")
    def run_extract(pid: str, req: ExtractRequest) -> dict:
        store = registry.open(pid)
        if not (req.api.base_url and req.api.api_key and req.api.model):
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

        factory = make_extractor_factory(store, req.api)
        return extract_group(store, pid, group_id, factory)

    @app.get("/api/projects/{pid}/graph")
    def get_graph(pid: str, group_id: str | None = None) -> dict:
        store = registry.open(pid)
        return store.get_graph(pid, group_id)

    return app


app = create_app()
