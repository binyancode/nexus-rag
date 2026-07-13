"""SQG 编译器：自然语言问题 → 纯逻辑意图 DAG，不泄漏任何物理执行方式。"""
from __future__ import annotations

import json

from ..llm.chat import chat_client
from .models import QueryContext, SQG

_LOGICAL_CATALOG = {
    "Retrieve": "找出满足某业务语义的对象或内容",
    "Compare": "比较多个结果集，表达交集、差异或合并意图",
    "Answer": "根据前置结果和依据回答用户问题",
}

_SYSTEM = (
    "你是法规查询的逻辑编译器。把用户问题编译成 SQG。SQG 只能表达『要做什么』，"
    "禁止出现任何『如何做』：不得出现数据库、SQL、AI Search、向量、实体 id、边类型代码、"
    "遍历方向、跳数、TopK、过滤语法、Prompt 或物理算子。只能使用给定逻辑算子。严格输出 JSON。"
)


class SQGCompiler:
    def compile(self, context: QueryContext, chat: chat_client) -> SQG:
        candidates = _relevant_catalog(context.question, context.entity_catalog, limit=160)
        request = {
            "question": context.question,
            "collection": {"name": context.collection.name},
            "logical_operators": _LOGICAL_CATALOG,
            "visible_entity_vocabulary": [
                {"type": x["type"], "name": x["name"], "aliases": x.get("aliases", [])}
                for x in candidates
            ],
            "output_contract": {
                "nodes": [{
                    "id": "op1",
                    "op": "Retrieve | Compare | Answer",
                    "desc": "人能读懂的业务目标",
                    "goal": {
                        "subject": "业务主体（可选）",
                        "target": "想得到的对象（可选）",
                        "relation": "业务关系语义（可选）",
                        "operation": "intersection | difference | union（Compare 时）",
                    },
                    "inputs": [],
                }]
            },
            "rules": [
                "每个节点只描述业务意图",
                "独立检索分支应拆成多个 Retrieve",
                "必须有且只有一个最终 Answer 节点",
                "Compare 的 inputs 顺序有语义：difference 时第一个减第二个",
            ],
        }
        raw = chat.complete_json(_SYSTEM, json.dumps(request, ensure_ascii=False))
        try:
            return SQG.model_validate(raw)
        except Exception as exc:
            raise ValueError(f"SQG 编译失败: {exc}") from exc


def _relevant_catalog(question: str, catalog: list[dict], limit: int) -> list[dict]:
    """通用候选缩减：问题中出现的名称/别名优先，其余按原目录补足；不做业务改写。"""
    q = question.casefold()
    matched, rest = [], []
    for item in catalog:
        terms = [item.get("name", ""), *(item.get("aliases") or [])]
        (matched if any(t and t.casefold() in q for t in terms) else rest).append(item)
    return (matched + rest)[:limit]
