"""查询物理算子库。每个算子只执行一个固定动作，统一返回 QueryResult。"""
from __future__ import annotations

import json
from typing import Callable

from core.services import services
from services.workflow import NodeContext, NodeResult, Workflow

from ..stores.block_store import block_store
from ..stores.edge_store import edge_store
from .models import EvidenceGroup, QueryContext, QueryResult

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
    workflow.register("BlockUnion", op_block_union)
    workflow.register("EvidenceBundle", op_evidence_bundle)
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
        doc_ids=p.get("doc_ids"),
    )
    items = [_block_item(b) for b in blocks]
    result = QueryResult(
        kind="block_set", items=items,
        meta={"mode": mode, "count": len(items), "doc_ids": p.get("doc_ids") or []},
    )
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
    frontier_provenance = {
        x["entity_id"]: set(x.get("_evidence_fullnames") or [])
        for x in source.items if x.get("entity_id") in starts
    }
    seen = set(starts)
    frontier = set(starts)
    reached: set[str] = set()
    reached_provenance: dict[str, set[str]] = {}
    store = services[edge_store]
    for _ in range(hops):
        if not frontier:
            break
        next_frontier: set[str] = set()
        next_provenance: dict[str, set[str]] = {}
        for edge in store.list_incident(list(frontier)):
            if edge_types and edge.type not in edge_types:
                continue
            if direction in ("out", "both") and edge.src in frontier and edge.dst in visible:
                next_frontier.add(edge.dst)
                next_provenance.setdefault(edge.dst, set()).update(
                    frontier_provenance.get(edge.src, set()) | _edge_evidence(edge.evidence)
                )
            if direction in ("in", "both") and edge.dst in frontier and edge.src in visible:
                next_frontier.add(edge.src)
                next_provenance.setdefault(edge.src, set()).update(
                    frontier_provenance.get(edge.dst, set()) | _edge_evidence(edge.evidence)
                )
        next_frontier -= seen
        next_provenance = {x: refs for x, refs in next_provenance.items() if x in next_frontier}
        reached.update(next_frontier)
        for entity_id, refs in next_provenance.items():
            reached_provenance.setdefault(entity_id, set()).update(refs)
        seen.update(next_frontier)
        frontier = next_frontier
        frontier_provenance = next_provenance
        if len(reached) >= query.budgets.max_entities:
            break
    items = []
    for entity_id in reached:
        if target_types and visible[entity_id]["type"] not in target_types:
            continue
        item = dict(visible[entity_id])
        refs = sorted(reached_provenance.get(entity_id) or [])
        if refs:
            item["_evidence_fullnames"] = refs
        items.append(item)
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
    by_entity: dict[str, list] = {}
    for ev in sorted(evidence, key=lambda x: x.weight, reverse=True):
        by_entity.setdefault(ev.entity_id, []).append(ev)

    # Traverse 携带的是“该关系由哪些原文块支持”；优先使用它，避免拿实体在其他语境下的出处佐证关系。
    for entity in entities.items:
        entity_id = entity.get("entity_id")
        for fullname in entity.get("_evidence_fullnames") or []:
            if len(items) >= max_blocks:
                break
            for store_id in query.allowed_stores:
                key = (store_id, fullname)
                if key in seen:
                    continue
                block = services[block_store].get_block(fullname, store_id)
                if block:
                    seen.add(key)
                    item = _block_item(block)
                    item["entity_id"] = entity_id
                    item["weight"] = 1.0
                    items.append(item)
                    break

    # 再为尚未覆盖的实体公平补一条出处，最后按权重填满剩余预算。
    covered = {x.get("entity_id") for x in items}
    ordered = []
    for entity_id in ids:
        if entity_id not in covered and by_entity.get(entity_id):
            ordered.append(by_entity[entity_id][0])
    ordered.extend(ev for values in by_entity.values() for ev in values)
    for ev in ordered:
        if len(items) >= max_blocks:
            break
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


