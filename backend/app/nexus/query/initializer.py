"""查询初始化器：确定唯一 Collection、可见 Store、预算和可见实体目录。"""
from __future__ import annotations

import json
import uuid

from core.services import services

from ..llm.chat import chat_client
from ..stores.entity_store import entity_store
from ..stores.document_store import document_store
from ..stores.store_registry import store_registry
from .models import CollectionScope, QueryBudgets, QueryContext

_COLLECTION_SELECTOR_SYSTEM = (
    "你是查询范围选择器。根据用户问题，从给定的可见 Collection 中选择最相关的一个。"
    "只能返回给定 collection_id，严格输出 JSON。"
)


class QueryInitializer:
    def initialize(self, question: str, llm_credential: str, embedding_credential: str,
                   chat: chat_client, collection_id: str | None = None,
                   as_user: str | None = None, max_parallel: int = 8,
                   budgets: QueryBudgets | None = None, run_id: str | None = None) -> QueryContext:
        question = (question or "").strip()
        if not question:
            raise ValueError("question 不能为空")

        collections = services[store_registry].list_visible_collections(as_user)
        if not collections:
            raise ValueError("没有可用于查询的 Collection")

        selected_by = "user"
        if collection_id:
            selected = next((c for c in collections if c.collection_id == collection_id), None)
            if selected is None:
                raise ValueError(f"Collection 不存在或当前用户不可见: {collection_id}")
        elif next((c for c in collections if c.is_default), None) is not None:
            selected = next(c for c in collections if c.is_default)
            selected_by = "user_default"
        elif len(collections) == 1:
            selected = collections[0]
            selected_by = "only_visible"
        else:
            selected = self._select_collection(question, collections, chat)
            selected_by = "semantic_router"

        allowed_stores = list(selected.stores or [])
        if not allowed_stores:
            raise ValueError(f"Collection {selected.collection_id!r} 没有可用 Store")

        visible = services[entity_store].list(store_ids=allowed_stores)
        catalog = [
            {"entity_id": e.entity_id, "type": e.type, "name": e.name, "aliases": e.aliases}
            for e in visible
        ]
        return QueryContext(
            run_id=run_id or uuid.uuid4().hex,
            as_user=as_user,
            question=question,
            collection=CollectionScope(
                collection_id=selected.collection_id,
                name=selected.name,
                selected_by=selected_by,
                allowed_stores=allowed_stores,
            ),
            llm_credential=llm_credential,
            embedding_credential=embedding_credential,
            max_parallel=max(1, min(64, int(max_parallel or 8))),
            budgets=budgets or QueryBudgets(),
            categories=services[document_store].list_categories(allowed_stores),
            entity_catalog=catalog,
        )

    @staticmethod
    def _select_collection(question: str, collections: list, chat: chat_client):
        options = [
            {"collection_id": c.collection_id, "name": c.name, "description": c.description}
            for c in collections
        ]
        result = chat.complete_json(
            _COLLECTION_SELECTOR_SYSTEM,
            "用户问题：\n" + question + "\n\n可见 Collections：\n"
            + json.dumps(options, ensure_ascii=False)
            + '\n\n输出：{"collection_id":"...","reason":"..."}',
        )
        selected_id = result.get("collection_id") if isinstance(result, dict) else None
        selected = next((c for c in collections if c.collection_id == selected_id), None)
        if selected is None:
            raise ValueError("无法自动确定 Collection，请由用户明确选择")
        return selected
