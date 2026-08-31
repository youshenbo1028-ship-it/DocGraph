"""图谱构建、去重合并、统计（FR-401 / FR-402 / FR-306）。"""

from .builder import build_graph, graph_stats
from .dedupe import MergeResult, entity_id, merge_entities, normalize_name

__all__ = ["MergeResult", "build_graph", "entity_id", "graph_stats", "merge_entities", "normalize_name"]
