"""Store 与 Collection（§1.6）。

SearchStore = 一个 AI Search 凭据 + 索引（一处块存储）。
Collection  = 一组 Store 的查询期视图（多对多，仅用于检索过滤，不写进任何 id）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SearchStore(BaseModel):
    store_id: str
    name: str
    credential_name: str            # 指向 app_credential 里的 azure_ai_search 凭据
    index_name: str | None = None
    kind: str = "block"             # 目前只有 block
    is_default: bool = False


class Collection(BaseModel):
    collection_id: str
    name: str
    description: str | None = None
    is_public: bool = False
    stores: list[str] = Field(default_factory=list)   # 成员 store_id
    is_default: bool = False                          # 针对当前查询用户的默认项（读取时填充）
