"""Entry point for isolated full-generation index runs."""
from __future__ import annotations

import time
import uuid

from core.cancellation_token import cancellation_token
from core.services import services
from nexus.infrastructure import (
    AssertionRepository,
    DocumentRepository,
    ExtractionAttemptRepository,
    GenerationRepository,
    GenerationSearchAdapter,
    QualityRepository,
    make_chat,
    make_embedder,
)
from utils.logger import get_logger

from .extractor import AssertionExtractor
from .chunker import content_hash, document_id, title_from_filename
from .prompts import EXTRACTOR_VERSION, ONTOLOGY_VERSION
from .recorder import IndexRunRecorder
from .resolution import ResolutionService
from .workflow import build_index_workflow, build_seed

_logger = get_logger("nexus.indexing.runner")
_RUNS: dict[str, cancellation_token] = {}


def classify_files(
    files: list[tuple[str, str, str]],
    base_documents: dict[str, dict],
) -> tuple[list[tuple[str, str, str]], set[str], list[dict]]:
    """Return changed uploads, retained document IDs, and an auditable classification."""
    incoming: list[dict] = []
    incoming_ids: set[str] = set()
    for filename, text, file_category in files:
        title = title_from_filename(filename)
        doc_id = document_id(file_category, title)
        if doc_id in incoming_ids:
            raise ValueError(f"duplicate logical document in upload: {title}")
        incoming_ids.add(doc_id)
        incoming.append({
            "filename": filename,
            "title": title,
            "category": file_category,
            "document_id": doc_id,
            "content_hash": content_hash(
                (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            ),
        })
    retained_document_ids = set(base_documents) - incoming_ids
    changed_files: list[tuple[str, str, str]] = []
    classifications: list[dict] = []
    for source, item in zip(files, incoming):
        previous = base_documents.get(item["document_id"])
        if previous and previous["content_hash"] == item["content_hash"]:
            retained_document_ids.add(item["document_id"])
            action = "unchanged"
        else:
            changed_files.append(source)
            action = "replace" if previous else "add"
        classifications.append({**item, "action": action})
    return changed_files, retained_document_ids, classifications


def cancel_run(run_id: str) -> bool:
    token = _RUNS.get(run_id)
    if token is None:
        return False
    token.cancel()
    return True


def plan_document_deletion(
    base_documents: dict[str, dict],
    deleted_document_ids: set[str],
) -> set[str]:
    if not deleted_document_ids:
        raise ValueError("at least one document_id is required")
    missing = sorted(deleted_document_ids - set(base_documents))
    if missing:
        raise ValueError("documents are not present in the base Generation: " + ", ".join(missing))
    retained = set(base_documents) - deleted_document_ids
    if not retained:
        raise ValueError("deleting every document from a Store is not supported")
    return retained


def run_index(
    run_id: str,
    files: list[tuple[str, str, str]],
    llm_credential: str,
    embedding_credential: str,
    store_id: str,
    category: str,
    max_parallel: int = 8,
    as_user: str | None = None,
) -> None:
    """Build a new full generation; legacy overwrite/auto-attach semantics do not apply."""
    started = time.time()
    max_parallel = max(1, min(64, int(max_parallel or 8)))
    generation_id = "gen_" + uuid.uuid4().hex
    recorder: IndexRunRecorder | None = None
    token = cancellation_token()
    _RUNS[run_id] = token
    try:
        embedder = make_embedder(embedding_credential)
        dimensions = embedder.dimensions
        file_categories = sorted({file_category for _, _, file_category in files})
        run_category = file_categories[0] if len(file_categories) == 1 else "MULTI"
        generations = services[GenerationRepository]
        documents = services[DocumentRepository]
        base = generations.active_generation(store_id)
        base_generation_id = base["generation_id"] if base else None
        if base and int(base["embedding_dimensions"]) != int(dimensions):
            raise ValueError(
                "the active Generation uses a different embedding dimension; "
                "use an explicit replace-all rebuild to change embedding models"
            )
        if base and base.get("embedding_credential") != embedding_credential:
            raise ValueError(
                "the active Generation uses a different embedding credential; "
                "incremental indexing cannot mix vector models"
            )
        if base and (
            base.get("ontology_version") != ONTOLOGY_VERSION
            or base.get("extractor_version") != EXTRACTOR_VERSION
        ):
            raise ValueError(
                "the active Generation uses a different ontology/extractor version; "
                "a replace-all rebuild is required before incremental indexing"
            )
        base_documents = {
            row["document_id"]: row for row in documents.generation_documents(base_generation_id)
        }
        changed_files, retained_document_ids, classifications = classify_files(files, base_documents)
        generations.create_run_and_generation(
            run_id=run_id,
            generation_id=generation_id,
            as_user=as_user,
            store_id=store_id,
            category=run_category,
            llm_credential=llm_credential,
            embedding_credential=embedding_credential,
            max_parallel=max_parallel,
            ontology_version=ONTOLOGY_VERSION,
            extractor_version=EXTRACTOR_VERSION,
            embedding_dimensions=dimensions,
            input_snapshot={
                "files": classifications,
                "mode": "merge_documents",
                "base_generation_id": base_generation_id,
                "retained_document_ids": sorted(retained_document_ids),
            },
            base_generation_id=base_generation_id,
        )
        recorder = IndexRunRecorder(generations, generation_id)
        chat = make_chat(llm_credential)
        search = services[GenerationSearchAdapter]
        search.create_or_update(store_id, dimensions)
        attempts = services[ExtractionAttemptRepository]
        assertions = services[AssertionRepository]
        shared = {
            "files": changed_files,
            "base_generation_id": base_generation_id,
            "retained_document_ids": retained_document_ids,
            "category": category,
            "store_id": store_id,
            "generation_id": generation_id,
            "dimensions": dimensions,
            "chat": chat,
            "embedder": embedder,
            "generations": generations,
            "documents": documents,
            "assertions": assertions,
            "quality": services[QualityRepository],
            "search": search,
            "extractor": AssertionExtractor(chat, attempts),
            "resolution": ResolutionService(assertions),
            "recorder": recorder,
        }
        build_index_workflow().run(
            run_id,
            build_seed(),
            max_parallel=max_parallel,
            recorder=recorder,
            shared=shared,
            cancel_token=token,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.exception(f"index generation failed: {exc}")
        if recorder is not None:
            state = "cancelled" if token.is_cancelled else "failed"
            try:
                recorder.finish_run(run_id, state, str(exc), int((time.time() - started) * 1000))
            except Exception:  # noqa: BLE001
                _logger.exception("failed to persist terminal index run state")
    finally:
        _RUNS.pop(run_id, None)


def run_delete_documents(
    run_id: str,
    store_id: str,
    base_generation_id: str,
    deleted_document_ids: list[str],
    max_parallel: int = 8,
    as_user: str | None = None,
    reason: str | None = None,
) -> None:
    """Publish a complete candidate that excludes selected active documents."""
    started = time.time()
    max_parallel = max(1, min(64, int(max_parallel or 8)))
    generation_id = "gen_" + uuid.uuid4().hex
    recorder: IndexRunRecorder | None = None
    token = cancellation_token()
    _RUNS[run_id] = token
    try:
        generations = services[GenerationRepository]
        source = generations.generation(store_id, base_generation_id)
        if source is None:
            raise ValueError(f"base Generation does not exist for Store: {base_generation_id}")
        documents = services[DocumentRepository]
        base_documents = {
            row["document_id"]: row
            for row in documents.generation_documents(base_generation_id)
        }
        deleted = set(dict.fromkeys(deleted_document_ids))
        retained = plan_document_deletion(base_documents, deleted)
        deleted_snapshot = [
            {
                "document_id": document_id,
                "title": base_documents[document_id]["title"],
                "category": base_documents[document_id]["category"],
                "content_hash": base_documents[document_id]["content_hash"],
            }
            for document_id in sorted(deleted)
        ]
        generations.create_run_and_generation(
            run_id=run_id,
            generation_id=generation_id,
            as_user=as_user,
            store_id=store_id,
            category="DELETE",
            llm_credential=source["llm_credential"],
            embedding_credential=source["embedding_credential"],
            max_parallel=max_parallel,
            ontology_version=source["ontology_version"],
            extractor_version=source["extractor_version"],
            embedding_dimensions=int(source["embedding_dimensions"]),
            input_snapshot={
                "files": [],
                "mode": "delete_documents",
                "base_generation_id": base_generation_id,
                "deleted_documents": deleted_snapshot,
                "retained_document_ids": sorted(retained),
                "reason": (reason or "").strip() or None,
            },
            base_generation_id=base_generation_id,
        )
        recorder = IndexRunRecorder(generations, generation_id)
        search = services[GenerationSearchAdapter]
        dimensions = int(source["embedding_dimensions"])
        search.create_or_update(store_id, dimensions)
        assertions = services[AssertionRepository]
        shared = {
            "files": [],
            "base_generation_id": base_generation_id,
            "retained_document_ids": retained,
            "strict_retained_facts": True,
            "category": "DELETE",
            "store_id": store_id,
            "generation_id": generation_id,
            "dimensions": dimensions,
            "embedder": None,
            "generations": generations,
            "documents": documents,
            "assertions": assertions,
            "quality": services[QualityRepository],
            "search": search,
            "extractor": None,
            "resolution": ResolutionService(assertions),
            "recorder": recorder,
        }
        build_index_workflow().run(
            run_id,
            build_seed(),
            max_parallel=max_parallel,
            recorder=recorder,
            shared=shared,
            cancel_token=token,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.exception(f"document deletion generation failed: {exc}")
        if recorder is not None:
            state = "cancelled" if token.is_cancelled else "failed"
            try:
                recorder.finish_run(run_id, state, str(exc), int((time.time() - started) * 1000))
            except Exception:  # noqa: BLE001
                _logger.exception("failed to persist terminal deletion run state")
    finally:
        _RUNS.pop(run_id, None)
