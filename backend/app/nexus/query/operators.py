"""查询物理算子库。每个算子只执行一个固定动作，统一返回 QueryResult。"""
from __future__ import annotations

from typing import Callable

from core.services import services
from services.workflow import NodeContext, NodeResult, Workflow

from ..stores.block_store import block_store
from ..stores.edge_store import edge_store
from .models import QueryContext, QueryResult

Operator = Callable[[NodeContext], NodeResult]


def register_physical_operators(workflow: Workflow) -> Workflow:
    workflow.register("EntitySearch", op_entity_search)
    workflow.register("BlockSearch", op_block_search)
    workflow.register("Traverse", op_traverse)
    workflow.register("Lift", op_lift)
    workflow.register("Ground", op_ground)
    workflow.register("Intersect", op_intersect)
    workflow.register("Diff", op_diff)
    workflow.register("Union", op_union)
    workflow.register("Dedup", op_dedup)
    return workflow


def op_entity_search(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    p = ctx.node.params
    entity_id = p.get("entity_id")
    text = str(p.get("text") or "").strip().casefold()
    allowed_types = set(p.get("entity_types") or [])
    exact, fuzzy = [], []
    for item in query.entity_catalog:
        if entity_id and item["entity_id"] != entity_id:
            continue
        if allowed_types and item["type"] not in allowed_types:
            continue
        terms = [item["name"], *(item.get("aliases") or [])]
        folded = [x.casefold() for x in terms]
        if entity_id or text in folded:
            exact.append(item)
        elif text and any(text in x or x in text for x in folded):
            fuzzy.append(item)
    items = (exact or fuzzy)[:query.budgets.max_entities]
    result = QueryResult(kind="entity_set", items=items, meta={"query": p.get("text"), "count": len(items)})
    return _done(result, f"命中 {len(items)} 个实体")


def op_block_search(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    p = ctx.node.params
    text = str(p.get("text") or query.question)
    mode = p.get("mode") or "hybrid"
    embedder = ctx.res("embedder")
    vector = None
    tokens = None
    if mode in ("vector", "hybrid"):
        embedder.reset_usage()
        vector = embedder.embed_one(text)
        tokens = embedder.pop_usage()
    blocks = services[block_store].search(
        query.allowed_stores,
        query_text=text if mode in ("keyword", "hybrid") else None,
        query_vector=vector,
        top=min(int(p.get("top") or query.budgets.max_blocks), query.budgets.max_blocks),
        category=p.get("category"),
    )
    items = [_block_item(b) for b in blocks]
    result = QueryResult(kind="block_set", items=items, meta={"mode": mode, "count": len(items)})
    return _done(result, f"命中 {len(items)} 个原文块", tokens)


def op_traverse(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    source = _input(ctx, "entities")
    p = ctx.node.params
    edge_types = set(p.get("edge_types") or [])
    target_types = set(p.get("target_types") or [])
    direction = p.get("direction") or "both"
    hops = max(1, min(10, int(p.get("hops") or 1)))
    visible = {x["entity_id"]: x for x in query.entity_catalog}
    starts = {x["entity_id"] for x in source.items if x.get("entity_id") in visible}
    seen = set(starts)
    frontier = set(starts)
    reached: set[str] = set()
    store = services[edge_store]
    for _ in range(hops):
        if not frontier:
            break
        next_frontier: set[str] = set()
        for edge in store.list_incident(list(frontier)):
            if edge_types and edge.type not in edge_types:
                continue
            if direction in ("out", "both") and edge.src in frontier and edge.dst in visible:
                next_frontier.add(edge.dst)
            if direction in ("in", "both") and edge.dst in frontier and edge.src in visible:
                next_frontier.add(edge.src)
        next_frontier -= seen
        reached.update(next_frontier)
        seen.update(next_frontier)
        frontier = next_frontier
        if len(reached) >= query.budgets.max_entities:
            break
    items = [visible[x] for x in reached if not target_types or visible[x]["type"] in target_types]
    items = items[:query.budgets.max_entities]
    return _done(QueryResult(kind="entity_set", items=items, meta={"hops": hops}), f"遍历得到 {len(items)} 个实体")


def op_lift(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    blocks = _input(ctx, "blocks")
    fullnames = [x.get("fullname") for x in blocks.items if x.get("fullname")]
    evidence = services[edge_store].list_evidence_for_fullnames(fullnames, query.allowed_stores)
    wanted = {x.entity_id for x in evidence}
    items = [x for x in query.entity_catalog if x["entity_id"] in wanted][:query.budgets.max_entities]
    return _done(QueryResult(kind="entity_set", items=items), f"提升得到 {len(items)} 个实体")


def op_ground(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    entities = _input(ctx, "entities")
    ids = [x.get("entity_id") for x in entities.items if x.get("entity_id")]
    evidence = services[edge_store].list_evidence_for_entities(ids, query.allowed_stores)
    max_blocks = min(int(ctx.node.params.get("top") or query.budgets.max_blocks), query.budgets.max_blocks)
    items, seen = [], set()
    for ev in sorted(evidence, key=lambda x: x.weight, reverse=True):
        key = (ev.store_id, ev.fullname)
        if key in seen:
            continue
        seen.add(key)
        block = services[block_store].get_block(ev.fullname, ev.store_id)
        if block:
            item = _block_item(block)
            item["entity_id"] = ev.entity_id
            item["weight"] = ev.weight
            items.append(item)
        if len(items) >= max_blocks:
            break
    return _done(QueryResult(kind="block_set", items=items), f"取得 {len(items)} 个依据块")


def op_intersect(ctx: NodeContext) -> NodeResult:
    return _set_op(ctx, "intersection")


def op_diff(ctx: NodeContext) -> NodeResult:
    return _set_op(ctx, "difference")


def op_union(ctx: NodeContext) -> NodeResult:
    return _set_op(ctx, "union")


def op_dedup(ctx: NodeContext) -> NodeResult:
    source = _input(ctx, "items")
    items = list(_by_key(source.items).values())
    return _done(QueryResult(kind=source.kind, items=items), f"去重后 {len(items)} 项")


def _set_op(ctx: NodeContext, operation: str) -> NodeResult:
    left = _input(ctx, "left")
    right = _input(ctx, "right")
    a, b = _by_key(left.items), _by_key(right.items)
    if operation == "intersection":
        keys = a.keys() & b.keys()
        items = [a[x] for x in keys]
    elif operation == "difference":
        keys = a.keys() - b.keys()
        items = [a[x] for x in keys]
    else:
        items = list({**a, **b}.values())
    return _done(QueryResult(kind=left.kind, items=items), f"集合运算后 {len(items)} 项")


def _query(ctx: NodeContext) -> QueryContext:
    return ctx.res("query_context")


def _input(ctx: NodeContext, port: str) -> QueryResult:
    bindings = ctx.node.params.get("_inputs") or {}
    node_id = bindings.get(port)
    if not node_id:
        raise ValueError(f"节点 {ctx.node.id} 缺少输入端口 {port}")
    return QueryResult.from_value(ctx.dep(node_id))


def _by_key(items: list[dict]) -> dict[str, dict]:
    result = {}
    for item in items:
        key = item.get("entity_id") or item.get("fullname") or item.get("id")
        if key:
            result[str(key)] = item
    return result


def _block_item(block) -> dict:
    return block.model_dump(exclude={"vector"})


def _done(result: QueryResult, value: str, tokens: dict | None = None) -> NodeResult:
    return NodeResult(output=result.to_dict(), value=value, tokens=tokens)
