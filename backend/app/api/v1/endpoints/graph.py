"""/api/v1/graph —— 两层图浏览与手工维护（建立索引阶段的查看/编辑）。

- GET  ""                     按 collection 作用域返回实体 + 结构边（供前端图谱）
- GET  "/entity/{entity_id}"  实体详情：别名 + 出处块 + 邻接边
- GET  "/block"               ?fullname=&store_id= 看某块原文
- POST "/entities"            手工新增实体（source=manual，可选 auto 归一）
- POST "/entities/{id}/attach" 手工把某块 fullname 挂为该实体出处
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from core.api_handler import api_handler
from nexus.stores.block_store import block_store
from nexus.stores.edge_store import edge_store
from nexus.stores.entity_store import entity_store
from nexus.stores.store_registry import store_registry
from nexus.index.attach_entity import attach_entity

router = APIRouter()


def _entity_node(e) -> dict:
    return {
        "id": e.entity_id, "type": e.type, "name": e.name, "status": e.status,
        "origin": e.source, "locked": e.locked, "aliases": e.aliases,
    }


@router.get("")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def graph_view(request: Request, reg: store_registry = None,
                     entities: entity_store = None, edges: edge_store = None):
    """返回图谱：nodes + edges。query: collection?, type?"""
    q = request.query_params
    collection = q.get("collection") or None
    type_ = q.get("type") or None
    store_ids = reg.allowed_stores(collection)
    nodes = entities.list(type_=type_, store_ids=(store_ids if collection else None))
    node_ids = [n.entity_id for n in nodes]
    rels = edges.list_edges(entity_ids=node_ids)
    return {
        "nodes": [_entity_node(n) for n in nodes],
        "edges": [
            {"id": r.edge_id, "source": r.src, "target": r.dst, "type": r.type,
             "weight": r.weight, "origin": r.source, "locked": r.locked}
            for r in rels
        ],
        "collection": collection,
    }


@router.get("/entity/{entity_id}")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def entity_detail(request: Request, entity_id: str = None,
                        entities: entity_store = None, edges: edge_store = None):
    entity_id = entity_id or request.path_params.get("entity_id")
    ent = entities.get(entity_id)
    if ent is None:
        return {"state": "error", "message": f"实体不存在: {entity_id}"}
    evidence = edges.list_evidence(entity_id)
    neighbors = edges.list_edges()  # 全量后筛选该点邻接（数据量小）
    adj = [
        {"id": r.edge_id, "source": r.src, "target": r.dst, "type": r.type,
         "weight": r.weight, "origin": r.source}
        for r in neighbors if r.src == entity_id or r.dst == entity_id
    ]
    return {
        "entity": _entity_node(ent),
        "evidence": [
            {"fullname": ev.fullname, "store_id": ev.store_id, "weight": ev.weight, "origin": ev.source}
            for ev in evidence
        ],
        "edges": adj,
    }


@router.get("/block")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def block_view(request: Request, blocks: block_store = None):
    """看某块原文。query: fullname（必填）, store_id（必填）"""
    q = request.query_params
    fullname = q.get("fullname")
    store_id = q.get("store_id")
    if not fullname or not store_id:
        return {"state": "error", "message": "fullname / store_id 必填"}
    blk = blocks.get_block(fullname, store_id)
    if blk is None:
        return {"state": "error", "message": f"块不存在: {fullname}"}
    return {
        "fullname": blk.fullname, "text": blk.text, "title": blk.title,
        "category": blk.category, "section": blk.section, "ordinal": blk.ordinal,
        "store_id": blk.store_id,
    }


@router.post("/entities")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def add_entity(request: Request, attach: attach_entity = None):
    """手工新增实体。body: {name, type, aliases?, auto?}

    auto=True 时对同类型已有实体做 LLM 归一（可能复用已有节点）；
    auto=False 时直接新建（source=manual, locked）。手工新增不做 LLM 归一时无需 chat。
    """
    body = await request.json()
    name = (body.get("name") or "").strip()
    type_ = (body.get("type") or "").strip()
    aliases = body.get("aliases") or []
    if not name or not type_:
        return {"state": "error", "message": "name / type 必填"}
    entity_id = attach.attach(name, type_, aliases, source="manual", auto=False)
    return {"entity_id": entity_id}


@router.post("/entities/{entity_id}/attach")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def attach_evidence(request: Request, entity_id: str = None, edges: edge_store = None):
    """手工把某块挂为该实体出处。body: {fullname, store_id}"""
    from nexus.models.evidence import Evidence
    entity_id = entity_id or request.path_params.get("entity_id")
    body = await request.json()
    fullname = (body.get("fullname") or "").strip()
    store_id = (body.get("store_id") or "").strip()
    if not fullname or not store_id:
        return {"state": "error", "message": "fullname / store_id 必填"}
    edges.add_evidence(Evidence(
        entity_id=entity_id, fullname=fullname, store_id=store_id, source="manual", locked=True,
    ))
    return {"entity_id": entity_id, "fullname": fullname}
