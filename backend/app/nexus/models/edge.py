"""结构边：实体 ↔ 实体（§1.4）。有向、带类型、带权；关系只存一次，反向靠遍历。"""
from __future__ import annotations

from pydantic import BaseModel

# 一期边类型（supersedes 二期）
EDGE_TYPES = ("requires", "belongs_to", "references", "supersedes")


class Edge(BaseModel):
    edge_id: int | None = None
    src: str                       # src_entity_id
    type: str                      # requires | belongs_to | references | supersedes
    dst: str                       # dst_entity_id
    weight: float = 1.0
    evidence: str | None = None    # 支撑该边的 block fullname 列表/说明（JSON 字符串）
    source: str = "llm"            # seed | manual | llm
    locked: bool = False
