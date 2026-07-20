"""Deterministic binding of validated logical names to visible stable IDs."""
from __future__ import annotations

from dataclasses import dataclass

from nexus.domain import QueryContext
from nexus.infrastructure import normalize_name


@dataclass(frozen=True)
class BoundNode:
    kind: str
    node_id: str
    label: str


@dataclass(frozen=True)
class BoundDocument:
    document_id: str
    title: str


class VocabularyBinder:
    def __init__(self, context: QueryContext):
        self.context = context

    def entity(self, value: str, entity_type: str | None = None) -> BoundNode:
        wanted = normalize_name(value)
        matches = [
            item for item in self.context.entities
            if wanted in {normalize_name(item.name), *(normalize_name(alias) for alias in item.aliases)}
            and (entity_type is None or item.entity_type == entity_type)
        ]
        ids = {item.entity_id for item in matches}
        if len(ids) != 1:
            raise ValueError(f"entity binding is missing or ambiguous: {value!r}")
        item = next(item for item in matches if item.entity_id in ids)
        return BoundNode(kind="entity", node_id=item.entity_id, label=item.name)

    def action(self, value: str) -> BoundNode:
        wanted = normalize_name(value)
        matches = [
            item for item in self.context.actions
            if wanted in {normalize_name(item.canonical_text), normalize_name(item.verb)}
        ]
        ids = {item.action_id for item in matches}
        if len(ids) != 1:
            raise ValueError(f"action binding is missing or ambiguous: {value!r}")
        item = next(item for item in matches if item.action_id in ids)
        return BoundNode(kind="action", node_id=item.action_id, label=item.canonical_text)

    def node(self, value: str, entity_type: str | None = None) -> BoundNode:
        entity_error: Exception | None = None
        try:
            return self.entity(value, entity_type)
        except ValueError as exc:
            entity_error = exc
        try:
            return self.action(value)
        except ValueError as action_error:
            raise ValueError(
                f"node binding failed for {value!r}: {entity_error}; {action_error}"
            ) from action_error

    def document(self, value: str) -> BoundDocument:
        wanted = normalize_name(value)
        matches = [
            item for item in self.context.documents
            if wanted in {normalize_name(item.title), normalize_name(item.document_id)}
        ]
        ids = {item.document_id for item in matches}
        if len(ids) != 1:
            raise ValueError(f"document binding is missing or ambiguous: {value!r}")
        item = next(item for item in matches if item.document_id in ids)
        return BoundDocument(document_id=item.document_id, title=item.title)
