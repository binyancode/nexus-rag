"""High-precision SQL persistence for entities, actions, assertions, and derived graph."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict

from nexus.domain import ActionDraft, Block, EntityMentionDraft, LegalAssertionDraft

from .base import SqlRepository, json_text


def normalize_name(value: str) -> str:
    """Conservative exact-match normalization: Unicode NFKC, case, and whitespace only."""
    import unicodedata

    return "".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def signature_hash(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AssertionRepository(SqlRepository):
    # ------------------------------------------------------------------
    # Bulk resolution/persistence used by the indexing reduce node
    # ------------------------------------------------------------------
    def resolution_entities(self, generation_id: str) -> list[dict]:
        return self.db.execute_query(
            """SELECT e.entity_id,e.entity_type,e.normalized_name,a.normalized_alias
               FROM nexus.entity e
               LEFT JOIN nexus.entity_alias a ON a.entity_id=e.entity_id
                 AND (a.generation_id IS NULL OR a.generation_id=? OR EXISTS (
                     SELECT 1 FROM nexus.index_generation g
                     WHERE g.generation_id=a.generation_id AND g.[state]='active'
                 ))
               WHERE e.lifecycle_state='active'
                  OR (e.lifecycle_state='candidate' AND e.created_generation_id=?)""",
            (generation_id, generation_id),
        )

    def resolution_actions(self) -> list[dict]:
        return self.db.execute_query(
            """SELECT action_id,signature_hash,lifecycle_state,created_generation_id
               FROM nexus.action WHERE lifecycle_state<>'rejected'"""
        )

    def resolution_assertions(self, generation_id: str) -> dict[str, str]:
        rows = self.db.execute_query(
            "SELECT assertion_hash,assertion_id FROM nexus.legal_assertion WHERE generation_id=?",
            (generation_id,),
        )
        return {row["assertion_hash"]: row["assertion_id"] for row in rows}

    def bulk_insert_entities(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.entity
                   (entity_id,entity_type,canonical_name,normalized_name,lifecycle_state,
                    created_generation_id,source,locked)
               VALUES (?,?,?,?,'candidate',?,'llm',0)""",
            rows,
        )

    def bulk_upsert_aliases(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """MERGE nexus.entity_alias AS t
               USING (SELECT ? entity_id,? generation_id,? alias,? normalized_alias,
                             ? confidence) AS s
                 ON t.entity_id=s.entity_id AND t.generation_id=s.generation_id
                AND t.normalized_alias=s.normalized_alias
               WHEN MATCHED THEN UPDATE SET alias=s.alias,confidence=s.confidence
               WHEN NOT MATCHED THEN INSERT
                   (entity_id,generation_id,alias,normalized_alias,source,confidence)
                   VALUES (s.entity_id,s.generation_id,s.alias,s.normalized_alias,'llm',s.confidence);""",
            rows,
        )

    def bulk_insert_entity_mentions(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.entity_mention
                   (generation_id,document_version_id,block_key,local_id,mention_text,
                    canonical_name,entity_type,start_offset,end_offset,entity_id,
                    resolution_state,confidence,candidates)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )

    def mention_ids(self, generation_id: str) -> dict[tuple[str, str], int]:
        rows = self.db.execute_query(
            "SELECT block_key,local_id,mention_id FROM nexus.entity_mention WHERE generation_id=?",
            (generation_id,),
        )
        return {(row["block_key"], row["local_id"]): int(row["mention_id"]) for row in rows}

    def bulk_insert_actions(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.action
                   (action_id,canonical_text,verb,signature_hash,lifecycle_state,
                    created_generation_id,attrs)
               VALUES (?,?,?,?,'candidate',?,?)""",
            rows,
        )

    def bulk_reassign_actions(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """UPDATE nexus.action SET created_generation_id=?,updated_at=SYSUTCDATETIME()
               WHERE action_id=? AND lifecycle_state='candidate'""",
            rows,
        )

    def bulk_insert_action_participants(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.action_participant
                   (action_id,role,ordinal,entity_id,value_text) VALUES (?,?,?,?,?)""",
            rows,
        )

    def bulk_insert_action_mentions(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.action_mention
                   (generation_id,document_version_id,block_key,local_id,canonical_text,
                    verb,signature,action_id,resolution_state,confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )

    def bulk_insert_assertions(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.legal_assertion
                   (assertion_id,generation_id,document_version_id,assertion_kind,
                    predicate,modality,action_id,condition_text,exception_text,scope_text,
                    payload,assertion_hash,confidence,[state],source,locked)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'accepted','llm',0)""",
            rows,
        )

    def bulk_insert_assertion_entities(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.assertion_entity
                   (assertion_id,role,ordinal,entity_id,mention_id,value_text)
               VALUES (?,?,?,?,?,?)""",
            rows,
        )

    def bulk_insert_evidence(self, rows: list[tuple]) -> int:
        return self.db.execute_many(
            """INSERT INTO nexus.assertion_evidence
                   (assertion_id,block_key,evidence_role,quote,quote_start,quote_end,confidence)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )

    # ------------------------------------------------------------------
    # Entity resolution and mentions
    # ------------------------------------------------------------------
    def find_entities_exact(self, entity_type: str, normalized: str, generation_id: str) -> list[dict]:
        return self.db.execute_query(
            """SELECT DISTINCT e.entity_id, e.canonical_name, e.lifecycle_state
               FROM nexus.entity e
               LEFT JOIN nexus.entity_alias a
                 ON a.entity_id=e.entity_id
                AND a.normalized_alias=?
                AND (
                    a.generation_id IS NULL OR a.generation_id=? OR EXISTS (
                        SELECT 1 FROM nexus.index_generation ag
                        WHERE ag.generation_id=a.generation_id AND ag.[state]='active'
                    )
                )
               WHERE e.entity_type=?
                 AND (e.lifecycle_state='active'
                      OR (e.lifecycle_state='candidate' AND e.created_generation_id=?))
                 AND (e.normalized_name=? OR a.alias_id IS NOT NULL)""",
            (normalized, generation_id, entity_type, generation_id, normalized),
        )

    def create_entity(self, draft: EntityMentionDraft, generation_id: str) -> str:
        entity_id = "ent_" + uuid.uuid4().hex
        self.db.execute_non_query(
            """INSERT INTO nexus.entity
                   (entity_id, entity_type, canonical_name, normalized_name, lifecycle_state,
                    created_generation_id, source, locked)
               VALUES (?, ?, ?, ?, 'candidate', ?, 'llm', 0)""",
            (
                entity_id, draft.entity_type, draft.canonical_name,
                normalize_name(draft.canonical_name), generation_id,
            ),
        )
        return entity_id

    def add_alias(self, entity_id: str, generation_id: str, alias: str, confidence: float) -> None:
        normalized = normalize_name(alias)
        if not normalized:
            return
        self.db.execute_non_query(
            """MERGE nexus.entity_alias AS t
               USING (SELECT ? AS entity_id, ? AS generation_id, ? AS normalized_alias) AS s
                 ON t.entity_id=s.entity_id AND t.generation_id=s.generation_id
                AND t.normalized_alias=s.normalized_alias
               WHEN MATCHED THEN UPDATE SET alias=?, confidence=?
               WHEN NOT MATCHED THEN INSERT
                   (entity_id, generation_id, alias, normalized_alias, source, confidence)
                   VALUES (?, ?, ?, ?, 'llm', ?);""",
            (
                entity_id, generation_id, normalized,
                alias, confidence,
                entity_id, generation_id, alias, normalized, confidence,
            ),
        )

    def insert_entity_mention(
        self,
        *,
        generation_id: str,
        document_version_id: str,
        block_key: str,
        draft: EntityMentionDraft,
        entity_id: str | None,
        resolution_state: str,
        candidates: list[str] | None = None,
    ) -> int:
        rows = self.db.execute_query(
            """INSERT INTO nexus.entity_mention
                   (generation_id, document_version_id, block_key, local_id, mention_text,
                    canonical_name, entity_type, start_offset, end_offset, entity_id,
                    resolution_state, confidence, candidates)
               OUTPUT inserted.mention_id
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                generation_id, document_version_id, block_key, draft.local_id,
                draft.mention_text, draft.canonical_name, draft.entity_type,
                draft.start_offset, draft.end_offset, entity_id, resolution_state,
                draft.confidence, json_text(candidates),
            ),
        )
        return int(rows[0]["mention_id"])

    # ------------------------------------------------------------------
    # Action normalization and mentions
    # ------------------------------------------------------------------
    def find_action(self, signature: str, generation_id: str) -> dict | None:
        rows = self.db.execute_query(
            """SELECT TOP 2 action_id, lifecycle_state, created_generation_id
               FROM nexus.action
               WHERE signature_hash=?""",
            (signature,),
        )
        if len(rows) > 1:
            raise ValueError(f"multiple actions share signature {signature}")
        if not rows:
            return None
        row = rows[0]
        if row["lifecycle_state"] == "rejected":
            raise ValueError(f"action signature is explicitly rejected: {signature}")
        if row["lifecycle_state"] == "candidate" and row.get("created_generation_id") != generation_id:
            self.db.execute_non_query(
                """UPDATE nexus.action
                   SET created_generation_id=?, updated_at=SYSUTCDATETIME()
                   WHERE action_id=? AND lifecycle_state='candidate'""",
                (generation_id, row["action_id"]),
            )
        return row

    def create_action(
        self,
        draft: ActionDraft,
        generation_id: str,
        signature: dict,
        participants: list[dict],
    ) -> str:
        action_id = "act_" + uuid.uuid4().hex
        sig_hash = signature_hash(signature)
        self.db.execute_non_query(
            """INSERT INTO nexus.action
                   (action_id, canonical_text, verb, signature_hash, lifecycle_state,
                    created_generation_id, attrs)
               VALUES (?, ?, ?, ?, 'candidate', ?, ?)""",
            (action_id, draft.canonical_text, draft.verb, sig_hash, generation_id, json_text({"signature": signature})),
        )
        role_ordinals: dict[str, int] = defaultdict(int)
        for participant in participants:
            role = participant["role"]
            role_ordinals[role] += 1
            self.db.execute_non_query(
                """INSERT INTO nexus.action_participant
                       (action_id, role, ordinal, entity_id, value_text)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    action_id, role, role_ordinals[role], participant.get("entity_id"),
                    participant.get("value_text"),
                ),
            )
        return action_id

    def insert_action_mention(
        self,
        *,
        generation_id: str,
        block: Block,
        draft: ActionDraft,
        signature: dict,
        action_id: str,
        resolution_state: str,
    ) -> None:
        self.db.execute_non_query(
            """INSERT INTO nexus.action_mention
                   (generation_id, document_version_id, block_key, local_id, canonical_text,
                    verb, signature, action_id, resolution_state, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                generation_id, block.document_version_id, block.block_key, draft.local_id,
                draft.canonical_text, draft.verb, json_text(signature), action_id,
                resolution_state, draft.confidence,
            ),
        )

    # ------------------------------------------------------------------
    # Assertions and exact evidence
    # ------------------------------------------------------------------
    def find_assertion(self, generation_id: str, assertion_hash: str) -> str | None:
        rows = self.db.execute_query(
            "SELECT TOP 1 assertion_id FROM nexus.legal_assertion WHERE generation_id=? AND assertion_hash=?",
            (generation_id, assertion_hash),
        )
        return rows[0]["assertion_id"] if rows else None

    def insert_assertion(
        self,
        *,
        generation_id: str,
        block: Block,
        draft: LegalAssertionDraft,
        action_id: str | None,
        assertion_hash: str,
        participants: list[dict],
    ) -> str:
        assertion_id = "ast_" + uuid.uuid4().hex
        self.db.execute_non_query(
            """INSERT INTO nexus.legal_assertion
                   (assertion_id, generation_id, document_version_id, assertion_kind,
                    predicate, modality, action_id, condition_text, exception_text,
                    scope_text, payload, assertion_hash, confidence, [state], source, locked)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', 'llm', 0)""",
            (
                assertion_id, generation_id, block.document_version_id, draft.kind,
                draft.predicate, draft.modality, action_id, draft.condition,
                draft.exception, draft.scope, json_text(draft.payload), assertion_hash,
                draft.confidence,
            ),
        )
        role_ordinals: dict[str, int] = defaultdict(int)
        for participant in participants:
            role = participant["role"]
            role_ordinals[role] += 1
            self.db.execute_non_query(
                """INSERT INTO nexus.assertion_entity
                       (assertion_id, role, ordinal, entity_id, mention_id, value_text)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    assertion_id, role, role_ordinals[role], participant["entity_id"],
                    participant["mention_id"], participant["value_text"],
                ),
            )
        return assertion_id

    def insert_evidence(
        self,
        *,
        assertion_id: str,
        block_key: str,
        role: str,
        quote: str,
        quote_start: int,
        quote_end: int,
        confidence: float,
    ) -> None:
        self.db.execute_non_query(
            """IF NOT EXISTS (
                   SELECT 1 FROM nexus.assertion_evidence
                   WHERE assertion_id=? AND block_key=? AND quote_start=?
               )
               INSERT INTO nexus.assertion_evidence
                   (assertion_id, block_key, evidence_role, quote, quote_start, quote_end, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                assertion_id, block_key, int(quote_start),
                assertion_id, block_key, role, quote, int(quote_start), int(quote_end), confidence,
            ),
        )

    # ------------------------------------------------------------------
    # Derived graph
    # ------------------------------------------------------------------
    def derive_graph(self, generation_id: str) -> int:
        rows = self.db.execute_query(
            """SELECT la.assertion_id, la.assertion_kind, la.predicate, la.modality,
                      la.action_id, la.confidence, ae.role, ae.ordinal, ae.entity_id
               FROM nexus.legal_assertion la
               JOIN nexus.assertion_entity ae ON ae.assertion_id=la.assertion_id
               WHERE la.generation_id=? AND la.[state]='accepted'
               ORDER BY la.assertion_id, ae.role, ae.ordinal""",
            (generation_id,),
        )
        grouped: dict[str, dict] = {}
        for row in rows:
            item = grouped.setdefault(row["assertion_id"], {
                "kind": row["assertion_kind"], "predicate": row["predicate"],
                "modality": row["modality"], "action_id": row.get("action_id"),
                "confidence": float(row.get("confidence") or 1), "participants": [],
            })
            if row.get("entity_id"):
                item["participants"].append((row["role"], row["entity_id"]))

        edge_ids: set[int] = set()
        modality_edge = {
            "must": "has_obligation",
            "must_not": "has_prohibition",
            "may": "has_permission",
            "conditional_may": "has_permission",
            "should": "has_recommendation",
            "factual": "has_fact",
        }
        for assertion_id, item in grouped.items():
            participants = item["participants"]
            if item["kind"] == "norm" and item["action_id"]:
                for role, entity_id in participants:
                    if role != "subject":
                        continue
                    edge_id = self._upsert_edge(
                        generation_id, "entity", entity_id,
                        modality_edge[item["modality"]], "action", item["action_id"],
                        item["confidence"], assertion_id,
                    )
                    edge_ids.add(edge_id)
            elif item["kind"] == "relation":
                sources = [eid for role, eid in participants if role == "subject"]
                targets = [eid for role, eid in participants if role != "subject" and eid not in sources]
                for src in sources:
                    for dst in targets:
                        if src == dst:
                            continue
                        edge_id = self._upsert_edge(
                            generation_id, "entity", src, item["predicate"],
                            "entity", dst, item["confidence"], assertion_id,
                        )
                        edge_ids.add(edge_id)
        return len(edge_ids)

    def _upsert_edge(
        self,
        generation_id: str,
        src_kind: str,
        src_id: str,
        edge_type: str,
        dst_kind: str,
        dst_id: str,
        weight: float,
        assertion_id: str,
    ) -> int:
        rows = self.db.execute_query(
            """MERGE nexus.graph_edge AS t
               USING (SELECT ? AS generation_id, ? AS src_kind, ? AS src_id,
                             ? AS edge_type, ? AS dst_kind, ? AS dst_id) AS s
                 ON t.generation_id=s.generation_id AND t.src_kind=s.src_kind
                AND t.src_id=s.src_id AND t.edge_type=s.edge_type
                AND t.dst_kind=s.dst_kind AND t.dst_id=s.dst_id
               WHEN MATCHED THEN UPDATE SET weight=CASE WHEN t.weight < ? THEN ? ELSE t.weight END
               WHEN NOT MATCHED THEN INSERT
                   (generation_id, src_kind, src_id, edge_type, dst_kind, dst_id, weight, source, locked)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'derived', 0)
               OUTPUT inserted.edge_id;""",
            (
                generation_id, src_kind, src_id, edge_type, dst_kind, dst_id,
                weight, weight,
                generation_id, src_kind, src_id, edge_type, dst_kind, dst_id, weight,
            ),
        )
        edge_id = int(rows[0]["edge_id"])
        self.db.execute_non_query(
            """IF NOT EXISTS (
                   SELECT 1 FROM nexus.graph_edge_support WHERE edge_id=? AND assertion_id=?
               )
               INSERT INTO nexus.graph_edge_support (edge_id, assertion_id) VALUES (?, ?)""",
            (edge_id, assertion_id, edge_id, assertion_id),
        )
        return edge_id

    # ------------------------------------------------------------------
    # Generation statistics
    # ------------------------------------------------------------------
    def counts(self, generation_id: str) -> dict[str, int]:
        rows = self.db.execute_query(
            """SELECT
                 (SELECT COUNT_BIG(*) FROM nexus.document_version WHERE generation_id=?) AS documents,
                 (SELECT COUNT_BIG(*) FROM nexus.block_manifest WHERE generation_id=?) AS blocks,
                 (SELECT COUNT_BIG(*) FROM (
                      SELECT ae.entity_id
                      FROM nexus.assertion_entity ae
                      JOIN nexus.legal_assertion la ON la.assertion_id=ae.assertion_id
                      WHERE la.generation_id=? AND la.[state]='accepted' AND ae.entity_id IS NOT NULL
                      UNION
                      SELECT ap.entity_id
                      FROM nexus.action_participant ap
                      JOIN nexus.legal_assertion la ON la.action_id=ap.action_id
                      WHERE la.generation_id=? AND la.[state]='accepted' AND ap.entity_id IS NOT NULL
                  ) e) AS entities,
                 (SELECT COUNT_BIG(DISTINCT action_id) FROM nexus.legal_assertion
                      WHERE generation_id=? AND [state]='accepted' AND action_id IS NOT NULL) AS actions,
                 (SELECT COUNT_BIG(*) FROM nexus.legal_assertion
                      WHERE generation_id=? AND [state]='accepted') AS assertions,
                 (SELECT COUNT_BIG(*) FROM nexus.graph_edge WHERE generation_id=?) AS graph_edges""",
            (generation_id,) * 7,
        )
        row = rows[0]
        return {key: int(row.get(key) or 0) for key in (
            "documents", "blocks", "entities", "actions", "assertions", "graph_edges",
        )}
