"""实体去重合并（FR-306 / FR-311 组内对齐）。

流程：
1. 名称归一（NFKC 全角转半角、统一大小写、折叠空白）；
2. 规范名/别名命中合并（同一对象共享名称 -> 合并）；
3. 相似度合并（difflib ratio >= similarity_threshold -> 自动合并）；
4. 邻近阈值（threshold-0.15 ~ threshold）记录为待确认（pending）；
5. 按最终规范名派生稳定 id（跨分块/跨文档同名自然同 id，配合存储 upsert 聚合来源文档）。
"""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from ..core.models import Entity, Relation

_WS = re.compile(r"\s+")

PENDING_WINDOW = 0.15  # 相似度在 [threshold-window, threshold) 视为待确认

# 有方向性的关系类型：A -> B 与 B -> A 不应同时存在（避免"互相从属"类矛盾）
ASYMMETRIC_RELATION_TYPES = {
    "从属", "基于", "属于", "提出", "改进", "包含", "引用", "验证", "应用于",
}


def _resolve_directional_conflicts(
    relations: list[Relation],
    pending: list[dict],
) -> list[Relation]:
    """对非对称关系类型做方向冲突检测：A->B 与 B->A 同时存在时保留置信度高者，另一条进待确认。"""
    if not relations:
        return relations
    by_key: dict[tuple[str, str, str], Relation] = {}
    for r in relations:
        by_key[(r.source_entity_id, r.target_entity_id, r.type)] = r
    kept_ids = {r.id for r in relations}
    seen = set()
    for (a, b, t), r in by_key.items():
        if t not in ASYMMETRIC_RELATION_TYPES:
            continue
        rev = by_key.get((b, a, t))
        if rev is None:
            continue
        pair = frozenset((a, b, t))
        if pair in seen:
            continue
        seen.add(pair)
        keep, drop = (r, rev) if r.confidence >= rev.confidence else (rev, r)
        kept_ids.discard(drop.id)
        pending.append(
            {
                "type": "directional_conflict",
                "source": keep.source_entity_id,
                "target": keep.target_entity_id,
                "relation": t,
                "kept_confidence": round(keep.confidence, 3),
                "dropped_confidence": round(drop.confidence, 3),
                "note": "非对称关系同时存在反向，已保留置信度高者",
            }
        )
    return [r for r in relations if r.id in kept_ids]


def normalize_name(name: str) -> str:
    """规范化名称：全角转半角（NFKC）、统一大小写、折叠空白。"""
    s = unicodedata.normalize("NFKC", name).strip()
    return _WS.sub(" ", s).casefold()


def entity_id(canonical_name: str) -> str:
    """由规范名派生稳定 id：同名实体跨块/跨文档 id 一致。"""
    return "e_" + hashlib.sha1(normalize_name(canonical_name).encode("utf-8")).hexdigest()[:12]


@dataclass
class MergeResult:
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)  # 待确认冲突（FR-306）


def merge_entities(
    candidates: list[Entity],
    relations: list[Relation],
    similarity_threshold: float = 0.9,
) -> MergeResult:
    pending: list[dict] = []

    # 1) 按归一化名称分组
    groups: dict[str, list[Entity]] = {}
    for e in candidates:
        groups.setdefault(normalize_name(e.canonical_name), []).append(e)

    # 2) 规范名/别名命中合并：一个名称被多个组共享 -> 归入首现组
    name_owners: dict[str, list[str]] = {}
    for key, group in groups.items():
        names: set[str] = {key}
        for e in group:
            names.update(normalize_name(a) for a in e.aliases)
        for n in names:
            name_owners.setdefault(n, []).append(key)

    merge_to: dict[str, str] = {}  # key -> 归属 key（首现者）
    for owners in name_owners.values():
        if len(owners) > 1:
            primary = owners[0]
            for o in owners[1:]:
                merge_to[o] = primary

    # 3) 相似度合并（剩余组两两比较）
    keys = [k for k in groups if k not in merge_to]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            a_root = merge_to.get(a, a)
            b_root = merge_to.get(b, b)
            if a_root == b_root:
                continue
            ratio = difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= similarity_threshold:
                merge_to[b] = a  # 并入 a（首现）
            elif ratio >= similarity_threshold - PENDING_WINDOW:
                pending.append(
                    {
                        "type": "similar_candidate",
                        "left": groups[a][0].canonical_name,
                        "right": groups[b][0].canonical_name,
                        "similarity": round(ratio, 3),
                    }
                )

    def root(key: str) -> str:
        while key in merge_to:
            key = merge_to[key]
        return key

    # 4) 构建最终实体
    merged_groups: dict[str, list[Entity]] = {}
    for key, group in groups.items():
        merged_groups.setdefault(root(key), []).extend(group)

    final_entities: list[Entity] = []
    name_to_id: dict[str, str] = {}
    for key, group in merged_groups.items():
        best = max(group, key=lambda e: e.confidence)
        aliases: list[str] = []
        for e in group:
            for a in e.aliases:
                if normalize_name(a) != key and a not in aliases:
                    aliases.append(a)
        final = Entity(
            id=entity_id(best.canonical_name),
            canonical_name=best.canonical_name,
            type=best.type,
            description=max((e.description for e in group), key=len, default=""),
            confidence=best.confidence,
            aliases=aliases,
        )
        final_entities.append(final)
        name_to_id[key] = final.id
        for a in aliases:
            name_to_id.setdefault(normalize_name(a), final.id)

    # 5) 关系重写（name -> id）+ 同关系合并
    final_relations: dict[tuple[str, str, str], Relation] = {}
    for r in relations:
        src_key = root(normalize_name(r.source_entity_id))
        dst_key = root(normalize_name(r.target_entity_id))
        src_id = name_to_id.get(src_key)
        dst_id = name_to_id.get(dst_key)
        if src_id is None or dst_id is None or src_id == dst_id:
            pending.append(
                {
                    "type": "relation_skipped",
                    "source": r.source_entity_id,
                    "target": r.target_entity_id,
                    "reason": "端点无法解析或自环",
                }
            )
            continue
        key = (src_id, dst_id, r.type)
        existing = final_relations.get(key)
        if existing is None:
            final_relations[key] = Relation(
                id="r_" + hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:12],
                source_entity_id=src_id,
                target_entity_id=dst_id,
                type=r.type,
                confidence=r.confidence,
                evidence=list(r.evidence),
            )
        else:
            existing.confidence = max(existing.confidence, r.confidence)
            for ev in r.evidence:
                if ev not in existing.evidence:
                    existing.evidence.append(ev)

    final_relations_list = list(final_relations.values())
    # 6) 方向冲突检测（非对称关系反向矛盾 -> 保留高置信度，另一条进待确认）
    final_relations_list = _resolve_directional_conflicts(final_relations_list, pending)

    return MergeResult(entities=final_entities, relations=final_relations_list, pending=pending)
