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
    "Each supplied evidence item has an opaque citation_id. Every citation must contain only one citation_id "
    "copied exactly from that item. Do not emit assertion_id, group, block_key, or quote: the server resolves "
    "the citation_id and attaches the validated identity and exact source text."
)


class AnswerGenerationError(ValueError):
    def __init__(self, message: str, raw_output: Any):
        self.raw_output = raw_output
        super().__init__(message)


class AnswerGenerator:
    _CITATION_METADATA_KEYS = (
        "document_id", "title", "category", "block_id",
        "article_no", "paragraph_no", "item_no", "heading_path", "ordinal",
        "assertion_kind", "predicate", "modality",
    )

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
                    "evidence": [
                        AnswerGenerator._evidence_item(item, f"G{group_index}E{item_index}")
                        for item_index, item in enumerate(group.items, 1)
                    ],
                }
                for group_index, group in enumerate(evidence.groups, 1)
            ]
            evidence_payload: dict[str, Any] = {"groups": groups}
            citation_shape = {"citation_id": "exact supplied citation_id"}
        else:
            evidence_payload = {
                "items": [
                    AnswerGenerator._evidence_item(item, f"E{index}")
                    for index, item in enumerate(evidence.items, 1)
                ]
            }
            citation_shape = {"citation_id": "exact supplied citation_id"}
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
    def _evidence_item(item: dict, citation_id: str | None = None) -> dict:
        keys = (
            "evidence_kind", "assertion_id", "assertion_kind", "predicate", "modality",
            "condition", "exception", "scope", "block_key", "block_id", "quote",
            "text", "document_id", "title", "category", "article_no", "paragraph_no",
            "item_no", "heading_path", "ordinal",
        )
        result = {key: item.get(key) for key in keys if item.get(key) is not None}
        if citation_id:
            result["citation_id"] = citation_id
        return result

    @staticmethod
    def _validate_citations(
        evidence: OperatorResult,
        citations: list,
        raw_output: Any,
    ) -> list[dict]:
        allowed_assertions: dict[tuple[str, str], dict] = {}
        allowed_blocks: dict[str, dict] = {}
        allowed_group_blocks: dict[tuple[str, str], dict] = {}
        group_labels = {group.key: group.label for group in evidence.groups}
        allowed_citation_ids: dict[str, tuple[dict, str | None, str | None]] = {}
        for index, item in enumerate(evidence.items, 1):
            block_key = item.get("block_key")
            if not block_key:
                continue
            allowed_blocks[block_key] = item
            allowed_citation_ids[f"E{index}"] = (item, None, None)
            if item.get("assertion_id"):
                allowed_assertions[(item["assertion_id"], block_key)] = item
        for group_index, group in enumerate(evidence.groups, 1):
            for item_index, item in enumerate(group.items, 1):
                if item.get("block_key"):
                    allowed_group_blocks[(group.key, item["block_key"])] = item
                    allowed_citation_ids[f"G{group_index}E{item_index}"] = (
                        item, group.key, group.label,
                    )

        validated: list[dict] = []
        seen: set[tuple] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                raise AnswerGenerationError("citation must be an object", raw_output)
            citation_id = citation.get("citation_id")
            if citation_id is not None:
                if not isinstance(citation_id, str) or citation_id not in allowed_citation_ids:
                    raise AnswerGenerationError("citation_id is outside provided evidence", raw_output)
                source, group, group_label = allowed_citation_ids[citation_id]
                block_key = source.get("block_key")
                if not block_key:
                    raise AnswerGenerationError("cited evidence has no block_key", raw_output)
                if group is not None:
                    result = {
                        "group": group,
                        "group_label": group_label,
                        "block_key": block_key,
                    }
                elif source.get("assertion_id"):
                    result = {
                        "assertion_id": source["assertion_id"],
                        "block_key": block_key,
                    }
                else:
                    result = {"block_key": block_key}
            elif evidence.kind == "evidence_bundle":
                # Backward compatibility for outputs persisted before citation_id existed.
                block_key = citation.get("block_key")
                if not isinstance(block_key, str) or not block_key:
                    raise AnswerGenerationError("citation requires citation_id", raw_output)
                group = citation.get("group")
                source = allowed_group_blocks.get((group, block_key))
                if source is None:
                    raise AnswerGenerationError("citation block does not belong to its evidence group", raw_output)
                result = {"group": group, "block_key": block_key}
                result["group_label"] = group_labels.get(group)
            else:
                # Backward compatibility: use an exact Assertion/Block pair when present;
                # otherwise a valid non-Assertion Block wins over a spurious model field.
                block_key = citation.get("block_key")
                if not isinstance(block_key, str) or not block_key:
                    raise AnswerGenerationError("citation requires citation_id", raw_output)
                assertion_id = citation.get("assertion_id")
                source = allowed_assertions.get((assertion_id, block_key))
                if source is not None:
                    result = {"assertion_id": assertion_id, "block_key": block_key}
                else:
                    source = allowed_blocks.get(block_key)
                    if source is None or source.get("assertion_id"):
                        raise AnswerGenerationError(
                            "citation assertion/block pair is outside provided evidence", raw_output,
                        )
                    result = {"block_key": block_key}
            source_text = str(source.get("quote") or source.get("text") or "")
            if not source_text.strip():
                raise AnswerGenerationError("cited evidence has no source text", raw_output)
            # Never persist model-authored excerpts. A valid evidence identity is enough;
            # the trusted source text is attached verbatim so citations are always contiguous
            # and auditable even when the model shortens or joins parts of a Block.
            result["quote"] = source_text
            for key in AnswerGenerator._CITATION_METADATA_KEYS:
                value = source.get(key)
                if value is not None:
                    result[key] = value
            marker = (
                result.get("group"), result.get("assertion_id"),
                result.get("block_key"), result.get("quote"),
            )
            if marker not in seen:
                seen.add(marker)
                validated.append(result)
        return validated
