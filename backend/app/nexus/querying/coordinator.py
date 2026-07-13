"""Stage 4: translate a validated PEP to the generic Workflow and run it only."""
from __future__ import annotations

from nexus.domain import QueryContext
from services.workflow import Node, Workflow
from services.workflow.node import TASK

from .models import OperatorResult, PEP
from .operators import register_physical_operators


class QueryCoordinator:
    def build_workflow(self) -> Workflow:
        return register_physical_operators(Workflow())

    @staticmethod
    def build_nodes(pep: PEP) -> list[Node]:
        return [
            Node(
                id=node.id,
                kind=TASK,
                op=node.op,
                name=node.name,
                phase=node.op,
                layer=node.layer,
                depends_on=node.depends_on,
                params={
                    **node.params.model_dump(mode="json"),
                    "_inputs": {
                        port: binding.node_id for port, binding in node.inputs.items()
                    },
                },
            )
            for node in pep.nodes
        ]

    def execute(
        self,
        *,
        context: QueryContext,
        pep: PEP,
        recorder,
        embedder,
        cancel_token=None,
    ) -> dict:
        result = self.build_workflow().run(
            context.run_id,
            self.build_nodes(pep),
            context.max_parallel,
            recorder,
            shared={"query_context": context, "embedder": embedder},
            cancel_token=cancel_token,
        )
        outputs = result.get("outputs") or {}
        return {
            **result,
            "facts": OperatorResult.from_value(outputs.get(pep.outputs["facts"].node_id)),
            "evidence": OperatorResult.from_value(outputs.get(pep.outputs["evidence"].node_id)),
        }
