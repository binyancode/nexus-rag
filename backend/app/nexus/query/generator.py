"""答案生成器：只消费 PEP 显式绑定的事实与证据，不自行检索。"""
from __future__ import annotations

import json

from ..llm.chat import chat_client
from .models import QueryContext, QueryResult

_SYSTEM = (
    "你是法规问答生成器。只能依据输入 facts 和 evidence 回答，不得补充输入中不存在的事实。"
    "每个关键结论必须引用 evidence 中的 fullname。依据不足时明确说依据不足。严格输出 JSON。"
    "当 facts_meta.set_operation 存在时，facts 已是当前 Collection 图谱计算出的交集、差集或并集；"
    "应直接回答该集合结果，不要再次要求 evidence 证明差集对象不属于右侧集合。"
    "evidence 用于证明结果对象与其主体的正向关系；必要时只需说明结论范围限于当前 Collection。"
    "如果 evidence_groups 存在，必须分别概括每组文档规定，再比较共同点和差异；"
    "引用必须来自对应组，禁止用一组文档的证据证明另一组文档的结论。"
    "顶层只能输出 answer 和 citations 两个字段：answer 必须是完整可直接展示的字符串；"
    "citations 必须是数组。不要输出 analysis、comparison、summary、documents 等其他顶层字段。"
)


class AnswerGenerationError(ValueError):
    def __init__(self, message: str, raw_output):
        super().__init__(message)
        self.raw_output = raw_output


class AnswerGenerator:
    def generate(self, context: QueryContext, facts: QueryResult, evidence: QueryResult,
                 chat: chat_client) -> QueryResult:
        if evidence.kind == "evidence_bundle":
            return self._generate_bundle(context, evidence, chat)
        blocks = evidence.items[:context.budgets.max_blocks]
        allowed = {x.get("fullname") for x in blocks if x.get("fullname")}
        payload = {
            "question": context.question,
            "facts": facts.items[:context.budgets.max_entities],
            "facts_meta": facts.meta,
            "evidence": [
                {
                    "fullname": b.get("fullname"), "title": b.get("title"),
                    "section": b.get("section"), "text": b.get("text"),
                }
                for b in blocks
            ],
            "output": {
                "answer": "string",
                "citations": [{"fullname": "必须来自 evidence", "quote": "简短原文摘录"}],
            },
        }
        raw = chat.complete_json(_SYSTEM, json.dumps(payload, ensure_ascii=False))
        if not isinstance(raw, dict) or not isinstance(raw.get("answer"), str):
            raise AnswerGenerationError("答案生成器未返回顶层字符串 answer", raw)
        citations = []
        for item in raw.get("citations") or []:
            if isinstance(item, dict) and item.get("fullname") in allowed:
                citations.append({"fullname": item["fullname"], "quote": item.get("quote")})
        return QueryResult(
            kind="answer",
            answer=raw["answer"].strip(),
            citations=citations,
            meta={"fact_count": len(facts.items), "evidence_count": len(blocks)},
        )

    def _generate_bundle(self, context: QueryContext, evidence: QueryResult,
                         chat: chat_client) -> QueryResult:
        empty = [g.label for g in evidence.groups if not g.items]
        if empty:
            return QueryResult(
                kind="answer",
                answer="依据不足：以下文档未检索到可用于比较的原文依据：" + "、".join(empty) + "。",
                meta={"answer_status": "insufficient_evidence", "empty_groups": empty},
            )
        groups = []
        fullname_group: dict[str, str] = {}
        remaining = context.budgets.max_blocks
        for group in evidence.groups:
            # 公平分配预算，确保每份文档都能进入生成器。
            take = max(1, min(len(group.items), remaining // max(1, len(evidence.groups) - len(groups))))
            items = group.items[:take]
            remaining -= len(items)
            for item in items:
                if item.get("fullname"):
                    fullname_group[item["fullname"]] = group.key
            groups.append({
                "key": group.key, "label": group.label, "doc_ids": group.doc_ids,
                "evidence": [{
                    "fullname": b.get("fullname"), "title": b.get("title"),
                    "section": b.get("section"), "text": b.get("text"),
                } for b in items],
            })
        payload = {
            "question": context.question,
            "evidence_groups": groups,
            "output": {
                "answer": "string，完整回答；先分别说明各文档规定，再比较共同点和差异",
                "citations": [{"group": "分组 key", "fullname": "必须来自该组", "quote": "简短原文摘录"}],
            },
            "strict_rules": [
                "顶层 JSON 必须且只能包含 answer、citations",
                "answer 必须是一个字符串，不得拆成对象或数组",
                "citations 的 group 必须使用 evidence_groups.key",
                "回答尽量简洁，控制在 800 个汉字以内",
            ],
        }
        raw = chat.complete_json(_SYSTEM, json.dumps(payload, ensure_ascii=False))
        if not isinstance(raw, dict) or not isinstance(raw.get("answer"), str):
            raise AnswerGenerationError("答案生成器未返回顶层字符串 answer", raw)
        citations = []
        for item in raw.get("citations") or []:
            if not isinstance(item, dict):
                continue
            fullname = item.get("fullname")
            actual_group = fullname_group.get(fullname)
            if actual_group and item.get("group") == actual_group:
                citations.append({
                    "group": actual_group, "fullname": fullname, "quote": item.get("quote"),
                })
        return QueryResult(
            kind="answer", answer=raw["answer"].strip(), citations=citations,
            meta={
                "answer_status": "answered", "group_count": len(groups),
                "evidence_count": sum(len(x["evidence"]) for x in groups),
            },
        )
