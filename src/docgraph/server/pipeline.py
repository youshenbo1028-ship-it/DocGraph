"""抽取管线编排（FR-305）。

单文档流程：解析分块 -> 逐块 LLM 抽取（可并行）-> 去重合并 -> 入库。
新文件场景：抽取前注入同组既有实体作为「已知实体上下文」（FR-311）。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from ..core.models import DOC_STATUS_EXTRACTED, DOC_STATUS_EXTRACTING, DOC_STATUS_FAILED, DOC_STATUS_PARSED, DOC_STATUS_PARSING, Document
from ..core.store import ProjectStore
from ..graph.dedupe import merge_entities
from ..parsers import get_parser
from ..parsers.base import ScannedPdfError
from .extractor_factory import ExtractorFactory

KNOWN_ENTITIES_LIMIT = 50  # FR-311：注入的同组已知实体上限


def parse_document(store: ProjectStore, doc: Document) -> None:
    """解析单个文档并保存分块（FR-201/FR-202）。"""
    parser = get_parser(doc.format)
    chunks = parser.parse(doc.path, doc.id)
    store.save_chunks(doc.id, chunks)
    store.set_document_status(doc.id, DOC_STATUS_PARSED)


def extract_group(
    store: ProjectStore,
    project_id: str,
    group_id: str,
    extractor_factory: ExtractorFactory,
) -> dict:
    """对分组内文档执行抽取（FR-305 / FR-310 / FR-311）。

    分块并行调用 LLM（并发数默认 3，可用分组 extract_config.concurrency 覆盖）。
    """
    extractor = extractor_factory(group_id=group_id)
    group = store.get_group(group_id)
    concurrency = int((group.extract_config or {}).get("concurrency", 3)) if group else 3
    concurrency = max(1, min(concurrency, 8))

    docs = [
        d
        for d in store.list_documents(project_id, group_id)
        if d.status not in (DOC_STATUS_PARSING, DOC_STATUS_EXTRACTING)
    ]
    summary: dict = {"documents": 0, "chunks": 0, "entities": 0, "relations": 0, "pending": 0, "errors": []}

    for doc in docs:
        store.set_document_status(doc.id, DOC_STATUS_EXTRACTING)
        chunks = store.list_chunks(doc.id)
        if not chunks:
            try:
                parse_document(store, doc)
                chunks = store.list_chunks(doc.id)
            except ScannedPdfError as exc:
                store.set_document_status(doc.id, DOC_STATUS_FAILED)
                summary["errors"].append({"document": doc.file_name, "error": str(exc)})
                continue
        try:
            # 重抽取前清理该文档独享的旧实体/关系（避免方向冲突等被丢弃的关系残留）
            store.clear_document_extraction(doc.id)
            known = [n["data"]["label"] for n in store.get_graph(project_id, group_id)["nodes"]][:KNOWN_ENTITIES_LIMIT]
            candidates: list = []
            relations: list = []
            # 并行分块抽取（FR-308 并发）
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {
                    pool.submit(extractor.extract, c.text, known_entities=known, chunk_id=c.id): c
                    for c in chunks
                }
                for fut in as_completed(futures):
                    result = fut.result()  # 某个块失败则抛出，交由外层标记失败
                    candidates.extend(result.entities)
                    relations.extend(result.relations)
                    # 记录这次 LLM 调用的请求/响应/耗时（模型 API 调用日志）
                    store.save_trace({
                        "project_id": project_id,
                        "group_id": group_id,
                        "document_id": doc.id,
                        "chunk_id": result.chunk_id,
                        "model": result.model,
                        "base_url": result.base_url,
                        "request": result.request,
                        "response": result.response,
                        "raw_response": result.raw_response,
                        "status": "ok",
                        "latency_ms": result.latency_ms,
                    })
            merged = merge_entities(candidates, relations)
            store.save_extraction(doc.id, merged.entities, merged.relations)
            store.set_document_status(doc.id, DOC_STATUS_EXTRACTED)
            summary["documents"] += 1
            summary["chunks"] += len(chunks)
            summary["entities"] += len(merged.entities)
            summary["relations"] += len(merged.relations)
            summary["pending"] += len(merged.pending)
        except Exception as exc:
            store.set_document_status(doc.id, DOC_STATUS_FAILED)
            summary["errors"].append({"document": doc.file_name, "error": str(exc)})
    return summary
