"""Stable document, version, and regulation block contracts."""
from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base contract used at all domain boundaries."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class Document(StrictModel):
    document_id: str = Field(min_length=1, max_length=256)
    canonical_title: str = Field(min_length=1, max_length=400)
    category: str = Field(min_length=1, max_length=100)
    source_uri: str | None = Field(default=None, max_length=1000)


class DocumentVersion(StrictModel):
    document_version_id: str = Field(min_length=1, max_length=64)
    generation_id: str = Field(min_length=1, max_length=64)
    document_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=400)
    category: str = Field(min_length=1, max_length=100)
    source_uri: str | None = Field(default=None, max_length=1000)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    block_count: int = Field(ge=0)
    raw_metadata: dict | None = None


class Block(StrictModel):
    """A generation-isolated evidence block with a stable structural address."""

    block_key: str = Field(min_length=1, max_length=450)
    generation_id: str = Field(min_length=1, max_length=64)
    document_version_id: str = Field(min_length=1, max_length=64)
    document_id: str = Field(min_length=1, max_length=256)
    block_id: str = Field(min_length=1, max_length=450)
    parent_block_id: str | None = Field(default=None, max_length=450)
    article_no: str | None = Field(default=None, max_length=50)
    paragraph_no: str | None = Field(default=None, max_length=50)
    item_no: str | None = Field(default=None, max_length=50)
    heading_path: str | None = Field(default=None, max_length=1000)
    ordinal: int = Field(gt=0)
    text: str = Field(min_length=1)
    text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def validate_identity(self) -> "Block":
        if sha256(self.text.encode("utf-8")).hexdigest() != self.text_hash:
            raise ValueError("text_hash does not match block text")
        return self


class DocumentBundle(StrictModel):
    document: Document
    version: DocumentVersion
    blocks: list[Block]

    @model_validator(mode="after")
    def validate_bundle(self) -> "DocumentBundle":
        if self.document.document_id != self.version.document_id:
            raise ValueError("document and version identities differ")
        if self.version.block_count != len(self.blocks):
            raise ValueError("document version block_count differs from blocks")
        if any(b.document_version_id != self.version.document_version_id for b in self.blocks):
            raise ValueError("block belongs to another document version")
        return self
