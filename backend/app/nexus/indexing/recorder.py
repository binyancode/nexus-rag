"""Workflow recorder for the final index_run/index_node schema."""
from __future__ import annotations

import json
from typing import Any

from nexus.infrastructure import GenerationRepository
from services.workflow import WorkflowRecorder


def _json(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    def fallback(item):
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        return str(item)

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=fallback)


class IndexRunRecorder(WorkflowRecorder):
    def __init__(self, generations: GenerationRepository, generation_id: str):
        self.generations = generations
        self.generation_id = generation_id
        self._tokens: dict[str, Any] = {}
        self._nodes: dict[str, dict] = {}
        self._errors: list[str] = []

    @property
    def db(self):
        return self.generations.db

    def on_dag_update(self, run_id: str, dag: dict) -> None:
        self._nodes = {node["id"]: node for node in dag.get("nodes", [])}
        self.db.execute_non_query(
            """UPDATE nexus.index_run
               SET dag=?, node_count=?, updated_at=SYSUTCDATETIME()
               WHERE run_id=?""",
            (_json(dag), len(self._nodes), run_id),
        )

    def start_node(self, run_id: str, node_id: str) -> None:
        node = self._nodes.get(node_id, {})
        op = node.get("op")
        input_value = _json({"depends_on": node.get("depends_on", [])})
        phase = node.get("phase")
        self.generations.set_phase(run_id, phase)
        self.db.execute_non_query(
            """MERGE nexus.index_node AS t
               USING (SELECT ? AS run_id, ? AS node_id) AS s
                 ON t.run_id=s.run_id AND t.node_id=s.node_id
               WHEN MATCHED THEN UPDATE SET
                   [state]='running', op=?, [input]=?, [output]=NULL, [value]=NULL,
                   tokens=NULL, error=NULL, cost_ms=NULL,
                   started_at=SYSUTCDATETIME(), ended_at=NULL
               WHEN NOT MATCHED THEN INSERT
                   (run_id, node_id, [state], op, [input], started_at)
                   VALUES (?, ?, 'running', ?, ?, SYSUTCDATETIME());""",
            (run_id, node_id, op, input_value, run_id, node_id, op, input_value),
        )

    def finish_node(
        self,
        run_id: str,
        node_id: str,
        state: str,
        output,
        value,
        tokens: dict | None,
        error: str | None,
        cost_ms: int,
    ) -> None:
        node = self._nodes.get(node_id, {})
        display = value if isinstance(value, str) else None
        persisted_output = output
        if node.get("op") == "extract_block" and isinstance(output, dict):
            extraction = output.get("extraction")
            persisted_output = {
                "block_key": getattr(output.get("block"), "block_key", None),
                "empty": getattr(extraction, "empty", None),
                "entity_count": len(getattr(extraction, "entities", []) or []),
                "action_count": len(getattr(extraction, "actions", []) or []),
                "assertion_count": len(getattr(extraction, "assertions", []) or []),
                "warning_count": int(output.get("warning_count") or 0),
                "quarantined": bool(output.get("quarantined")),
            }
        if error:
            self._errors.append(f"{node_id}: {error}")
        self.db.execute_non_query(
            """MERGE nexus.index_node AS t
               USING (SELECT ? AS run_id, ? AS node_id) AS s
                 ON t.run_id=s.run_id AND t.node_id=s.node_id
               WHEN MATCHED THEN UPDATE SET
                   [state]=?, op=COALESCE(t.op, ?), [output]=?, [value]=?, tokens=?,
                   error=?, cost_ms=?, ended_at=SYSUTCDATETIME()
               WHEN NOT MATCHED THEN INSERT
                   (run_id, node_id, [state], op, [output], [value], tokens, error,
                    cost_ms, started_at, ended_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME());""",
            (
                run_id, node_id,
                state, node.get("op"), _json(persisted_output), display, _json(tokens), error, int(cost_ms),
                run_id, node_id, state, node.get("op"), _json(persisted_output), display,
                _json(tokens), error, int(cost_ms),
            ),
        )

    def progress_node(self, run_id: str, node_id: str, output: str) -> None:
        self.db.execute_non_query(
            "UPDATE nexus.index_node SET [value]=? WHERE run_id=? AND node_id=?",
            (str(output), run_id, node_id),
        )

    def bump_tokens(self, run_id: str, tokens: dict) -> None:
        for key, value in (tokens or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self._tokens[key] = int(self._tokens.get(key, 0) or 0) + int(value)
            else:
                self._tokens[key] = value
        self.db.execute_non_query(
            "UPDATE nexus.index_run SET tokens=?, updated_at=SYSUTCDATETIME() WHERE run_id=?",
            (_json(self._tokens), run_id),
        )

    def finish_run(self, run_id: str, state: str, error: str | None, cost_ms: int) -> None:
        final_error = error or ("\n".join(self._errors) if self._errors else None)
        self.db.execute_non_query(
            """UPDATE nexus.index_run
               SET [state]=?, current_phase=NULL, error=?, cost_ms=?, updated_at=SYSUTCDATETIME()
               WHERE run_id=?""",
            (state, final_error, int(cost_ms), run_id),
        )
        self.generations.mark_terminal(run_id, self.generation_id, state)
