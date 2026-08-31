"""抽取管线编排（FR-305）。

单文档流程：解析分块 -> 逐块 LLM 抽取 -> 去重合并 -> 入库。
新文件场景：抽取前注入同组既有实体作为「已知实体上下文」（FR-311）。
"""

from __future__ import annotations

from typing import Callable

from ..core.models import DOC_STATUS_EXTRACTED, DOC_STATUS_EXTRACTING, DOC_STATUS_FAILED, DOC_STATUS_PARSED, Document
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
    """对分组内已解析文档执行抽取（FR-305 / FR-310 / FR-311）。"""
    extractor = extractor_factory(group_id=group_id)
    docs = [
        d
        for d in store.list_documents(project_id, group_id)
        if d.status in (DOC_STATUS_PARSED, DOC_STATUS_EXTRACTED, DOC_STATUS_FAILED)
    ]
    summary: dict = {"documents": 0, "chunks": 0, "entities": 0, "relations": 0, "pending": 0, "errors": []}

    for doc in docs:
        store.set_document_status(doc.id, DOC_STATUS_EXTRACTING)
        chunks = store.list_chunks(doc.id)
        if not chunks:
            # 未解析（可能导入后未调 parse）-> 先解析
            try:
                parse_document(store, doc)
                chunks = store.list_chunks(doc.id)
            except ScannedPdfError as exc:
                store.set_document_status(doc.id, DOC_STATUS_FAILED)
                summary["errors"].append({"document": doc.file_name, "error": str(exc)})
                continue
        try:
            # FR-311：注入同组既有实体作为已知实体上下文
            known = [n["data"]["label"] for n in store.get_graph(project_id, group_id)["nodes"]][:KNOWN_ENTITIES_LIMIT]
            candidates = []
            relations = []
            for chunk in chunks:
                result = extractor.extract(chunk.text, known_entities=known, chunk_id=chunk.id)
                candidates.extend(result.entities)
                relations.extend(result.relations)
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
