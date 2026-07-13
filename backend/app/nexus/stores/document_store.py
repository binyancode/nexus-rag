"""文档注册：路由（文档→store）+ 增量（content_hash）（§1.5/§1.6）。"""
from __future__ import annotations

from core.services import services
from services.sql_db import sql_db

from ..models.document import Document


class document_store:
    def __init__(self, config: dict = None):
        pass

    @property
    def _db(self) -> sql_db:
        return services[sql_db]

    def get(self, doc_id: str) -> Document | None:
        rows = self._db.execute_query(
            "SELECT TOP 1 doc_id, title, category, store_id, content_hash, source_uri, block_count "
            "FROM nexus.document WHERE doc_id = ?",
            (doc_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return Document(
            doc_id=r["doc_id"], title=r.get("title"), category=r.get("category"),
            store_id=r["store_id"], content_hash=r.get("content_hash"),
            source_uri=r.get("source_uri"), block_count=r.get("block_count") or 0,
        )

    def unchanged(self, doc_id: str, content_hash: str) -> bool:
        """增量判断：文档已存在且内容 hash 未变 → 可跳过重抽。"""
        doc = self.get(doc_id)
        return bool(doc and doc.content_hash and doc.content_hash == content_hash)

    def list_categories(self, store_ids: list[str]) -> list[str]:
        """列出当前 Collection 的 Store 中真实存在的文档类别，供查询优化器绑定过滤值。"""
        if not store_ids:
            return []
        ph = ",".join("?" * len(store_ids))
        rows = self._db.execute_query(
            f"SELECT DISTINCT category FROM nexus.document WHERE store_id IN ({ph}) AND category IS NOT NULL ORDER BY category",
            tuple(store_ids),
        )
        return [r["category"] for r in rows]

    def list_documents(self, store_ids: list[str]) -> list[Document]:
        """列出当前 Collection 可见 Store 中的真实文档目录，供编译器/优化器绑定 doc_id。"""
        if not store_ids:
            return []
        ph = ",".join("?" * len(store_ids))
        rows = self._db.execute_query(
            "SELECT doc_id,title,category,store_id,content_hash,source_uri,block_count "
            f"FROM nexus.document WHERE store_id IN ({ph}) ORDER BY title,doc_id",
            tuple(store_ids),
        )
        return [Document(
            doc_id=r["doc_id"], title=r.get("title"), category=r.get("category"),
            store_id=r["store_id"], content_hash=r.get("content_hash"),
            source_uri=r.get("source_uri"), block_count=r.get("block_count") or 0,
        ) for r in rows]

    def upsert(self, doc: Document) -> None:
        self._db.execute_non_query(
            """MERGE nexus.document AS t
               USING (SELECT ? AS doc_id) AS s ON t.doc_id = s.doc_id
               WHEN MATCHED THEN UPDATE SET
                   title = ?, category = ?, store_id = ?, content_hash = ?,
                   source_uri = ?, block_count = ?, updated_at = SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (doc_id, title, category, store_id, content_hash, source_uri, block_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
            (
                doc.doc_id,
                doc.title, doc.category, doc.store_id, doc.content_hash, doc.source_uri, doc.block_count,
                doc.doc_id, doc.title, doc.category, doc.store_id, doc.content_hash, doc.source_uri, doc.block_count,
            ),
        )
