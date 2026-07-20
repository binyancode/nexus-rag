"""Stage 2: LLM compilation into one strong logical SQG intent."""
from __future__ import annotations

import json
from typing import Any

from nexus.domain import QueryContext
from nexus.infrastructure import ChatClient, JsonCompletionError, normalize_name

from .models import (
    CompareDocumentsIntent,
    CompareSubjectsIntent,
    FindSubjectIntent,
    ReverseActionIntent,
    SQG,
    SemanticEvidenceIntent,
    TraverseRelationIntent,
)

_SYSTEM = (
    "You are a legal query intent compiler. Emit exactly one JSON object matching one supplied "
    "logical intent contract. The SQG says WHAT the user asks, never HOW to retrieve it. "
    "Never mention SQL, database tables, stores, generations, vectors, search modes, Top-K, "
    "physical operators, graph direction, hops, internal entity/action/document IDs, or invented names. "
    "Every named subject, action, relation, and document must be copied exactly from visible vocabulary."
)

_RELATION_MEANINGS = {
    "has_obligation": "主体必须做什么、应当做什么、有哪些义务、依法要做哪些事",
    "has_prohibition": "主体不得、禁止实施哪些行动",
    "has_permission": "主体可以、获准实施哪些行动",
    "has_recommendation": "对主体建议或鼓励实施哪些行动",
    "has_fact": "与主体直接关联的事实或行动",
    "based_on": "以什么为依据、根据哪些法规制定",
    "formulated_by": "由谁制定",
    "issued_by": "由谁发布",
    "includes": "包括什么、分为哪些组成或类别",
    "classified_as": "被划分为什么类别",
    "purpose": "目的是什么",
    "implement": "实施什么制度或事项",
}


class CompilerError(ValueError):
    def __init__(self, message: str, raw_output: Any):
        self.raw_output = raw_output
        super().__init__(message)


class SQGCompiler:
    def compile(self, context: QueryContext, chat: ChatClient) -> SQG:
        request = self._request(context)
        raw: Any = None
        feedback: str | None = None
        for attempt in (1, 2):
            payload = request if attempt == 1 else {
                **request,
                "previous_invalid_output": raw,
                "validation_feedback": feedback,
                "repair": "Return a complete corrected SQG object; do not remove named user constraints.",
            }
            try:
                raw = chat.complete_json(_SYSTEM, json.dumps(payload, ensure_ascii=False))
                sqg = SQG.model_validate(raw, strict=True)
                if sqg.question != context.question:
                    raise ValueError("SQG.question must exactly preserve the user question")
                self._validate_visible_bindings(context, sqg)
                return sqg
            except JsonCompletionError as exc:
                raw = exc.raw_output
                feedback = str(exc)
            except Exception as exc:  # validation or explicit call failure
                feedback = str(exc)
            if attempt == 2:
                raise CompilerError(f"SQG compilation failed: {feedback}", raw)
        raise AssertionError("unreachable")

    @staticmethod
    def _request(context: QueryContext) -> dict:
        return {
            "question": context.question,
            "visible_subjects": [
                {"name": item.name, "type": item.entity_type, "aliases": list(item.aliases)}
                for item in _relevant_entities(context)
            ],
            "visible_actions": [
                {"canonical_text": item.canonical_text, "verb": item.verb}
                for item in _relevant_actions(context)
            ],
            "visible_documents": [
                {"title": item.title, "category": item.category}
                for item in _relevant_documents(context)
            ],
            "visible_graph_relations": [
                {
                    "name": relation,
                    "meaning": _RELATION_MEANINGS.get(
                        relation, relation.replace("_", " "),
                    ),
                }
                for relation in context.graph_relations
            ],
            "intent_contracts": {
                "find_subject_facts": {
                    "kind": "find_subject_facts", "subjects": ["exact visible name"],
                    "target": "assertions | actions", "modalities": [],
                    "assertion_kinds": [], "predicate": None,
                },
                "compare_subjects": {
                    "kind": "compare_subjects", "subjects": ["two or more exact visible names"],
                    "target": "assertions | actions",
                    "operation": "intersection | difference | union",
                    "modalities": [], "assertion_kinds": [], "predicate": None,
                },
                "find_action_subjects": {
                    "kind": "find_action_subjects", "action": "exact visible canonical_text",
                    "modalities": [],
                },
                "traverse_relation": {
                    "kind": "traverse_relation", "start": "exact visible subject or action",
                    "start_type": "exact visible entity type; null only for an action start",
                    "relation": "exact visible relation name", "inverse": False,
                },
                "compare_documents": {
                    "kind": "compare_documents", "documents": ["two or more exact visible titles"],
                    "focus": "comparison focus copied from question",
                },
                "semantic_evidence": {
                    "kind": "semantic_evidence", "query": "semantic evidence need",
                    "documents": ["optional exact visible titles"],
                },
            },
            "rules": [
                "Choose exactly one intent contract.",
                "Prefer traverse_relation when the user asks what is connected to one named start by a visible relation, including natural phrases described in visible_graph_relations.",
                "Questions asking one subject's obligations, prohibitions, permissions, recommendations, included items, basis, issuer, formulator, classification, or purpose are relation traversal when that relation is visible.",
                "A request to group, summarize, or cite the traversal results does not change the retrieval intent into semantic_evidence.",
                "When the same start name exists under multiple entity types, start_type is mandatory and must select the type that matches the role described by the question.",
                "Use compare_documents only when the user explicitly names at least two documents.",
                "Use semantic_evidence only as a fallback for an open evidence search that cannot bind a structured subject, action, document comparison, or graph relation.",
                "Difference is ordered: first subject minus all later subjects.",
                "Do not introduce a document merely because it contains evidence about a named subject.",
                "Return all optional array and null fields shown by the selected contract.",
            ],
            "output": {"question": context.question, "intent": "one contract object"},
        }

    @staticmethod
    def _validate_visible_bindings(context: QueryContext, sqg: SQG) -> None:
        intent = sqg.intent
        if isinstance(intent, (FindSubjectIntent, CompareSubjectsIntent)):
            for name in intent.subjects:
                _bind_entity(context, name)
            if len(intent.subjects) != len({normalize_name(name) for name in intent.subjects}):
                raise ValueError("named subjects must be unique")
        elif isinstance(intent, ReverseActionIntent):
            _bind_action(context, intent.action)
        elif isinstance(intent, TraverseRelationIntent):
            _bind_node(context, intent.start, intent.start_type)
            if intent.relation not in context.graph_relations:
                raise ValueError(f"graph relation is not visible: {intent.relation}")
        elif isinstance(intent, CompareDocumentsIntent):
            ids = [_bind_document(context, title) for title in intent.documents]
            if len(ids) != len(set(ids)):
                raise ValueError("document comparison must name distinct documents")
        elif isinstance(intent, SemanticEvidenceIntent):
            for title in intent.documents:
                _bind_document(context, title)
            normalized_question = normalize_name(context.question)
            explicit_relations = [
                relation for relation in context.graph_relations
                if normalize_name(relation) in normalized_question
            ]
            if explicit_relations:
                raise ValueError(
                    "semantic_evidence cannot ignore explicitly named visible graph relations: "
                    + ", ".join(explicit_relations)
                    + "; use traverse_relation"
                )


