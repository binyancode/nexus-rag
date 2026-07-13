"""Deterministic in-memory resolution followed by batched SQL persistence."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict

from nexus.domain import Block, BlockExtraction
from nexus.infrastructure import AssertionRepository, normalize_name, signature_hash


class ResolutionService:
    """Resolve one complete Generation with a fixed number of database round trips."""

    def __init__(self, repository: AssertionRepository):
        self.repository = repository

    def persist(self, generation_id: str, results: list[dict]) -> dict[str, int]:
        non_empty = [result for result in results if not result["extraction"].empty]
        if not non_empty:
            return {"entities_created": 0, "actions_created": 0, "assertions_created": 0}

        canonical_index, alias_index = self._entity_indexes(generation_id)
        entity_rows: list[tuple] = []
        alias_rows: dict[tuple[str, str], tuple] = {}
        mention_rows: list[tuple] = []
        mention_meta: dict[tuple[str, str], dict] = {}

        # Pass 1: resolve every entity mention in memory.
        for result in non_empty:
            block: Block = result["block"]
            extraction: BlockExtraction = result["extraction"]
            for draft in extraction.entities:
                normalized = normalize_name(draft.canonical_name)
                key = (draft.entity_type, normalized)
                canonical_candidates = canonical_index.get(key, set())
                candidates = sorted(
                    canonical_candidates if canonical_candidates else alias_index.get(key, set())
                )
                if len(candidates) == 1:
                    entity_id = candidates[0]
                    state = "matched"
                elif len(candidates) > 1:
                    entity_id = None
                    state = "ambiguous"
                else:
                    entity_id = "ent_" + uuid.uuid4().hex
                    state = "new"
                    entity_rows.append((
                        entity_id, draft.entity_type, draft.canonical_name,
                        normalized, generation_id,
                    ))
                    canonical_index.setdefault(key, set()).add(entity_id)

                candidates_json = json.dumps(candidates, ensure_ascii=False) if candidates else None
                mention_rows.append((
                    generation_id, block.document_version_id, block.block_key,
                    draft.local_id, draft.mention_text, draft.canonical_name,
                    draft.entity_type, draft.start_offset, draft.end_offset,
                    entity_id, state, draft.confidence, candidates_json,
                ))
                mention_meta[(block.block_key, draft.local_id)] = {
                    "entity_id": entity_id,
                    "canonical_name": draft.canonical_name,
                    "mention_text": draft.mention_text,
                }
                if entity_id:
                    for alias in [draft.mention_text, *draft.aliases]:
                        normalized_alias = normalize_name(alias)
                        if normalized_alias and normalized_alias != normalized:
                            alias_rows[(entity_id, normalized_alias)] = (
                                entity_id, generation_id, alias,
                                normalized_alias, draft.confidence,
                            )
                            alias_index.setdefault(
                                (draft.entity_type, normalized_alias), set(),
                            ).add(entity_id)

        # Pass 2: normalize Actions by their complete participant signature.
        existing_actions = {
            row["signature_hash"]: row for row in self.repository.resolution_actions()
        }
        action_rows: list[tuple] = []
        action_owner_rows: dict[str, tuple] = {}
        action_participant_rows: list[tuple] = []
        action_mention_rows: list[tuple] = []
        action_meta: dict[tuple[str, str], str] = {}

        for result in non_empty:
            block = result["block"]
            extraction = result["extraction"]
            for draft in extraction.actions:
                participants = []
                unresolved = False
                for participant in draft.participants:
                    if participant.entity_local_id:
                        mention = mention_meta[(block.block_key, participant.entity_local_id)]
                        unresolved = unresolved or mention["entity_id"] is None
                        participants.append({
                            "role": participant.role,
                            "entity_id": mention["entity_id"],
                            "value_text": None if mention["entity_id"] else mention["canonical_name"],
                        })
                    else:
                        participants.append({
                            "role": participant.role,
                            "entity_id": None,
                            "value_text": participant.value_text,
                        })
                signature = self._action_signature(draft.verb, participants)
                sig_hash = signature_hash(signature)
                existing = existing_actions.get(sig_hash)
                if existing:
                    action_id = existing["action_id"]
                    state = "ambiguous" if unresolved else "matched"
                    if (
                        existing.get("lifecycle_state") == "candidate"
                        and existing.get("created_generation_id") != generation_id
                    ):
                        action_owner_rows[action_id] = (generation_id, action_id)
                else:
                    action_id = "act_" + uuid.uuid4().hex
                    state = "ambiguous" if unresolved else "new"
                    action_rows.append((
                        action_id, draft.canonical_text, draft.verb, sig_hash,
                        generation_id,
                        json.dumps({"signature": signature}, ensure_ascii=False, separators=(",", ":")),
                    ))
                    existing_actions[sig_hash] = {
                        "action_id": action_id,
                        "lifecycle_state": "candidate",
                        "created_generation_id": generation_id,
                    }
                    ordinals: dict[str, int] = defaultdict(int)
                    for participant in participants:
                        ordinals[participant["role"]] += 1
                        action_participant_rows.append((
                            action_id, participant["role"], ordinals[participant["role"]],
                            participant.get("entity_id"), participant.get("value_text"),
                        ))
                action_mention_rows.append((
                    generation_id, block.document_version_id, block.block_key,
                    draft.local_id, draft.canonical_text, draft.verb,
                    json.dumps(signature, ensure_ascii=False, separators=(",", ":")),
                    action_id, state, draft.confidence,
                ))
                action_meta[(block.block_key, draft.local_id)] = action_id

        # Pass 3: de-duplicate Assertions in memory and collect exact evidence.
        assertion_index = self.repository.resolution_assertions(generation_id)
        assertion_rows: list[tuple] = []
        assertion_participants_pending: list[tuple] = []
        evidence_rows: list[tuple] = []
        evidence_keys: set[tuple] = set()

        for result in non_empty:
            block = result["block"]
            extraction = result["extraction"]
            for draft in extraction.assertions:
                participants = []
                for participant in draft.participants:
                    if participant.entity_local_id:
                        mention = mention_meta[(block.block_key, participant.entity_local_id)]
                        participants.append({
                            "role": participant.role,
                            "entity_id": mention["entity_id"],
                            "mention_key": (block.block_key, participant.entity_local_id),
                            "value_text": participant.value_text or mention["mention_text"],
                        })
                    else:
                        participants.append({
                            "role": participant.role,
                            "entity_id": None,
                            "mention_key": None,
                            "value_text": participant.value_text,
                        })
                action_id = (
                    action_meta[(block.block_key, draft.action_local_id)]
                    if draft.action_local_id else None
                )
                identity = {
                    "kind": draft.kind,
                    "predicate": draft.predicate,
                    "modality": draft.modality,
                    "action_id": action_id,
                    "participants": sorted(
                        [{
                            "role": item["role"],
                            "entity_id": item["entity_id"],
                            "value_text": normalize_name(item["value_text"] or ""),
                        } for item in participants],
                        key=lambda item: (
                            item["role"], item["entity_id"] or "", item["value_text"],
                        ),
                    ),
                    "condition": self._normalized_text(draft.condition),
                    "exception": self._normalized_text(draft.exception),
                    "scope": self._normalized_text(draft.scope),
                    "payload": draft.payload,
                }
                assertion_hash = signature_hash(identity)
                assertion_id = assertion_index.get(assertion_hash)
                is_new = assertion_id is None
                if is_new:
                    assertion_id = "ast_" + uuid.uuid4().hex
                    assertion_index[assertion_hash] = assertion_id
                    assertion_rows.append((
                        assertion_id, generation_id, block.document_version_id,
                        draft.kind, draft.predicate, draft.modality, action_id,
                        draft.condition, draft.exception, draft.scope,
                        json.dumps(draft.payload, ensure_ascii=False, separators=(",", ":"))
                        if draft.payload is not None else None,
                        assertion_hash, draft.confidence,
                    ))
                    ordinals: dict[str, int] = defaultdict(int)
                    for participant in participants:
                        ordinals[participant["role"]] += 1
                        assertion_participants_pending.append((
                            assertion_id, participant["role"], ordinals[participant["role"]],
                            participant["entity_id"], participant["mention_key"],
                            participant["value_text"],
                        ))
                evidence_key = (assertion_id, block.block_key, draft.quote_start)
                if evidence_key not in evidence_keys:
                    evidence_keys.add(evidence_key)
                    evidence_rows.append((
                        assertion_id, block.block_key,
                        "primary" if is_new else "supporting",
                        draft.quote, draft.quote_start, draft.quote_end, draft.confidence,
                    ))

        # Fixed-count batch writes. Mention IDs are loaded once after the identity insert.
        self.repository.bulk_insert_entities(entity_rows)
        self.repository.bulk_upsert_aliases(list(alias_rows.values()))
        self.repository.bulk_insert_entity_mentions(mention_rows)
        mention_ids = self.repository.mention_ids(generation_id)
        self.repository.bulk_insert_actions(action_rows)
        self.repository.bulk_reassign_actions(list(action_owner_rows.values()))
        self.repository.bulk_insert_action_participants(action_participant_rows)
        self.repository.bulk_insert_action_mentions(action_mention_rows)
        self.repository.bulk_insert_assertions(assertion_rows)
        assertion_entity_rows = [(
            assertion_id, role, ordinal, entity_id,
            mention_ids.get(mention_key) if mention_key else None,
            value_text,
        ) for assertion_id, role, ordinal, entity_id, mention_key, value_text
          in assertion_participants_pending]
        self.repository.bulk_insert_assertion_entities(assertion_entity_rows)
        self.repository.bulk_insert_evidence(evidence_rows)

        return {
            "entities_created": len(entity_rows),
            "actions_created": len(action_rows),
            "assertions_created": len(assertion_rows),
        }

    def _entity_indexes(
        self,
        generation_id: str,
    ) -> tuple[dict[tuple[str, str], set[str]], dict[tuple[str, str], set[str]]]:
        canonical: dict[tuple[str, str], set[str]] = defaultdict(set)
        aliases: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in self.repository.resolution_entities(generation_id):
            canonical[(row["entity_type"], row["normalized_name"])].add(row["entity_id"])
            if row.get("normalized_alias"):
                aliases[(row["entity_type"], row["normalized_alias"])].add(row["entity_id"])
        return canonical, aliases

    @staticmethod
    def _action_signature(verb: str, participants: list[dict]) -> dict:
        return {
            "verb": normalize_name(verb),
            "participants": sorted(
                [{
                    "role": item["role"],
                    "entity_id": item.get("entity_id"),
                    "value_text": normalize_name(item.get("value_text") or "") or None,
                } for item in participants],
                key=lambda item: (
                    item["role"], item["entity_id"] or "", item["value_text"] or "",
                ),
            ),
        }

    @staticmethod
    def _normalized_text(value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None
