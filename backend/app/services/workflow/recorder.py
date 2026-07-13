"""Workflow 持久化接口(依赖倒置)。

引擎只依赖此接口;index / query 各给一个写不同表的实现。
所有回调都由引擎的**单一调度线程**调用 → 实现里无需加锁。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class WorkflowRecorder(ABC):
    # —— 整图(结构):初始 + 每次虚拟节点展开时被调用,传当前完整 DAG ——
    @abstractmethod
    def on_dag_update(self, run_id: str, dag: dict) -> None: ...

    # —— 节点生命周期(懒插入:开始执行才建行)——
    @abstractmethod
    def start_node(self, run_id: str, node_id: str) -> None: ...

    @abstractmethod
    def finish_node(self, run_id: str, node_id: str, state: str,
                    output, value, tokens: dict | None, error: str | None, cost_ms: int) -> None: ...

    def progress_node(self, run_id: str, node_id: str, output: str) -> None:
        """节点执行中的增量进度(可选;默认忽略)。注意：可能由 worker 线程调用,
        实现里只更新该节点自己那一行,不与他人竞争。"""
        return None

    # —— run 级 token 聚合(增量);实现按已知键映到自己的列/JSON ——
    @abstractmethod
    def bump_tokens(self, run_id: str, tokens: dict) -> None: ...

    # —— run 收尾 ——
    @abstractmethod
    def finish_run(self, run_id: str, state: str, error: str | None, cost_ms: int) -> None: ...


class NullWorkflowRecorder(WorkflowRecorder):
    """空实现(测试 / 未接库时)。"""
    def on_dag_update(self, run_id, dag): pass
    def start_node(self, run_id, node_id): pass
    def finish_node(self, run_id, node_id, state, output, value, tokens, error, cost_ms): pass
    def progress_node(self, run_id, node_id, output): pass
    def bump_tokens(self, run_id, tokens): pass
    def finish_run(self, run_id, state, error, cost_ms): pass
