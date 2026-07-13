"""Store, Collection, and immutable query-scope contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .documents import StrictModel


class FrozenStrictModel(StrictModel):
    """Strict value object used after query initialization."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, frozen=True)


class SearchStore(StrictModel):
    store_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    credential_name: str = Field(min_length=1, max_length=200)
    index_name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Literal["block"] = "block"
    active_generation_id: str | None = Field(default=None, max_length=64)
    is_default: bool = False


class Collection(StrictModel):
    collection_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    is_public: bool = False
    stores: list[str] = Field(default_factory=list)
    is_default: bool = False


CollectionSelection = Literal["user", "user_default", "only_visible", "semantic_router"]


class CollectionScope(FrozenStrictModel):
    collection_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    selected_by: CollectionSelection
    allowed_stores: tuple[str, ...] = Field(min_length=1)
    generation_scope: dict[str, str]

    @model_validator(mode="after")
    def validate_generation_scope(self) -> "CollectionScope":
        if len(self.allowed_stores) != len(set(self.allowed_stores)):
            raise ValueError("allowed_stores must be unique")
        if set(self.allowed_stores) != set(self.generation_scope):
            raise ValueError("generation_scope must contain exactly one generation for every allowed store")
        if any(not generation_id.strip() for generation_id in self.generation_scope.values()):
            raise ValueError("generation_scope cannot contain empty generation ids")
        return self


class QueryBudgets(FrozenStrictModel):
    max_entities: int = Field(default=200, ge=1, le=5000)
    max_blocks: int = Field(default=30, ge=1, le=500)
    max_tokens: int = Field(default=30000, ge=1000, le=500000)


class EntityVocabularyItem(FrozenStrictModel):
    entity_id: str
    entity_type: str
    name: str
    aliases: tuple[str, ...] = ()


class ActionVocabularyItem(FrozenStrictModel):
    action_id: str
    canonical_text: str
    verb: str


class DocumentVocabularyItem(FrozenStrictModel):
    document_id: str
    document_version_id: str
    store_id: str
    generation_id: str
    title: str
    category: str
    block_count: int = Field(ge=0)


class QueryContext(FrozenStrictModel):
    run_id: str = Field(min_length=1, max_length=64)
    as_user: str | None = Field(default=None, max_length=256)
    question: str = Field(min_length=1)
    collection: CollectionScope
    llm_credential: str = Field(min_length=1, max_length=200)
    embedding_credential: str = Field(min_length=1, max_length=200)
    max_parallel: int = Field(default=8, ge=1, le=64)
    budgets: QueryBudgets = Field(default_factory=QueryBudgets)
    generation_dimensions: dict[str, int]
    categories: tuple[str, ...] = ()
    documents: tuple[DocumentVocabularyItem, ...] = ()
    entities: tuple[EntityVocabularyItem, ...] = ()
    actions: tuple[ActionVocabularyItem, ...] = ()
    graph_relations: tuple[str, ...] = ()

    @property
    def allowed_stores(self) -> tuple[str, ...]:
        return self.collection.allowed_stores

    @property
    def generation_scope(self) -> dict[str, str]:
        return self.collection.generation_scope

    @model_validator(mode="after")
    def validate_dimensions(self) -> "QueryContext":
        if set(self.generation_dimensions) != set(self.collection.allowed_stores):
            raise ValueError("generation_dimensions must cover the frozen Store scope")
        if any(int(value) <= 0 for value in self.generation_dimensions.values()):
            raise ValueError("embedding dimensions must be positive")
        return self
