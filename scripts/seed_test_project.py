"""自测种子：在隔离数据目录创建一个含文档+图谱+证据的项目，供 UI 自测使用。"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from docgraph.core.models import Chunk, Entity, Relation
from docgraph.core.settings import set_last_project_id
from docgraph.core.store import ProjectStore


def main() -> None:
    data_dir = Path(os.environ["DOCGRAPH_USER_DATA"]) / "data"
    pid = uuid.uuid4().hex
    store = ProjectStore(data_dir / pid)
    store.create_project("自测项目", project_id=pid)
    gid = store.list_groups(pid)[0].id

    src = Path(__file__).resolve().parent.parent / "examples" / "图神经网络综述.docx"
    target = store.files_dir / "自测-图神经网络.docx"
    shutil.copy(src, target)
    doc = store.add_document(pid, gid, str(target), format="docx")
    store.set_document_status(doc.id, "extracted")

    store.save_chunks(
        doc.id,
        [
            Chunk(
                id=f"{doc.id}:c0",
                document_id=doc.id,
                page=0,
                seq=0,
                text="Graph Neural Network (GNN) 是一种用于图结构数据的深度学习模型。"
                "GAT 引入注意力机制改进 GNN，使其能力更强。Transformer 架构也被用于图结构。",
                token_count=30,
            )
        ],
    )

    e1 = Entity(id="e_gnn", canonical_name="GNN", type="概念/方法/理论", confidence=0.95, aliases=["Graph Neural Network"], source_docs=[doc.id])
    e2 = Entity(id="e_gat", canonical_name="GAT", type="概念/方法/理论", confidence=0.9, source_docs=[doc.id])
    e3 = Entity(id="e_trans", canonical_name="Transformer", type="概念/方法/理论", confidence=0.88, source_docs=[doc.id])
    r1 = Relation(id="r_gat_gnn", source_entity_id="e_gnn", target_entity_id="e_gat", type="改进", confidence=0.9, evidence=["GAT 引入注意力机制改进 GNN"], source_docs=[doc.id])
    store.save_extraction(doc.id, [e1, e2, e3], [r1])

    set_last_project_id(pid)  # 让 active 接口恢复该项目
    print(f"seeded pid={pid} doc={doc.id}")
    store.close()


if __name__ == "__main__":
    main()
