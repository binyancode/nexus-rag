"""Store / Collection 注册与作用域解析（§1.6）。

Store = 一条 azure_ai_search 凭据（块的物理落点）。
Collection = 一组 store 的查询期视图（多对多，纯过滤器，不写进任何 id）。
"""
from __future__ import annotations

from core.services import services
from services.sql_db import sql_db
from utils.logger import get_logger

from ..models.store import Collection, SearchStore

_logger = get_logger("nexus.store_registry")


class store_registry:
    def __init__(self, config: dict = None):
        conf = config or {}
        self._schema = conf.get("schema", "nexus")

    @property
    def _db(self) -> sql_db:
        return services[sql_db]

    # ---------------- Store ----------------
    def list_stores(self) -> list[SearchStore]:
        rows = self._db.execute_query(
            "SELECT store_id, name, credential_name, index_name, kind, is_default "
            "FROM nexus.search_store ORDER BY name"
        )
        return [self._to_store(r) for r in rows]

    def get_store(self, store_id: str) -> SearchStore | None:
        rows = self._db.execute_query(
            "SELECT TOP 1 store_id, name, credential_name, index_name, kind, is_default "
            "FROM nexus.search_store WHERE store_id = ?",
            (store_id,),
        )
        return self._to_store(rows[0]) if rows else None

    def default_store(self) -> SearchStore | None:
        rows = self._db.execute_query(
            "SELECT TOP 1 store_id, name, credential_name, index_name, kind, is_default "
            "FROM nexus.search_store WHERE is_default = 1 ORDER BY name"
        )
        return self._to_store(rows[0]) if rows else None

    def upsert_store(self, store: SearchStore) -> None:
        self._db.execute_non_query(
            """MERGE nexus.search_store AS t
               USING (SELECT ? AS store_id) AS s ON t.store_id = s.store_id
               WHEN MATCHED THEN UPDATE SET
                   name = ?, credential_name = ?, index_name = ?, kind = ?,
                   is_default = ?, updated_at = SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (store_id, name, credential_name, index_name, kind, is_default)
                   VALUES (?, ?, ?, ?, ?, ?);""",
            (
                store.store_id,
                store.name, store.credential_name, store.index_name, store.kind, int(store.is_default),
                store.store_id, store.name, store.credential_name, store.index_name, store.kind, int(store.is_default),
            ),
        )

    # ---------------- Collection ----------------
    def list_collections(self) -> list[Collection]:
        rows = self._db.execute_query(
            "SELECT collection_id, name, description, is_public FROM nexus.collection ORDER BY name"
        )
        cols = [Collection(collection_id=r["collection_id"], name=r["name"],
                           description=r.get("description"), is_public=bool(r.get("is_public"))) for r in rows]
        for c in cols:
            c.stores = self.allowed_stores(c.collection_id)
        return cols

    def list_visible_collections(self, as_user: str | None) -> list[Collection]:
        """当前用户可见 Collection：公开项 + 显式 user 授权；同时标记该用户默认项。"""
        rows = self._db.execute_query(
            """SELECT DISTINCT c.collection_id, c.name, c.description, c.is_public,
                      CAST(CASE WHEN d.collection_id IS NULL THEN 0 ELSE 1 END AS bit) AS is_default
               FROM nexus.collection c
               LEFT JOIN nexus.collection_access a
                 ON a.collection_id=c.collection_id AND a.principal_type='user' AND a.principal_id=?
               LEFT JOIN nexus.collection_access d
                 ON d.collection_id=c.collection_id AND d.principal_type='user'
                AND d.principal_id=? AND d.is_default=1
               WHERE c.is_public=1 OR a.collection_id IS NOT NULL
               ORDER BY is_default DESC, c.name""",
            (as_user or "", as_user or ""),
        )
        cols = [Collection(
            collection_id=r["collection_id"], name=r["name"], description=r.get("description"),
            is_public=bool(r.get("is_public")), is_default=bool(r.get("is_default")),
        ) for r in rows]
        for c in cols:
            c.stores = self.allowed_stores(c.collection_id)
        return cols

    def get_collection(self, collection_id: str) -> Collection | None:
        rows = self._db.execute_query(
            "SELECT TOP 1 collection_id, name, description, is_public FROM nexus.collection WHERE collection_id = ?",
            (collection_id,),
        )
        if not rows:
            return None
        r = rows[0]
        c = Collection(collection_id=r["collection_id"], name=r["name"],
                   description=r.get("description"), is_public=bool(r.get("is_public")))
        c.stores = self.allowed_stores(collection_id)
        return c

    def upsert_collection(self, collection: Collection) -> None:
        self._db.execute_non_query(
            """MERGE nexus.collection AS t
               USING (SELECT ? AS collection_id) AS s ON t.collection_id = s.collection_id
               WHEN MATCHED THEN UPDATE SET name = ?, description = ?, is_public=?, updated_at = SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT (collection_id, name, description, is_public) VALUES (?, ?, ?, ?);""",
            (
                collection.collection_id,
                collection.name, collection.description, int(collection.is_public),
                collection.collection_id, collection.name, collection.description, int(collection.is_public),
            ),
        )
        if collection.stores is not None:
            self.set_collection_stores(collection.collection_id, collection.stores)

    def set_collection_stores(self, collection_id: str, store_ids: list[str]) -> None:
        self._db.execute_non_query(
            "DELETE FROM nexus.collection_store WHERE collection_id = ?", (collection_id,)
        )
        for sid in dict.fromkeys(store_ids):   # 去重保序
            self._db.execute_non_query(
                "INSERT INTO nexus.collection_store (collection_id, store_id) VALUES (?, ?)",
                (collection_id, sid),
            )

    def allowed_stores(self, collection_id: str | None) -> list[str]:
        """解析查询作用域：collection → 其成员 store_id 列表。

        collection_id 为空 → 返回所有 store（全局作用域）。
        """
        if not collection_id:
            return [s.store_id for s in self.list_stores()]
        rows = self._db.execute_query(
            "SELECT store_id FROM nexus.collection_store WHERE collection_id = ?",
            (collection_id,),
        )
        return [r["store_id"] for r in rows]

    # ---------------- helpers ----------------
    @staticmethod
    def _to_store(r: dict) -> SearchStore:
        return SearchStore(
            store_id=r["store_id"],
            name=r["name"],
            credential_name=r["credential_name"],
            index_name=r.get("index_name"),
            kind=r.get("kind") or "block",
            is_default=bool(r.get("is_default")),
        )
