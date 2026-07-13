"""Final Store/Collection repository and active-generation scope freezer."""
from __future__ import annotations

from collections.abc import Iterable

from nexus.domain import Collection, CollectionScope, SearchStore

from .base import SqlRepository


class StoreCollectionRepository(SqlRepository):
    """Owns Store/Collection configuration and user-visible scope resolution."""

    _STORE_COLUMNS = (
        "store_id, name, credential_name, index_name, kind, "
        "active_generation_id, is_default"
    )

    # ------------------------------------------------------------------
    # Stores
    # ------------------------------------------------------------------
    def list_stores(self) -> list[SearchStore]:
        rows = self.db.execute_query(
            f"SELECT {self._STORE_COLUMNS} FROM nexus.search_store ORDER BY name, store_id"
        )
        return [self._store(row) for row in rows]

    def get_store(self, store_id: str) -> SearchStore | None:
        rows = self.db.execute_query(
            f"SELECT TOP 1 {self._STORE_COLUMNS} FROM nexus.search_store WHERE store_id=?",
            (store_id,),
        )
        return self._store(rows[0]) if rows else None

    def default_store(self) -> SearchStore | None:
        rows = self.db.execute_query(
            f"SELECT TOP 1 {self._STORE_COLUMNS} FROM nexus.search_store "
            "WHERE is_default=1 ORDER BY name, store_id"
        )
        return self._store(rows[0]) if rows else None

    def upsert_store(self, store: SearchStore) -> None:
        self.db.execute_non_query(
            """BEGIN TRY
                   BEGIN TRANSACTION;
                   IF ?=1
                       UPDATE nexus.search_store SET is_default=0
                       WHERE is_default=1 AND store_id<>?;

                   MERGE nexus.search_store AS target
                   USING (SELECT ? AS store_id) AS source
                     ON target.store_id=source.store_id
                   WHEN MATCHED THEN UPDATE SET
                       name=?, credential_name=?, index_name=?, kind=?, is_default=?,
                       updated_at=SYSUTCDATETIME()
                   WHEN NOT MATCHED THEN INSERT
                       (store_id, name, credential_name, index_name, kind, is_default)
                       VALUES (?, ?, ?, ?, ?, ?);
                   COMMIT TRANSACTION;
               END TRY
               BEGIN CATCH
                   IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
                   THROW;
               END CATCH""",
            (
                int(store.is_default), store.store_id,
                store.store_id,
                store.name, store.credential_name, store.index_name, store.kind,
                int(store.is_default),
                store.store_id, store.name, store.credential_name, store.index_name,
                store.kind, int(store.is_default),
            ),
        )

    # ------------------------------------------------------------------
    # Collections and visibility
    # ------------------------------------------------------------------
    def list_collections(self) -> list[Collection]:
        rows = self.db.execute_query(
            "SELECT collection_id,name,description,is_public FROM nexus.collection ORDER BY name,collection_id"
        )
        return [self._collection(row, self.allowed_stores(row["collection_id"])) for row in rows]

    def list_visible_collections(
        self,
        as_user: str | None,
        roles: Iterable[str] = (),
    ) -> list[Collection]:
        role_values = tuple(dict.fromkeys(str(role) for role in roles if str(role).strip()))
        role_clause = ""
        params: list[object] = [as_user or "", as_user or ""]
        if role_values:
            placeholders = ",".join("?" for _ in role_values)
            role_clause = (
                " OR EXISTS (SELECT 1 FROM nexus.collection_access ar "
                "WHERE ar.collection_id=c.collection_id AND ar.principal_type='role' "
                f"AND ar.principal_id IN ({placeholders}))"
            )
            params.extend(role_values)
        rows = self.db.execute_query(
            """SELECT c.collection_id,c.name,c.description,c.is_public,
                      CAST(CASE WHEN EXISTS (
                          SELECT 1 FROM nexus.collection_access d
                          WHERE d.collection_id=c.collection_id AND d.principal_type='user'
                            AND d.principal_id=? AND d.is_default=1
                      ) THEN 1 ELSE 0 END AS bit) AS is_default
               FROM nexus.collection c
               WHERE c.is_public=1
                  OR EXISTS (
                      SELECT 1 FROM nexus.collection_access a
                      WHERE a.collection_id=c.collection_id AND a.principal_type='user'
                        AND a.principal_id=?
                  )""" + role_clause +
            " ORDER BY is_default DESC,c.name,c.collection_id",
            tuple(params),
        )
        return [
            self._collection(
                row,
                self.allowed_stores(row["collection_id"]),
                is_default=bool(row.get("is_default")),
            )
            for row in rows
        ]

    def get_collection(self, collection_id: str) -> Collection | None:
        rows = self.db.execute_query(
            "SELECT TOP 1 collection_id,name,description,is_public "
            "FROM nexus.collection WHERE collection_id=?",
            (collection_id,),
        )
        return self._collection(rows[0], self.allowed_stores(collection_id)) if rows else None

    def upsert_collection(self, collection: Collection) -> None:
        store_ids = list(dict.fromkeys(collection.stores))
        if not store_ids:
            raise ValueError("Collection must contain at least one Store")
        values = ",".join("(?)" for _ in store_ids)
        self.db.execute_non_query(
            f"""BEGIN TRY
                    BEGIN TRANSACTION;
                    IF EXISTS (
                        SELECT 1 FROM (VALUES {values}) requested(store_id)
                        LEFT JOIN nexus.search_store s ON s.store_id=requested.store_id
                        WHERE s.store_id IS NULL
                    ) THROW 51002, 'Collection contains an unknown Store', 1;

                    MERGE nexus.collection AS target
                    USING (SELECT ? AS collection_id) AS source
                      ON target.collection_id=source.collection_id
                    WHEN MATCHED THEN UPDATE SET
                        name=?, description=?, is_public=?, updated_at=SYSUTCDATETIME()
                    WHEN NOT MATCHED THEN INSERT
                        (collection_id,name,description,is_public) VALUES (?,?,?,?);

                    DELETE FROM nexus.collection_store WHERE collection_id=?;
                    INSERT INTO nexus.collection_store(collection_id,store_id)
                    SELECT ?,requested.store_id FROM (VALUES {values}) requested(store_id);
                    COMMIT TRANSACTION;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
                    THROW;
                END CATCH""",
            (
                *store_ids,
                collection.collection_id,
                collection.name, collection.description, int(collection.is_public),
                collection.collection_id, collection.name, collection.description,
                int(collection.is_public),
                collection.collection_id, collection.collection_id, *store_ids,
            ),
        )

    def allowed_stores(self, collection_id: str) -> list[str]:
        if not (collection_id or "").strip():
            raise ValueError("collection_id is required; an unscoped Store list is not allowed")
        rows = self.db.execute_query(
            "SELECT store_id FROM nexus.collection_store WHERE collection_id=? ORDER BY store_id",
            (collection_id,),
        )
        return [row["store_id"] for row in rows]

    def freeze_scope(
        self,
        collection: Collection,
        selected_by: str,
    ) -> CollectionScope:
        """Freeze exactly the currently active Generation of every Collection Store."""
        allowed = tuple(dict.fromkeys(collection.stores))
        if not allowed:
            raise ValueError(f"Collection has no Stores: {collection.collection_id}")
        placeholders = ",".join("?" for _ in allowed)
        rows = self.db.execute_query(
            f"""SELECT s.store_id,s.active_generation_id
                FROM nexus.search_store s
                JOIN nexus.index_generation g
                  ON g.generation_id=s.active_generation_id
                 AND g.store_id=s.store_id AND g.[state]='active'
                WHERE s.store_id IN ({placeholders})""",
            allowed,
        )
        generation_scope = {
            row["store_id"]: row["active_generation_id"]
            for row in rows if row.get("active_generation_id")
        }
        missing = sorted(set(allowed) - set(generation_scope))
        if missing:
            raise ValueError(
                "Collection contains Stores without an active Generation: " + ", ".join(missing)
            )
        return CollectionScope(
            collection_id=collection.collection_id,
            name=collection.name,
            selected_by=selected_by,
            allowed_stores=allowed,
            generation_scope=generation_scope,
        )

    @staticmethod
    def _store(row: dict) -> SearchStore:
        return SearchStore(
            store_id=row["store_id"],
            name=row["name"],
            credential_name=row["credential_name"],
            index_name=row.get("index_name"),
            kind=row.get("kind") or "block",
            active_generation_id=row.get("active_generation_id"),
            is_default=bool(row.get("is_default")),
        )

    @staticmethod
    def _collection(row: dict, stores: list[str], is_default: bool = False) -> Collection:
        return Collection(
            collection_id=row["collection_id"],
            name=row["name"],
            description=row.get("description"),
            is_public=bool(row.get("is_public")),
            stores=stores,
            is_default=is_default,
        )
