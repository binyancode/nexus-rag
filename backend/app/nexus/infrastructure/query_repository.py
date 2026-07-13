"""Generation-scoped SQL reads for Assertion-first query operators."""
from __future__ import annotations

import json
from typing import Any

from nexus.domain import CollectionScope

from .base import SqlRepository


class QueryRepository(SqlRepository):
    """Every public read requires a complete frozen CollectionScope."""

    # ------------------------------------------------------------------
    # Initializer vocabularies
    # ------------------------------------------------------------------
    def generation_dimensions(self, scope: CollectionScope) -> dict[str, int]:
        cte, params = self.scope_cte(scope)
        rows = self.db.execute_query(
            cte +
            """ SELECT q.store_id,g.embedding_dimensions
                FROM query_scope q
                JOIN nexus.index_generation g
                  ON g.store_id=q.store_id AND g.generation_id=q.generation_id""",
            params,
        )
        result = {row["store_id"]: int(row["embedding_dimensions"]) for row in rows}
        if set(result) != set(scope.allowed_stores):
            raise ValueError("frozen generation metadata is incomplete")
        return result

    def visible_entities(self, scope: CollectionScope) -> list[dict]:
        cte, params = self.scope_cte(scope)
        rows = self.db.execute_query(
            cte +
            """, visible_entity(entity_id) AS (
                    SELECT ae.entity_id
                    FROM query_scope q
                    JOIN nexus.legal_assertion la ON la.generation_id=q.generation_id
                    JOIN nexus.assertion_entity ae ON ae.assertion_id=la.assertion_id
                    WHERE la.[state]='accepted' AND ae.entity_id IS NOT NULL
                    UNION
                    SELECT ap.entity_id
                    FROM query_scope q
                    JOIN nexus.legal_assertion la ON la.generation_id=q.generation_id
                    JOIN nexus.action_participant ap ON ap.action_id=la.action_id
                    WHERE la.[state]='accepted' AND ap.entity_id IS NOT NULL
                )
                SELECT e.entity_id,e.entity_type,e.canonical_name,
                       a.alias,a.generation_id AS alias_generation_id
                FROM visible_entity visible
                JOIN nexus.entity e ON e.entity_id=visible.entity_id
                LEFT JOIN nexus.entity_alias a ON a.entity_id=e.entity_id
                  AND (a.generation_id IS NULL OR EXISTS (
                      SELECT 1 FROM query_scope aq WHERE aq.generation_id=a.generation_id
                  ))
                WHERE e.lifecycle_state='active'
                ORDER BY e.entity_type,e.canonical_name,e.entity_id,a.alias""",
            params,
        )
        grouped: dict[str, dict] = {}
        for row in rows:
            item = grouped.setdefault(row["entity_id"], {
                "entity_id": row["entity_id"],
                "entity_type": row["entity_type"],
                "name": row["canonical_name"],
                "aliases": [],
            })
            alias = row.get("alias")
            if alias and alias not in item["aliases"]:
                item["aliases"].append(alias)
        return list(grouped.values())

    def visible_actions(self, scope: CollectionScope) -> list[dict]:
        cte, params = self.scope_cte(scope)
        rows = self.db.execute_query(
            cte +
            """ SELECT DISTINCT a.action_id,a.canonical_text,a.verb
                FROM query_scope q
                JOIN nexus.legal_assertion la ON la.generation_id=q.generation_id
                JOIN nexus.action a ON a.action_id=la.action_id
                WHERE la.[state]='accepted' AND a.lifecycle_state='active'
                ORDER BY a.canonical_text,a.action_id""",
            params,
        )
        return rows

    def visible_documents(self, scope: CollectionScope) -> list[dict]:
        cte, params = self.scope_cte(scope)
        return self.db.execute_query(
            cte +
            """ SELECT q.store_id,q.generation_id,dv.document_id,dv.document_version_id,
                       dv.title,dv.category,dv.block_count
                FROM query_scope q
                JOIN nexus.document_version dv ON dv.generation_id=q.generation_id
                WHERE dv.[state]='validated'
                ORDER BY dv.title,q.store_id,dv.document_id""",
            params,
        )

    def visible_graph_relations(self, scope: CollectionScope) -> list[str]:
        cte, params = self.scope_cte(scope)
        rows = self.db.execute_query(
            cte +
            """ SELECT DISTINCT ge.edge_type
                FROM query_scope q
                JOIN nexus.graph_edge ge ON ge.generation_id=q.generation_id
                JOIN nexus.graph_edge_support gs ON gs.edge_id=ge.edge_id
                JOIN nexus.legal_assertion la
                  ON la.assertion_id=gs.assertion_id
                 AND la.generation_id=q.generation_id AND la.[state]='accepted'
                ORDER BY ge.edge_type""",
            params,
        )
        return [row["edge_type"] for row in rows]

    # ------------------------------------------------------------------
    # Assertion/action facts
    # ------------------------------------------------------------------
    def subject_assertions(
        self,
        scope: CollectionScope,
        subject_ids: list[str],
        *,
        modalities: list[str] | None = None,
        kinds: list[str] | None = None,
        predicate: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        if not subject_ids:
            return []
        return self._query_assertions(
            scope,
            subject_ids=subject_ids,
            modalities=modalities,
            kinds=kinds,
            predicate=predicate,
            limit=limit,
        )

    def subject_actions(
        self,
        scope: CollectionScope,
        subject_ids: list[str],
        *,
        modalities: list[str] | None = None,
        kinds: list[str] | None = None,
        predicate: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        assertions = self.subject_assertions(
            scope,
            subject_ids,
            modalities=modalities,
            kinds=kinds,
            predicate=predicate,
            limit=limit,
        )
        grouped: dict[str, dict] = {}
        for assertion in assertions:
            action_id = assertion.get("action_id")
            if not action_id:
                continue
            item = grouped.setdefault(action_id, {
                "fact_kind": "action",
                "fact_key": action_id,
                "comparison_key": action_id,
                "action_id": action_id,
                "canonical_text": assertion.get("action_text"),
                "verb": assertion.get("action_verb"),
                "assertion_ids": [],
                "supports": {},
                "modalities": [],
                "assertions": [],
            })
            self._append_unique(item["assertion_ids"], assertion["assertion_id"])
            self._append_unique(item["modalities"], assertion["modality"])
            item["assertions"].append(assertion)
            for subject_id, assertion_ids in assertion.get("supports", {}).items():
                support = item["supports"].setdefault(subject_id, [])
                for assertion_id in assertion_ids:
                    self._append_unique(support, assertion_id)
        return list(grouped.values())

    def action_subjects(
        self,
        scope: CollectionScope,
        action_ids: list[str],
        *,
        modalities: list[str] | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        if not action_ids:
            return []
        assertions = self._query_assertions(
            scope,
            action_ids=action_ids,
            modalities=modalities,
            limit=limit,
        )
        names = {row["entity_id"]: row["name"] for row in self.visible_entities(scope)}
        grouped: dict[str, dict] = {}
        for assertion in assertions:
            subject_id = assertion.get("subject_id")
            if not subject_id:
                continue
            item = grouped.setdefault(subject_id, {
                "fact_kind": "subject",
                "fact_key": subject_id,
                "comparison_key": subject_id,
                "entity_id": subject_id,
                "name": names.get(subject_id, assertion.get("subject_name") or subject_id),
                "assertion_ids": [],
                "supports": {},
                "actions": [],
            })
            self._append_unique(item["assertion_ids"], assertion["assertion_id"])
            if assertion.get("action_id"):
                self._append_unique(item["actions"], assertion["action_id"])
            support = item["supports"].setdefault(subject_id, [])
            self._append_unique(support, assertion["assertion_id"])
        return list(grouped.values())

    def assertion_search(
        self,
        scope: CollectionScope,
        *,
        entity_ids: list[str] | None = None,
        modalities: list[str] | None = None,
        kinds: list[str] | None = None,
        predicate: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        return self._query_assertions(
            scope,
            any_entity_ids=entity_ids,
            modalities=modalities,
            kinds=kinds,
            predicate=predicate,
            limit=limit,
        )

    def _query_assertions(
        self,
        scope: CollectionScope,
        *,
        subject_ids: list[str] | None = None,
        action_ids: list[str] | None = None,
        any_entity_ids: list[str] | None = None,
        modalities: list[str] | None = None,
        kinds: list[str] | None = None,
        predicate: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        cte, scope_params = self.scope_cte(scope)
        where = ["la.[state]='accepted'"]
        params: list[Any] = [*scope_params, max(1, min(int(limit), 10000))]
        if subject_ids:
            placeholders = ",".join("?" for _ in subject_ids)
            where.append(f"subject.entity_id IN ({placeholders})")
            params.extend(subject_ids)
        if action_ids:
            placeholders = ",".join("?" for _ in action_ids)
            where.append(f"la.action_id IN ({placeholders})")
            params.extend(action_ids)
        if any_entity_ids:
            placeholders = ",".join("?" for _ in any_entity_ids)
            where.append(
                "EXISTS (SELECT 1 FROM nexus.assertion_entity wanted "
                f"WHERE wanted.assertion_id=la.assertion_id AND wanted.entity_id IN ({placeholders}))"
            )
            params.extend(any_entity_ids)
        if modalities:
            placeholders = ",".join("?" for _ in modalities)
            where.append(f"la.modality IN ({placeholders})")
            params.extend(modalities)
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            where.append(f"la.assertion_kind IN ({placeholders})")
            params.extend(kinds)
        if predicate:
            where.append("la.predicate=?")
            params.append(predicate)
        rows = self.db.execute_query(
            cte +
            f""" SELECT TOP (?) q.store_id,q.generation_id,
                        la.assertion_id,la.assertion_kind,la.predicate,la.modality,
                        la.action_id,la.condition_text,la.exception_text,la.scope_text,
                        la.payload,la.confidence,
                        action.canonical_text AS action_text,action.verb AS action_verb,
                        subject.entity_id AS subject_id,subject_entity.canonical_name AS subject_name,
                        participant.role AS participant_role,participant.ordinal AS participant_ordinal,
                        participant.entity_id AS participant_entity_id,
                        participant.value_text AS participant_value_text,
                        participant_entity.canonical_name AS participant_name
                 FROM query_scope q
                 JOIN nexus.legal_assertion la ON la.generation_id=q.generation_id
                 LEFT JOIN nexus.action action ON action.action_id=la.action_id
                 LEFT JOIN nexus.assertion_entity subject
                   ON subject.assertion_id=la.assertion_id AND subject.role='subject'
                 LEFT JOIN nexus.entity subject_entity ON subject_entity.entity_id=subject.entity_id
                 LEFT JOIN nexus.assertion_entity participant
                   ON participant.assertion_id=la.assertion_id
                 LEFT JOIN nexus.entity participant_entity
                   ON participant_entity.entity_id=participant.entity_id
                 WHERE {' AND '.join(where)}
                 ORDER BY la.assertion_id,subject.ordinal,participant.role,participant.ordinal""",
            tuple(params),
        )
        grouped: dict[tuple[str, str], dict] = {}
        for row in rows:
            subject_id = row.get("subject_id") or ""
            key = (row["assertion_id"], subject_id)
            item = grouped.setdefault(key, {
                "fact_kind": "assertion",
                "fact_key": row["assertion_id"],
                "assertion_id": row["assertion_id"],
                "assertion_ids": [row["assertion_id"]],
                "store_id": row["store_id"],
                "generation_id": row["generation_id"],
                "kind": row["assertion_kind"],
                "predicate": row["predicate"],
                "modality": row["modality"],
                "action_id": row.get("action_id"),
                "action_text": row.get("action_text"),
                "action_verb": row.get("action_verb"),
                "condition": row.get("condition_text"),
                "exception": row.get("exception_text"),
                "scope": row.get("scope_text"),
                "payload": self._parse_json(row.get("payload")),
                "confidence": float(row.get("confidence") or 0),
                "subject_id": row.get("subject_id"),
                "subject_name": row.get("subject_name"),
                "participants": [],
                "supports": ({subject_id: [row["assertion_id"]]} if subject_id else {}),
            })
            role = row.get("participant_role")
            if role:
                participant = {
                    "role": role,
                    "ordinal": int(row.get("participant_ordinal") or 1),
                    "entity_id": row.get("participant_entity_id"),
                    "name": row.get("participant_name"),
                    "value_text": row.get("participant_value_text"),
                }
                marker = (
                    participant["role"], participant["ordinal"],
                    participant["entity_id"], participant["value_text"],
                )
                if marker not in {
                    (p["role"], p["ordinal"], p.get("entity_id"), p.get("value_text"))
                    for p in item["participants"]
                }:
                    item["participants"].append(participant)
        for item in grouped.values():
            comparison = {
                "kind": item["kind"],
                "predicate": item["predicate"],
                "modality": item["modality"],
                "action_id": item.get("action_id"),
                "condition": item.get("condition"),
                "exception": item.get("exception"),
                "scope": item.get("scope"),
                "payload": item.get("payload"),
                "participants": sorted(
                    [
                        {
                            "role": part["role"],
                            "entity_id": part.get("entity_id"),
                            "value_text": part.get("value_text"),
                        }
                        for part in item["participants"] if part["role"] != "subject"
                    ],
                    key=lambda part: (
                        part["role"], part.get("entity_id") or "", part.get("value_text") or "",
                    ),
                ),
            }
            item["comparison_key"] = json.dumps(
                comparison, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
            )
        return list(grouped.values())

    # ------------------------------------------------------------------
    # Derived graph traversal
    # ------------------------------------------------------------------
    def graph_traverse(
        self,
        scope: CollectionScope,
        starts: list[dict],
        relation: str,
        direction: str,
        hops: int,
        limit: int = 2000,
    ) -> list[dict]:
        frontier = {(item["node_kind"], item["node_id"]) for item in starts}
        seen = set(frontier)
        reached: dict[tuple[str, str], dict] = {}
        for hop in range(1, max(1, min(int(hops), 10)) + 1):
            if not frontier:
                break
            rows = self._incident_edges(scope, frontier, relation)
            next_frontier: set[tuple[str, str]] = set()
            edge_support: dict[int, dict] = {}
            for row in rows:
                edge = edge_support.setdefault(int(row["edge_id"]), {
                    "edge_id": int(row["edge_id"]),
                    "source_kind": row["src_kind"], "source_id": row["src_id"],
                    "source_name": row["src_name"], "relation": row["edge_type"],
                    "target_kind": row["dst_kind"], "target_id": row["dst_id"],
                    "target_name": row["dst_name"], "weight": float(row["weight"]),
                    "assertion_ids": [], "hop": hop,
                })
                if row.get("assertion_id"):
                    self._append_unique(edge["assertion_ids"], row["assertion_id"])
            for edge in edge_support.values():
                source = (edge["source_kind"], edge["source_id"])
                target = (edge["target_kind"], edge["target_id"])
                candidates: list[tuple[tuple[str, str], str]] = []
                if direction in {"out", "both"} and source in frontier:
                    candidates.append((target, edge["target_name"]))
                if direction in {"in", "both"} and target in frontier:
                    candidates.append((source, edge["source_name"]))
                for node, name in candidates:
                    if node in seen:
                        continue
                    item = reached.setdefault(node, {
                        "fact_kind": "graph_node",
                        "fact_key": f"{node[0]}:{node[1]}",
                        "comparison_key": f"{node[0]}:{node[1]}",
                        "node_kind": node[0], "node_id": node[1], "name": name,
                        "assertion_ids": [], "supports": {}, "paths": [],
                    })
                    for assertion_id in edge["assertion_ids"]:
                        self._append_unique(item["assertion_ids"], assertion_id)
                    item["paths"].append(edge)
                    next_frontier.add(node)
            seen.update(next_frontier)
            frontier = next_frontier
            if len(reached) >= limit:
                break
        return list(reached.values())[:limit]

    def _incident_edges(
        self,
        scope: CollectionScope,
        frontier: set[tuple[str, str]],
        relation: str,
    ) -> list[dict]:
        cte, scope_params = self.scope_cte(scope)
        clauses: list[str] = []
        params: list[Any] = list(scope_params)
        for kind, node_id in sorted(frontier):
            clauses.append("((ge.src_kind=? AND ge.src_id=?) OR (ge.dst_kind=? AND ge.dst_id=?))")
            params.extend((kind, node_id, kind, node_id))
        params.append(relation)
        return self.db.execute_query(
            cte +
            f""" SELECT ge.edge_id,ge.src_kind,ge.src_id,ge.edge_type,ge.dst_kind,ge.dst_id,
                        ge.weight,gs.assertion_id,
                        COALESCE(src_entity.canonical_name,src_action.canonical_text,ge.src_id) AS src_name,
                        COALESCE(dst_entity.canonical_name,dst_action.canonical_text,ge.dst_id) AS dst_name
                 FROM query_scope q
                 JOIN nexus.graph_edge ge ON ge.generation_id=q.generation_id
                 JOIN nexus.graph_edge_support gs ON gs.edge_id=ge.edge_id
                 JOIN nexus.legal_assertion la
                   ON la.assertion_id=gs.assertion_id
                  AND la.generation_id=q.generation_id AND la.[state]='accepted'
                 LEFT JOIN nexus.entity src_entity
                   ON ge.src_kind='entity' AND src_entity.entity_id=ge.src_id
                 LEFT JOIN nexus.action src_action
                   ON ge.src_kind='action' AND src_action.action_id=ge.src_id
                 LEFT JOIN nexus.entity dst_entity
                   ON ge.dst_kind='entity' AND dst_entity.entity_id=ge.dst_id
                 LEFT JOIN nexus.action dst_action
                   ON ge.dst_kind='action' AND dst_action.action_id=ge.dst_id
                 WHERE ({' OR '.join(clauses)}) AND ge.edge_type=?
                 ORDER BY ge.edge_id,gs.assertion_id""",
            tuple(params),
        )

    # ------------------------------------------------------------------
    # Exact Assertion evidence
    # ------------------------------------------------------------------
    def ground_assertions(
        self,
        scope: CollectionScope,
        assertion_ids: list[str],
        limit: int = 200,
    ) -> list[dict]:
        assertion_ids = list(dict.fromkeys(assertion_ids))
        if not assertion_ids:
            return []
        cte, scope_params = self.scope_cte(scope)
        placeholders = ",".join("?" for _ in assertion_ids)
        top = max(1, min(int(limit), 2000))
        rows = self.db.execute_query(
            cte +
            f""" SELECT TOP (?) q.store_id,q.generation_id,
                        la.assertion_id,la.assertion_kind,la.predicate,la.modality,
                        la.action_id,la.condition_text,la.exception_text,la.scope_text,
                        ae.evidence_role,ae.block_key,ae.quote,ae.quote_start,ae.quote_end,
                        ae.confidence AS evidence_confidence,
                        bm.block_id,bm.document_id,bm.document_version_id,bm.article_no,
                        bm.paragraph_no,bm.item_no,bm.heading_path,bm.ordinal,
                        dv.title,dv.category,dv.source_uri
                 FROM query_scope q
                 JOIN nexus.legal_assertion la ON la.generation_id=q.generation_id
                 JOIN nexus.assertion_evidence ae ON ae.assertion_id=la.assertion_id
                 JOIN nexus.block_manifest bm
                   ON bm.block_key=ae.block_key AND bm.generation_id=q.generation_id
                 JOIN nexus.document_version dv
                   ON dv.document_version_id=bm.document_version_id
                  AND dv.generation_id=q.generation_id
                 WHERE la.[state]='accepted' AND la.assertion_id IN ({placeholders})
                 ORDER BY CASE ae.evidence_role WHEN 'primary' THEN 0 ELSE 1 END,
                          dv.title,bm.ordinal,la.assertion_id""",
            (*scope_params, top, *assertion_ids),
        )
        return [
            {
                "evidence_kind": "assertion",
                "store_id": row["store_id"],
                "generation_id": row["generation_id"],
                "assertion_id": row["assertion_id"],
                "assertion_kind": row["assertion_kind"],
                "predicate": row["predicate"],
                "modality": row["modality"],
                "action_id": row.get("action_id"),
                "condition": row.get("condition_text"),
                "exception": row.get("exception_text"),
                "scope": row.get("scope_text"),
                "evidence_role": row["evidence_role"],
                "block_key": row["block_key"],
                "block_id": row["block_id"],
                "quote": row["quote"],
                "quote_start": int(row["quote_start"]),
                "quote_end": int(row["quote_end"]),
                "confidence": float(row.get("evidence_confidence") or 0),
                "document_id": row["document_id"],
                "document_version_id": row["document_version_id"],
                "title": row["title"],
                "category": row["category"],
                "source_uri": row.get("source_uri"),
                "article_no": row.get("article_no"),
                "paragraph_no": row.get("paragraph_no"),
                "item_no": row.get("item_no"),
                "heading_path": row.get("heading_path"),
                "ordinal": int(row["ordinal"]),
            }
            for row in rows
        ]

    @staticmethod
    def assertion_ids(items: list[dict]) -> list[str]:
        result: list[str] = []
        for item in items:
            for assertion_id in item.get("assertion_ids") or []:
                QueryRepository._append_unique(result, assertion_id)
            if item.get("assertion_id"):
                QueryRepository._append_unique(result, item["assertion_id"])
            for values in (item.get("supports") or {}).values():
                for assertion_id in values or []:
                    QueryRepository._append_unique(result, assertion_id)
        return result

    @staticmethod
    def _append_unique(values: list, value: Any) -> None:
        if value is not None and value not in values:
            values.append(value)

    @staticmethod
    def _parse_json(value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
