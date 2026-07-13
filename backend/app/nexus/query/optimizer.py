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
        "params": {"text": "string|required", "mode": "keyword|vector|hybrid", "top": "integer", "category": "string", "doc_ids": "string[]"},
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
    "BlockUnion": {"output": "block_set", "inputs": {"*": "block_set"}, "min_inputs": 2, "params": {}},
    "EvidenceBundle": {
        "output": "evidence_bundle", "inputs": {"*": "block_set"}, "min_inputs": 2,
        "purpose": "保留多个文档或类别范围各自的原文证据分组", "params": {"labels": "string_map|required"},
    },
}

_SYSTEM = (
    "你是查询优化器。把纯逻辑 SQG 编译为物理执行计划 PEP。"
    "只能使用给定物理算子和可见实体/关系目录；不得发明实体 id、边类型或算子。"
    "所有物理参数必须明确。PEP 顶层 outputs 必须显式绑定 facts 和 evidence 两个生成器输入，"
    "其中 evidence 必须来自 Ground、BlockSearch 或 EvidenceBundle。生成器不属于 PEP，由第五阶段独立执行。"
    "Intersect、Diff、Union、Dedup 只处理实体集合；必须先完成所有实体集合运算，再对最终实体结果执行 Ground。"
    "绝不能把 Ground 输出接入任何集合算子。非 EvidenceBundle 计划需要同时保留事实和依据时，"
    "facts 指向 Ground 之前的最终实体节点，"
    "evidence 指向以该 facts 节点为输入的 Ground 节点。"
    "当 SQG 比较多份明确指定的文档内容时，必须为每份文档使用带 doc_ids 的独立 BlockSearch，"
    "再用 EvidenceBundle 保留各文档证据分组；不要 Lift，不要实体集合运算，不要 Ground。"
    "只要计划使用 EvidenceBundle，outputs.facts 和 outputs.evidence 必须共同指向同一个 EvidenceBundle 节点。"
    "当 SQG 比较多个明确命名的实体集合时，必须保留每个实体的独立 EntitySearch 和关系分支，"
    "再按 Compare.operation 使用 Intersect、Diff 或 Union，禁止改为搜索共同来源法规。"
    "Traverse 只能实现明确关系遍历，不能按『加快机制、风险措施、主要影响』等开放语义筛选邻居。"
    "比较多个主体的开放语义内容时，应为每个主体建立按相关 category 或 doc_ids 限定的独立 BlockSearch，"
    "再用 EvidenceBundle 保留分组；此时 facts/evidence 共同指向 EvidenceBundle。"
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
            "available_documents": context.documents,
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
                "SQG 中不同命名实体的 Retrieve 必须保留为独立 EntitySearch 分支，不得折叠成其共同来源法规或文档",
                "实体集合 Compare.operation=intersection/difference/union 时分别使用 Intersect/Diff/Union，再对集合结果 Ground",
                "Traverse 只按边和类型过滤，不能按开放语义过滤；语义型 target 使用 BlockSearch，不得用多边双向多跳遍历冒充语义筛选",
                "比较多个开放语义内容分支时，每个分支使用由 available_documents 推导的不同 doc_ids 或 category 范围，并汇入 EvidenceBundle",
                "非 EvidenceBundle 计划中，outputs.facts 指向 Ground 之前的最终事实节点；outputs.evidence 指向该 facts 对应的 Ground/BlockSearch",
                "所有名称、类型、边类型必须来自给定目录",
                "Traverse 的边类型、方向和 target_types 必须严格对应 SQG 的 relation/target，禁止顺带加入无关关系或实体类型",
                "问题明确比较 available_documents 中的文档时，BlockSearch.doc_ids 必须使用对应真实 doc_id",
                "指定文档比较路径为多个 BlockSearch(doc_ids) → EvidenceBundle；EvidenceBundle inputs 端口可自定义但 labels 必须逐一对应",
                "EvidenceBundle.labels 使用 available_documents.title 的人类可读文档名，不要使用 doc_id",
                "不同文档分组的 BlockSearch.doc_ids 必须不同；不得用相同搜索分支冒充两份文档",
                "只要使用 EvidenceBundle，outputs.facts 和 outputs.evidence 必须共同指向该 EvidenceBundle 节点",
                "BlockSearch.category 只能从 available_categories 原样选择；不确定时必须省略 category，禁止自行创造",
                "params 字段名必须与 physical_operators.params 完全一致；禁止 query、top_k、entity_type 等别名",
                "标记 required 的物理参数必须提供；无参数算子必须输出空对象 params:{}",
            ],
        }
        raw = chat.complete_json(_SYSTEM, json.dumps(request, ensure_ascii=False))
        for attempt in range(2):
            try:
                pep = PEP.model_validate(raw)
                _validate_contracts(pep)
                _validate_bindings(pep, context)
                return pep
            except Exception as exc:
                if attempt == 0:
                    repair_request = {
                        **request,
                        "previous_invalid_pep": raw,
                        "validation_error": str(exc),
                        "repair_instruction": (
                            "修正校验错误并返回完整 PEP；保留原业务意图，不得绕过或删除必要节点。"
                        ),
                    }
                    raw = chat.complete_json(
                        _SYSTEM,
                        json.dumps(repair_request, ensure_ascii=False),
                    )
                    continue
                raise PEPOptimizationError(f"PEP 优化失败: {exc}", raw) from exc


