"""查询优化器：SQG → 可执行 PEP；负责实体/关系绑定、物理展开和输入端口校验。"""
from __future__ import annotations

import json

from ..index.catalog import EDGE_TYPES, ENTITY_TYPES
from ..llm.chat import chat_client
from .models import PEP, QueryContext, SQG

_PHYSICAL_CATALOG = {
    "EntitySearch": {
        "output": "entity_set", "inputs": {}, "purpose": "按名称/别名定位实体",
        "params": {"text": "string|required", "entity_id": "string", "entity_types": "string[]"},
    },
    "BlockSearch": {
        "output": "block_set", "inputs": {}, "purpose": "关键词/向量/混合检索原文块",
        "params": {"text": "string|required", "mode": "keyword|vector|hybrid", "top": "integer", "category": "string"},
    },
    "Traverse": {
        "output": "entity_set", "inputs": {"entities": "entity_set"}, "purpose": "沿实体关系遍历",
        "params": {"edge_types": "string[]", "direction": "out|in|both", "hops": "integer", "target_types": "string[]"},
    },
    "Lift": {"output": "entity_set", "inputs": {"blocks": "block_set"}, "purpose": "由块沿出处边提升到实体", "params": {}},
    "Ground": {
        "output": "block_set", "inputs": {"entities": "entity_set"}, "purpose": "由实体取得当前 Collection 内原文依据",
        "params": {"top": "integer"},
    },
    "Intersect": {"output": "entity_set", "inputs": {"left": "entity_set", "right": "entity_set"}, "params": {}},
    "Diff": {"output": "entity_set", "inputs": {"left": "entity_set", "right": "entity_set"}, "params": {}},
    "Union": {"output": "entity_set", "inputs": {"left": "entity_set", "right": "entity_set"}, "params": {}},
    "Dedup": {"output": "entity_set", "inputs": {"items": "entity_set"}, "params": {}},
}

_SYSTEM = (
    "你是法规查询优化器。把纯逻辑 SQG 编译为物理执行计划 PEP。"
    "只能使用给定物理算子和可见实体/关系目录；不得发明实体 id、边类型或算子。"
    "所有物理参数必须明确。PEP 顶层 outputs 必须显式绑定 facts 和 evidence 两个生成器输入，"
    "其中 evidence 必须来自 Ground 或 BlockSearch。生成器不属于 PEP，由第五阶段独立执行。"
    "Intersect、Diff、Union、Dedup 只处理实体集合；必须先完成所有实体集合运算，再对最终实体结果执行 Ground。"
    "绝不能把 Ground 输出接入任何集合算子。需要同时保留事实和依据时，facts 指向 Ground 之前的最终实体节点，"
    "evidence 指向以该 facts 节点为输入的 Ground 节点。"
    "严格输出 JSON。"
)


class PEPOptimizationError(ValueError):
    """PEP 生成后校验失败；raw_pep 用于持久化和排查，不能拿去执行。"""
    def __init__(self, message: str, raw_pep):
        super().__init__(message)
        self.raw_pep = raw_pep


class QueryOptimizer:
    def optimize(self, context: QueryContext, sqg: SQG, chat: chat_client) -> PEP:
        request = {
            "question": context.question,
            "sqg": sqg.model_dump(),
            "visible_entities": _binding_candidates(context, sqg, 240),
            "entity_types": ENTITY_TYPES,
            "edge_types": EDGE_TYPES,
            "available_categories": context.categories,
            "physical_operators": _PHYSICAL_CATALOG,
            "pep_contract": {
                "nodes": [{
                    "id": "p1", "op": "physical operator", "name": "人类可读名称",
                    "inputs": {"port_name": "upstream_node_id"},
                    "params": {}, "layer": 0,
                }],
                "outputs": {"facts": "事实结果节点 id", "evidence": "依据块节点 id"},
            },
            "rules": [
                "精确实体入口用 EntitySearch；语义描述入口用 BlockSearch 后接 Lift",
                "Intersect/Diff/Union/Dedup 的输入和输出都是 entity_set",
                "所有集合运算必须在 Ground 之前完成；Ground 输出 block_set，禁止再进入集合算子",
                "先得到最终 entity_set facts，再由 Ground(facts) 生成 block_set evidence",
                "独立分支保持独立以便并行",
                "PEP outputs.facts 指向 Ground 之前的最终事实节点；outputs.evidence 指向该 facts 对应的 Ground/BlockSearch",
                "所有名称、类型、边类型必须来自给定目录",
                "BlockSearch.category 只能从 available_categories 原样选择；不确定时必须省略 category，禁止自行创造",
                "params 字段名必须与 physical_operators.params 完全一致；禁止 query、top_k、entity_type 等别名",
                "标记 required 的物理参数必须提供；无参数算子必须输出空对象 params:{}",
            ],
        }
        raw = chat.complete_json(_SYSTEM, json.dumps(request, ensure_ascii=False))
        try:
            pep = PEP.model_validate(raw)
            _validate_contracts(pep)
            _validate_bindings(pep, context)
            return pep
        except Exception as exc:
            raise PEPOptimizationError(f"PEP 优化失败: {exc}", raw) from exc


