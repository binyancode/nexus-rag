"""Strong logical SQG, typed PEP ports, and operator result contracts."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from nexus.domain import StrictModel

AssertionKind = Literal["norm", "definition", "relation", "deadline", "penalty"]
Modality = Literal["must", "must_not", "may", "should", "factual", "conditional_may"]
SetOperation = Literal["intersection", "difference", "union"]


# ----------------------------------------------------------------------
# SQG: logical intent only. No physical operator, Store, Generation, SQL,
# vector, direction, hop, or Top-K fields are present in these contracts.
# ----------------------------------------------------------------------
class FindSubjectIntent(StrictModel):
    kind: Literal["find_subject_facts"]
    subjects: list[str] = Field(min_length=1, max_length=20)
    target: Literal["assertions", "actions"]
    modalities: list[Modality] = Field(default_factory=list)
    assertion_kinds: list[AssertionKind] = Field(default_factory=list)
    predicate: str | None = Field(default=None, min_length=1, max_length=50)


class CompareSubjectsIntent(StrictModel):
    kind: Literal["compare_subjects"]
    subjects: list[str] = Field(min_length=2, max_length=20)
    target: Literal["assertions", "actions"]
    operation: SetOperation
    modalities: list[Modality] = Field(default_factory=list)
    assertion_kinds: list[AssertionKind] = Field(default_factory=list)
    predicate: str | None = Field(default=None, min_length=1, max_length=50)


class ReverseActionIntent(StrictModel):
    kind: Literal["find_action_subjects"]
    action: str = Field(min_length=1, max_length=1000)
    modalities: list[Modality] = Field(default_factory=list)


class TraverseRelationIntent(StrictModel):
    kind: Literal["traverse_relation"]
    start: str = Field(min_length=1, max_length=1000)
    relation: str = Field(min_length=1, max_length=50)
    inverse: bool = False


class CompareDocumentsIntent(StrictModel):
    kind: Literal["compare_documents"]
    documents: list[str] = Field(min_length=2, max_length=20)
    focus: str = Field(min_length=1)


class SemanticEvidenceIntent(StrictModel):
    kind: Literal["semantic_evidence"]
    query: str = Field(min_length=1)
    documents: list[str] = Field(default_factory=list, max_length=20)


QueryIntent = Annotated[
    FindSubjectIntent
    | CompareSubjectsIntent
    | ReverseActionIntent
    | TraverseRelationIntent
    | CompareDocumentsIntent
    | SemanticEvidenceIntent,
    Field(discriminator="kind"),
]


class SQG(StrictModel):
    """The compiler output: one strongly typed logical query intent."""

    question: str = Field(min_length=1)
    intent: QueryIntent


# ----------------------------------------------------------------------
# PEP: physical plan with explicit typed ports and outputs.
# ----------------------------------------------------------------------
DataKind = Literal["entity_set", "action_set", "fact_set", "evidence_set", "evidence_bundle"]
OperatorName = Literal[
    "EntityLookup", "ActionLookup", "SubjectAssertions", "SubjectActions",
    "ActionSubjects", "AssertionSearch", "GraphTraverse", "FilterModality",
    "Intersect", "Diff", "Union", "GroundAssertions", "BlockSearch",
    "EvidenceBundle",
]


class PortBinding(StrictModel):
    node_id: str = Field(min_length=1, max_length=120)
    kind: DataKind


class EntityLookupParams(StrictModel):
    kind: Literal["EntityLookup"] = "EntityLookup"
    entity_ids: list[str] = Field(min_length=1)
    labels: list[str] = Field(min_length=1)


class ActionLookupParams(StrictModel):
    kind: Literal["ActionLookup"] = "ActionLookup"
    action_ids: list[str] = Field(min_length=1)
    labels: list[str] = Field(min_length=1)


class AssertionFilterParams(StrictModel):
    kind: Literal["SubjectAssertions", "SubjectActions", "AssertionSearch"]
    modalities: list[Modality] = Field(default_factory=list)
    assertion_kinds: list[AssertionKind] = Field(default_factory=list)
    predicate: str | None = Field(default=None, min_length=1, max_length=50)
    entity_ids: list[str] = Field(default_factory=list)


class ActionSubjectsParams(StrictModel):
    kind: Literal["ActionSubjects"] = "ActionSubjects"
    modalities: list[Modality] = Field(default_factory=list)


class GraphTraverseParams(StrictModel):
    kind: Literal["GraphTraverse"] = "GraphTraverse"
    relation: str = Field(min_length=1, max_length=50)
    direction: Literal["out", "in"]
    hops: int = Field(default=1, ge=1, le=10)


class FilterModalityParams(StrictModel):
    kind: Literal["FilterModality"] = "FilterModality"
    modalities: list[Modality] = Field(min_length=1)


class SetParams(StrictModel):
    kind: Literal["Intersect", "Diff", "Union"]
    left_label: str = Field(min_length=1)
    right_label: str = Field(min_length=1)


class GroundAssertionsParams(StrictModel):
    kind: Literal["GroundAssertions"] = "GroundAssertions"
    top: int = Field(default=100, ge=1, le=2000)


class BlockSearchParams(StrictModel):
    kind: Literal["BlockSearch"] = "BlockSearch"
    query: str = Field(min_length=1)
    mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    top: int = Field(default=20, ge=1, le=500)
    document_ids: list[str] = Field(default_factory=list)


class EvidenceBundleParams(StrictModel):
    kind: Literal["EvidenceBundle"] = "EvidenceBundle"
    labels: dict[str, str]


PEPParams = Annotated[
    EntityLookupParams
    | ActionLookupParams
    | AssertionFilterParams
    | ActionSubjectsParams
    | GraphTraverseParams
    | FilterModalityParams
    | SetParams
    | GroundAssertionsParams
    | BlockSearchParams
    | EvidenceBundleParams,
    Field(discriminator="kind"),
]

_OUTPUT_KIND: dict[str, DataKind] = {
    "EntityLookup": "entity_set",
    "ActionLookup": "action_set",
    "SubjectAssertions": "fact_set",
    "SubjectActions": "fact_set",
    "ActionSubjects": "fact_set",
    "AssertionSearch": "fact_set",
    "GraphTraverse": "fact_set",
    "FilterModality": "fact_set",
    "Intersect": "fact_set",
    "Diff": "fact_set",
    "Union": "fact_set",
    "GroundAssertions": "evidence_set",
    "BlockSearch": "evidence_set",
    "EvidenceBundle": "evidence_bundle",
}

_INPUT_KINDS: dict[str, dict[str, tuple[DataKind, ...]]] = {
    "EntityLookup": {},
    "ActionLookup": {},
    "SubjectAssertions": {"subjects": ("entity_set",)},
    "SubjectActions": {"subjects": ("entity_set",)},
    "ActionSubjects": {"actions": ("action_set",)},
    "AssertionSearch": {},
    "GraphTraverse": {"starts": ("entity_set", "action_set")},
    "FilterModality": {"facts": ("fact_set",)},
    "Intersect": {"left": ("fact_set",), "right": ("fact_set",)},
    "Diff": {"left": ("fact_set",), "right": ("fact_set",)},
    "Union": {"left": ("fact_set",), "right": ("fact_set",)},
    "GroundAssertions": {"facts": ("fact_set",)},
    "BlockSearch": {},
    "EvidenceBundle": {"*": ("evidence_set",)},
}


class PEPNode(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    op: OperatorName
    name: str = Field(min_length=1, max_length=200)
    inputs: dict[str, PortBinding] = Field(default_factory=dict)
    output: DataKind
    params: PEPParams
    layer: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_contract(self) -> "PEPNode":
        if self.params.kind != self.op:
            raise ValueError(f"{self.id} params kind does not match operator {self.op}")
        expected_output = _OUTPUT_KIND[self.op]
        if self.output != expected_output:
            raise ValueError(f"{self.id}/{self.op} must output {expected_output}")
        expected_inputs = _INPUT_KINDS[self.op]
        if "*" in expected_inputs:
            if len(self.inputs) < 2:
                raise ValueError(f"{self.id}/{self.op} requires at least two input ports")
            allowed = expected_inputs["*"]
            bad = [port for port, binding in self.inputs.items() if binding.kind not in allowed]
        else:
            if set(self.inputs) != set(expected_inputs):
                raise ValueError(
                    f"{self.id}/{self.op} input ports must be {sorted(expected_inputs)}"
                )
            bad = [
                port for port, binding in self.inputs.items()
                if binding.kind not in expected_inputs[port]
            ]
        if bad:
            raise ValueError(f"{self.id}/{self.op} has incompatible input kinds on {bad}")
        return self

    @property
    def depends_on(self) -> list[str]:
        return list(dict.fromkeys(binding.node_id for binding in self.inputs.values()))


class OutputBinding(StrictModel):
    node_id: str = Field(min_length=1, max_length=120)
    kind: DataKind


class PEP(StrictModel):
    nodes: list[PEPNode] = Field(min_length=1)
    outputs: dict[Literal["facts", "evidence"], OutputBinding]

    @model_validator(mode="after")
    def validate_graph(self) -> "PEP":
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("PEP node ids must be unique")
        by_id = {node.id: node for node in self.nodes}
        for node in self.nodes:
            for port, binding in node.inputs.items():
                upstream = by_id.get(binding.node_id)
                if upstream is None:
                    raise ValueError(f"{node.id}.{port} references unknown node {binding.node_id}")
                if upstream.output != binding.kind:
                    raise ValueError(
                        f"{node.id}.{port} declares {binding.kind}, but {upstream.id} outputs {upstream.output}"
                    )
        self._assert_acyclic({node.id: node.depends_on for node in self.nodes})
        if set(self.outputs) != {"facts", "evidence"}:
            raise ValueError("PEP must explicitly bind facts and evidence outputs")
        for name, binding in self.outputs.items():
            node = by_id.get(binding.node_id)
            if node is None or node.output != binding.kind:
                raise ValueError(f"PEP output {name} has an invalid typed binding")
        if self.outputs["facts"].kind not in {"fact_set", "evidence_set", "evidence_bundle"}:
            raise ValueError("facts output must be a fact or evidence result")
        if self.outputs["evidence"].kind not in {"evidence_set", "evidence_bundle"}:
            raise ValueError("evidence output must be evidence")
        return self

    @staticmethod
    def _assert_acyclic(deps: dict[str, list[str]]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"PEP contains a cycle through {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in deps[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in deps:
            visit(node_id)


class EvidenceGroup(StrictModel):
    key: str
    label: str
    document_ids: list[str] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)


class OperatorResult(StrictModel):
    kind: Literal["entity_set", "action_set", "fact_set", "evidence_set", "evidence_bundle", "answer", "empty"]
    items: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[EvidenceGroup] = Field(default_factory=list)
    answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any) -> "OperatorResult":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict) and value.get("kind"):
            return cls.model_validate(value)
        return cls(kind="empty")