def _validate_contracts(pep: PEP) -> None:
    by_id = {n.id: n for n in pep.nodes}
    for node in pep.nodes:
        spec = _PHYSICAL_CATALOG[node.op]
        if node.op == "Traverse":
            edge_types = node.params.get("edge_types") or []
            hops = int(node.params.get("hops") or 1)
            target_types = node.params.get("target_types") or []
            if (
                node.params.get("direction") == "both"
                and len(edge_types) > 1
                and (hops > 1 or len(target_types) > 1)
            ):
                raise ValueError(
                    f"{node.id}/Traverse 是多边类型、双向且跨多跳/多类型的宽泛扩散，"
                    "无法表达精确关系；请按 SQG relation/target 收窄边、方向和目标类型，"
                    "开放语义筛选则改用 BlockSearch"
                )
        required = spec.get("inputs", {})
        wildcard = required.get("*")
        if wildcard:
            if len(node.inputs) < int(spec.get("min_inputs") or 1):
                raise ValueError(f"{node.id}/{node.op} 至少需要 {spec.get('min_inputs')} 个输入")
            ports = [(port, wildcard) for port in node.inputs]
        else:
            missing = [port for port in required if port not in node.inputs]
            if missing:
                raise ValueError(f"{node.id}/{node.op} 缺少输入端口: {missing}")
            ports = list(required.items())
        for port, expected in ports:
            upstream = by_id[node.inputs[port]]
            actual = _PHYSICAL_CATALOG[upstream.op]["output"]
            if actual != expected:
                raise ValueError(
                    f"{node.id}.{port} 需要 {expected}，但 {upstream.id}/{upstream.op} 输出 {actual}"
                )
        _validate_params(node.id, node.op, node.params, spec.get("params", {}))
    facts_id = pep.outputs.get("facts")
    evidence_id = pep.outputs.get("evidence")
    facts_type = _PHYSICAL_CATALOG[by_id[facts_id].op]["output"]
    evidence_type = _PHYSICAL_CATALOG[by_id[evidence_id].op]["output"]
    if facts_type not in ("entity_set", "block_set", "evidence_bundle"):
        raise ValueError("PEP outputs.facts 必须指向事实集合")
    if evidence_type not in ("block_set", "evidence_bundle"):
        raise ValueError("PEP outputs.evidence 必须指向块集合或分组证据")
    if "evidence_bundle" in (facts_type, evidence_type) and not (
        facts_type == evidence_type == "evidence_bundle" and facts_id == evidence_id
    ):
        raise ValueError("文档比较时 facts/evidence 必须共同指向同一个 EvidenceBundle")
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
        if p.get("doc_ids") is not None:
            visible_docs = {x["doc_id"] for x in context.documents}
            unknown_docs = set(p["doc_ids"]) - visible_docs
            if unknown_docs:
                raise ValueError(f"不可见或不存在的 doc_id: {sorted(unknown_docs)}")
            if not p["doc_ids"]:
                raise ValueError(f"{node.id}/BlockSearch.doc_ids 不能为空")
    _validate_evidence_bundles(pep)


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
        if rule.startswith("string") and not rule.startswith(("string[]", "string_map")) and not isinstance(value, str):
            raise ValueError(f"{node_id}/{op}.{name} 必须是字符串")
        if "required" in rule and isinstance(value, str) and not value.strip():
            raise ValueError(f"{node_id}/{op}.{name} 不能为空")
        if rule.startswith("integer") and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"{node_id}/{op}.{name} 必须是整数")
        if not rule.startswith(("string", "integer")) and "|" in rule and value not in rule.split("|"):
            raise ValueError(f"{node_id}/{op}.{name} 必须是以下之一: {rule}")
        if rule.startswith("string_map") and (
            not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in value.items())
        ):
            raise ValueError(f"{node_id}/{op}.{name} 必须是非空字符串映射")


def _validate_evidence_bundles(pep: PEP) -> None:
    by_id = {n.id: n for n in pep.nodes}
    for node in pep.nodes:
        if node.op != "EvidenceBundle":
            continue
        labels = node.params.get("labels") or {}
        if set(labels) != set(node.inputs):
            raise ValueError(f"{node.id}/EvidenceBundle.labels 必须与 inputs 端口完全一致")
        scopes = []
        for port, upstream_id in node.inputs.items():
            branch_scopes = _upstream_search_scopes(upstream_id, by_id, set())
            if not branch_scopes:
                raise ValueError(
                    f"{node.id}.{port} 必须来自带 doc_ids 或 category 范围的 BlockSearch 分支"
                )
            scopes.append((port, frozenset(branch_scopes)))
        if len({scope for _, scope in scopes}) != len(scopes):
            raise ValueError(f"{node.id}/EvidenceBundle 的证据分组不能使用相同检索范围")


def _upstream_search_scopes(node_id: str, by_id: dict, visited: set[str]) -> set[str]:
    if node_id in visited:
        return set()
    visited.add(node_id)
    node = by_id[node_id]
    own = set()
    if node.op == "BlockSearch":
        own.update(f"doc:{x}" for x in (node.params.get("doc_ids") or []))
        if node.params.get("category"):
            own.add(f"category:{node.params['category']}")
    for dep in node.depends_on:
        own.update(_upstream_search_scopes(dep, by_id, visited))
    return own


def _binding_candidates(context: QueryContext, sqg: SQG, limit: int) -> list[dict]:
    """绑定候选按问题/SQG 中实际出现的词优先，避免目录变大后目标实体被截断。"""
    text = (context.question + " " + json.dumps(sqg.model_dump(), ensure_ascii=False)).casefold()
    matched, rest = [], []
    for item in context.entity_catalog:
        terms = [item.get("name", ""), *(item.get("aliases") or [])]
        (matched if any(t and t.casefold() in text for t in terms) else rest).append(item)
    return (matched + rest)[:limit]
