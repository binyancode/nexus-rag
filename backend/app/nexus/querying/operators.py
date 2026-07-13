"""Assertion-aware physical operator implementations."""
from __future__ import annotations

from typing import Callable

from core.services import services
from nexus.domain import QueryContext
from nexus.infrastructure import GenerationSearchAdapter, QueryRepository
from services.workflow import NodeContext, NodeResult, Workflow

from .models import EvidenceGroup, OperatorResult

Operator = Callable[[NodeContext], NodeResult]


def register_physical_operators(workflow: Workflow) -> Workflow:
    workflow.register("EntityLookup", op_entity_lookup)
    workflow.register("ActionLookup", op_action_lookup)
    workflow.register("SubjectAssertions", op_subject_assertions)
    workflow.register("SubjectActions", op_subject_actions)
    workflow.register("ActionSubjects", op_action_subjects)
    workflow.register("AssertionSearch", op_assertion_search)
    workflow.register("GraphTraverse", op_graph_traverse)
    workflow.register("FilterModality", op_filter_modality)
    workflow.register("Intersect", op_intersect)
    workflow.register("Diff", op_diff)
    workflow.register("Union", op_union)
    workflow.register("GroundAssertions", op_ground_assertions)
    workflow.register("BlockSearch", op_block_search)
    workflow.register("EvidenceBundle", op_evidence_bundle)
    return workflow


