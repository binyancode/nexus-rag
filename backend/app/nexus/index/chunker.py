"""切块器：把法规原文切成检索块（§2 索引管线）。

策略（面向中文法规）：
- 识别「第X章 …」作为章节；识别「第X条」作为条文块边界；
- 每个「条」为一个块；无「条」标记时按长度兜底切分。
fullname = 类别.文档.章节.块序号（逻辑主键，不含 store）。
"""
from __future__ import annotations

import hashlib
import re

from ..models.block import Block

# 「第一章 总则」「第 3 章」等
_CHAPTER = re.compile(r"^\s*第\s*[一二三四五六七八九十百零〇\d]+\s*[章编]\s*(.*)$")
# 「第十二条」「第 12 条」等（行首）
_ARTICLE = re.compile(r"^\s*第\s*[一二三四五六七八九十百千零〇\d]+\s*条")

_MAX_CHARS = 800          # 兜底切分时单块最大字符
_SANITIZE = re.compile(r"[.\s]+")


def sanitize(part: str) -> str:
    """fullname 分段用：去掉点号/空白（点号是 fullname 分隔符）。"""
    return _SANITIZE.sub("_", (part or "").strip()).strip("_") or "_"


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def make_doc_id(category: str, title: str) -> str:
    return f"{sanitize(category)}:{sanitize(title)}"


def chunk_document(text: str, category: str, title: str, doc_id: str | None = None) -> list[Block]:
    """把一份文档切成 Block 列表（未含向量）。"""
    doc_id = doc_id or make_doc_id(category, title)
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    blocks: list[Block] = []
    section = "正文"
    buf: list[str] = []
    has_article = any(_ARTICLE.match(ln) for ln in lines)

    def flush(sec: str):
        if not buf:
            return
        body = "\n".join(buf).strip()
        buf.clear()
        if not body:
            return
        ordinal = len(blocks) + 1
        fullname = f"{sanitize(category)}.{sanitize(title)}.{sanitize(sec)}.{ordinal}"
        blocks.append(Block(
            fullname=fullname, text=body, doc_id=doc_id, category=category,
            title=title, section=sec, ordinal=ordinal,
        ))

    if has_article:
        for ln in lines:
            ch = _CHAPTER.match(ln)
            if ch:
                flush(section)
                section = (ln.strip())
                continue
            if _ARTICLE.match(ln):
                flush(section)          # 上一条结束
            buf.append(ln)
        flush(section)
    else:
        # 无「条」标记：按段落聚合到 _MAX_CHARS
        size = 0
        for ln in lines:
            ch = _CHAPTER.match(ln)
            if ch:
                flush(section)
                section = ln.strip()
                size = 0
                continue
            buf.append(ln)
            size += len(ln)
            if size >= _MAX_CHARS:
                flush(section)
                size = 0
        flush(section)

    return blocks
