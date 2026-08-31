"""内置 HTTP 服务（FastAPI）。

前端（Vue3）通过 JSBridge/HTTP 调用后端路由：
导入 -> 解析 -> 抽取 -> 图谱查询（FR-1xx / 2xx / 3xx / 4xx）。
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="DocGraph", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# TODO(M1): /api/projects /api/import /api/parse /api/extract /api/graph 等路由
