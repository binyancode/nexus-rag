"""在线查询 API：提交/取消走 Python；运行详情与历史由 BFF 直读数据库。"""
from __future__ import annotations

import threading
import uuid

from fastapi import APIRouter, Request

from core.api_handler import api_handler
from nexus.domain import QueryBudgets
from nexus.infrastructure import StoreCollectionRepository
from nexus.querying import cancel_query, run_query

router = APIRouter()


@router.get("/collections")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_query_collections(request: Request, registry: StoreCollectionRepository = None):
    identity = getattr(request.state, "identity", None)
    as_user = identity.user if identity else None
    return {
        "collections": [
            {
                "collection_id": c.collection_id,
                "name": c.name,
                "description": c.description,
                "stores": c.stores,
                "is_default": c.is_default,
            }
            for c in registry.list_visible_collections(as_user)
        ]
    }


@router.post("")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def create_query(request: Request):
    body = await request.json()
    question = (body.get("question") or "").strip()
    llm = (body.get("llm_credential") or "").strip()
    embedding = (body.get("embedding_credential") or "").strip()
    collection = (body.get("collection") or "").strip() or None
    if not question or not llm or not embedding:
        return {"state": "error", "message": "question / llm_credential / embedding_credential 必填"}
    try:
        max_parallel = max(1, min(64, int(body.get("max_parallel") or 8)))
        budgets = QueryBudgets.model_validate(body.get("budgets") or {})
    except Exception as exc:
        return {"state": "error", "message": f"查询参数不合法: {exc}"}

    identity = getattr(request.state, "identity", None)
    as_user = identity.user if identity else None
    run_id = uuid.uuid4().hex
    threading.Thread(
        target=run_query,
        args=(run_id, question, llm, embedding, collection, max_parallel, as_user, budgets),
        daemon=True,
    ).start()
    return {"run_id": run_id}


@router.post("/runs/{run_id}/cancel")
@api_handler.log()
@api_handler.auth()
async def cancel_query_run(request: Request, run_id: str = None):
    run_id = run_id or request.path_params.get("run_id")
    return {"run_id": run_id, "cancelling": cancel_query(run_id)}
