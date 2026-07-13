"""Stage 5: answer only from explicitly bound facts/evidence; never retrieves."""
from __future__ import annotations

import json
from typing import Any

from nexus.domain import QueryContext
from nexus.infrastructure import ChatClient, JsonCompletionError

from .models import OperatorResult

_SYSTEM = (
    "You answer a legal question using only the supplied facts and evidence. Do not retrieve, infer "
    "missing rules, or cite anything else. Preserve modality, condition, exception, scope, and set-operation "
    "meaning. If evidence is insufficient, say so. Return strict JSON with exactly answer and citations. "
    "Assertion citations use assertion_id, block_key, quote. Document-comparison citations additionally use "
    "the supplied group key. Quotes must be copied from the supplied quote or block text."
)


class AnswerGenerationError(ValueError):
    def __init__(self, message: str, raw_output: Any):
        self.raw_output = raw_output
        super().__init__(message)


class AnswerGenerator:
    def generate(
        self,
        context: QueryContext,
        facts: OperatorResult,
        evidence: OperatorResult,
        chat: ChatClient,
    ) -> OperatorResult:
        if not evidence.items:
            return OperatorResult(
                kind="answer",
                answer="依据不足：当前 Collection 的冻结索引代次中没有可用于回答的证据。",
                citations=[],
                meta={"answer_status": "insufficient_evidence", "fact_count": len(facts.items)},
            )
        payload = self._payload(context, facts, evidence)
        try:
            raw = chat.complete_json(_SYSTEM, json.dumps(payload, ensure_ascii=False, default=str))
        except JsonCompletionError as exc:
            raise AnswerGenerationError(str(exc), exc.raw_output) from exc
        if not isinstance(raw, dict) or set(raw) != {"answer", "citations"}:
            raise AnswerGenerationError("generator must return exactly answer and citations", raw)
        answer = raw.get("answer")
        citations = raw.get("citations")
        if not isinstance(answer, str) or not answer.strip() or not isinstance(citations, list):
            raise AnswerGenerationError("generator returned an invalid answer/citations contract", raw)
        validated = self._validate_citations(evidence, citations, raw)
        if evidence.items and not validated:
            raise AnswerGenerationError("generator returned no valid citation for available evidence", raw)
        return OperatorResult(
            kind="answer",
            answer=answer.strip(),
            citations=validated,
            meta={
                "answer_status": "answered",
                "fact_count": len(facts.items),
                "evidence_count": len(evidence.items),
                "group_count": len(evidence.groups),
            },
        )

    @staticmethod
    def _payload(context: QueryContext, facts: OperatorResult, evidence: OperatorResult) -> dict:
        fact_items = facts.items[:context.budgets.max_entities]
        if evidence.kind == "evidence_bundle":
            groups = [
                {
                    "key": group.key,
                    "label": group.label,
                    "document_ids": group.document_ids,
                    "evidence": [AnswerGenerator._evidence_item(item) for item in group.items],
                }
                for group in evidence.groups
            ]
            evidence_payload: dict[str, Any] = {"groups": groups}
            citation_shape = {
                "group": "supplied group key",
                "block_key": "supplied block key",
                "quote": "exact excerpt from block text",
            }
        else:
            evidence_payload = {
                "items": [AnswerGenerator._evidence_item(item) for item in evidence.items]
            }
            citation_shape = {
                "assertion_id": "required when evidence_kind is assertion",
                "block_key": "supplied block key",
                "quote": "exact excerpt from supplied quote or block text",
            }
        return {
            "question": context.question,
            "collection": context.collection.name,
            "facts": fact_items,
            "facts_meta": facts.meta,
            "evidence": evidence_payload,
            "rules": [
                "Treat must, must_not, may, should, factual, and conditional_may as distinct.",
                "State conditions and exceptions with the conclusion they qualify.",
                "For difference, absence means absent from the frozen Collection scope, not universal nonexistence.",
                "For grouped documents, describe each group before comparing them.",
            ],
            "output": {"answer": "display-ready string", "citations": [citation_shape]},
        }

    @staticmethod
    def _evidence_item(item: dict) -> dict:
        keys = (
            "evidence_kind", "assertion_id", "assertion_kind", "predicate", "modality",
            "condition", "exception", "scope", "block_key", "block_id", "quote",
            "text", "document_id", "title", "category", "article_no", "paragraph_no",
            "item_no", "heading_path", "ordinal",
        )
        return {key: item.get(key) for key in keys if item.get(key) is not None}

    @staticmethod
    def _validate_citations(
        evidence: OperatorResult,
        citations: list,
        raw_output: Any,
    ) -> list[dict]:
        allowed_assertions: dict[tuple[str, str], dict] = {}
        allowed_blocks: dict[str, dict] = {}
        allowed_group_blocks: dict[tuple[str, str], dict] = {}
        for item in evidence.items:
            block_key = item.get("block_key")
            if not block_key:
                continue
            allowed_blocks[block_key] = item
            if item.get("assertion_id"):
                allowed_assertions[(item["assertion_id"], block_key)] = item
        for group in evidence.groups:
            for item in group.items:
                if item.get("block_key"):
                    allowed_group_blocks[(group.key, item["block_key"])] = item

        validated: list[dict] = []
        seen: set[tuple] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                raise AnswerGenerationError("citation must be an object", raw_output)
            block_key = citation.get("block_key")
            quote = citation.get("quote")
            if not isinstance(block_key, str) or not isinstance(quote, str) or not quote.strip():
                raise AnswerGenerationError("citation requires block_key and non-empty quote", raw_output)
            if evidence.kind == "evidence_bundle":
                group = citation.get("group")
                source = allowed_group_blocks.get((group, block_key))
                if source is None:
                    raise AnswerGenerationError("citation block does not belong to its evidence group", raw_output)
                result = {"group": group, "block_key": block_key, "quote": quote.strip()}
            elif citation.get("assertion_id") is not None:
                assertion_id = citation.get("assertion_id")
                source = allowed_assertions.get((assertion_id, block_key))
                if source is None:
                    raise AnswerGenerationError("citation assertion/block pair is outside provided evidence", raw_output)
                result = {
                    "assertion_id": assertion_id,
                    "block_key": block_key,
                    "quote": quote.strip(),
                }
            else:
                source = allowed_blocks.get(block_key)
                if source is None or source.get("assertion_id"):
                    raise AnswerGenerationError("block citation is outside provided block evidence", raw_output)
                result = {"block_key": block_key, "quote": quote.strip()}
            source_text = str(source.get("quote") or source.get("text") or "")
            if quote.strip() not in source_text:
                raise AnswerGenerationError("citation quote is not present in provided evidence", raw_output)
            marker = (
                result.get("group"), result.get("assertion_id"),
                result.get("block_key"), result.get("quote"),
            )
            if marker not in seen:
                seen.add(marker)
                validated.append(result)
        return validated
