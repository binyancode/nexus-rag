"""答案生成器：只消费 PEP 显式绑定的事实与证据，不自行检索。"""
from __future__ import annotations

import json

from ..llm.chat import chat_client
from .models import QueryContext, QueryResult

_SYSTEM = (
    "你是法规问答生成器。只能依据输入 facts 和 evidence 回答，不得补充输入中不存在的事实。"
    "每个关键结论必须引用 evidence 中的 fullname。依据不足时明确说依据不足。严格输出 JSON。"
)


class AnswerGenerator:
    def generate(self, context: QueryContext, facts: QueryResult, evidence: QueryResult,
                 chat: chat_client) -> QueryResult:
        blocks = evidence.items[:context.budgets.max_blocks]
        allowed = {x.get("fullname") for x in blocks if x.get("fullname")}
        payload = {
            "question": context.question,
            "facts": facts.items[:context.budgets.max_entities],
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
            raise ValueError("答案生成器未返回合法 answer")
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
