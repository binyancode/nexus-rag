"""Generation-scoped repository for the Assertion-supported graph API."""
from __future__ import annotations

from nexus.domain import CollectionScope

from .base import SqlRepository


class GraphRepository(SqlRepository):
    def catalog(self, scope: CollectionScope, type_filter: str | None = None) -> list[dict]:
        nodes = self._nodes(scope)
        if type_filter:
            nodes = [
                node for node in nodes
                if node["type"] == type_filter or node["kind"] == type_filter.casefold()
            ]
        return nodes

    def graph(
        self,
        scope: CollectionScope,
        type_filter: str | None = None,
    ) -> tuple[list[dict], list[dict]]:
        nodes = self.catalog(scope, type_filter)
        allowed = {node["id"] for node in nodes}
        edges = self._edges(scope)
        if type_filter:
            edges = [edge for edge in edges if edge["source"] in allowed and edge["target"] in allowed]
        return nodes, edges

    def neighborhood(
        self,
        scope: CollectionScope,
        node_id: str,
        depth: int,
    ) -> tuple[list[dict], list[dict], list[str]]:
        catalog = {node["id"]: node for node in self._nodes(scope)}
        if node_id not in catalog:
            raise ValueError(f"node is not visible in the Collection scope: {node_id}")
        all_edges = self._edges(scope)
        seen = {node_id}
        frontier = {node_id}
        edge_map: dict[int, dict] = {}
        level = 0
        while frontier and (depth == 0 or level < depth):
            next_frontier: set[str] = set()
            for edge in all_edges:
                if edge["source"] not in frontier and edge["target"] not in frontier:
                    continue
                edge_map[edge["id"]] = edge
                other_ids = {edge["source"], edge["target"]} - seen
                next_frontier.update(other_ids)
            seen.update(next_frontier)
            frontier = next_frontier
            level += 1
        expandable: set[str] = set()
        if depth > 0 and frontier:
            for edge in all_edges:
                if edge["source"] in frontier and edge["target"] not in seen:
                    expandable.add(edge["source"])
                if edge["target"] in frontier and edge["source"] not in seen:
                    expandable.add(edge["target"])
        return (
            [catalog[node] for node in seen if node in catalog],
            list(edge_map.values()),
            sorted(expandable),
        )

    def node_detail(self, scope: CollectionScope, node_id: str) -> dict:
        node = next((item for item in self._nodes(scope) if item["id"] == node_id), None)
        if node is None:
            raise ValueError(f"node is not visible in the Collection scope: {node_id}")
        edges = [
            edge for edge in self._edges(scope)
            if edge["source"] == node_id or edge["target"] == node_id
        ]
        support: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for edge in edges:
            for item in self.edge_support(scope, edge["id"]):
                marker = (item["assertion_id"], item["block_key"])
                if marker not in seen:
                    seen.add(marker)
                    support.append(item)
        return {"node": node, "entity": node, "support": support, "evidence": support, "edges": edges}

    def edge_support(self, scope: CollectionScope, edge_id: int) -> list[dict]:
        cte, scope_params = self.scope_cte(scope)
        rows = self.db.execute_query(
            cte +
            """ SELECT q.store_id,q.generation_id,ge.edge_id,
                       la.assertion_id,la.assertion_kind,la.predicate,la.modality,
                       la.condition_text,la.exception_text,la.scope_text,
                       evidence.block_key,evidence.evidence_role,evidence.quote,
                       bm.block_id,bm.document_id,bm.article_no,bm.paragraph_no,
                       bm.item_no,bm.heading_path,bm.ordinal,dv.title,dv.category
                FROM query_scope q
                JOIN nexus.graph_edge ge
                  ON ge.generation_id=q.generation_id AND ge.edge_id=?
                JOIN nexus.graph_edge_support support ON support.edge_id=ge.edge_id
                JOIN nexus.legal_assertion la
                  ON la.assertion_id=support.assertion_id
                 AND la.generation_id=q.generation_id AND la.[state]='accepted'
                JOIN nexus.assertion_evidence evidence
                  ON evidence.assertion_id=la.assertion_id
                JOIN nexus.block_manifest bm
                  ON bm.block_key=evidence.block_key AND bm.generation_id=q.generation_id
                JOIN nexus.document_version dv
                  ON dv.document_version_id=bm.document_version_id
                 AND dv.generation_id=q.generation_id
                ORDER BY la.assertion_id,
                         CASE evidence.evidence_role WHEN 'primary' THEN 0 ELSE 1 END,
                         bm.ordinal""",
            (*scope_params, int(edge_id)),
        )
        return [
            {
                "edge_id": int(row["edge_id"]),
                "store_id": row["store_id"],
                "generation_id": row["generation_id"],
                "assertion_id": row["assertion_id"],
                "assertion_kind": row["assertion_kind"],
                "predicate": row["predicate"],
                "modality": row["modality"],
                "condition": row.get("condition_text"),
                "exception": row.get("exception_text"),
                "scope": row.get("scope_text"),
                "block_key": row["block_key"],
                "block_id": row["block_id"],
                "evidence_role": row["evidence_role"],
                "quote": row["quote"],
                "document_id": row["document_id"],
                "title": row["title"],
                "category": row["category"],
                "article_no": row.get("article_no"),
                "paragraph_no": row.get("paragraph_no"),
                "item_no": row.get("item_no"),
                "heading_path": row.get("heading_path"),
                "ordinal": int(row["ordinal"]),
            }
            for row in rows
        ]

    def block_location(self, scope: CollectionScope, block_key: str) -> dict | None:
        cte, params = self.scope_cte(scope)
        rows = self.db.execute_query(
            cte +
            """ SELECT TOP 1 q.store_id,q.generation_id,g.embedding_dimensions,
                       bm.block_key,bm.block_id,bm.document_id,bm.document_version_id
                FROM query_scope q
                JOIN nexus.index_generation g
                  ON g.store_id=q.store_id AND g.generation_id=q.generation_id
                JOIN nexus.block_manifest bm
                  ON bm.generation_id=q.generation_id AND bm.block_key=?""",
            (*params, block_key),
        )
        return rows[0] if rows else None

    def _nodes(self, scope: CollectionScope) -> list[dict]:
        edges = self._edge_rows(scope)
        degree: dict[str, int] = {}
        entity_ids: set[str] = set()
        action_ids: set[str] = set()
        for edge in edges:
            degree[edge["src_id"]] = degree.get(edge["src_id"], 0) + 1
            degree[edge["dst_id"]] = degree.get(edge["dst_id"], 0) + 1
            (entity_ids if edge["src_kind"] == "entity" else action_ids).add(edge["src_id"])
            (entity_ids if edge["dst_kind"] == "entity" else action_ids).add(edge["dst_id"])

        nodes: list[dict] = []
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            cte, scope_params = self.scope_cte(scope)
            rows = self.db.execute_query(
                cte + f""" SELECT DISTINCT e.entity_id,e.entity_type,e.canonical_name,e.lifecycle_state,
                           e.source,e.locked,a.alias
                    FROM query_scope q
                    JOIN nexus.graph_edge ge ON ge.generation_id=q.generation_id
                    JOIN nexus.entity e
                      ON e.entity_id IN (ge.src_id,ge.dst_id)
                     AND e.entity_id IN ({placeholders})
                    LEFT JOIN nexus.entity_alias a ON a.entity_id=e.entity_id
                      AND (a.generation_id IS NULL OR EXISTS (
                          SELECT 1 FROM query_scope aq WHERE aq.generation_id=a.generation_id
                      ))
                    WHERE e.entity_id IN ({placeholders})
                    ORDER BY e.entity_id,a.alias""",
                (*scope_params, *sorted(entity_ids), *sorted(entity_ids)),
            )
            grouped: dict[str, dict] = {}
            for row in rows:
                item = grouped.setdefault(row["entity_id"], {
                    "id": row["entity_id"], "kind": "entity", "type": row["entity_type"],
                    "name": row["canonical_name"], "status": row["lifecycle_state"],
                    "origin": row["source"], "locked": bool(row["locked"]),
                    "aliases": [], "degree": degree.get(row["entity_id"], 0),
                })
                if row.get("alias") and row["alias"] not in item["aliases"]:
                    item["aliases"].append(row["alias"])
            nodes.extend(grouped.values())
        if action_ids:
            placeholders = ",".join("?" for _ in action_ids)
            cte, scope_params = self.scope_cte(scope)
            rows = self.db.execute_query(
                cte + f""" SELECT DISTINCT action.action_id,action.canonical_text,
                           action.verb,action.lifecycle_state
                    FROM query_scope q
                    JOIN nexus.graph_edge ge ON ge.generation_id=q.generation_id
                    JOIN nexus.action action
                      ON action.action_id IN (ge.src_id,ge.dst_id)
                     AND action.action_id IN ({placeholders})
                    ORDER BY action.canonical_text,action.action_id""",
                (*scope_params, *sorted(action_ids)),
            )
            nodes.extend({
                "id": row["action_id"], "kind": "action", "type": "Action",
                "name": row["canonical_text"], "status": row["lifecycle_state"],
                "origin": "derived", "locked": False, "aliases": [row["verb"]],
                "degree": degree.get(row["action_id"], 0),
            } for row in rows)
        return sorted(nodes, key=lambda node: (node["kind"], node["type"], node["name"], node["id"]))

    def _edges(self, scope: CollectionScope) -> list[dict]:
        grouped: dict[int, dict] = {}
        for row in self._edge_rows(scope):
            edge = grouped.setdefault(int(row["edge_id"]), {
                "id": int(row["edge_id"]),
                "source": row["src_id"], "source_kind": row["src_kind"],
                "target": row["dst_id"], "target_kind": row["dst_kind"],
                "type": row["edge_type"], "weight": float(row["weight"]),
                "origin": row["source"], "locked": bool(row["locked"]),
                "assertion_ids": [],
            })
            if row.get("assertion_id") and row["assertion_id"] not in edge["assertion_ids"]:
                edge["assertion_ids"].append(row["assertion_id"])
        return list(grouped.values())

    def _edge_rows(self, scope: CollectionScope) -> list[dict]:
        cte, params = self.scope_cte(scope)
        return self.db.execute_query(
            cte +
            """ SELECT ge.edge_id,ge.src_kind,ge.src_id,ge.edge_type,
                       ge.dst_kind,ge.dst_id,ge.weight,ge.source,ge.locked,
                       support.assertion_id
                FROM query_scope q
                JOIN nexus.graph_edge ge ON ge.generation_id=q.generation_id
                JOIN nexus.graph_edge_support support ON support.edge_id=ge.edge_id
                JOIN nexus.legal_assertion la
                  ON la.assertion_id=support.assertion_id
                 AND la.generation_id=q.generation_id AND la.[state]='accepted'
                ORDER BY ge.edge_id,support.assertion_id""",
            params,
        )
