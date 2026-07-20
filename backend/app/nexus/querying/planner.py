"""Stage 3: deterministic SQG binding and PEP template planning."""
from __future__ import annotations

from nexus.domain import QueryContext

from .binder import VocabularyBinder
from .models import (
    ActionLookupParams,
    ActionSubjectsParams,
    AssertionFilterParams,
    BlockSearchParams,
    CompareDocumentsIntent,
    CompareSubjectsIntent,
    EntityLookupParams,
    EvidenceBundleParams,
    FilterModalityParams,
    FindSubjectIntent,
    GraphTraverseParams,
    GroundAssertionsParams,
    OutputBinding,
    PEP,
    PEPNode,
    PortBinding,
    ReverseActionIntent,
    SQG,
    SemanticEvidenceIntent,
    SetParams,
    TraverseRelationIntent,
)


class DeterministicPlanner:
    """Maps one strong logical intent to a reviewed physical template; no LLM is called."""

    def plan(self, context: QueryContext, sqg: SQG) -> PEP:
        binder = VocabularyBinder(context)
        intent = sqg.intent
        nodes: list[PEPNode] = []
        if isinstance(intent, FindSubjectIntent):
            facts = self._subject_branch(nodes, binder, intent, 1)
            return self._with_ground(context, nodes, facts)
        if isinstance(intent, CompareSubjectsIntent):
            branch_ids = [
                self._subject_branch(nodes, binder, intent, index, subject)
                for index, subject in enumerate(intent.subjects, 1)
            ]
            facts = branch_ids[0]
            left_label = intent.subjects[0]
            op = {"intersection": "Intersect", "difference": "Diff", "union": "Union"}[intent.operation]
            for index, right in enumerate(branch_ids[1:], 2):
                set_id = f"set_{index - 1}"
                nodes.append(self._node(
                    nodes,
                    node_id=set_id,
                    op=op,
                    name=f"{intent.operation}: {left_label} / {intent.subjects[index - 1]}",
                    inputs={
                        "left": PortBinding(node_id=facts, kind="fact_set"),
                        "right": PortBinding(node_id=right, kind="fact_set"),
                    },
                    output="fact_set",
                    params=SetParams(
                        kind=op,
                        left_label=left_label,
                        right_label=intent.subjects[index - 1],
                    ),
                ))
                facts = set_id
                left_label = f"{left_label} {intent.operation} {intent.subjects[index - 1]}"
            return self._with_ground(context, nodes, facts)
        if isinstance(intent, ReverseActionIntent):
            action = binder.action(intent.action)
            nodes.append(self._node(
                nodes,
                node_id="action_lookup",
                op="ActionLookup",
                name=f"绑定行动：{action.label}",
                inputs={}, output="action_set",
                params=ActionLookupParams(action_ids=[action.node_id], labels=[action.label]),
            ))
            nodes.append(self._node(
                nodes,
                node_id="action_subjects",
                op="ActionSubjects",
                name="反查行动主体",
                inputs={"actions": PortBinding(node_id="action_lookup", kind="action_set")},
                output="fact_set",
                params=ActionSubjectsParams(modalities=intent.modalities),
            ))
            return self._with_ground(context, nodes, "action_subjects")
        if isinstance(intent, TraverseRelationIntent):
            start = binder.node(intent.start, intent.start_type)
            lookup_op = "EntityLookup" if start.kind == "entity" else "ActionLookup"
            lookup_output = "entity_set" if start.kind == "entity" else "action_set"
            lookup_params = (
                EntityLookupParams(entity_ids=[start.node_id], labels=[start.label])
                if start.kind == "entity"
                else ActionLookupParams(action_ids=[start.node_id], labels=[start.label])
            )
            nodes.append(self._node(
                nodes,
                node_id="start_lookup", op=lookup_op, name=f"绑定起点：{start.label}",
                inputs={}, output=lookup_output, params=lookup_params,
            ))
            nodes.append(self._node(
                nodes,
                node_id="graph_traverse", op="GraphTraverse", name=f"关联：{intent.relation}",
                inputs={"starts": PortBinding(node_id="start_lookup", kind=lookup_output)},
                output="fact_set",
                params=GraphTraverseParams(
                    relation=intent.relation,
                    direction="in" if intent.inverse else "out",
                    hops=1,
                ),
            ))
            return self._with_ground(context, nodes, "graph_traverse")
        if isinstance(intent, CompareDocumentsIntent):
            bound = [binder.document(title) for title in intent.documents]
            inputs: dict[str, PortBinding] = {}
            labels: dict[str, str] = {}
            per_branch = max(1, context.budgets.max_blocks // len(bound))
            for index, document in enumerate(bound, 1):
                node_id = f"document_search_{index}"
                port = f"document_{index}"
                nodes.append(self._node(
                    nodes,
                    node_id=node_id, op="BlockSearch", name=f"文档证据：{document.title}",
                    inputs={}, output="evidence_set",
                    params=BlockSearchParams(
                        query=intent.focus,
                        mode="hybrid",
                        top=per_branch,
                        document_ids=[document.document_id],
                    ),
                ))
                inputs[port] = PortBinding(node_id=node_id, kind="evidence_set")
                labels[port] = document.title
            nodes.append(self._node(
                nodes,
                node_id="evidence_bundle", op="EvidenceBundle", name="按文档汇总证据",
                inputs=inputs, output="evidence_bundle",
                params=EvidenceBundleParams(labels=labels),
            ))
            binding = OutputBinding(node_id="evidence_bundle", kind="evidence_bundle")
            return PEP(nodes=nodes, outputs={"facts": binding, "evidence": binding})
        if isinstance(intent, SemanticEvidenceIntent):
            document_ids = [binder.document(title).document_id for title in intent.documents]
            nodes.append(self._node(
                nodes,
                node_id="semantic_evidence", op="BlockSearch", name="开放语义证据检索",
                inputs={}, output="evidence_set",
                params=BlockSearchParams(
                    query=intent.query,
                    mode="hybrid",
                    top=context.budgets.max_blocks,
                    document_ids=list(dict.fromkeys(document_ids)),
                ),
            ))
            binding = OutputBinding(node_id="semantic_evidence", kind="evidence_set")
            return PEP(nodes=nodes, outputs={"facts": binding, "evidence": binding})
        raise TypeError(f"unsupported SQG intent: {type(intent).__name__}")

    def _subject_branch(
        self,
        nodes: list[PEPNode],
        binder: VocabularyBinder,
        intent: FindSubjectIntent | CompareSubjectsIntent,
        index: int,
        subject_name: str | None = None,
    ) -> str:
        names = [subject_name] if subject_name is not None else list(intent.subjects)
        bound = [binder.entity(name) for name in names]
        lookup_id = f"subject_lookup_{index}"
        facts_id = f"subject_{intent.target}_{index}"
        nodes.append(self._node(
            nodes,
            node_id=lookup_id, op="EntityLookup", name="绑定主体：" + "、".join(item.label for item in bound),
            inputs={}, output="entity_set",
            params=EntityLookupParams(
                entity_ids=[item.node_id for item in bound],
                labels=[item.label for item in bound],
            ),
        ))
        operator = "SubjectAssertions" if intent.target == "assertions" else "SubjectActions"
        nodes.append(self._node(
            nodes,
            node_id=facts_id, op=operator,
            name="查找主体断言" if intent.target == "assertions" else "查找主体行动",
            inputs={"subjects": PortBinding(node_id=lookup_id, kind="entity_set")},
            output="fact_set",
            params=AssertionFilterParams(
                kind=operator,
                modalities=[],
                assertion_kinds=intent.assertion_kinds,
                predicate=intent.predicate,
                entity_ids=[],
            ),
        ))
        if intent.modalities:
            filtered_id = f"modality_filter_{index}"
            nodes.append(self._node(
                nodes,
                node_id=filtered_id, op="FilterModality", name="筛选法律模态",
                inputs={"facts": PortBinding(node_id=facts_id, kind="fact_set")},
                output="fact_set",
                params=FilterModalityParams(modalities=intent.modalities),
            ))
            return filtered_id
        return facts_id

    @staticmethod
    def _with_ground(context: QueryContext, nodes: list[PEPNode], facts_id: str) -> PEP:
        ground_id = "ground_assertions"
        nodes.append(DeterministicPlanner._node(
            nodes,
            node_id=ground_id, op="GroundAssertions", name="取得精确断言证据",
            inputs={"facts": PortBinding(node_id=facts_id, kind="fact_set")},
            output="evidence_set",
            params=GroundAssertionsParams(top=context.budgets.max_blocks),
        ))
        return PEP(nodes=nodes, outputs={
            "facts": OutputBinding(node_id=facts_id, kind="fact_set"),
            "evidence": OutputBinding(node_id=ground_id, kind="evidence_set"),
        })

    @staticmethod
    def _node(
        nodes: list[PEPNode],
        *,
        node_id: str,
        op: str,
        name: str,
        inputs: dict[str, PortBinding],
        output: str,
        params,
    ) -> PEPNode:
        layers = {node.id: node.layer for node in nodes}
        layer = 0 if not inputs else 1 + max(layers[binding.node_id] for binding in inputs.values())
        return PEPNode(
            id=node_id,
            op=op,
            name=name,
            inputs=inputs,
            output=output,
            params=params,
            layer=layer,
        )
