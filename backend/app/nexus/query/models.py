"""查询域的强类型契约：上下文、逻辑 SQG、物理 PEP、算子结果。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CollectionScope(BaseModel):
    collection_id: str
    name: str
    selected_by: Literal["user", "user_default", "only_visible", "semantic_router"]
    allowed_stores: list[str]


class QueryBudgets(BaseModel):
    max_entities: int = 200
    max_blocks: int = 30
    max_tokens: int = 30000


class QueryContext(BaseModel):
    run_id: str
    as_user: str | None = None
    question: str
    collection: CollectionScope
    llm_credential: str
    embedding_credential: str
    max_parallel: int = 8
    budgets: QueryBudgets = Field(default_factory=QueryBudgets)
    categories: list[str] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    entity_catalog: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def allowed_stores(self) -> list[str]:
        return self.collection.allowed_stores


class SQGNode(BaseModel):
    """逻辑节点只表达要做什么；goal 是结构化业务意图，不得出现物理实现参数。"""
    id: str
    op: Literal["Retrieve", "Compare", "Answer"]
    desc: str
    goal: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)


class SQG(BaseModel):
    nodes: list[SQGNode]

    @model_validator(mode="after")
    def validate_graph(self):
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("SQG 节点 id 必须唯一")
        id_set = set(ids)
        for n in self.nodes:
            missing = [x for x in n.inputs if x not in id_set]
            if missing:
                raise ValueError(f"SQG 节点 {n.id} 引用了不存在的输入: {missing}")
            if n.id in n.inputs:
                raise ValueError(f"SQG 节点 {n.id} 不能依赖自己")
        _assert_acyclic({n.id: n.inputs for n in self.nodes}, "SQG")
        answers = [n for n in self.nodes if n.op == "Answer"]
        if len(answers) != 1:
            raise ValueError("SQG 必须且只能包含一个 Answer 终点")
        depended = {x for n in self.nodes for x in n.inputs}
        if answers[0].id in depended:
            raise ValueError("SQG 的 Answer 必须是终点")
        return self


class PEPNode(BaseModel):
    """物理节点：inputs 是具名端口到上游节点 id 的绑定。"""
    id: str
    op: Literal[
        "EntitySearch", "BlockSearch", "Traverse", "Lift", "Ground",
        "Intersect", "Diff", "Union", "Dedup", "BlockUnion", "EvidenceBundle",
    ]
    name: str
    inputs: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    layer: int = 0

    @property
    def depends_on(self) -> list[str]:
        return list(dict.fromkeys(self.inputs.values()))


class PEP(BaseModel):
    nodes: list[PEPNode]
    outputs: dict[str, str]

    @model_validator(mode="after")
    def validate_graph(self):
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("PEP 节点 id 必须唯一")
        id_set = set(ids)
        for n in self.nodes:
            missing = [x for x in n.depends_on if x not in id_set]
            if missing:
                raise ValueError(f"PEP 节点 {n.id} 引用了不存在的输入: {missing}")
        _assert_acyclic({n.id: n.depends_on for n in self.nodes}, "PEP")
        for port, node_id in self.outputs.items():
            if node_id not in id_set:
                raise ValueError(f"PEP 输出 {port} 引用了不存在的节点: {node_id}")
        if set(self.outputs) != {"facts", "evidence"}:
            raise ValueError("PEP 必须显式声明 facts 和 evidence 两个生成器输入")
        return self


@dataclass
class EvidenceGroup:
    key: str
    label: str
    doc_ids: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "doc_ids": self.doc_ids, "items": self.items}

    @classmethod
    def from_value(cls, value: Any) -> "EvidenceGroup":
        return cls(
            key=str(value.get("key") or ""), label=str(value.get("label") or ""),
            doc_ids=list(value.get("doc_ids") or []), items=list(value.get("items") or []),
        )


@dataclass
class QueryResult:
    """所有物理算子的统一输出；kind 决定 items 的业务类型。"""
    kind: Literal["entity_set", "block_set", "evidence_bundle", "answer", "empty"]
    items: list[dict[str, Any]] = field(default_factory=list)
    groups: list[EvidenceGroup] = field(default_factory=list)
    answer: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "items": self.items,
            "groups": [x.to_dict() for x in self.groups],
            "answer": self.answer,
            "citations": self.citations,
            "meta": self.meta,
        }

    @classmethod
    def from_value(cls, value: Any) -> "QueryResult":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict) and value.get("kind"):
            return cls(
                kind=value["kind"], items=value.get("items") or [], answer=value.get("answer"),
                groups=[EvidenceGroup.from_value(x) for x in (value.get("groups") or [])],
                citations=value.get("citations") or [], meta=value.get("meta") or {},
            )
        return cls(kind="empty")


def _assert_acyclic(deps: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError(f"{label} 必须无环，检测到环经过 {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in deps.get(node_id, []):
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in deps:
        visit(node_id)
