"""边存储：结构边（实体↔实体，§1.4）+ 出处边（实体↔块，§1.3）。"""
from __future__ import annotations

from core.services import services
from services.sql_db import sql_db

from ..models.edge import Edge
from ..models.evidence import Evidence


class edge_store:
    def __init__(self, config: dict = None):
        pass

    @property
    def _db(self) -> sql_db:
        return services[sql_db]

    # ---------------- 结构边 ----------------
    def upsert_edge(self, edge: Edge) -> None:
        self._db.execute_non_query(
            """MERGE nexus.entity_edge AS t
               USING (SELECT ? AS src, ? AS type, ? AS dst) AS s
                   ON t.src_entity_id = s.src AND t.type = s.type AND t.dst_entity_id = s.dst
               WHEN MATCHED THEN UPDATE SET weight = ?, evidence = ?, source = ?, locked = ?
               WHEN NOT MATCHED THEN INSERT
                   (src_entity_id, type, dst_entity_id, weight, evidence, source, locked)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
            (
                edge.src, edge.type, edge.dst,
                edge.weight, edge.evidence, edge.source, int(edge.locked),
                edge.src, edge.type, edge.dst, edge.weight, edge.evidence, edge.source, int(edge.locked),
            ),
        )

    def list_edges(self, entity_ids: list[str] | None = None, types: list[str] | None = None) -> list[Edge]:
        """列出边。entity_ids 非空时只返回两端都在集合内的边（导出子图用）。"""
        where = []
        params: list = []
        if entity_ids is not None:
            if not entity_ids:
                return []
            ph = ",".join("?" * len(entity_ids))
            where.append(f"src_entity_id IN ({ph}) AND dst_entity_id IN ({ph})")
            params.extend(entity_ids)
            params.extend(entity_ids)
        if types:
            ph = ",".join("?" * len(types))
            where.append(f"type IN ({ph})")
            params.extend(types)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._db.execute_query(
            "SELECT edge_id, src_entity_id, type, dst_entity_id, weight, evidence, source, locked "
            f"FROM nexus.entity_edge{clause}",
            tuple(params) if params else None,
        )
        return [self._to_edge(r) for r in rows]

    # ---------------- 出处边 ----------------
    def add_evidence(self, ev: Evidence) -> None:
        self._db.execute_non_query(
            """MERGE nexus.evidence AS t
               USING (SELECT ? AS entity_id, ? AS fullname) AS s
                   ON t.entity_id = s.entity_id AND t.fullname = s.fullname
               WHEN MATCHED THEN UPDATE SET store_id = ?, weight = ?, source = ?, locked = ?
               WHEN NOT MATCHED THEN INSERT
                   (entity_id, fullname, store_id, weight, source, locked)
                   VALUES (?, ?, ?, ?, ?, ?);""",
            (
                ev.entity_id, ev.fullname,
                ev.store_id, ev.weight, ev.source, int(ev.locked),
                ev.entity_id, ev.fullname, ev.store_id, ev.weight, ev.source, int(ev.locked),
            ),
        )

    def list_evidence(self, entity_id: str) -> list[Evidence]:
        rows = self._db.execute_query(
            "SELECT evidence_id, entity_id, fullname, store_id, weight, source, locked "
            "FROM nexus.evidence WHERE entity_id = ? ORDER BY weight DESC",
            (entity_id,),
        )
        return [self._to_evidence(r) for r in rows]

    def delete_evidence_by_docs(self, prefixes: list[str]) -> int:
        """覆盖：只删本次这几篇文档的出处边（按 fullname 前缀 = 类别.文档.）。
        共享实体/结构边不动，重建时走 upsert 合并。prefixes 里的 _ % [ 会被转义避免误删。"""
        total = 0
        for p in prefixes:
            if not p:
                continue
            pat = (p.replace("\\", "\\\\").replace("%", "\\%")
                    .replace("_", "\\_").replace("[", "\\[")) + "%"
            total += self._db.execute_non_query(
                "DELETE FROM nexus.evidence WHERE fullname LIKE ? ESCAPE '\\'", (pat,)
            )
        return total

    # ---------------- helpers ----------------
    @staticmethod
    def _to_edge(r: dict) -> Edge:
        return Edge(
            edge_id=r.get("edge_id"), src=r["src_entity_id"], type=r["type"], dst=r["dst_entity_id"],
            weight=r.get("weight") or 1.0, evidence=r.get("evidence"),
            source=r.get("source") or "llm", locked=bool(r.get("locked")),
        )

    @staticmethod
    def _to_evidence(r: dict) -> Evidence:
        return Evidence(
            evidence_id=r.get("evidence_id"), entity_id=r["entity_id"], fullname=r["fullname"],
            store_id=r["store_id"], weight=r.get("weight") or 1.0,
            source=r.get("source") or "llm", locked=bool(r.get("locked")),
        )
