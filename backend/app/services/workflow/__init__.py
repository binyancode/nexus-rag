"""Workflow 引擎:通用 DAG 执行器(索引 / 检索共用)。

- Node / NodeContext(node.py)、NodeResult(result.py)、WorkflowRecorder(recorder.py)
- Workflow(workflow.py):虚拟节点惰性展开 + 缝合 + 单写者调度 + dag-update 事件 + 并行度

引擎只认 DAG:满足依赖(上游全终态)即调度,全局并发 ≤ max_parallel;不认识任何业务。
"""
from .node import Node, NodeContext
from .result import NodeResult
from .recorder import WorkflowRecorder, NullWorkflowRecorder
from .workflow import Workflow

__all__ = [
    "Node", "NodeContext", "NodeResult",
    "WorkflowRecorder", "NullWorkflowRecorder", "Workflow",
]
