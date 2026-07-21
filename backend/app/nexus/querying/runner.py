"""Explicit five-stage Assertion-first query orchestration."""
from __future__ import annotations

import time

from core.cancellation_token import CancelledError, cancellation_token
from nexus.domain import QueryBudgets
from nexus.infrastructure import make_chat, make_embedder
from utils.logger import get_logger

from .compiler import CompilerError, SQGCompiler
from .coordinator import QueryCoordinator
from .generator import AnswerGenerationError, AnswerGenerator
from .initializer import QueryInitializer
from .planner import DeterministicPlanner
from .recorder import QueryRunRecorder

_logger = get_logger("nexus.querying.runner")
_RUNS: dict[str, cancellation_token] = {}


def cancel_query(run_id: str) -> bool:
    token = _RUNS.get(run_id)
    if token is None:
        return False
    token.cancel()
    return True


def run_query(
    run_id: str,
    question: str,
    llm_credential: str,
    embedding_credential: str,
    collection_id: str | None = None,
    max_parallel: int = 8,
    as_user: str | None = None,
    budgets: QueryBudgets | None = None,
    llm_temperature: float | None = None,
) -> None:
    budgets = budgets or QueryBudgets()
    max_parallel = max(1, min(64, int(max_parallel or 8)))
    recorder = QueryRunRecorder()
    recorder.create_run(
        run_id=run_id,
        question=question,
        as_user=as_user,
        llm_credential=llm_credential,
        embedding_credential=embedding_credential,
        max_parallel=max_parallel,
        budgets=budgets,
    )
    token = cancellation_token()
    _RUNS[run_id] = token
    run_started = time.time()
    stage_started = run_started
    current_stage = "initializer"
    chat = None
    try:
        recorder.start_stage(run_id, "initializer", {
            "question": question,
            "requested_collection": collection_id,
            "as_user": as_user,
            "max_parallel": max_parallel,
            "budgets": budgets.model_dump(mode="json"),
        })
        stage_started = time.time()
        chat = make_chat(llm_credential)
        embedder = make_embedder(embedding_credential)
        chat.reset_usage()
        context = QueryInitializer().initialize(
            run_id=run_id,
            question=question,
            llm_credential=llm_credential,
            embedding_credential=embedding_credential,
            chat=chat,
            embedder=embedder,
            collection_id=collection_id,
            as_user=as_user,
            max_parallel=max_parallel,
            budgets=budgets,
            temperature=llm_temperature,
        )
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.set_scope(context)
        recorder.finish_stage(
            run_id, "initializer", context.model_dump(mode="json"), _elapsed_ms(stage_started),
        )
        token.raise_if_cancelled()

        current_stage = "compiler"
        stage_started = time.time()
        recorder.start_stage(run_id, "compiler", {
            "question": context.question,
            "collection": context.collection.model_dump(mode="json"),
            "vocabulary_counts": {
                "entities": len(context.entities),
                "actions": len(context.actions),
                "documents": len(context.documents),
                "relations": len(context.graph_relations),
            },
        })
        chat.reset_usage()
        sqg = SQGCompiler().compile(context, chat, temperature=llm_temperature)
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.finish_stage(run_id, "compiler", sqg.model_dump(mode="json"), _elapsed_ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "optimizer"
        stage_started = time.time()
        recorder.start_stage(run_id, "optimizer", sqg.model_dump(mode="json"))
        pep = DeterministicPlanner().plan(context, sqg)
        recorder.set_pep_metadata(pep)
        recorder.finish_stage(run_id, "optimizer", pep.model_dump(mode="json"), _elapsed_ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "coordinator"
        stage_started = time.time()
        recorder.start_stage(run_id, "coordinator", pep.model_dump(mode="json"))
        execution = QueryCoordinator().execute(
            context=context,
            pep=pep,
            recorder=recorder,
            embedder=embedder,
            cancel_token=token,
        )
        if execution.get("state") == "cancelled":
            raise CancelledError("query workflow was cancelled")
        if execution.get("state") != "succeeded":
            raise RuntimeError(f"PEP workflow failed: {execution.get('state')}")
        coordinator_output = {
            "facts": execution["facts"].model_dump(mode="json"),
            "evidence": execution["evidence"].model_dump(mode="json"),
        }
        recorder.finish_stage(run_id, "coordinator", coordinator_output, _elapsed_ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "generator"
        stage_started = time.time()
        recorder.start_stage(run_id, "generator", coordinator_output)
        chat.reset_usage()
        answer = AnswerGenerator().generate(
            context, execution["facts"], execution["evidence"], chat, llm_temperature,
        )
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.set_answer(run_id, answer)
        recorder.finish_stage(run_id, "generator", answer.model_dump(mode="json"), _elapsed_ms(stage_started))
        recorder.finish_query(run_id, "succeeded", None, _elapsed_ms(run_started))
    except Exception as exc:  # noqa: BLE001
        cancelled = token.is_cancelled or isinstance(exc, CancelledError)
        state = "cancelled" if cancelled else "failed"
        _logger.exception(f"query run failed: {exc}")
        if chat is not None:
            try:
                outstanding = chat.pop_usage()
                if outstanding:
                    recorder.bump_tokens(run_id, outstanding)
            except Exception:  # noqa: BLE001
                _logger.exception("failed to settle outstanding query token usage")
        if isinstance(exc, CompilerError):
            failed_output = exc.raw_output
        elif isinstance(exc, AnswerGenerationError):
            failed_output = exc.raw_output
        else:
            failed_output = None
        recorder.fail_stage(
            run_id,
            current_stage,
            str(exc),
            _elapsed_ms(stage_started),
            cancelled=cancelled,
            output_value=failed_output,
        )
        recorder.finish_query(run_id, state, str(exc), _elapsed_ms(run_started))
    finally:
        _RUNS.pop(run_id, None)


def _elapsed_ms(started: float) -> int:
    return int((time.time() - started) * 1000)