def _validate_contracts(pep: PEP) -> None:
    by_id = {n.id: n for n in pep.nodes}
    for node in pep.nodes:
        spec = _PHYSICAL_CATALOG[node.op]
        required = spec.get("inputs", {})
        missing = [port for port in required if port not in node.inputs]
        if missing:
            raise ValueError(f"{node.id}/{node.op} 缺少输入端口: {missing}")
        for port, expected in required.items():
            upstream = by_id[node.inputs[port]]
            actual = _PHYSICAL_CATALOG[upstream.op]["output"]
            if actual != expected:
                raise ValueError(
                    f"{node.id}.{port} 需要 {expected}，但 {upstream.id}/{upstream.op} 输出 {actual}"
                )
        _validate_params(node.id, node.op, node.params, spec.get("params", {}))
    facts_id = pep.outputs.get("facts")
    evidence_id = pep.outputs.get("evidence")
    if _PHYSICAL_CATALOG[by_id[facts_id].op]["output"] not in ("entity_set", "block_set"):
        raise ValueError("PEP outputs.facts 必须指向事实集合")
    if _PHYSICAL_CATALOG[by_id[evidence_id].op]["output"] != "block_set":
        raise ValueError("PEP outputs.evidence 必须指向块集合")
    evidence_node = by_id[evidence_id]
    if evidence_node.op == "Ground" and evidence_node.inputs.get("entities") != facts_id:
        raise ValueError(
            "PEP outputs.evidence 的 Ground 必须直接消费 outputs.facts；"
            f"当前 Ground 输入={evidence_node.inputs.get('entities')}，facts={facts_id}"
        )


def _validate_bindings(pep: PEP, context: QueryContext) -> None:
    entity_ids = {x["entity_id"] for x in context.entity_catalog}
    entity_types = set(ENTITY_TYPES)
    edge_types = set(EDGE_TYPES)
    for node in pep.nodes:
        p = node.params
        if p.get("entity_id") and p["entity_id"] not in entity_ids:
            raise ValueError(f"不可见或不存在的实体 id: {p['entity_id']}")
        bad_types = set(p.get("entity_types") or []) - entity_types
        if bad_types:
            raise ValueError(f"未知实体类型: {sorted(bad_types)}")
        bad_edges = set(p.get("edge_types") or []) - edge_types
        if bad_edges:
            raise ValueError(f"未知边类型: {sorted(bad_edges)}")
        if p.get("direction") not in (None, "out", "in", "both"):
            raise ValueError(f"非法遍历方向: {p.get('direction')}")
        if p.get("category") is not None and p["category"] not in context.categories:
            raise ValueError(
                f"未知 category: {p['category']!r}；当前 Collection 可用值: {context.categories}"
            )


def _validate_params(node_id: str, op: str, params: dict, schema: dict[str, str]) -> None:
    unknown = set(params) - set(schema)
    if unknown:
        raise ValueError(f"{node_id}/{op} 包含未知参数: {sorted(unknown)}；允许参数: {sorted(schema)}")
    missing = [name for name, rule in schema.items() if "required" in rule and name not in params]
    if missing:
        raise ValueError(f"{node_id}/{op} 缺少必填参数: {missing}")
    for name, value in params.items():
        rule = schema[name]
        if rule.startswith("string[]") and not isinstance(value, list):
            raise ValueError(f"{node_id}/{op}.{name} 必须是字符串数组")
        if rule.startswith("string[]") and isinstance(value, list) and not all(isinstance(x, str) for x in value):
            raise ValueError(f"{node_id}/{op}.{name} 必须只包含字符串")
        if rule.startswith("string") and not rule.startswith("string[]") and not isinstance(value, str):
            raise ValueError(f"{node_id}/{op}.{name} 必须是字符串")
        if "required" in rule and isinstance(value, str) and not value.strip():
            raise ValueError(f"{node_id}/{op}.{name} 不能为空")
        if rule.startswith("integer") and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"{node_id}/{op}.{name} 必须是整数")
        if not rule.startswith(("string", "integer")) and "|" in rule and value not in rule.split("|"):
            raise ValueError(f"{node_id}/{op}.{name} 必须是以下之一: {rule}")


def _binding_candidates(context: QueryContext, sqg: SQG, limit: int) -> list[dict]:
    """绑定候选按问题/SQG 中实际出现的词优先，避免目录变大后目标实体被截断。"""
    text = (context.question + " " + json.dumps(sqg.model_dump(), ensure_ascii=False)).casefold()
    matched, rest = [], []
    for item in context.entity_catalog:
        terms = [item.get("name", ""), *(item.get("aliases") or [])]
        (matched if any(t and t.casefold() in text for t in terms) else rest).append(item)
    return (matched + rest)[:limit]
