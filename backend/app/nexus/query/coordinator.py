"""查询协调器：把 PEP 转为通用 Workflow DAG 并执行；不解释语义、不修改计划。"""
from __future__ import annotations

from services.workflow import Node, Workflow
from services.workflow.node import TASK

from .models import PEP, QueryContext, QueryResult
from .operators import register_physical_operators


class QueryCoordinator:
    def build_workflow(self) -> Workflow:
        return register_physical_operators(Workflow())

    def build_nodes(self, pep: PEP) -> list[Node]:
        layers = _topological_layers(pep)
        return [
            Node(
                id=n.id,
                kind=TASK,
                op=n.op,
                name=n.name,
                phase=n.op,
                layer=layers[n.id],
                depends_on=n.depends_on,
                params={**n.params, "_inputs": n.inputs},
            )
            for n in pep.nodes
        ]

    def execute(self, context: QueryContext, pep: PEP, recorder, chat, embedder,
                cancel_token=None) -> dict:
        result = self.build_workflow().run(
            context.run_id,
            self.build_nodes(pep),
            context.max_parallel,
            recorder,
            shared={
                "query_context": context,
                "chat": chat,
                "embedder": embedder,
            },
            cancel_token=cancel_token,
        )
        outputs = result.get("outputs") or {}
        return {
            **result,
            "facts": QueryResult.from_value(outputs.get(pep.outputs["facts"])),
            "evidence": QueryResult.from_value(outputs.get(pep.outputs["evidence"])),
        }


def _topological_layers(pep: PEP) -> dict[str, int]:
    deps = {n.id: n.depends_on for n in pep.nodes}
    memo: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id not in memo:
            memo[node_id] = 0 if not deps[node_id] else 1 + max(depth(x) for x in deps[node_id])
        return memo[node_id]

    return {node_id: depth(node_id) for node_id in deps}
