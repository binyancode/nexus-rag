"""Strict Assertion-first extraction contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .documents import StrictModel

EntityType = Literal["Reg", "Org", "Activity", "Product", "Category", "Concept"]
ActionParticipantRole = Literal["object", "recipient", "authority", "beneficiary", "instrument", "target"]
AssertionParticipantRole = Literal[
    "subject", "object", "recipient", "authority", "beneficiary",
    "regulation", "activity", "product", "term",
]
AssertionKind = Literal["norm", "definition", "relation", "deadline", "penalty"]
Modality = Literal["must", "must_not", "may", "should", "factual", "conditional_may"]


class EntityMentionDraft(StrictModel):
    local_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    mention_text: str = Field(min_length=1, max_length=1000)
    canonical_name: str = Field(min_length=1, max_length=400)
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list, max_length=20)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, gt=0)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_span(self) -> "EntityMentionDraft":
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("mention offsets must both be present or absent")
        if self.start_offset is not None and self.end_offset <= self.start_offset:
            raise ValueError("mention end_offset must be greater than start_offset")
        return self


class ActionParticipantDraft(StrictModel):
    role: ActionParticipantRole
    entity_local_id: str | None = Field(default=None, min_length=1, max_length=64)
    value_text: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_target(self) -> "ActionParticipantDraft":
        if (self.entity_local_id is None) == (self.value_text is None):
            raise ValueError("action participant requires exactly one entity_local_id or value_text")
        return self


class ActionDraft(StrictModel):
    local_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    canonical_text: str = Field(min_length=1, max_length=1000)
    verb: str = Field(min_length=1, max_length=200)
    participants: list[ActionParticipantDraft] = Field(default_factory=list, max_length=30)
    confidence: float = Field(ge=0, le=1)


class AssertionParticipantDraft(StrictModel):
    role: AssertionParticipantRole
    entity_local_id: str | None = Field(default=None, min_length=1, max_length=64)
    value_text: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_target(self) -> "AssertionParticipantDraft":
        if self.entity_local_id is None and self.value_text is None:
            raise ValueError("assertion participant requires entity_local_id or value_text")
        return self


class LegalAssertionDraft(StrictModel):
    local_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    kind: AssertionKind
    predicate: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    modality: Modality
    action_local_id: str | None = Field(default=None, min_length=1, max_length=64)
    participants: list[AssertionParticipantDraft] = Field(min_length=1, max_length=40)
    condition: str | None = None
    exception: str | None = None
    scope: str | None = None
    payload: dict | None = None
    quote: str = Field(min_length=1)
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_shape(self) -> "LegalAssertionDraft":
        if self.quote_end <= self.quote_start:
            raise ValueError("quote_end must be greater than quote_start")
        roles = {p.role for p in self.participants}
        if self.kind in {"norm", "deadline", "penalty"} and self.action_local_id is None:
            raise ValueError(f"{self.kind} assertion requires action_local_id")
        if self.kind == "norm" and "subject" not in roles:
            raise ValueError("norm assertion requires a subject participant")
        if self.kind == "relation" and ("subject" not in roles or len(self.participants) < 2):
            raise ValueError("relation assertion requires a subject and at least one target participant")
        if self.modality == "conditional_may" and not (self.condition or "").strip():
            raise ValueError("conditional_may requires condition")
        return self


class BlockExtraction(StrictModel):
    """The only accepted LLM response shape, including explicit empty output."""

    empty: bool
    empty_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    entities: list[EntityMentionDraft]
    actions: list[ActionDraft]
    assertions: list[LegalAssertionDraft]

    @model_validator(mode="after")
    def validate_empty_contract(self) -> "BlockExtraction":
        if self.empty:
            if not (self.empty_reason or "").strip():
                raise ValueError("explicit empty extraction requires empty_reason")
            if self.entities or self.actions or self.assertions:
                raise ValueError("empty extraction cannot contain entities, actions, or assertions")
        else:
            if self.empty_reason is not None:
                raise ValueError("non-empty extraction cannot contain empty_reason")
            if not self.assertions:
                raise ValueError("non-empty extraction requires at least one legal assertion")
        return self
