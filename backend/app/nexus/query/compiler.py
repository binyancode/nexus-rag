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
    "遍历方向、跳数、TopK、过滤语法、Prompt 或物理算子。只能使用给定逻辑算子。"
    "问题直接点名 visible_entity_vocabulary 中的业务主体时，必须保留这些主体，"
    "不得替换成其证据所在的法规或文档。未被问题提及的 visible_documents 不得出现在 SQG。"
    "严格输出 JSON。"
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
            "visible_documents": _relevant_documents(context.question, context.documents, limit=160),
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
                "问题明确提到文档时，goal.subject 使用 visible_documents 中的人类可读 title，不写 doc_id",
                "问题点名多个可见实体时，每个实体必须保留为对应 Retrieve 的 subject，不得改成共同来源文档",
                "问题询问多个主体共同具备的对象时，为每个主体建立独立 Retrieve，再用 operation=intersection 的 Compare",
                "不得仅因某实体的依据来自某份法规，就在 SQG 中引入该法规或文档",
                "独立检索分支应拆成多个 Retrieve",
                "必须有且只有一个最终 Answer 节点",
                "Compare 的 inputs 顺序有语义：difference 时第一个减第二个",
            ],
        }
        raw = chat.complete_json(_SYSTEM, json.dumps(request, ensure_ascii=False))
        for attempt in range(2):
            try:
                sqg = SQG.model_validate(raw)
                _validate_document_grounding(sqg, context)
                return sqg
            except Exception as exc:
                if attempt == 0:
                    raw = chat.complete_json(_SYSTEM, json.dumps({
                        **request,
                        "previous_invalid_sqg": raw,
                        "validation_error": str(exc),
                        "repair_instruction": "修正错误并返回完整 SQG；保留问题中点名的业务主体。",
                    }, ensure_ascii=False))
                    continue
                raise ValueError(f"SQG 编译失败: {exc}") from exc


def _validate_document_grounding(sqg: SQG, context: QueryContext) -> None:
    """SQG 只能使用问题实际提到的文档，不能用证据来源替换业务主体。"""
    question = context.question.casefold()
    sqg_text = json.dumps(sqg.model_dump(), ensure_ascii=False).casefold()
    for document in context.documents:
        terms = _document_terms(document)
        if not any(term in sqg_text for term in terms):
            continue
        if any(term in question for term in terms):
            continue
        related_regs = [
            item for item in context.entity_catalog
            if item.get("type") == "Reg"
            and any(str(item.get("name") or "").casefold() in term for term in terms)
        ]
        if any(
            alias and alias.casefold() in question
            for item in related_regs
            for alias in [item.get("name", ""), *(item.get("aliases") or [])]
        ):
            continue
        raise ValueError(f"SQG 引入了问题未提及的文档: {document.get('title')}")


def _document_terms(document: dict) -> list[str]:
    title = str(document.get("title") or "").strip().casefold()
    terms = [title]
    if "_" in title:
        terms.append(title.split("_", 1)[1])
    return [term for term in dict.fromkeys(terms) if len(term) >= 4]


def _relevant_catalog(question: str, catalog: list[dict], limit: int) -> list[dict]:
    """通用候选缩减：问题中出现的名称/别名优先，其余按原目录补足；不做业务改写。"""
    q = question.casefold()
    matched, rest = [], []
    for item in catalog:
        terms = [item.get("name", ""), *(item.get("aliases") or [])]
        (matched if any(t and t.casefold() in q for t in terms) else rest).append(item)
    return (matched + rest)[:limit]


def _relevant_documents(question: str, documents: list[dict], limit: int) -> list[dict]:
    q = question.casefold()
    matched, rest = [], []
    for doc in documents:
        title = str(doc.get("title") or "")
        (matched if title and title.casefold() in q else rest).append(doc)
    return (matched + rest)[:limit]