def op_block_union(ctx: NodeContext) -> NodeResult:
    sources = _all_inputs(ctx)
    merged: dict[str, dict] = {}
    for source in sources.values():
        for item in source.items:
            key = f"{item.get('store_id') or ''}|{item.get('fullname') or ''}"
            if item.get("fullname"):
                merged[key] = item
    items = list(merged.values())
    return _done(QueryResult(kind="block_set", items=items), f"合并得到 {len(items)} 个原文块")


def op_evidence_bundle(ctx: NodeContext) -> NodeResult:
    sources = _all_inputs(ctx)
    labels = ctx.node.params.get("labels") or {}
    groups: list[EvidenceGroup] = []
    flattened: list[dict] = []
    for port, source in sources.items():
        items = list(source.items)
        doc_ids = list(dict.fromkeys(x.get("doc_id") for x in items if x.get("doc_id")))
        groups.append(EvidenceGroup(key=port, label=labels[port], doc_ids=doc_ids, items=items))
        flattened.extend(items)
    empty = [g.key for g in groups if not g.items]
    result = QueryResult(
        kind="evidence_bundle", items=flattened, groups=groups,
        meta={"group_count": len(groups), "empty_groups": empty, "complete": not empty},
    )
    return _done(result, f"证据分组 {len(groups)} 组 · 共 {len(flattened)} 块")


def _set_op(ctx: NodeContext, operation: str) -> NodeResult:
    left = _input(ctx, "left")
    right = _input(ctx, "right")
    a, b = _by_key(left.items), _by_key(right.items)
    if operation == "intersection":
        keys = a.keys() & b.keys()
        items = [_merge_item(a[x], b[x]) for x in keys]
    elif operation == "difference":
        keys = a.keys() - b.keys()
        items = [a[x] for x in keys]
    else:
        items = []
        for key in a.keys() | b.keys():
            items.append(_merge_item(a[key], b[key]) if key in a and key in b else (a.get(key) or b[key]))
    result = QueryResult(
        kind=left.kind,
        items=items,
        meta={
            "set_operation": operation,
            "left_count": len(a),
            "right_count": len(b),
            "result_count": len(items),
        },
    )
    return _done(result, f"集合运算后 {len(items)} 项")


def _query(ctx: NodeContext) -> QueryContext:
    return ctx.res("query_context")


def _input(ctx: NodeContext, port: str) -> QueryResult:
    bindings = ctx.node.params.get("_inputs") or {}
    node_id = bindings.get(port)
    if not node_id:
        raise ValueError(f"节点 {ctx.node.id} 缺少输入端口 {port}")
    return QueryResult.from_value(ctx.dep(node_id))


def _all_inputs(ctx: NodeContext) -> dict[str, QueryResult]:
    bindings = ctx.node.params.get("_inputs") or {}
    return {port: QueryResult.from_value(ctx.dep(node_id)) for port, node_id in bindings.items()}


def _by_key(items: list[dict]) -> dict[str, dict]:
    result = {}
    for item in items:
        key = item.get("entity_id") or item.get("fullname") or item.get("id")
        if key:
            normalized = str(key)
            result[normalized] = _merge_item(result[normalized], item) if normalized in result else item
    return result


def _merge_item(left: dict, right: dict) -> dict:
    merged = dict(left)
    refs = set(left.get("_evidence_fullnames") or []) | set(right.get("_evidence_fullnames") or [])
    if refs:
        merged["_evidence_fullnames"] = sorted(refs)
    return merged


def _edge_evidence(value: str | None) -> set[str]:
    if not value:
        return set()
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        parsed = value
    if isinstance(parsed, list):
        return {str(x) for x in parsed if x}
    return {str(parsed)} if parsed else set()


def _block_item(block) -> dict:
    return block.model_dump(exclude={"vector"})


def _done(result: QueryResult, value: str, tokens: dict | None = None) -> NodeResult:
    return NodeResult(output=result.to_dict(), value=value, tokens=tokens)
