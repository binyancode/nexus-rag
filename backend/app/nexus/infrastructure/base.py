"""Shared SQL repository helpers."""
from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel

from core.services import services
from services.sql_db import sql_db


def jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(jsonable(value), ensure_ascii=False, separators=(",", ":"), default=str)


class SqlRepository:
    def __init__(self, config: dict | None = None):
        self._config = config or {}

    @property
    def db(self) -> sql_db:
        return services[sql_db]

    @staticmethod
    def scope_cte(scope, name: str = "query_scope") -> tuple[str, tuple[str, ...]]:
        """Return a parameterized Store/Generation CTE and its ordered parameters."""
        generation_scope = dict(getattr(scope, "generation_scope", {}) or {})
        allowed_stores = tuple(getattr(scope, "allowed_stores", ()) or ())
        if not generation_scope or set(generation_scope) != set(allowed_stores):
            raise ValueError("a complete frozen Collection generation_scope is required")
        entries = [(store_id, generation_scope[store_id]) for store_id in sorted(allowed_stores)]
        values = ",".join("(?,?)" for _ in entries)
        cte = (
            f"WITH {name}(store_id,generation_id) AS ("
            f"SELECT store_id,generation_id FROM (VALUES {values}) v(store_id,generation_id))"
        )
        params = tuple(value for entry in entries for value in entry)
        return cte, params
