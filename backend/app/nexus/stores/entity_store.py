"""实体存储：实体节点 + 别名（§1.2）。"""
from __future__ import annotations

import json

from core.services import services
from services.sql_db import sql_db

from ..models.entity import Entity


class entity_store:
    def __init__(self, config: dict = None):
        pass

    @property
    def _db(self) -> sql_db:
        return services[sql_db]

    # ---------------- 读 ----------------
    def get(self, entity_id: str) -> Entity | None:
        rows = self._db.execute_query(
            "SELECT TOP 1 entity_id, type, name, status, attrs, source, locked "
            "FROM nexus.entity WHERE entity_id = ?",
            (entity_id,),
        )
        if not rows:
            return None
        ent = self._to_entity(rows[0])
        ent.aliases = self._aliases_of([entity_id]).get(entity_id, [])
        return ent

    def find_by_name(self, name: str) -> list[Entity]:
        """按规范名或别名精确匹配（归一去重用）。"""
        rows = self._db.execute_query(
            """SELECT DISTINCT e.entity_id, e.type, e.name, e.status, e.attrs, e.source, e.locked
               FROM nexus.entity e
               LEFT JOIN nexus.entity_alias a ON a.entity_id = e.entity_id
               WHERE e.name = ? OR a.alias = ?""",
            (name, name),
        )
        return self._hydrate(rows)

    def list(self, type_: str | None = None, store_ids: list[str] | None = None) -> list[Entity]:
        """列出实体；可按类型过滤；store_ids 非空时只返回在这些 store 有出处的实体（collection 作用域）。"""
        where = []
        params: list = []
        if type_:
            where.append("e.type = ?")
            params.append(type_)
        if store_ids is not None:
            if not store_ids:
                return []
            ph = ",".join("?" * len(store_ids))
            where.append(
                f"EXISTS (SELECT 1 FROM nexus.evidence ev "
                f"WHERE ev.entity_id = e.entity_id AND ev.store_id IN ({ph}))"
            )
            params.extend(store_ids)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._db.execute_query(
            "SELECT e.entity_id, e.type, e.name, e.status, e.attrs, e.source, e.locked "
            f"FROM nexus.entity e{clause} ORDER BY e.type, e.name",
            tuple(params) if params else None,
        )
        return self._hydrate(rows)

    # ---------------- 写 ----------------
    def upsert(self, entity: Entity) -> None:
        attrs_json = json.dumps(entity.attrs, ensure_ascii=False) if entity.attrs is not None else None
        self._db.execute_non_query(
            """MERGE nexus.entity AS t
               USING (SELECT ? AS entity_id) AS s ON t.entity_id = s.entity_id
               WHEN MATCHED THEN UPDATE SET
                   type = ?, name = ?, status = ?, attrs = ?, source = ?, locked = ?,
                   updated_at = SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (entity_id, type, name, status, attrs, source, locked)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
            (
                entity.entity_id,
                entity.type, entity.name, entity.status, attrs_json, entity.source, int(entity.locked),
                entity.entity_id, entity.type, entity.name, entity.status, attrs_json, entity.source, int(entity.locked),
            ),
        )
        if entity.aliases:
            self.add_aliases(entity.entity_id, entity.aliases)

    def add_aliases(self, entity_id: str, aliases: list[str]) -> None:
        for alias in dict.fromkeys(a for a in aliases if a):
            self._db.execute_non_query(
                """INSERT INTO nexus.entity_alias (entity_id, alias)
                   SELECT ?, ?
                   WHERE NOT EXISTS (
                       SELECT 1 FROM nexus.entity_alias WHERE entity_id = ? AND alias = ?)""",
                (entity_id, alias, entity_id, alias),
            )

    # ---------------- helpers ----------------
    def _hydrate(self, rows: list[dict]) -> list[Entity]:
        ents = [self._to_entity(r) for r in rows]
        alias_map = self._aliases_of([e.entity_id for e in ents])
        for e in ents:
            e.aliases = alias_map.get(e.entity_id, [])
        return ents

    def _aliases_of(self, ids: list[str]) -> dict[str, list[str]]:
        if not ids:
            return {}
        ph = ",".join("?" * len(ids))
        rows = self._db.execute_query(
            f"SELECT entity_id, alias FROM nexus.entity_alias WHERE entity_id IN ({ph})",
            tuple(ids),
        )
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["entity_id"], []).append(r["alias"])
        return out

    @staticmethod
    def _to_entity(r: dict) -> Entity:
        attrs = None
        raw = r.get("attrs")
        if raw:
            try:
                attrs = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                attrs = None
        return Entity(
            entity_id=r["entity_id"], type=r["type"], name=r["name"], status=r.get("status"),
            attrs=attrs, source=r.get("source") or "llm", locked=bool(r.get("locked")),
        )
