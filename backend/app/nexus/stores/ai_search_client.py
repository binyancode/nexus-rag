"""Azure AI Search 客户端：封装单个 block store 的建索引 / 写块 / 检索。

块本体（原文 + 向量 + 元数据）存这里；SQL 只存 fullname 指针（§1.6）。
文档 key = base64url(fullname)（AI Search key 不允许中文/点号），fullname 另存可过滤字段。
"""
from __future__ import annotations

import base64

from utils.logger import get_logger

_logger = get_logger("nexus.ai_search")

_DEFAULT_API_VERSION = "2024-07-01"
_ZH_ANALYZER = "zh-Hans.microsoft"
_VECTOR_PROFILE = "nexus-hnsw"
_VECTOR_ALGO = "nexus-hnsw-algo"


class ai_search_client:
    def __init__(self, endpoint: str, key: str, index_name: str,
                 dimensions: int = 1536, api_version: str | None = None):
        self._endpoint = endpoint
        self._key = key
        self._index_name = index_name
        self._dimensions = dimensions
        self._api_version = api_version or _DEFAULT_API_VERSION
        self._search = None
        self._index = None

    # ---------------- key 编码 ----------------
    @staticmethod
    def key_of(fullname: str) -> str:
        return base64.urlsafe_b64encode(fullname.encode("utf-8")).decode("ascii").rstrip("=")

    # ---------------- 客户端 ----------------
    def _credential(self):
        from azure.core.credentials import AzureKeyCredential
        return AzureKeyCredential(self._key)

    def _search_client(self):
        if self._search is None:
            from azure.search.documents import SearchClient
            self._search = SearchClient(self._endpoint, self._index_name, self._credential(),
                                        api_version=self._api_version)
        return self._search

    def _index_client(self):
        if self._index is None:
            from azure.search.documents.indexes import SearchIndexClient
            self._index = SearchIndexClient(self._endpoint, self._credential(),
                                            api_version=self._api_version)
        return self._index

    # ---------------- 建索引 ----------------
    def ensure_index(self) -> None:
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration, SearchableField, SearchField,
            SearchFieldDataType, SearchIndex, SimpleField, VectorSearch,
            VectorSearchProfile,
        )
        idx_client = self._index_client()
        try:
            existing = {i for i in idx_client.list_index_names()}
        except Exception:
            existing = set()
        if self._index_name in existing:
            return

        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="fullname", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="text", type=SearchFieldDataType.String, analyzer_name=_ZH_ANALYZER),
            SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchableField(name="title", type=SearchFieldDataType.String, filterable=True, analyzer_name=_ZH_ANALYZER),
            SearchableField(name="section", type=SearchFieldDataType.String, analyzer_name=_ZH_ANALYZER),
            SimpleField(name="ordinal", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SearchableField(name="summary", type=SearchFieldDataType.String, analyzer_name=_ZH_ANALYZER),
            SearchField(name="keywords", type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                        searchable=True, filterable=True),
            SearchField(
                name="vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self._dimensions,
                vector_search_profile_name=_VECTOR_PROFILE,
            ),
        ]
        vector_search = VectorSearch(
            profiles=[VectorSearchProfile(name=_VECTOR_PROFILE, algorithm_configuration_name=_VECTOR_ALGO)],
            algorithms=[HnswAlgorithmConfiguration(name=_VECTOR_ALGO)],
        )
        idx_client.create_or_update_index(
            SearchIndex(name=self._index_name, fields=fields, vector_search=vector_search)
        )
        _logger.info(f"created AI Search index: {self._index_name} (dims={self._dimensions})")

    # ---------------- 写块 ----------------
    def upsert(self, docs: list[dict]) -> int:
        """docs: 已含 id/fullname/text/vector 等字段。分批 merge_or_upload。"""
        if not docs:
            return 0
        client = self._search_client()
        total = 0
        for i in range(0, len(docs), 1000):
            batch = docs[i:i + 1000]
            client.merge_or_upload_documents(documents=batch)
            total += len(batch)
        return total

    def delete_by_doc(self, doc_id: str) -> None:
        """删除某文档的全部块（重建/增量替换用）。"""
        client = self._search_client()
        keys = [d["id"] for d in client.search(search_text="*", filter=f"doc_id eq '{doc_id}'",
                                                select=["id"], top=100000)]
        if keys:
            client.delete_documents(documents=[{"id": k} for k in keys])

    # ---------------- 检索 ----------------
    def search(self, query_text: str | None = None, query_vector: list[float] | None = None,
               top: int = 10, odata_filter: str | None = None) -> list[dict]:
        client = self._search_client()
        vector_queries = None
        if query_vector:
            from azure.search.documents.models import VectorizedQuery
            vector_queries = [VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="vector")]
        results = client.search(
            search_text=query_text or None,
            vector_queries=vector_queries,
            filter=odata_filter,
            top=top,
            select=["fullname", "text", "doc_id", "category", "title", "section", "ordinal", "summary", "keywords"],
        )
        out = []
        for r in results:
            d = dict(r)
            d["score"] = r.get("@search.score")
            out.append(d)
        return out

    def get(self, fullname: str) -> dict | None:
        client = self._search_client()
        try:
            return dict(client.get_document(key=self.key_of(fullname)))
        except Exception:
            return None
