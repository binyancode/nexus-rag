"""DAG 节点与执行上下文。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 节点种类
TASK = "task"        # 有 op(注册的处理器),执行一次工作
VIRTUAL = "virtual"  # 有 expander(注册的展开器),运行期展开成物理节点后从图中消失


@dataclass
class Node:
    id: str
    kind: str = TASK
    op: str | None = None            # TASK:处理器 key
    expander: str | None = None      # VIRTUAL:展开器 key
    name: str = ""                   # 人类可读标签(进 dag JSON)
    phase: str = ""                  # 布局分层用(parse|embed|extract|attach|done…)
    layer: int = 0                   # 列位置(拓扑深度,建/展开时定)
    sibling_group: str | None = None # 同父兄弟折叠键(前端 >8 折叠);通常=产生它的虚拟节点 id
    depends_on: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)   # 处理器读 ctx.node.params

    def to_json(self) -> dict:
        d = {
            "id": self.id, "kind": self.kind, "name": self.name,
            "phase": self.phase, "layer": self.layer,
            "depends_on": list(self.depends_on),
        }
        if self.sibling_group:
            d["sibling_group"] = self.sibling_group
        if self.kind == TASK and self.op:
            d["op"] = self.op
        if self.kind == VIRTUAL and self.expander:
            d["expander"] = self.expander
        return d


@dataclass
class NodeContext:
    """传给处理器 / 展开器的运行上下文。"""
    run_id: str
    node: Node
    deps: dict[str, Any]        # {父节点 id: 其 output}(仅成功的父)
    max_parallel: int
    shared: dict[str, Any]      # 每次 run 注入的资源(chat / embedder / stores / store_id …)
    cancel_token: Any = None    # 协作式取消令牌(有 is_cancelled / raise_if_cancelled)

    def dep(self, node_id: str, default=None):
        return self.deps.get(node_id, default)

    def param(self, key: str, default=None):
        return self.node.params.get(key, default)

    def res(self, key: str, default=None):
        return self.shared.get(key, default)

    def raise_if_cancelled(self) -> None:
        if self.cancel_token is not None:
            self.cancel_token.raise_if_cancelled()
