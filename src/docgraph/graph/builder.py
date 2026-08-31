"""图谱构建与统计（FR-401 / FR-402 / FR-306）。"""

from __future__ import annotations

import networkx as nx

from ..core.models import Entity, Relation


def build_graph(entities: list[Entity], relations: list[Relation]) -> nx.DiGraph:
    """以实体为节点、关系为有向边构建图（FR-401）。"""
    g = nx.DiGraph()
    for e in entities:
        g.add_node(
            e.id,
            canonical_name=e.canonical_name,
            type=e.type,
            description=e.description,
            confidence=e.confidence,
            aliases=e.aliases,
        )
    for r in relations:
        g.add_edge(
            r.source_entity_id,
            r.target_entity_id,
            type=r.type,
            confidence=r.confidence,
            evidence=r.evidence,
        )
    return g


def dedupe_and_merge(
    entities: list[Entity],
    relations: list[Relation],
) -> tuple[list[Entity], list[Relation]]:
    """名称归一 -> 同名合并 -> 别名命中 -> 相似度阈值合并（FR-306）。

    同时作用于块间合并与「新文件 vs 同组既有图谱」对齐两个层面（FR-311）。
    低置信度冲突进入「待确认」队列（TODO(M1) 实现）。
    """
    raise NotImplementedError("M1: 实现去重合并与实体对齐")


def graph_stats(g: nx.DiGraph) -> dict:
    """节点数 / 边数 / 连通分量 / Top 高连接度实体（FR-402）。"""
    top_degree = sorted(g.degree(), key=lambda item: item[1], reverse=True)[:10]
    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "components": nx.number_weakly_connected_components(g),
        "top_entities": [(name, deg) for name, deg in top_degree],
    }
