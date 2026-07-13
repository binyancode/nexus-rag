"""节点处理器的返回值。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NodeResult:
    output: Any = None                 # 传给下游的产物
    value: Any = None                  # 落库的展示值(可选)
    tokens: dict | None = None         # {"input","output","cached","embedding"}(各维独立,无 total)
    error: str | None = None           # 非空 → 该节点 failed
