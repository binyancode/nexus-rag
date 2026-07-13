"""查询运行入口：串联五个模块，并把 PEP 交给协调器/Workflow 执行。"""
from __future__ import annotations

import time

from core.cancellation_token import cancellation_token
from utils.logger import get_logger

from ..llm.resolve import make_chat, make_embedder
from .compiler import SQGCompiler
from .coordinator import QueryCoordinator
from .generator import AnswerGenerator
from .initializer import QueryInitializer
from .models import QueryBudgets
from .optimizer import PEPOptimizationError, QueryOptimizer
from .recorder import QueryRunRecorder

_logger = get_logger("nexus.query.runner")
_RUNS: dict[str, cancellation_token] = {}


def cancel_query(run_id: str) -> bool:
    token = _RUNS.get(run_id)
    if token is None:
        return False
    token.cancel()
    return True


def run_query(run_id: str, question: str, llm_credential: str, embedding_credential: str,
              collection_id: str | None = None, max_parallel: int = 8,
              as_user: str | None = None, budgets: QueryBudgets | None = None) -> None:
    recorder = QueryRunRecorder()
    recorder.create_run(
        run_id, question, as_user, llm_credential, embedding_credential, max_parallel,
    )
    token = cancellation_token()
    _RUNS[run_id] = token
    started = time.time()
    current_stage = "initializer"
    stage_started = started
    try:
        chat = make_chat(llm_credential)
        embedder = make_embedder(embedding_credential)

        recorder.start_stage(run_id, "initializer", {
            "question": question, "requested_collection": collection_id,
            "as_user": as_user, "budgets": (budgets or QueryBudgets()).model_dump(),
        })
        chat.reset_usage()
        context = QueryInitializer().initialize(
            question=question,
            collection_id=collection_id,
            llm_credential=llm_credential,
            embedding_credential=embedding_credential,
            max_parallel=max_parallel,
            as_user=as_user,
            budgets=budgets,
            run_id=run_id,
            chat=chat,
        )
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.set_scope(context)
        recorder.finish_stage(run_id, "initializer", context.model_dump(), _ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "compiler"
        stage_started = time.time()
        recorder.start_stage(run_id, "compiler", context.model_dump())
        chat.reset_usage()
        sqg = SQGCompiler().compile(context, chat)
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.finish_stage(run_id, "compiler", sqg.model_dump(), _ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "optimizer"
        stage_started = time.time()
        recorder.start_stage(run_id, "optimizer", {
            "context": context.model_dump(), "sqg": sqg.model_dump(),
        })
        chat.reset_usage()
        pep = QueryOptimizer().optimize(context, sqg, chat)
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.set_pep_metadata(pep)
        recorder.finish_stage(run_id, "optimizer", pep.model_dump(), _ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "coordinator"
        stage_started = time.time()
        recorder.start_stage(run_id, "coordinator", pep.model_dump())
        result = QueryCoordinator().execute(
            context=context,
            pep=pep,
            recorder=recorder,
            chat=chat,
            embedder=embedder,
            cancel_token=token,
        )
        if result.get("state") != "succeeded":
            raise RuntimeError(f"PEP 执行失败: {result.get('state')}")
        coordinator_output = {
            "facts": result["facts"].to_dict(),
            "evidence": result["evidence"].to_dict(),
        }
        recorder.finish_stage(run_id, "coordinator", coordinator_output, _ms(stage_started))
        token.raise_if_cancelled()

        current_stage = "generator"
        stage_started = time.time()
        recorder.start_stage(run_id, "generator", {
            "facts": result["facts"].to_dict(), "evidence": result["evidence"].to_dict(),
        })
        chat.reset_usage()
        answer = AnswerGenerator().generate(context, result["facts"], result["evidence"], chat)
        recorder.bump_tokens(run_id, chat.pop_usage())
        recorder.set_answer(run_id, answer)
        recorder.finish_stage(run_id, "generator", answer.to_dict(), _ms(stage_started))
        recorder.finish_query(run_id, "succeeded", None, _ms(started))
    except Exception as exc:  # noqa: BLE001
        state = "cancelled" if token.is_cancelled else "failed"
        _logger.exception(f"query run failed: {exc}")
        # LLM 调用成功返回、但后续解析/校验失败时，usage 仍必须结算到当前阶段和 run。
        try:
            outstanding_tokens = chat.pop_usage()
            if outstanding_tokens:
                recorder.bump_tokens(run_id, outstanding_tokens)
        except Exception:  # noqa: BLE001
            pass
        failed_output = exc.raw_pep if isinstance(exc, PEPOptimizationError) else None
        recorder.fail_stage(
            run_id, current_stage, str(exc), _ms(stage_started), token.is_cancelled,
            output_value=failed_output,
        )
        recorder.finish_query(run_id, state, str(exc), _ms(started))
    finally:
        _RUNS.pop(run_id, None)


def _ms(started: float) -> int:
    return int((time.time() - started) * 1000)
