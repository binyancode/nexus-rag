"""Assertion-supported graph API constrained to one visible Collection snapshot."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api_handler import api_handler
from nexus.infrastructure import GenerationSearchAdapter, GraphRepository, StoreCollectionRepository

router = APIRouter()


def _scope(request: Request, registry: StoreCollectionRepository):
    identity = getattr(request.state, "identity", None)
    as_user = identity.user if identity else None
    visible = registry.list_visible_collections(as_user)
    requested = (request.query_params.get("collection") or "").strip() or None
    if requested:
        selected = next((item for item in visible if item.collection_id == requested), None)
        selected_by = "user"
        if selected is None:
            raise ValueError(f"Collection is not visible: {requested}")
    else:
        selected = next((item for item in visible if item.is_default), None)
        selected_by = "user_default"
        if selected is None and len(visible) == 1:
            selected = visible[0]
            selected_by = "only_visible"
        if selected is None:
            raise ValueError("collection is required when no unique/default visible Collection exists")
    return registry.freeze_scope(selected, selected_by)


@router.get("")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def graph_view(
    request: Request,
    registry: StoreCollectionRepository = None,
    graph: GraphRepository = None,
):
    scope = _scope(request, registry)
    nodes, edges = graph.graph(scope, request.query_params.get("type") or None)
    return {
        "nodes": nodes,
        "edges": edges,
        "collection": scope.collection_id,
        "generation_scope": scope.generation_scope,
    }


@router.get("/catalog")
@router.get("/entities")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def graph_catalog(
    request: Request,
    registry: StoreCollectionRepository = None,
    graph: GraphRepository = None,
):
    scope = _scope(request, registry)
    return {
        "nodes": graph.catalog(scope, request.query_params.get("type") or None),
        "collection": scope.collection_id,
        "generation_scope": scope.generation_scope,
    }


@router.get("/neighborhood/{node_id}")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def graph_neighborhood(
    request: Request,
    node_id: str = None,
    registry: StoreCollectionRepository = None,
    graph: GraphRepository = None,
):
    node_id = node_id or request.path_params.get("node_id")
    try:
        depth = int(request.query_params.get("depth") or 2)
    except (TypeError, ValueError):
        depth = 2
    depth = 0 if depth == 0 else max(1, min(10, depth))
    scope = _scope(request, registry)
    try:
        nodes, edges, expandable = graph.neighborhood(scope, node_id, depth)
    except ValueError as exc:
        return JSONResponse(
            {
                "state": "stale_generation",
                "message": "活动索引代次已变化，请刷新知识图谱后重试",
                "node_id": node_id,
                "collection": scope.collection_id,
                "generation_scope": scope.generation_scope,
                "detail": str(exc),
            },
            status_code=409,
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "expandable": expandable,
        "root": node_id,
        "depth": depth,
        "collection": scope.collection_id,
        "generation_scope": scope.generation_scope,
    }


@router.get("/node/{node_id}")
@router.get("/entity/{node_id}")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def node_detail(
    request: Request,
    node_id: str = None,
    registry: StoreCollectionRepository = None,
    graph: GraphRepository = None,
):
    node_id = node_id or request.path_params.get("node_id")
    scope = _scope(request, registry)
    try:
        detail = graph.node_detail(scope, node_id)
    except ValueError as exc:
        return JSONResponse(
            {
                "state": "stale_generation",
                "message": "活动索引代次已变化，请刷新知识图谱后重试",
                "node_id": node_id,
                "collection": scope.collection_id,
                "generation_scope": scope.generation_scope,
                "detail": str(exc),
            },
            status_code=409,
        )
    detail["collection"] = scope.collection_id
    return detail


@router.get("/edge/{edge_id}")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def edge_detail(
    request: Request,
    edge_id: int = None,
    registry: StoreCollectionRepository = None,
    graph: GraphRepository = None,
):
    edge_id = int(edge_id or request.path_params.get("edge_id"))
    scope = _scope(request, registry)
    return {
        "edge_id": edge_id,
        "support": graph.edge_support(scope, edge_id),
        "collection": scope.collection_id,
    }


@router.get("/block")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def block_view(
    request: Request,
    registry: StoreCollectionRepository = None,
    graph: GraphRepository = None,
    search: GenerationSearchAdapter = None,
):
    block_key = (request.query_params.get("block_key") or "").strip()
    if not block_key:
        return {"state": "error", "message": "block_key is required"}
    scope = _scope(request, registry)
    location = graph.block_location(scope, block_key)
    if location is None:
        return {"state": "error", "message": "block is outside the Collection generation scope"}
    block = search.get_block(
        store_id=location["store_id"],
        generation_id=location["generation_id"],
        block_key=block_key,
        dimensions=int(location["embedding_dimensions"]),
    )
    if block is None:
        return {"state": "error", "message": f"block is missing from AI Search: {block_key}"}
    block["store_id"] = location["store_id"]
    return block


@router.post("/entities")
@router.post("/entities/{node_id}/attach")
@api_handler.log()
@api_handler.auth()
async def unsupported_manual_graph_edit(request: Request, node_id: str = None):
    return {
        "state": "unsupported",
        "message": (
            "Manual entity creation and legacy evidence attachment are not supported by the "
            "Assertion-first graph. Rebuild a reviewed index generation instead."
        ),
    }
