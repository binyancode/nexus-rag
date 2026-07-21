"""Stage 1: choose one visible Collection and freeze active Generations."""
from __future__ import annotations

import json

from core.services import services
from nexus.domain import (
    ActionVocabularyItem,
    DocumentVocabularyItem,
    EntityVocabularyItem,
    QueryBudgets,
    QueryContext,
)
from nexus.infrastructure import ChatClient, EmbeddingClient, QueryRepository, StoreCollectionRepository

_COLLECTION_SYSTEM = (
    "You select exactly one visible Collection for a legal-information question. "
    "Return strict JSON with collection_id and reason. Use only a supplied collection_id."
)


class QueryInitializer:
    def initialize(
        self,
        *,
        run_id: str,
        question: str,
        llm_credential: str,
        embedding_credential: str,
        chat: ChatClient,
        embedder: EmbeddingClient,
        collection_id: str | None,
        as_user: str | None,
        max_parallel: int,
        budgets: QueryBudgets,
        temperature: float | None = None,
    ) -> QueryContext:
        question = (question or "").strip()
        if not question:
            raise ValueError("question is required")
        registry = services[StoreCollectionRepository]
        visible = registry.list_visible_collections(as_user)
        if not visible:
            raise ValueError("the current user has no visible Collection")

        selected_by = "user"
        if collection_id:
            selected = next((item for item in visible if item.collection_id == collection_id), None)
            if selected is None:
                raise ValueError(f"Collection is not visible: {collection_id}")
        else:
            selected = next((item for item in visible if item.is_default), None)
            if selected is not None:
                selected_by = "user_default"
            elif len(visible) == 1:
                selected = visible[0]
                selected_by = "only_visible"
            else:
                selected = self._route(question, visible, chat, temperature=temperature)
                selected_by = "semantic_router"

        scope = registry.freeze_scope(selected, selected_by)
        repository = services[QueryRepository]
        dimensions = repository.generation_dimensions(scope)
        incompatible = {
            store_id: value for store_id, value in dimensions.items()
            if value != embedder.dimensions
        }
        if incompatible:
            raise ValueError(
                "the selected embedding credential does not match frozen index dimensions: "
                + json.dumps(incompatible, ensure_ascii=False)
            )

        entity_rows = repository.visible_entities(scope)
        action_rows = repository.visible_actions(scope)
        document_rows = repository.visible_documents(scope)
        relations = tuple(repository.visible_graph_relations(scope))
        return QueryContext(
            run_id=run_id,
            as_user=as_user,
            question=question,
            collection=scope,
            llm_credential=llm_credential,
            embedding_credential=embedding_credential,
            max_parallel=max(1, min(64, int(max_parallel or 8))),
            budgets=budgets,
            generation_dimensions=dimensions,
            categories=tuple(sorted({row["category"] for row in document_rows})),
            documents=tuple(DocumentVocabularyItem(
                document_id=row["document_id"],
                document_version_id=row["document_version_id"],
                store_id=row["store_id"],
                generation_id=row["generation_id"],
                title=row["title"],
                category=row["category"],
                block_count=int(row.get("block_count") or 0),
            ) for row in document_rows),
            entities=tuple(EntityVocabularyItem(
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                name=row["name"],
                aliases=tuple(row.get("aliases") or ()),
            ) for row in entity_rows),
            actions=tuple(ActionVocabularyItem(
                action_id=row["action_id"],
                canonical_text=row["canonical_text"],
                verb=row["verb"],
            ) for row in action_rows),
            graph_relations=relations,
        )

    @staticmethod
    def _route(
        question: str,
        collections: list,
        chat: ChatClient,
        temperature: float | None = None,
    ):
        payload = {
            "question": question,
            "visible_collections": [
                {
                    "collection_id": item.collection_id,
                    "name": item.name,
                    "description": item.description,
                }
                for item in collections
            ],
            "output": {"collection_id": "one supplied id", "reason": "short string"},
        }
        if temperature is None:
            raw = chat.complete_json(_COLLECTION_SYSTEM, json.dumps(payload, ensure_ascii=False))
        else:
            raw = chat.complete_json(
                _COLLECTION_SYSTEM,
                json.dumps(payload, ensure_ascii=False),
                temperature=temperature,
            )
        selected_id = raw.get("collection_id") if isinstance(raw, dict) else None
        selected = next((item for item in collections if item.collection_id == selected_id), None)
        if selected is None:
            raise ValueError("Collection routing did not return a visible collection_id")
        return selected
