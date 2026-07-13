"""出处边：实体 ↔ 块（§1.3）。grounding，把概念挂到具体条文块上。

store_id 记录该块所在的 AI Search 存储（§1.6）——
「实体属于集合 C ⟺ 该实体存在出处，其 store_id ∈ C.stores」。
"""
from __future__ import annotations

from pydantic import BaseModel


class Evidence(BaseModel):
    evidence_id: int | None = None
    entity_id: str
    fullname: str                  # 块逻辑主键：类别.文档.章节.块（不含 store）
    store_id: str                  # 该块所在的块存储
    weight: float = 1.0
    source: str = "llm"            # seed | manual | llm
    locked: bool = False
