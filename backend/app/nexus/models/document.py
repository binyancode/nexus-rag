"""文档：一份法规原文，切块后写入某个 Store。"""
from __future__ import annotations

from pydantic import BaseModel


class Document(BaseModel):
    doc_id: str                     # 稳定 id（如 content_hash 或 类别:标题）
    title: str | None = None
    category: str | None = None     # 必填（进入 fullname）
    store_id: str                   # 块写入的存储
    content_hash: str | None = None
    source_uri: str | None = None
    block_count: int = 0
