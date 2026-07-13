"""index_run_recorder：把 workflow 事件落到 nexus.index_run / nexus.index_node。

实现 WorkflowRecorder（引擎单写者线程调用，无需加锁）。
额外的 create_run / set_counts 是领域字段，引擎看不到，由索引 runner 调。
"""
from __future__ import annotations

import json

from core.services import services
from services.sql_db import sql_db
from services.workflow import WorkflowRecorder
from utils.logger import get_logger

_logger = get_logger("nexus.index_recorder")


def _j(obj) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False, default=str)


class index_run_recorder(WorkflowRecorder):
    def __init__(self):
        self._tokens: dict = {}      # run 级 token 聚合（单写者累加）

    @property
    def _db(self) -> sql_db:
        return services[sql_db]

    # ---------------- 领域字段（引擎之外）----------------
    def create_run(self, run_id, as_user, store_id, category,
                   llm_credential, embedding_credential, max_parallel) -> None:
        self._db.execute_non_query(
            """INSERT INTO nexus.index_run
                   (run_id, as_user, store_id, category, llm_credential, embedding_credential,
                    max_parallel, [state], created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'running', SYSUTCDATETIME(), SYSUTCDATETIME())""",
            (run_id, as_user, store_id, category, llm_credential, embedding_credential, int(max_parallel)),
        )

    def set_counts(self, run_id, doc_count: int, block_count: int) -> None:
        self._db.execute_non_query(
            "UPDATE nexus.index_run SET doc_count=?, block_count=?, updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (int(doc_count), int(block_count), run_id),
        )

    # ---------------- WorkflowRecorder ----------------
    def on_dag_update(self, run_id, dag: dict) -> None:
        node_count = len(dag.get("nodes", []))
        self._db.execute_non_query(
            "UPDATE nexus.index_run SET dag=?, node_count=?, updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (_j(dag), node_count, run_id),
        )

    def start_node(self, run_id, node_id) -> None:
        # 懒插入：开始执行才建行
        self._db.execute_non_query(
            """MERGE nexus.index_node AS t
               USING (SELECT ? AS run_id, ? AS node_id) AS s
                   ON t.run_id=s.run_id AND t.node_id=s.node_id
               WHEN MATCHED THEN UPDATE SET [state]='running', started_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT (run_id, node_id, [state], started_at)
                   VALUES (?, ?, 'running', SYSUTCDATETIME());""",
            (run_id, node_id, run_id, node_id),
        )

    def finish_node(self, run_id, node_id, state, output, value, tokens, error, cost_ms) -> None:
        disp = value if isinstance(value, str) else (output if isinstance(output, str) else None)
        self._db.execute_non_query(
            """MERGE nexus.index_node AS t
               USING (SELECT ? AS run_id, ? AS node_id) AS s
                   ON t.run_id=s.run_id AND t.node_id=s.node_id
               WHEN MATCHED THEN UPDATE SET
                   [state]=?, [output]=?, tokens=?, error=?, cost_ms=?, ended_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (run_id, node_id, [state], [output], tokens, error, cost_ms, started_at, ended_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME());""",
            (run_id, node_id,
             state, disp, _j(tokens) if tokens else None, error, cost_ms,
             run_id, node_id, state, disp, _j(tokens) if tokens else None, error, cost_ms),
        )

    def progress_node(self, run_id, node_id, output) -> None:
        # 节点执行中的增量进度：只刷新该行 output（由 worker 线程调用，单行更新安全）
        self._db.execute_non_query(
            "UPDATE nexus.index_node SET [output]=? WHERE run_id=? AND node_id=?",
            (output, run_id, node_id),
        )

    def bump_tokens(self, run_id, tokens: dict) -> None:
        for k, v in (tokens or {}).items():
            self._tokens[k] = self._tokens.get(k, 0) + (v or 0)
        self._db.execute_non_query(
            "UPDATE nexus.index_run SET tokens=?, updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (_j(self._tokens), run_id),
        )

    def finish_run(self, run_id, state, error, cost_ms) -> None:
        self._db.execute_non_query(
            "UPDATE nexus.index_run SET [state]=?, error=?, cost_ms=?, updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (state, error, cost_ms, run_id),
        )
