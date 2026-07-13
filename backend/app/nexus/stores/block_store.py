"""块存储门面：按 store_id 解析凭据 → AI Search 客户端 → 建索引/写块/检索。

供索引管线（写块）与查询（检索块）共用；对上层隐藏 AI Search 细节。
"""
from __future__ import annotations

from core.services import services
from services.credential import azure_keyvault_credential_provider
from utils.logger import get_logger

from ..models.block import Block
from ..models.store import SearchStore
from .ai_search_client import ai_search_client
from .store_registry import store_registry

_logger = get_logger("nexus.block_store")


class block_store:
    def __init__(self, config: dict = None):
        self._clients: dict[str, ai_search_client] = {}

    @property
    def _registry(self) -> store_registry:
        return services[store_registry]

    def _resolve_store(self, store_id: str) -> SearchStore:
        store = self._registry.get_store(store_id)
        if store is None:
            raise ValueError(f"store 不存在: {store_id!r}")
        return store

    def _client_for(self, store_id: str, dimensions: int = 1536) -> ai_search_client:
        client = self._clients.get(store_id)
        if client is not None:
            return client
        store = self._resolve_store(store_id)
        provider = services[azure_keyvault_credential_provider]
        cred = provider.load(store.credential_name)
        if cred is None:
            raise ValueError(f"store {store_id!r} 的凭据不可用: {store.credential_name!r}")
        conf = cred.to_config()   # {endpoint, key, index_name?, api_version?}
        index_name = store.index_name or conf.get("index_name")
        if not index_name:
            raise ValueError(f"store {store_id!r} 未指定 index_name（凭据与 store 均为空）")
        client = ai_search_client(
            endpoint=conf["endpoint"], key=conf["key"], index_name=index_name,
            dimensions=dimensions, api_version=conf.get("api_version"),
        )
        self._clients[store_id] = client
        return client

    # ---------------- 建索引 ----------------
    def ensure_index(self, store_id: str, dimensions: int) -> None:
        self._client_for(store_id, dimensions).ensure_index()

    # ---------------- 写块 ----------------
    def write_blocks(self, store_id: str, blocks: list[Block], dimensions: int = 1536) -> int:
        docs = [self._to_doc(b) for b in blocks]
        return self._client_for(store_id, dimensions).upsert(docs)

    def delete_document(self, store_id: str, doc_id: str) -> None:
        self._client_for(store_id).delete_by_doc(doc_id)

    def delete_docs(self, store_id: str, doc_ids: list[str]) -> int:
        """覆盖：只删本次这几篇文档的旧块（按 doc_id）。返回删除的文档数。"""
        client = self._client_for(store_id)
        n = 0
        for doc_id in doc_ids:
            if not doc_id:
                continue
            client.delete_by_doc(doc_id)
            n += 1
        return n

    # ---------------- 检索 ----------------
    def search(self, store_ids: list[str], query_text: str | None = None,
               query_vector: list[float] | None = None, top: int = 10,
               category: str | None = None, doc_ids: list[str] | None = None) -> list[Block]:
        """在给定 store 集合（collection 作用域）内 fan-out 检索并合并。"""
        filters = []
        if category:
            filters.append(f"category eq {_odata_string(category)}")
        if doc_ids:
            filters.append("(" + " or ".join(f"doc_id eq {_odata_string(x)}" for x in doc_ids) + ")")
        odata = " and ".join(filters) if filters else None
        scored: list[tuple[float, Block]] = []
        for sid in store_ids:
            try:
                rows = self._client_for(sid).search(query_text, query_vector, top, odata)
            except Exception as exc:
                _logger.warning(f"search store {sid} failed: {exc}")
                continue
            for r in rows:
                blk = self._to_block(r)
                blk.store_id = sid
                scored.append((float(r.get("score") or 0.0), blk))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [b for _, b in scored[:top]]

    def get_block(self, fullname: str, store_id: str) -> Block | None:
        r = self._client_for(store_id).get(fullname)
        if not r:
            return None
        blk = self._to_block(r)
        blk.store_id = store_id
        return blk

    # ---------------- 映射 ----------------
    @staticmethod
    def _to_doc(b: Block) -> dict:
        return {
            "id": ai_search_client.key_of(b.fullname),
            "fullname": b.fullname,
            "text": b.text,
            "doc_id": b.doc_id,
            "category": b.category,
            "title": b.title,
            "section": b.section,
            "ordinal": b.ordinal,
            "summary": b.summary,
            "keywords": b.keywords or [],
            "vector": b.vector,
        }

    @staticmethod
    def _to_block(r: dict) -> Block:
        return Block(
            fullname=r.get("fullname", ""),
            text=r.get("text", ""),
            doc_id=r.get("doc_id"),
            category=r.get("category"),
            title=r.get("title"),
            section=r.get("section"),
            ordinal=r.get("ordinal"),
            summary=r.get("summary"),
            keywords=r.get("keywords") or [],
            score=float(r.get("score")) if r.get("score") is not None else None,
        )


def _odata_string(value: str) -> str:
    """OData 单引号字面量；单引号以两个单引号转义。"""
    return "'" + value.replace("'", "''") + "'"
