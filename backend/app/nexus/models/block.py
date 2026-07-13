"""块：原文最小检索单元。本体（text+vector）存 AI Search，这里只是内存/传输模型。

fullname 是逻辑主键（不含 store）：类别.文档.章节.块序号。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Block(BaseModel):
    fullname: str                                   # 类别.文档.章节.块序号
    text: str                                        # 原文
    doc_id: str | None = None
    category: str | None = None
    title: str | None = None                         # 所属文档标题
    section: str | None = None                       # 章节
    ordinal: int | None = None                       # 块序号
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    vector: list[float] | None = None                # 嵌入向量
    store_id: str | None = None                      # 写入的块存储
