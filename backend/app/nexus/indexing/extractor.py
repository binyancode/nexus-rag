"""Audited two-attempt LLM extraction with strict semantic validation."""
from __future__ import annotations

import json
import copy
import difflib
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from nexus.domain import (
    ActionDraft,
    Block,
    BlockExtraction,
    EntityMentionDraft,
    LegalAssertionDraft,
)
from nexus.infrastructure import ExtractionAttemptRepository

from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, user_prompt

_MODALITY_TERMS = {
    "must": ("应当", "必须", "须", "负责", "需要", "需"),
    "must_not": ("不得", "禁止", "严禁", "不应"),
    "may": ("可以", "可"),
    "should": ("宜", "建议", "鼓励"),
    "conditional_may": ("可以", "可"),
}


class ExtractionValidationError(ValueError):
    def __init__(self, errors: list[dict], tokens: dict | None = None):
        self.errors = errors
        self.tokens = tokens or {}
        super().__init__(json.dumps(errors, ensure_ascii=False))


@dataclass(frozen=True)
class ExtractionResult:
    extraction: BlockExtraction
    tokens: dict
    warnings: list[dict] = field(default_factory=list)
    quarantined: bool = False


class AssertionExtractor:
    def __init__(self, chat, attempts: ExtractionAttemptRepository):
        self.chat = chat
        self.attempts = attempts

    def extract(self, run_id: str, generation_id: str, block: Block) -> ExtractionResult:
        feedback: list[dict] | None = None
        total_tokens: dict[str, int] = {}
        for attempt_no in (1, 2):
            self.chat.reset_usage()
            started = time.time()
            raw: Any = None
            raw_text: str | None = None
            try:
                raw = self.chat.complete_json(
                    SYSTEM_PROMPT,
                    user_prompt(block, feedback),
                    temperature=0.0,
                )
                raw_text = json.dumps(raw, ensure_ascii=False, default=str)
                extraction = self._validate(raw, block)
                tokens = self.chat.pop_usage()
                self._merge_tokens(total_tokens, tokens)
                state = "empty" if extraction.empty else "succeeded"
                self.attempts.record(
                    run_id=run_id,
                    generation_id=generation_id,
                    block_key=block.block_key,
                    attempt_no=attempt_no,
                    state=state,
                    prompt_version=PROMPT_VERSION,
                    raw_output=raw_text,
                    validation_errors=None,
                    tokens=tokens,
                    cost_ms=int((time.time() - started) * 1000),
                )
                return ExtractionResult(extraction=extraction, tokens=total_tokens)
            except (ExtractionValidationError, ValidationError, ValueError, TypeError) as exc:
                tokens = self.chat.pop_usage()
                self._merge_tokens(total_tokens, tokens)
                feedback = self._errors(exc)
                if attempt_no == 2:
                    try:
                        extraction, warnings = self._salvage(raw, block)
                        state = "empty" if extraction.empty else "succeeded"
                        self.attempts.record(
                            run_id=run_id,
                            generation_id=generation_id,
                            block_key=block.block_key,
                            attempt_no=attempt_no,
                            state=state,
                            prompt_version=PROMPT_VERSION,
                            raw_output=raw_text,
                            validation_errors=warnings or None,
                            tokens=tokens,
                            cost_ms=int((time.time() - started) * 1000),
                        )
                        return ExtractionResult(
                            extraction=extraction,
                            tokens=total_tokens,
                            warnings=warnings,
                        )
                    except (ExtractionValidationError, ValidationError, ValueError, TypeError) as salvage_exc:
                        quarantine_errors = [
                            *feedback,
                            *self._quarantine_errors("block", 0, salvage_exc),
                        ]
                        extraction = BlockExtraction(
                            empty=True,
                            empty_reason="两次抽取后无有效法规断言，已隔离该 Block",
                            entities=[],
                            actions=[],
                            assertions=[],
                        )
                        self.attempts.record(
                            run_id=run_id,
                            generation_id=generation_id,
                            block_key=block.block_key,
                            attempt_no=attempt_no,
                            state="quarantined",
                            prompt_version=PROMPT_VERSION,
                            raw_output=raw_text,
                            validation_errors=quarantine_errors,
                            tokens=tokens,
                            cost_ms=int((time.time() - started) * 1000),
                        )
                        return ExtractionResult(
                            extraction=extraction,
                            tokens=total_tokens,
                            warnings=quarantine_errors,
                            quarantined=True,
                        )
                self.attempts.record(
                    run_id=run_id,
                    generation_id=generation_id,
                    block_key=block.block_key,
                    attempt_no=attempt_no,
                    state="invalid",
                    prompt_version=PROMPT_VERSION,
                    raw_output=raw_text,
                    validation_errors=feedback,
                    tokens=tokens,
                    cost_ms=int((time.time() - started) * 1000),
                )
            except Exception as exc:
                tokens = self.chat.pop_usage()
                self._merge_tokens(total_tokens, tokens)
                feedback = [{"type": "llm_call_failed", "message": str(exc)}]
                self.attempts.record(
                    run_id=run_id,
                    generation_id=generation_id,
                    block_key=block.block_key,
                    attempt_no=attempt_no,
                    state="quarantined" if attempt_no == 2 else "failed",
                    prompt_version=PROMPT_VERSION,
                    raw_output=raw_text,
                    validation_errors=feedback,
                    tokens=tokens,
                    cost_ms=int((time.time() - started) * 1000),
                )
                if attempt_no == 2:
                    extraction = BlockExtraction(
                        empty=True,
                        empty_reason="两次抽取调用失败，已隔离该 Block",
                        entities=[],
                        actions=[],
                        assertions=[],
                    )
                    return ExtractionResult(
                        extraction=extraction,
                        tokens=total_tokens,
                        warnings=feedback,
                        quarantined=True,
                    )
            if attempt_no == 2:
                raise ExtractionValidationError(
                    feedback or [{"message": "unknown extraction failure"}],
                    total_tokens,
                )
        raise AssertionError("unreachable")

    @staticmethod
    def _salvage(raw: Any, block: Block) -> tuple[BlockExtraction, list[dict]]:
        """Keep valid facts after the second whole-response validation failure.

        Invalid items are quarantined with audit warnings. A non-empty response still
        fails when no valid Assertion survives, so unsupported or wholly malformed blocks
        cannot silently enter the active Generation.
        """
        if not isinstance(raw, dict) or not raw:
            raise ExtractionValidationError([{
                "type": "invalid_json_contract",
                "message": "cannot salvage an empty or non-object JSON value",
            }])
        repaired = AssertionExtractor._repair_exact_spans(raw, block.text)
        if repaired.get("empty") is True:
            return BlockExtraction.model_validate(repaired, strict=True), []

        warnings: list[dict] = []
        entities: list[EntityMentionDraft] = []
        entity_ids: set[str] = set()
        for index, item in enumerate(repaired.get("entities") or []):
            try:
                entity = EntityMentionDraft.model_validate(item, strict=True)
                if entity.local_id in entity_ids:
                    raise ValueError(f"duplicate entity local_id: {entity.local_id}")
                if entity.start_offset is not None and (
                    block.text[entity.start_offset:entity.end_offset] != entity.mention_text
                ):
                    raise ValueError("mention text is not present at its repaired span")
                entities.append(entity)
                entity_ids.add(entity.local_id)
            except Exception as exc:  # one malformed candidate is quarantined
                warnings.extend(AssertionExtractor._quarantine_errors("entity", index, exc))

        actions: list[ActionDraft] = []
        action_ids: set[str] = set()
        for index, item in enumerate(repaired.get("actions") or []):
            try:
                action = ActionDraft.model_validate(item, strict=True)
                if action.local_id in action_ids:
                    raise ValueError(f"duplicate action local_id: {action.local_id}")
                unknown = [
                    participant.entity_local_id for participant in action.participants
                    if participant.entity_local_id and participant.entity_local_id not in entity_ids
                ]
                if unknown:
                    raise ValueError(f"unknown action entity references: {unknown}")
                actions.append(action)
                action_ids.add(action.local_id)
            except Exception as exc:
                warnings.extend(AssertionExtractor._quarantine_errors("action", index, exc))

        assertions: list[LegalAssertionDraft] = []
        assertion_ids: set[str] = set()
        for index, item in enumerate(repaired.get("assertions") or []):
            try:
                assertion = LegalAssertionDraft.model_validate(item, strict=True)
                if assertion.local_id in assertion_ids:
                    raise ValueError(f"duplicate assertion local_id: {assertion.local_id}")
                if assertion.action_local_id and assertion.action_local_id not in action_ids:
                    raise ValueError(
                        f"unknown assertion action reference: {assertion.action_local_id}"
                    )
                unknown = [
                    participant.entity_local_id for participant in assertion.participants
                    if participant.entity_local_id and participant.entity_local_id not in entity_ids
                ]
                if unknown:
                    raise ValueError(f"unknown assertion entity references: {unknown}")
                if block.text[assertion.quote_start:assertion.quote_end] != assertion.quote:
                    raise ValueError("assertion quote is not an exact source span")
                terms = _MODALITY_TERMS.get(assertion.modality)
                context = AssertionExtractor._sentence_context(
                    block.text, assertion.quote_start, assertion.quote_end,
                )
                if terms and not any(term in context for term in terms):
                    raise ValueError(
                        f"modality {assertion.modality} has no lexical support in source context"
                    )
                assertions.append(assertion)
                assertion_ids.add(assertion.local_id)
            except Exception as exc:
                warnings.extend(AssertionExtractor._quarantine_errors("assertion", index, exc))

        if not assertions:
            raise ExtractionValidationError(
                warnings or [{"type": "no_valid_assertions", "message": "no assertion survived"}]
            )

        referenced_actions = {
            assertion.action_local_id for assertion in assertions if assertion.action_local_id
        }
        actions = [action for action in actions if action.local_id in referenced_actions]
        referenced_entities = {
            participant.entity_local_id
            for assertion in assertions for participant in assertion.participants
            if participant.entity_local_id
        }
        referenced_entities.update(
            participant.entity_local_id
            for action in actions for participant in action.participants
            if participant.entity_local_id
        )
        entities = [entity for entity in entities if entity.local_id in referenced_entities]
        extraction = BlockExtraction(
            empty=False,
            empty_reason=None,
            entities=entities,
            actions=actions,
            assertions=assertions,
        )
        return extraction, warnings

    @staticmethod
    def _quarantine_errors(kind: str, index: int, exc: Exception) -> list[dict]:
        errors = AssertionExtractor._errors(exc)
        return [{
            **error,
            "type": "quarantined_" + str(error.get("type") or exc.__class__.__name__),
            "item_kind": kind,
            "item_index": index,
        } for error in errors]

    @staticmethod
    def _validate(raw: Any, block: Block) -> BlockExtraction:
        if not isinstance(raw, dict) or not raw:
            raise ExtractionValidationError([{
                "type": "invalid_json_contract",
                "message": "LLM returned an empty or non-object JSON value",
            }])
        repaired = AssertionExtractor._repair_exact_spans(raw, block.text)
        extraction = BlockExtraction.model_validate(repaired, strict=True)
        entity_ids = {entity.local_id for entity in extraction.entities}
        action_ids = {action.local_id for action in extraction.actions}
        errors: list[dict] = []
        if len(entity_ids) != len(extraction.entities):
            errors.append({"type": "duplicate_local_id", "location": "entities"})
        if len(action_ids) != len(extraction.actions):
            errors.append({"type": "duplicate_local_id", "location": "actions"})
        assertion_ids = {assertion.local_id for assertion in extraction.assertions}
        if len(assertion_ids) != len(extraction.assertions):
            errors.append({"type": "duplicate_local_id", "location": "assertions"})

        for entity in extraction.entities:
            if entity.start_offset is not None:
                actual = block.text[entity.start_offset:entity.end_offset]
                if actual != entity.mention_text:
                    errors.append({
                        "type": "mention_span_mismatch", "local_id": entity.local_id,
                        "expected": entity.mention_text, "actual": actual,
                    })
        for action in extraction.actions:
            for participant in action.participants:
                if participant.entity_local_id and participant.entity_local_id not in entity_ids:
                    errors.append({
                        "type": "unknown_entity_reference", "local_id": action.local_id,
                        "reference": participant.entity_local_id,
                    })
        for assertion in extraction.assertions:
            if assertion.action_local_id and assertion.action_local_id not in action_ids:
                errors.append({
                    "type": "unknown_action_reference", "local_id": assertion.local_id,
                    "reference": assertion.action_local_id,
                })
            for participant in assertion.participants:
                if participant.entity_local_id and participant.entity_local_id not in entity_ids:
                    errors.append({
                        "type": "unknown_entity_reference", "local_id": assertion.local_id,
                        "reference": participant.entity_local_id,
                    })
            actual_quote = block.text[assertion.quote_start:assertion.quote_end]
            if actual_quote != assertion.quote:
                errors.append({
                    "type": "quote_span_mismatch", "local_id": assertion.local_id,
                    "expected": assertion.quote, "actual": actual_quote,
                    "quote_start": assertion.quote_start, "quote_end": assertion.quote_end,
                })
            terms = _MODALITY_TERMS.get(assertion.modality)
            modality_context = AssertionExtractor._sentence_context(
                block.text, assertion.quote_start, assertion.quote_end,
            )
            if terms and not any(term in modality_context for term in terms):
                errors.append({
                    "type": "modality_without_lexical_support", "local_id": assertion.local_id,
                    "modality": assertion.modality, "supported_terms": list(terms),
                    "context": modality_context,
                })
            if assertion.modality == "conditional_may" and not (assertion.condition or "").strip():
                errors.append({
                    "type": "conditional_may_without_condition", "local_id": assertion.local_id,
                })
        if errors:
            raise ExtractionValidationError(errors)
        return extraction

    @staticmethod
    def _repair_exact_spans(raw: dict, text: str) -> dict:
        """Use exact extracted text as truth and compute Python offsets locally.

        LLMs are reliable at copying short source spans but not at counting Unicode code
        points. A copied value that does not occur in the block remains a hard error.
        """
        repaired = copy.deepcopy(raw)
        entity_ids = {
            entity.get("local_id") for entity in repaired.get("entities") or []
            if entity.get("local_id")
        }
        action_ids = {
            action.get("local_id") for action in repaired.get("actions") or []
            if action.get("local_id")
        }
        for action in repaired.get("actions") or []:
            action_participants = []
            for participant in action.get("participants") or []:
                role = participant.get("role")
                if role == "subject":
                    continue
                if role in {"activity", "product", "regulation", "term"}:
                    participant["role"] = "object"
                # The text is only a display duplicate when a local entity is bound.
                if participant.get("entity_local_id"):
                    participant["value_text"] = None
                action_participants.append(participant)
            action["participants"] = action_participants

        valid_assertions = []
        for assertion in repaired.get("assertions") or []:
            payload = assertion.get("payload")
            if payload is not None and not isinstance(payload, dict):
                assertion["payload"] = {"value": payload}

            participants = []
            for participant in assertion.get("participants") or []:
                if participant.get("role") in {"target", "instrument"}:
                    participant["role"] = "object"
                entity_local_id = participant.get("entity_local_id")
                value_text = participant.get("value_text")
                if entity_local_id and entity_local_id not in entity_ids:
                    participants.append(participant)  # strict reference validation reports it
                elif entity_local_id or (isinstance(value_text, str) and value_text.strip()):
                    participants.append(participant)
            assertion["participants"] = participants

            kind = assertion.get("kind")
            action_local_id = assertion.get("action_local_id")
            if kind in {"norm", "deadline", "penalty"} and action_local_id not in action_ids:
                continue
            roles = {participant.get("role") for participant in participants}
            if kind == "norm" and "subject" not in roles:
                continue
            if kind == "relation":
                if "subject" not in roles:
                    # For a binary relation, promote the first explicit source-like participant.
                    candidate = next((
                        participant for role in ("activity", "regulation", "product", "term", "object")
                        for participant in participants if participant.get("role") == role
                    ), None)
                    if candidate is not None:
                        candidate["role"] = "subject"
                roles = {participant.get("role") for participant in participants}
                if "subject" not in roles or len(participants) < 2:
                    continue

            quote = assertion.get("quote")
            if isinstance(quote, str) and quote:
                repaired_quote = AssertionExtractor._repair_quote(
                    text, quote, assertion.get("quote_start"),
                )
                if repaired_quote is not None:
                    start, end, exact_quote = repaired_quote
                    assertion["quote_start"], assertion["quote_end"] = start, end
                    assertion["quote"] = exact_quote
                    terms = _MODALITY_TERMS.get(assertion.get("modality"))
                    context = AssertionExtractor._sentence_context(text, start, end)
                    if terms and not any(term in context for term in terms):
                        # Never manufacture a legal obligation/permission without lexical support.
                        assertion["modality"] = "factual"
            valid_assertions.append(assertion)
        repaired["assertions"] = valid_assertions

        for entity in repaired.get("entities") or []:
            mention = entity.get("mention_text")
            if isinstance(mention, str) and mention:
                located = AssertionExtractor._locate(text, mention, entity.get("start_offset"))
                if located is not None:
                    entity["start_offset"], entity["end_offset"] = located
        return repaired

    @staticmethod
    def _locate(text: str, value: str, suggested_start: Any) -> tuple[int, int] | None:
        starts = [match.start() for match in re.finditer(re.escape(value), text)]
        if not starts:
            return None
        try:
            suggested = int(suggested_start)
        except (TypeError, ValueError):
            suggested = starts[0]
        start = min(starts, key=lambda item: abs(item - suggested))
        return start, start + len(value)

    @staticmethod
    def _repair_quote(
        text: str,
        quote: str,
        suggested_start: Any,
    ) -> tuple[int, int, str] | None:
        """Return one exact, continuous source span for a copied or abridged quote.

        Exact text and whitespace-only drift are repaired directly. For enumerated legal
        clauses, a model may copy the common preamble plus item (二)/(三), omitting earlier
        list items. That is accepted only when at least 90% of the model quote aligns in
        order and the resulting source envelope is tightly bounded. Paraphrases remain a
        hard failure.
        """
        exact = AssertionExtractor._locate(text, quote, suggested_start)
        if exact is not None:
            return exact[0], exact[1], text[exact[0]:exact[1]]

        compact_text, text_map = AssertionExtractor._compact_map(text)
        compact_quote, _ = AssertionExtractor._compact_map(quote)
        if not compact_quote:
            return None

        compact_exact = AssertionExtractor._locate(compact_text, compact_quote, suggested_start)
        if compact_exact is not None:
            start = text_map[compact_exact[0]]
            end = text_map[compact_exact[1] - 1] + 1
            return start, end, text[start:end]

        matcher = difflib.SequenceMatcher(None, compact_quote, compact_text, autojunk=False)
        blocks = [block for block in matcher.get_matching_blocks() if block.size]
        if not blocks:
            return None
        matched = sum(block.size for block in blocks)
        tolerance = max(2, len(compact_quote) // 50)
        first, last = blocks[0], blocks[-1]
        if (
            matched / len(compact_quote) < 0.90
            or first.a > tolerance
            or last.a + last.size < len(compact_quote) - tolerance
        ):
            return None

        compact_start = first.b
        compact_end = last.b + last.size
        if compact_end <= compact_start:
            return None
        source_start = text_map[compact_start]
        source_end = text_map[compact_end - 1] + 1
        envelope_length = source_end - source_start
        if envelope_length > max(len(quote) * 3, len(quote) + 240):
            return None
        return source_start, source_end, text[source_start:source_end]

    @staticmethod
    def _compact_map(value: str) -> tuple[str, list[int]]:
        chars: list[str] = []
        positions: list[int] = []
        for index, char in enumerate(value):
            if char.isspace():
                continue
            chars.append(char)
            positions.append(index)
        return "".join(chars), positions

    @staticmethod
    def _sentence_context(text: str, start: int, end: int) -> str:
        delimiters = "。！？；\n"
        left = max((text.rfind(mark, 0, start) for mark in delimiters), default=-1) + 1
        right_candidates = [
            position for mark in delimiters
            if (position := text.find(mark, end)) >= 0
        ]
        right = min(right_candidates) + 1 if right_candidates else len(text)
        return text[left:right]

    @staticmethod
    def _errors(exc: Exception) -> list[dict]:
        if isinstance(exc, ExtractionValidationError):
            return exc.errors
        if isinstance(exc, ValidationError):
            return [
                {
                    "type": error.get("type"),
                    "location": list(error.get("loc") or []),
                    "message": error.get("msg"),
                    "input": error.get("input"),
                }
                for error in exc.errors(include_url=False)
            ]
        return [{"type": exc.__class__.__name__, "message": str(exc)}]

    @staticmethod
    def _merge_tokens(total: dict[str, int], current: dict | None) -> None:
        for key, value in (current or {}).items():
            total[key] = total.get(key, 0) + int(value or 0)