def op_entity_lookup(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    wanted = set(ctx.node.params.get("entity_ids") or [])
    items = [
        {
            "node_kind": "entity",
            "node_id": item.entity_id,
            "entity_id": item.entity_id,
            "type": item.entity_type,
            "name": item.name,
            "aliases": list(item.aliases),
        }
        for item in query.entities if item.entity_id in wanted
    ]
    if {item["entity_id"] for item in items} != wanted:
        raise ValueError("EntityLookup contains an ID outside the frozen visible vocabulary")
    return _done(OperatorResult(kind="entity_set", items=items), f"绑定 {len(items)} 个主体")


def op_action_lookup(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    wanted = set(ctx.node.params.get("action_ids") or [])
    items = [
        {
            "node_kind": "action",
            "node_id": item.action_id,
            "action_id": item.action_id,
            "canonical_text": item.canonical_text,
            "verb": item.verb,
            "name": item.canonical_text,
        }
        for item in query.actions if item.action_id in wanted
    ]
    if {item["action_id"] for item in items} != wanted:
        raise ValueError("ActionLookup contains an ID outside the frozen visible vocabulary")
    return _done(OperatorResult(kind="action_set", items=items), f"绑定 {len(items)} 个行动")


def op_subject_assertions(ctx: NodeContext) -> NodeResult:
    subjects = _input(ctx, "subjects")
    params = ctx.node.params
    items = services[QueryRepository].subject_assertions(
        _query(ctx).collection,
        [item["entity_id"] for item in subjects.items],
        modalities=params.get("modalities") or [],
        kinds=params.get("assertion_kinds") or [],
        predicate=params.get("predicate"),
        limit=_query(ctx).budgets.max_entities * 10,
    )
    return _done(OperatorResult(kind="fact_set", items=items), f"取得 {len(items)} 条断言")


def op_subject_actions(ctx: NodeContext) -> NodeResult:
    subjects = _input(ctx, "subjects")
    params = ctx.node.params
    items = services[QueryRepository].subject_actions(
        _query(ctx).collection,
        [item["entity_id"] for item in subjects.items],
        modalities=params.get("modalities") or [],
        kinds=params.get("assertion_kinds") or [],
        predicate=params.get("predicate"),
        limit=_query(ctx).budgets.max_entities * 10,
    )
    return _done(OperatorResult(kind="fact_set", items=items), f"取得 {len(items)} 个行动")


def op_action_subjects(ctx: NodeContext) -> NodeResult:
    actions = _input(ctx, "actions")
    items = services[QueryRepository].action_subjects(
        _query(ctx).collection,
        [item["action_id"] for item in actions.items],
        modalities=ctx.node.params.get("modalities") or [],
        limit=_query(ctx).budgets.max_entities * 10,
    )
    return _done(OperatorResult(kind="fact_set", items=items), f"反查到 {len(items)} 个主体")


def op_assertion_search(ctx: NodeContext) -> NodeResult:
    params = ctx.node.params
    items = services[QueryRepository].assertion_search(
        _query(ctx).collection,
        entity_ids=params.get("entity_ids") or [],
        modalities=params.get("modalities") or [],
        kinds=params.get("assertion_kinds") or [],
        predicate=params.get("predicate"),
        limit=_query(ctx).budgets.max_entities * 10,
    )
    return _done(OperatorResult(kind="fact_set", items=items), f"检索到 {len(items)} 条断言")


def op_graph_traverse(ctx: NodeContext) -> NodeResult:
    starts = _input(ctx, "starts")
    params = ctx.node.params
    items = services[QueryRepository].graph_traverse(
        _query(ctx).collection,
        starts.items,
        relation=params["relation"],
        direction=params["direction"],
        hops=int(params.get("hops") or 1),
        limit=_query(ctx).budgets.max_entities,
    )
    return _done(OperatorResult(kind="fact_set", items=items), f"图关系得到 {len(items)} 项")


def op_filter_modality(ctx: NodeContext) -> NodeResult:
    source = _input(ctx, "facts")
    allowed = set(ctx.node.params.get("modalities") or [])
    items = []
    for item in source.items:
        values = set(item.get("modalities") or [])
        if item.get("modality"):
            values.add(item["modality"])
        if values & allowed:
            items.append(item)
    return _done(
        OperatorResult(kind="fact_set", items=items, meta={**source.meta, "modalities": sorted(allowed)}),
        f"模态筛选后 {len(items)} 项",
    )


def op_intersect(ctx: NodeContext) -> NodeResult:
    return _set_operation(ctx, "intersection")


def op_diff(ctx: NodeContext) -> NodeResult:
    return _set_operation(ctx, "difference")


def op_union(ctx: NodeContext) -> NodeResult:
    return _set_operation(ctx, "union")


def op_ground_assertions(ctx: NodeContext) -> NodeResult:
    facts = _input(ctx, "facts")
    assertion_ids = services[QueryRepository].assertion_ids(facts.items)
    items = services[QueryRepository].ground_assertions(
        _query(ctx).collection,
        assertion_ids,
        limit=int(ctx.node.params.get("top") or _query(ctx).budgets.max_blocks),
    )
    result = OperatorResult(
        kind="evidence_set",
        items=items,
        meta={
            "assertion_count": len(assertion_ids),
            "evidence_count": len(items),
            "set_operation": facts.meta.get("set_operation"),
        },
    )
    return _done(result, f"取得 {len(items)} 条精确断言证据")


def op_block_search(ctx: NodeContext) -> NodeResult:
    query = _query(ctx)
    params = ctx.node.params
    text = str(params.get("query") or "").strip()
    mode = params.get("mode") or "hybrid"
    top = min(int(params.get("top") or query.budgets.max_blocks), query.budgets.max_blocks)
    embedder = ctx.res("embedder")
    tokens: dict | None = None
    vector = None
    try:
        if mode in {"vector", "hybrid"}:
            embedder.reset_usage()
            vector = embedder.embed_one(text)
            tokens = embedder.pop_usage()
        requested_documents = set(params.get("document_ids") or [])
        visible_documents = {item.document_id for item in query.documents}
        if requested_documents - visible_documents:
            raise ValueError("BlockSearch document filter escaped the frozen document vocabulary")
        rows: list[dict] = []
        search = services[GenerationSearchAdapter]
        for store_id in query.allowed_stores:
            ctx.raise_if_cancelled()
            generation_id = query.generation_scope[store_id]
            store_documents = {
                item.document_id for item in query.documents
                if item.store_id == store_id and (
                    not requested_documents or item.document_id in requested_documents
                )
            }
            if requested_documents and not store_documents:
                continue
            extra_filter = None
            if store_documents:
                extra_filter = " or ".join(
                    f"document_id eq {_odata(document_id)}" for document_id in sorted(store_documents)
                )
                extra_filter = f"({extra_filter})"
            dimensions = query.generation_dimensions[store_id]
            if vector is not None and len(vector) != dimensions:
                raise ValueError(
                    f"embedding dimension mismatch for {store_id}: {len(vector)} != {dimensions}"
                )
            found = search.search(
                store_id=store_id,
                generation_id=generation_id,
                query_text=text if mode in {"keyword", "hybrid"} else None,
                query_vector=vector,
                top=top,
                dimensions=dimensions,
                extra_filter=extra_filter,
            )
            for item in found:
                item["store_id"] = store_id
                item["evidence_kind"] = "block"
                rows.append(item)
        rows.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        rows = rows[:top]
        return _done(
            OperatorResult(
                kind="evidence_set",
                items=rows,
                meta={
                    "mode": mode,
                    "query": text,
                    "document_ids": sorted(requested_documents),
                    "count": len(rows),
                },
            ),
            f"检索到 {len(rows)} 个代次内原文块",
            tokens,
        )
    except Exception as exc:  # preserve embedding usage on operator failure
        if mode in {"vector", "hybrid"} and tokens is None:
            tokens = embedder.pop_usage()
        return NodeResult(error=str(exc), tokens=tokens)


def op_evidence_bundle(ctx: NodeContext) -> NodeResult:
    sources = _all_inputs(ctx)
    labels = ctx.node.params.get("labels") or {}
    if set(labels) != set(sources):
        raise ValueError("EvidenceBundle labels must exactly match input ports")
    groups: list[EvidenceGroup] = []
    flattened: list[dict] = []
    for port, source in sources.items():
        items = list(source.items)
        groups.append(EvidenceGroup(
            key=port,
            label=labels[port],
            document_ids=list(dict.fromkeys(
                item.get("document_id") for item in items if item.get("document_id")
            )),
            items=items,
        ))
        flattened.extend(items)
    return _done(
        OperatorResult(
            kind="evidence_bundle",
            items=flattened,
            groups=groups,
            meta={
                "group_count": len(groups),
                "empty_groups": [group.key for group in groups if not group.items],
            },
        ),
        f"汇总 {len(groups)} 个证据组",
    )


def _set_operation(ctx: NodeContext, operation: str) -> NodeResult:
    left = _input(ctx, "left")
    right = _input(ctx, "right")
    left_by_key = {_fact_key(item): item for item in left.items}
    right_by_key = {_fact_key(item): item for item in right.items}
    if operation == "intersection":
        keys = left_by_key.keys() & right_by_key.keys()
        items = [_merge_fact(left_by_key[key], right_by_key[key]) for key in keys]
    elif operation == "difference":
        keys = left_by_key.keys() - right_by_key.keys()
        items = [dict(left_by_key[key]) for key in keys]
    else:
        keys = left_by_key.keys() | right_by_key.keys()
        items = [
            _merge_fact(left_by_key[key], right_by_key[key])
            if key in left_by_key and key in right_by_key
            else dict(left_by_key.get(key) or right_by_key[key])
            for key in keys
        ]
    metadata = {
        "set_operation": operation,
        "left_label": ctx.node.params.get("left_label"),
        "right_label": ctx.node.params.get("right_label"),
        "left_count": len(left_by_key),
        "right_count": len(right_by_key),
        "result_count": len(items),
    }
    for item in items:
        item["set_operation"] = metadata
    return _done(OperatorResult(kind="fact_set", items=items, meta=metadata), f"集合运算后 {len(items)} 项")


def _fact_key(item: dict) -> str:
    value = item.get("comparison_key") or item.get("fact_key") or item.get("assertion_id")
    if value is None:
        raise ValueError("fact item has no deterministic comparison key")
    return str(value)


def _merge_fact(left: dict, right: dict) -> dict:
    merged = dict(left)
    for list_key in ("assertion_ids", "modalities", "actions", "assertions", "paths"):
        values = list(merged.get(list_key) or [])
        for value in right.get(list_key) or []:
            if value not in values:
                values.append(value)
        if values:
            merged[list_key] = values
    supports = {key: list(values) for key, values in (left.get("supports") or {}).items()}
    for subject_id, assertion_ids in (right.get("supports") or {}).items():
        target = supports.setdefault(subject_id, [])
        for assertion_id in assertion_ids:
            if assertion_id not in target:
                target.append(assertion_id)
    if supports:
        merged["supports"] = supports
    return merged


def _query(ctx: NodeContext) -> QueryContext:
    return ctx.res("query_context")


def _input(ctx: NodeContext, port: str) -> OperatorResult:
    bindings = ctx.node.params.get("_inputs") or {}
    node_id = bindings.get(port)
    if not node_id:
        raise ValueError(f"operator {ctx.node.id} has no binding for port {port}")
    return OperatorResult.from_value(ctx.dep(node_id))


def _all_inputs(ctx: NodeContext) -> dict[str, OperatorResult]:
    bindings = ctx.node.params.get("_inputs") or {}
    return {port: OperatorResult.from_value(ctx.dep(node_id)) for port, node_id in bindings.items()}


def _done(result: OperatorResult, value: str, tokens: dict | None = None) -> NodeResult:
    return NodeResult(output=result.model_dump(mode="json"), value=value, tokens=tokens)


def _odata(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
