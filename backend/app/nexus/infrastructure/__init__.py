"""Final SQL and Azure AI Search adapters for Nexus."""
from .ai_clients import (
    ChatClient,
    EmbeddingClient,
    JsonCompletionError,
    make_chat,
    make_embedder,
)
from .assertion_repository import AssertionRepository, normalize_name, signature_hash
from .document_repository import DocumentRepository
from .extraction_repository import ExtractionAttemptRepository
from .generation_repository import GenerationRepository
from .graph_repository import GraphRepository
from .quality_repository import QualityMetric, QualityRepository
from .query_repository import QueryRepository
from .search_adapter import GenerationSearchAdapter
from .store_repository import StoreCollectionRepository

__all__ = [
    "GenerationRepository", "DocumentRepository", "ExtractionAttemptRepository",
    "AssertionRepository", "QualityRepository", "QualityMetric",
    "GenerationSearchAdapter", "normalize_name", "signature_hash",
    "StoreCollectionRepository", "ChatClient", "EmbeddingClient",
    "JsonCompletionError", "make_chat", "make_embedder",
    "QueryRepository", "GraphRepository",
]
