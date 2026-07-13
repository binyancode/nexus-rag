"""Deterministic structure-aware chunking for Chinese regulations."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from nexus.domain import Block, Document, DocumentBundle, DocumentVersion
from nexus.domain.documents import make_block_key, make_document_version_id

_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(第\s*[一二三四五六七八九十百千万零〇两\d]+\s*[编章节款]\s*[^\n]*)\s*$"
)
_ARTICLE = re.compile(
    r"^\s*(第\s*(?P<number>[一二三四五六七八九十百千万零〇两\d]+)\s*条)(?P<body>[\s\S]*)$"
)
_SAFE = re.compile(r"[^0-9A-Za-z\u3400-\u9fff_-]+")


@dataclass(frozen=True)
class _Segment:
    text: str
    heading_path: str | None
    article_no: str | None
    paragraph_no: str | None = None
    item_no: str | None = None


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def document_id(category: str, title: str) -> str:
    digest = hashlib.sha256(f"{category.strip()}\0{title.strip()}".encode("utf-8")).hexdigest()[:32]
    return f"doc_{digest}"


def title_from_filename(filename: str) -> str:
    """Keep the upload title rule in one place for merge/replacement classification."""
    value = (filename or "untitled.txt").strip()
    return value.rsplit(".", 1)[0].strip() or value


def document_version_id(generation_id: str, doc_id: str, doc_hash: str) -> str:
    return make_document_version_id(generation_id, doc_id, doc_hash)


def generation_block_key(generation_id: str, block_id: str) -> str:
    return make_block_key(generation_id, block_id)


def _address(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    return _SAFE.sub("-", normalized).strip("-") or "missing"


def chunk_document(
    *,
    text: str,
    category: str,
    title: str,
    generation_id: str,
    source_uri: str | None = None,
    raw_metadata: dict | None = None,
) -> DocumentBundle:
    """Chunk one regulation while keeping stable article addresses.

    Article labels are the primary stable identity. Duplicate labels receive deterministic
    ``duplicate-N`` suffixes in encounter order. Content without an article label receives
    a content-hash address, so unrelated insertions do not renumber it.
    """
    normalized_text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_text:
        raise ValueError("document text is empty")
    title = (title or "").strip()
    category = (category or "").strip()
    if not title or not category:
        raise ValueError("title and category are required")

    doc_id = document_id(category, title)
    doc_hash = content_hash(normalized_text)
    version_id = document_version_id(generation_id, doc_id, doc_hash)
    segments = _segments(normalized_text)
    duplicates: dict[str, int] = {}
    fallback_duplicates: dict[str, int] = {}
    blocks: list[Block] = []

    for ordinal, segment in enumerate(segments, start=1):
        if segment.article_no:
            stem = "article-" + _address(segment.article_no)
            duplicates[stem] = duplicates.get(stem, 0) + 1
            suffix = "" if duplicates[stem] == 1 else f"-duplicate-{duplicates[stem]}"
            address = stem + suffix
        else:
            digest = content_hash(segment.text)[:16]
            fallback_duplicates[digest] = fallback_duplicates.get(digest, 0) + 1
            suffix = "" if fallback_duplicates[digest] == 1 else f"-{fallback_duplicates[digest]}"
            address = "unlabelled-" + digest + suffix

        block_id = f"{doc_id}:{address}"
        if segment.paragraph_no:
            block_id += ":paragraph-" + _address(segment.paragraph_no)
        if segment.item_no:
            block_id += ":item-" + _address(segment.item_no)
        block_key = generation_block_key(generation_id, block_id)
        blocks.append(Block(
            block_key=block_key,
            generation_id=generation_id,
            document_version_id=version_id,
            document_id=doc_id,
            block_id=block_id,
            parent_block_id=None,
            article_no=segment.article_no,
            paragraph_no=segment.paragraph_no,
            item_no=segment.item_no,
            heading_path=segment.heading_path,
            ordinal=ordinal,
            text=segment.text,
            text_hash=content_hash(segment.text),
            category=category,
            title=title,
        ))

    document = Document(
        document_id=doc_id,
        canonical_title=title,
        category=category,
        source_uri=source_uri,
    )
    version = DocumentVersion(
        document_version_id=version_id,
        generation_id=generation_id,
        document_id=doc_id,
        title=title,
        category=category,
        source_uri=source_uri,
        content_hash=doc_hash,
        block_count=len(blocks),
        raw_metadata=raw_metadata,
    )
    return DocumentBundle(document=document, version=version, blocks=blocks)


def _segments(text: str) -> list[_Segment]:
    lines = text.split("\n")
    heading_stack: list[str] = []
    segments: list[_Segment] = []
    buffer: list[str] = []
    article_no: str | None = None
    active_heading: str | None = None

    def flush() -> None:
        nonlocal buffer, article_no
        body = "\n".join(buffer).strip()
        buffer = []
        if body:
            segments.append(_Segment(text=body, heading_path=active_heading, article_no=article_no))
        article_no = None

    for line in lines:
        heading_match = _HEADING.match(line)
        article_match = _ARTICLE.match(line)
        if heading_match and not article_match:
            flush()
            heading = heading_match.group(1).strip()
            if re.search(r"第\s*.+\s*[编章]", heading):
                heading_stack = [heading]
            else:
                heading_stack = heading_stack[:1] + [heading]
            active_heading = " / ".join(heading_stack)
            continue
        if article_match:
            flush()
            article_no = article_match.group("number")
            buffer.append(line.strip())
            continue
        buffer.append(line)
    flush()

    if not segments:
        raise ValueError("chunker produced no blocks")
    return segments
