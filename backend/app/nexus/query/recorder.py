"""查询持久化：query_run 总体、query_stage 五阶段、query_node 物理执行节点。"""
from __future__ import annotations

import json

from core.services import services
from services.sql_db import sql_db
from services.workflow import WorkflowRecorder


STAGES = [
    ("initializer", 1, "初始化器"),
    ("compiler", 2, "编译器"),
    ("optimizer", 3, "优化器"),
    ("coordinator", 4, "协调器"),
    ("generator", 5, "生成器"),
]


def _j(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


class QueryRunRecorder(WorkflowRecorder):
    def __init__(self):
        self._tokens: dict[str, int] = {}
        self._stage_tokens: dict[str, int] = {}
        self._current_stage: str | None = None
        self._node_ops: dict[str, str] = {}
        self._node_inputs: dict[str, dict] = {}

    @property
    def _db(self) -> sql_db:
        return services[sql_db]

    # ---------------- run / stage ----------------
    def create_run(self, run_id: str, question: str, as_user: str | None,
                   llm_credential: str, embedding_credential: str, max_parallel: int) -> None:
        self._db.execute_non_query(
            """INSERT INTO nexus.query_run
                   (run_id,as_user,question,llm_credential,embedding_credential,max_parallel,[state])
               VALUES (?,?,?,?,?,?,'running')""",
            (run_id, as_user, question, llm_credential, embedding_credential, int(max_parallel)),
        )
        for stage_id, ordinal, name in STAGES:
            self._db.execute_non_query(
                "INSERT INTO nexus.query_stage(run_id,stage_id,ordinal,name,[state]) VALUES (?,?,?,?,'pending')",
                (run_id, stage_id, ordinal, name),
            )

    def start_stage(self, run_id: str, stage_id: str, input_value=None) -> None:
        self._current_stage = stage_id
        self._stage_tokens = {}
        self._db.execute_non_query(
            """UPDATE nexus.query_stage SET [state]='running',[input]=?,started_at=SYSUTCDATETIME(),
                   ended_at=NULL,error=NULL WHERE run_id=? AND stage_id=?;
               UPDATE nexus.query_run SET current_stage=?,updated_at=SYSUTCDATETIME() WHERE run_id=?;""",
            (_j(input_value), run_id, stage_id, stage_id, run_id),
        )

    def finish_stage(self, run_id: str, stage_id: str, output_value=None, cost_ms: int = 0) -> None:
        self._db.execute_non_query(
            """UPDATE nexus.query_stage SET [state]='succeeded',[output]=?,tokens=?,cost_ms=?,
                   ended_at=SYSUTCDATETIME() WHERE run_id=? AND stage_id=?""",
            (_j(output_value), _j(self._stage_tokens), int(cost_ms), run_id, stage_id),
        )
        self._current_stage = None

    def fail_stage(self, run_id: str, stage_id: str, error: str, cost_ms: int = 0,
                   cancelled: bool = False, output_value=None) -> None:
        state = "cancelled" if cancelled else "failed"
        self._db.execute_non_query(
              """UPDATE nexus.query_stage SET [state]=?,[output]=?,tokens=?,error=?,cost_ms=?,ended_at=SYSUTCDATETIME()
                 WHERE run_id=? AND stage_id=?;
               UPDATE nexus.query_stage SET [state]='skipped',ended_at=SYSUTCDATETIME()
                 WHERE run_id=? AND ordinal>(SELECT ordinal FROM nexus.query_stage WHERE run_id=? AND stage_id=?);
            """,
            (state, _j(output_value), _j(self._stage_tokens), error, int(cost_ms), run_id, stage_id,
             run_id, run_id, stage_id),
        )
        self._current_stage = None

    def set_scope(self, context) -> None:
        self._db.execute_non_query(
            """UPDATE nexus.query_run SET collection_id=?,collection_name=?,collection_selected_by=?,
                   allowed_stores=?,updated_at=SYSUTCDATETIME() WHERE run_id=?""",
            (context.collection.collection_id, context.collection.name, context.collection.selected_by,
             _j(context.allowed_stores), context.run_id),
        )

    def set_pep_metadata(self, pep) -> None:
        self._node_ops = {n.id: n.op for n in pep.nodes}
        self._node_inputs = {n.id: n.inputs for n in pep.nodes}

    def set_answer(self, run_id: str, result) -> None:
        self._db.execute_non_query(
            "UPDATE nexus.query_run SET answer=?,citations=?,updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (result.answer, _j(result.citations), run_id),
        )

    def finish_query(self, run_id: str, state: str, error: str | None, cost_ms: int) -> None:
        self._db.execute_non_query(
            """UPDATE nexus.query_run SET [state]=?,current_stage=NULL,error=?,cost_ms=?,
                   updated_at=SYSUTCDATETIME() WHERE run_id=?""",
            (state, error, int(cost_ms), run_id),
        )

    # ---------------- WorkflowRecorder（只属于 coordinator stage）----------------
    def on_dag_update(self, run_id: str, dag: dict) -> None:
        self._db.execute_non_query(
            "UPDATE nexus.query_run SET node_count=?,updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (len(dag.get("nodes", [])), run_id),
        )

    def start_node(self, run_id: str, node_id: str) -> None:
        self._db.execute_non_query(
            """MERGE nexus.query_node AS t
               USING (SELECT ? AS run_id,? AS node_id) AS s
                 ON t.run_id=s.run_id AND t.node_id=s.node_id
               WHEN MATCHED THEN UPDATE SET [state]='running',op=?,[input]=?,started_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT(run_id,node_id,[state],op,[input],started_at)
                 VALUES(?,?,'running',?,?,SYSUTCDATETIME());""",
            (run_id, node_id, self._node_ops[node_id], _j(self._node_inputs.get(node_id)),
             run_id, node_id, self._node_ops[node_id], _j(self._node_inputs.get(node_id))),
        )

    def finish_node(self, run_id, node_id, state, output, value, tokens, error, cost_ms) -> None:
        self._db.execute_non_query(
            """MERGE nexus.query_node AS t
               USING (SELECT ? AS run_id,? AS node_id) AS s ON t.run_id=s.run_id AND t.node_id=s.node_id
               WHEN MATCHED THEN UPDATE SET [state]=?,op=?,[output]=?,[value]=?,tokens=?,error=?,
                   cost_ms=?,ended_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT(run_id,node_id,[state],op,[output],[value],tokens,error,cost_ms,started_at,ended_at)
                 VALUES(?,?,?,?,?,?,?,?,?,SYSUTCDATETIME(),SYSUTCDATETIME());""",
            (run_id, node_id, state, self._node_ops[node_id], _j(output), value, _j(tokens), error, cost_ms,
             run_id, node_id, state, self._node_ops[node_id], _j(output), value, _j(tokens), error, cost_ms),
        )

    def bump_tokens(self, run_id: str, tokens: dict) -> None:
        for key, value in (tokens or {}).items():
            amount = int(value or 0)
            self._tokens[key] = self._tokens.get(key, 0) + amount
            self._stage_tokens[key] = self._stage_tokens.get(key, 0) + amount
        self._db.execute_non_query(
            "UPDATE nexus.query_run SET tokens=?,updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (_j(self._tokens), run_id),
        )

    def finish_run(self, run_id: str, state: str, error: str | None, cost_ms: int) -> None:
        """Workflow 自己的终态由 runner 归入 coordinator stage；这里不能提前结束整个 query_run。"""
        return
