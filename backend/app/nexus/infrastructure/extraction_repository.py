"""Audit repository for every block extraction attempt."""
from __future__ import annotations

from .base import SqlRepository, json_text


class ExtractionAttemptRepository(SqlRepository):
    def record(
        self,
        *,
        run_id: str,
        generation_id: str,
        block_key: str,
        attempt_no: int,
        state: str,
        prompt_version: str,
        raw_output: str | None,
        validation_errors: list[dict] | None,
        tokens: dict | None,
        cost_ms: int,
    ) -> None:
        if state not in {"succeeded", "empty", "quarantined", "invalid", "failed"}:
            raise ValueError(f"invalid extraction attempt state: {state}")
        self.db.execute_non_query(
            """INSERT INTO nexus.block_extraction_attempt
                   (run_id, generation_id, block_key, attempt_no, [state], prompt_version,
                    raw_output, validation_errors, tokens, cost_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, generation_id, block_key, int(attempt_no), state, prompt_version,
                raw_output, json_text(validation_errors), json_text(tokens), int(cost_ms),
            ),
        )
