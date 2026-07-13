"""Entry point for isolated full-generation index runs."""
from __future__ import annotations

import hashlib
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
from .prompts import EXTRACTOR_VERSION, ONTOLOGY_VERSION
from .recorder import IndexRunRecorder
from .resolution import ResolutionService
from .workflow import build_index_workflow, build_seed

_logger = get_logger("nexus.indexing.runner")
_RUNS: dict[str, cancellation_token] = {}


def cancel_run(run_id: str) -> bool:
    token = _RUNS.get(run_id)
    if token is None:
        return False
    token.cancel()
    return True


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
                "files": [
                    {
                        "filename": filename,
                        "category": file_category,
                        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    }
                    for filename, text, file_category in files
                ],
                "full_generation": True,
            },
        )
        recorder = IndexRunRecorder(generations, generation_id)
        chat = make_chat(llm_credential)
        search = services[GenerationSearchAdapter]
        search.create_or_update(store_id, dimensions)
        attempts = services[ExtractionAttemptRepository]
        assertions = services[AssertionRepository]
        shared = {
            "files": files,
            "category": category,
            "store_id": store_id,
            "generation_id": generation_id,
            "dimensions": dimensions,
            "chat": chat,
            "embedder": embedder,
            "generations": generations,
            "documents": services[DocumentRepository],
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
