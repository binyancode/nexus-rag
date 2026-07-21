"""Persistence for query_run, five query_stage rows, and PEP query_node rows."""
from __future__ import annotations

import json
from typing import Any

from core.services import services
from services.sql_db import sql_db
from services.workflow import WorkflowRecorder

STAGES = [
    ("initializer", 1, "初始化器"),
    ("compiler", 2, "SQG 编译器"),
    ("optimizer", 3, "PEP 优化器/规划器"),
    ("coordinator", 4, "Workflow 协调器"),
    ("generator", 5, "答案生成器"),
]


def _json(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class QueryRunRecorder(WorkflowRecorder):
    def __init__(self):
        self._tokens: dict[str, Any] = {}
        self._stage_tokens: dict[str, Any] = {}
        self._node_ops: dict[str, str] = {}
        self._node_inputs: dict[str, dict] = {}

    @property
    def db(self) -> sql_db:
        return services[sql_db]

    def create_run(
        self,
        *,
        run_id: str,
        question: str,
        as_user: str | None,
        llm_credential: str,
        embedding_credential: str,
        max_parallel: int,
        budgets,
    ) -> None:
        self.db.execute_non_query(
            """INSERT INTO nexus.query_run
                   (run_id,as_user,question,llm_credential,embedding_credential,
                    max_parallel,budgets,[state])
               VALUES (?,?,?,?,?,?,?,'running')""",
            (
                run_id, as_user, question, llm_credential, embedding_credential,
                int(max_parallel), _json(budgets),
            ),
        )
        for stage_id, ordinal, name in STAGES:
            self.db.execute_non_query(
                "INSERT INTO nexus.query_stage(run_id,stage_id,ordinal,name,[state]) "
                "VALUES (?,?,?,?,'pending')",
                (run_id, stage_id, ordinal, name),
            )

    def start_stage(self, run_id: str, stage_id: str, input_value=None) -> None:
        self._stage_tokens = {}
        self.db.execute_non_query(
            """UPDATE nexus.query_stage
               SET [state]='running',[input]=?,started_at=SYSUTCDATETIME(),
                   ended_at=NULL,error=NULL
               WHERE run_id=? AND stage_id=?;
               UPDATE nexus.query_run
               SET current_stage=?,updated_at=SYSUTCDATETIME() WHERE run_id=?;""",
            (_json(input_value), run_id, stage_id, stage_id, run_id),
        )

    def finish_stage(self, run_id: str, stage_id: str, output_value=None, cost_ms: int = 0) -> None:
        self.db.execute_non_query(
            """UPDATE nexus.query_stage
               SET [state]='succeeded',[output]=?,tokens=?,cost_ms=?,ended_at=SYSUTCDATETIME()
               WHERE run_id=? AND stage_id=?""",
            (_json(output_value), _json(self._stage_tokens), int(cost_ms), run_id, stage_id),
        )

    def fail_stage(
        self,
        run_id: str,
        stage_id: str,
        error: str,
        cost_ms: int = 0,
        cancelled: bool = False,
        output_value=None,
    ) -> None:
        state = "cancelled" if cancelled else "failed"
        self.db.execute_non_query(
            """UPDATE nexus.query_stage
               SET [state]=?,[output]=?,tokens=?,error=?,cost_ms=?,ended_at=SYSUTCDATETIME()
               WHERE run_id=? AND stage_id=?;
               UPDATE nexus.query_stage
               SET [state]='skipped',ended_at=SYSUTCDATETIME()
               WHERE run_id=? AND ordinal>(
                   SELECT ordinal FROM nexus.query_stage WHERE run_id=? AND stage_id=?
               );""",
            (
                state, _json(output_value), _json(self._stage_tokens), error, int(cost_ms),
                run_id, stage_id, run_id, run_id, stage_id,
            ),
        )

    def set_scope(self, context) -> None:
        self.db.execute_non_query(
            """UPDATE nexus.query_run
               SET collection_id=?,collection_name=?,collection_selected_by=?,
                   allowed_stores=?,generation_scope=?,budgets=?,updated_at=SYSUTCDATETIME()
               WHERE run_id=?""",
            (
                context.collection.collection_id,
                context.collection.name,
                context.collection.selected_by,
                _json(context.allowed_stores),
                _json(context.generation_scope),
                _json(context.budgets),
                context.run_id,
            ),
        )

    def set_pep_metadata(self, pep) -> None:
        self._node_ops = {node.id: node.op for node in pep.nodes}
        self._node_inputs = {
            node.id: {
                port: binding.model_dump(mode="json")
                for port, binding in node.inputs.items()
            }
            for node in pep.nodes
        }

    def set_answer(self, run_id: str, result) -> None:
        self.db.execute_non_query(
            "UPDATE nexus.query_run SET answer=?,citations=?,updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (result.answer, _json(result.citations), run_id),
        )

    def finish_query(self, run_id: str, state: str, error: str | None, cost_ms: int) -> None:
        self.db.execute_non_query(
            """UPDATE nexus.query_run
               SET [state]=?,current_stage=NULL,error=?,cost_ms=?,updated_at=SYSUTCDATETIME()
               WHERE run_id=?""",
            (state, error, int(cost_ms), run_id),
        )

    # WorkflowRecorder methods; the generic engine remains unchanged.
    def on_dag_update(self, run_id: str, dag: dict) -> None:
        self.db.execute_non_query(
            "UPDATE nexus.query_run SET node_count=?,updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (len(dag.get("nodes") or []), run_id),
        )

    def start_node(self, run_id: str, node_id: str) -> None:
        self.db.execute_non_query(
            """MERGE nexus.query_node AS target
               USING (SELECT ? AS run_id,? AS node_id) AS source
                 ON target.run_id=source.run_id AND target.node_id=source.node_id
               WHEN MATCHED THEN UPDATE SET
                   [state]='running',op=?,[input]=?,started_at=SYSUTCDATETIME(),
                   ended_at=NULL,error=NULL
               WHEN NOT MATCHED THEN INSERT
                   (run_id,node_id,[state],op,[input],started_at)
                   VALUES (?,?,'running',?,?,SYSUTCDATETIME());""",
            (
                run_id, node_id, self._node_ops[node_id], _json(self._node_inputs.get(node_id)),
                run_id, node_id, self._node_ops[node_id], _json(self._node_inputs.get(node_id)),
            ),
        )

    def finish_node(self, run_id, node_id, state, output, value, tokens, error, cost_ms) -> None:
        self.db.execute_non_query(
            """MERGE nexus.query_node AS target
               USING (SELECT ? AS run_id,? AS node_id) AS source
                 ON target.run_id=source.run_id AND target.node_id=source.node_id
               WHEN MATCHED THEN UPDATE SET
                   [state]=?,op=?,[output]=?,[value]=?,tokens=?,error=?,cost_ms=?,
                   ended_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (run_id,node_id,[state],op,[output],[value],tokens,error,cost_ms,started_at,ended_at)
                   VALUES (?,?,?,?,?,?,?,?,?,SYSUTCDATETIME(),SYSUTCDATETIME());""",
            (
                run_id, node_id, state, self._node_ops[node_id], _json(output), value,
                _json(tokens), error, cost_ms,
                run_id, node_id, state, self._node_ops[node_id], _json(output), value,
                _json(tokens), error, cost_ms,
            ),
        )

    def bump_tokens(self, run_id: str, tokens: dict) -> None:
        for key, value in (tokens or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                amount = int(value)
                self._tokens[key] = int(self._tokens.get(key, 0) or 0) + amount
                self._stage_tokens[key] = int(self._stage_tokens.get(key, 0) or 0) + amount
            else:
                self._tokens[key] = value
                self._stage_tokens[key] = value
        self.db.execute_non_query(
            "UPDATE nexus.query_run SET tokens=?,updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (_json(self._tokens), run_id),
        )

    def finish_run(self, run_id: str, state: str, error: str | None, cost_ms: int) -> None:
        # The runner owns the five-stage run terminal state.
        return
