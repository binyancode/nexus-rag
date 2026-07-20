"""Generation-aware Azure AI Search block adapter."""
from __future__ import annotations

import base64
import time

from core.services import services
from nexus.domain import Block
from services.credential import azure_keyvault_credential_provider

from .base import SqlRepository

_DEFAULT_API_VERSION = "2024-07-01"
_ZH_ANALYZER = "zh-Hans.microsoft"
_VECTOR_PROFILE = "nexus-hnsw"
_VECTOR_ALGORITHM = "nexus-hnsw-algo"


def _odata(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class GenerationSearchAdapter(SqlRepository):
    """Writes and reads only documents carrying an explicit generation identity."""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._clients: dict[tuple[str, int], object] = {}
        self._index_clients: dict[str, object] = {}

    @staticmethod
    def key_of(block_key: str) -> str:
        return base64.urlsafe_b64encode(block_key.encode("utf-8")).decode("ascii").rstrip("=")

    def create_or_update(self, store_id: str, dimensions: int) -> None:
        """Create a new index or merge required fields into an existing physical index."""
        from azure.core.exceptions import ResourceNotFoundError
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration,
            SearchableField,
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SimpleField,
            VectorSearch,
            VectorSearchProfile,
        )

        client, index_name, _ = self._resolve(store_id)
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="generation_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="block_key", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="block_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="document_version_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchableField(name="title", type=SearchFieldDataType.String, filterable=True, analyzer_name=_ZH_ANALYZER),
            SearchableField(name="text", type=SearchFieldDataType.String, analyzer_name=_ZH_ANALYZER),
            SimpleField(name="parent_block_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="article_no", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="paragraph_no", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="item_no", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="heading_path", type=SearchFieldDataType.String, analyzer_name=_ZH_ANALYZER),
            SimpleField(name="ordinal", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="text_hash", type=SearchFieldDataType.String, filterable=True),
            SearchField(
                name="vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                hidden=False,
                stored=True,
                vector_search_dimensions=int(dimensions),
                vector_search_profile_name=_VECTOR_PROFILE,
            ),
        ]
        vector_search = VectorSearch(
            profiles=[VectorSearchProfile(name=_VECTOR_PROFILE, algorithm_configuration_name=_VECTOR_ALGORITHM)],
            algorithms=[HnswAlgorithmConfiguration(name=_VECTOR_ALGORITHM)],
        )
        try:
            current = client.get_index(index_name)
        except ResourceNotFoundError:
            current = None
        if current is not None:
            incoming = {field.name: field for field in fields}
            merged = list(current.fields)
            existing_names = {field.name for field in merged}
            existing_vector = next((field for field in merged if field.name == "vector"), None)
            if existing_vector is not None:
                existing_dimensions = getattr(existing_vector, "vector_search_dimensions", None)
                if existing_dimensions is not None and int(existing_dimensions) != int(dimensions):
                    raise ValueError(
                        f"existing AI Search vector dimension {existing_dimensions} "
                        f"does not match generation dimension {dimensions}"
                    )
                # Incremental candidates inherit unchanged Block vectors. Azure AI Search
                # makes vector fields non-retrievable by default, so explicitly repair old
                # indexes as well as setting the flag for newly-created indexes.
                existing_vector.hidden = False
            merged.extend(field for name, field in incoming.items() if name not in existing_names)
            current.fields = merged
            if current.vector_search is None:
                current.vector_search = vector_search
            else:
                profile_names = {profile.name for profile in current.vector_search.profiles or []}
                if _VECTOR_PROFILE not in profile_names:
                    current.vector_search.profiles = list(current.vector_search.profiles or []) + vector_search.profiles
                algorithm_names = {algorithm.name for algorithm in current.vector_search.algorithms or []}
                if _VECTOR_ALGORITHM not in algorithm_names:
                    current.vector_search.algorithms = list(current.vector_search.algorithms or []) + vector_search.algorithms
            client.create_or_update_index(current)
        else:
            client.create_or_update_index(SearchIndex(name=index_name, fields=fields, vector_search=vector_search))
        self._clients.pop((store_id, int(dimensions)), None)

    def write(self, store_id: str, blocks: list[Block], vectors: list[list[float]], dimensions: int) -> int:
        if len(blocks) != len(vectors):
            raise ValueError("block and vector counts differ")
        for block, vector in zip(blocks, vectors):
            if len(vector) != dimensions:
                raise ValueError(
                    f"embedding dimension mismatch for {block.block_key}: "
                    f"{len(vector)} != {dimensions}"
                )
        client = self._search_client(store_id, dimensions)
        docs = [self._to_doc(block, vector) for block, vector in zip(blocks, vectors)]
        written = 0
        for i in range(0, len(docs), 1000):
            results = client.merge_or_upload_documents(documents=docs[i:i + 1000])
            failed = [r for r in results if not getattr(r, "succeeded", False)]
            if failed:
                raise RuntimeError("AI Search rejected block writes: " + "; ".join(
                    f"{getattr(r, 'key', '?')}: {getattr(r, 'error_message', 'unknown error')}" for r in failed
                ))
            written += len(results)
        return written

    def clone_blocks(
        self,
        store_id: str,
        source_generation_id: str | None,
        target_generation_id: str,
        block_map: dict[str, dict],
        dimensions: int,
    ) -> int:
        """Copy unchanged Search documents, including their existing vectors."""
        if not source_generation_id or not block_map:
            return 0
        client = self._search_client(store_id, dimensions)
        select = [
            "generation_id", "block_key", "block_id", "document_id", "document_version_id",
            "category", "title", "text", "parent_block_id", "article_no", "paragraph_no",
            "item_no", "heading_path", "ordinal", "text_hash", "vector",
        ]
        rows = client.search(
            search_text="*",
            filter=f"generation_id eq {_odata(source_generation_id)}",
            select=select,
        )
        docs: list[dict] = []
        found: set[str] = set()
        for raw in rows:
            row = dict(raw)
            mapped = block_map.get(row.get("block_key"))
            if not mapped:
                continue
            vector = list(row.get("vector") or [])
            if len(vector) != int(dimensions):
                raise ValueError(
                    f"base AI Search vector is unavailable or has the wrong dimension: {row.get('block_key')}"
                )
            target_block_key = mapped["target_block_key"]
            row.update({
                "id": self.key_of(target_block_key),
                "generation_id": target_generation_id,
                "block_key": target_block_key,
                "document_version_id": mapped["target_document_version_id"],
                "vector": vector,
            })
            docs.append({field: row.get(field) for field in ["id", *select]})
            found.add(mapped["source_block_key"])
        missing = sorted(set(block_map) - found)
        if missing:
            preview = ", ".join(missing[:5])
            raise ValueError(
                f"base AI Search generation is missing {len(missing)} retained blocks: {preview}"
            )
        written = 0
        for offset in range(0, len(docs), 1000):
            results = client.merge_or_upload_documents(documents=docs[offset:offset + 1000])
            failed = [result for result in results if not getattr(result, "succeeded", False)]
            if failed:
                raise RuntimeError("AI Search rejected retained block copies: " + "; ".join(
                    f"{getattr(result, 'key', '?')}: {getattr(result, 'error_message', 'unknown error')}"
                    for result in failed
                ))
            written += len(results)
        return written

    def count_generation(self, store_id: str, generation_id: str, dimensions: int = 1536) -> int:
        client = self._search_client(store_id, dimensions)
        rows = client.search(
            search_text="*", filter=f"generation_id eq {_odata(generation_id)}",
            select=["id"], top=1, include_total_count=True,
        )
        return int(rows.get_count() or 0)

    def wait_for_generation_count(
        self,
        store_id: str,
        generation_id: str,
        expected: int,
        dimensions: int = 1536,
        attempts: int = 12,
    ) -> int:
        """Wait for Azure Search's eventually-consistent count to reach the manifest count."""
        actual = 0
        for attempt in range(max(1, int(attempts))):
            actual = self.count_generation(store_id, generation_id, dimensions)
            if actual == int(expected):
                return actual
            if attempt + 1 < attempts:
                time.sleep(1)
        return actual

    def delete_generation(self, store_id: str, generation_id: str, dimensions: int = 1536) -> int:
        client = self._search_client(store_id, dimensions)
        deleted = 0
        while True:
            rows = list(client.search(
                search_text="*", filter=f"generation_id eq {_odata(generation_id)}",
                select=["id"], top=1000,
            ))
            if not rows:
                break
            results = client.delete_documents(documents=[{"id": row["id"]} for row in rows])
            failed = [r for r in results if not getattr(r, "succeeded", False)]
            if failed:
                raise RuntimeError("AI Search rejected generation cleanup")
            deleted += len(results)
        return deleted

    def get_block(
        self,
        store_id: str,
        generation_id: str,
        block_id: str | None = None,
        block_key: str | None = None,
        dimensions: int = 1536,
    ) -> dict | None:
        client = self._search_client(store_id, dimensions)
        filters = [f"generation_id eq {_odata(generation_id)}"]
        if block_key:
            filters.append(f"block_key eq {_odata(block_key)}")
        elif block_id:
            filters.append(f"block_id eq {_odata(block_id)}")
        else:
            raise ValueError("block_id or block_key is required")
        rows = client.search(
            search_text="*", filter=" and ".join(filters), top=1,
            select=[
                "generation_id", "block_key", "block_id", "document_id", "document_version_id",
                "category", "title", "text", "parent_block_id", "article_no", "paragraph_no",
                "item_no", "heading_path", "ordinal", "text_hash",
            ],
        )
        return next((dict(row) for row in rows), None)

    def list_document_blocks(
        self,
        store_id: str,
        generation_id: str,
        document_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        dimensions: int = 1536,
    ) -> dict:
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        rows = self._search_client(store_id, dimensions).search(
            search_text="*",
            filter=(
                f"generation_id eq {_odata(generation_id)} and "
                f"document_id eq {_odata(document_id)}"
            ),
            order_by=["ordinal asc"],
            skip=(page - 1) * page_size,
            top=page_size,
            include_total_count=True,
            select=[
                "generation_id", "block_key", "block_id", "document_id",
                "document_version_id", "category", "title", "text",
                "parent_block_id", "article_no", "paragraph_no", "item_no",
                "heading_path", "ordinal", "text_hash",
            ],
        )
        items = [dict(row) for row in rows]
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": int(rows.get_count() or 0),
        }

    def search(
        self,
        store_id: str,
        generation_id: str,
        query_text: str | None,
        query_vector: list[float] | None,
        top: int = 10,
        dimensions: int = 1536,
        extra_filter: str | None = None,
    ) -> list[dict]:
        """Generation is mandatory; old physical documents without it are invisible."""
        from azure.search.documents.models import VectorizedQuery

        generation_filter = f"generation_id eq {_odata(generation_id)}"
        odata_filter = f"({generation_filter}) and ({extra_filter})" if extra_filter else generation_filter
        vector_queries = None
        if query_vector:
            vector_queries = [VectorizedQuery(
                vector=query_vector, k_nearest_neighbors=top, fields="vector",
            )]
        rows = self._search_client(store_id, dimensions).search(
            search_text=query_text or None,
            vector_queries=vector_queries,
            filter=odata_filter,
            top=top,
            select=[
                "generation_id", "block_key", "block_id", "document_id", "document_version_id",
                "category", "title", "text", "parent_block_id", "article_no", "paragraph_no",
                "item_no", "heading_path", "ordinal", "text_hash",
            ],
        )
        out = []
        for row in rows:
            item = dict(row)
            item["score"] = row.get("@search.score")
            out.append(item)
        return out

    @staticmethod
    def _to_doc(block: Block, vector: list[float]) -> dict:
        return {
            "id": GenerationSearchAdapter.key_of(block.block_key),
            "generation_id": block.generation_id,
            "block_key": block.block_key,
            "block_id": block.block_id,
            "document_id": block.document_id,
            "document_version_id": block.document_version_id,
            "category": block.category,
            "title": block.title,
            "text": block.text,
            "parent_block_id": block.parent_block_id,
            "article_no": block.article_no,
            "paragraph_no": block.paragraph_no,
            "item_no": block.item_no,
            "heading_path": block.heading_path,
            "ordinal": block.ordinal,
            "text_hash": block.text_hash,
            "vector": vector,
        }

    def _resolve(self, store_id: str):
        rows = self.db.execute_query(
            "SELECT TOP 1 credential_name, index_name FROM nexus.search_store WHERE store_id=?",
            (store_id,),
        )
        if not rows:
            raise ValueError(f"search store does not exist: {store_id}")
        store = rows[0]
        credential = services[azure_keyvault_credential_provider].load(store["credential_name"])
        if credential is None:
            raise ValueError(f"AI Search credential is unavailable: {store['credential_name']}")
        conf = credential.to_config()
        index_name = store.get("index_name") or conf.get("index_name")
        if not index_name:
            raise ValueError(f"search store {store_id} has no index_name")
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.indexes import SearchIndexClient
        index_client = self._index_clients.get(store_id)
        if index_client is None:
            index_client = SearchIndexClient(
                conf["endpoint"], AzureKeyCredential(conf["key"]),
                api_version=conf.get("api_version") or _DEFAULT_API_VERSION,
            )
            self._index_clients[store_id] = index_client
        return index_client, index_name, conf

    def _search_client(self, store_id: str, dimensions: int):
        key = (store_id, int(dimensions))
        client = self._clients.get(key)
        if client is not None:
            return client
        _, index_name, conf = self._resolve(store_id)
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        client = SearchClient(
            conf["endpoint"], index_name, AzureKeyCredential(conf["key"]),
            api_version=conf.get("api_version") or _DEFAULT_API_VERSION,
        )
        self._clients[key] = client
        return client