def _bind_entity(context: QueryContext, value: str, entity_type: str | None = None) -> str:
    wanted = normalize_name(value)
    matches = {
        item.entity_id
        for item in context.entities
        if wanted in {normalize_name(item.name), *(normalize_name(alias) for alias in item.aliases)}
        and (entity_type is None or item.entity_type == entity_type)
    }
    if len(matches) != 1:
        raise ValueError(f"subject binding must resolve to exactly one visible entity: {value!r}")
    return next(iter(matches))


def _bind_action(context: QueryContext, value: str) -> str:
    wanted = normalize_name(value)
    matches = {
        item.action_id for item in context.actions
        if wanted in {normalize_name(item.canonical_text), normalize_name(item.verb)}
    }
    if len(matches) != 1:
        raise ValueError(f"action binding must resolve to exactly one visible action: {value!r}")
    return next(iter(matches))


def _bind_document(context: QueryContext, value: str) -> str:
    wanted = normalize_name(value)
    matches = {
        item.document_id for item in context.documents
        if wanted in {normalize_name(item.title), normalize_name(item.document_id)}
    }
    if len(matches) != 1:
        raise ValueError(f"document binding must resolve to exactly one visible document: {value!r}")
    return next(iter(matches))


def _bind_node(
    context: QueryContext,
    value: str,
    entity_type: str | None = None,
) -> tuple[str, str]:
    try:
        return "entity", _bind_entity(context, value, entity_type)
    except ValueError:
        return "action", _bind_action(context, value)


def _relevant_entities(context: QueryContext, limit: int = 300):
    question = normalize_name(context.question)
    matched, rest = [], []
    for item in context.entities:
        terms = (item.name, *item.aliases)
        (matched if any(normalize_name(term) in question for term in terms) else rest).append(item)
    return (matched + rest)[:limit]


def _relevant_actions(context: QueryContext, limit: int = 300):
    question = normalize_name(context.question)
    matched, rest = [], []
    for item in context.actions:
        terms = (item.canonical_text, item.verb)
        (matched if any(normalize_name(term) in question for term in terms) else rest).append(item)
    return (matched + rest)[:limit]


def _relevant_documents(context: QueryContext, limit: int = 300):
    question = normalize_name(context.question)
    matched, rest = [], []
    seen: set[tuple[str, str]] = set()
    for item in context.documents:
        marker = (item.document_id, item.title)
        if marker in seen:
            continue
        seen.add(marker)
        (matched if normalize_name(item.title) in question else rest).append(item)
    return (matched + rest)[:limit]
