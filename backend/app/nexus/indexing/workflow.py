"""Full generation indexing DAG assembly."""
from __future__ import annotations

from services.workflow import Node, Workflow
from services.workflow.node import TASK, VIRTUAL

from .expanders import extract_blocks
from .ops import (
    op_activate,
    op_derive_graph,
    op_embed,
    op_extract_block,
    op_finalize,
    op_parse,
    op_quality_gate,
    op_resolve_persist,
    op_seed_candidate,
)


def build_index_workflow() -> Workflow:
    return (
        Workflow()
        .register("seed_candidate", op_seed_candidate)
        .register("parse", op_parse)
        .register("embed", op_embed)
        .register("extract_block", op_extract_block)
        .register("resolve_persist", op_resolve_persist)
        .register("derive_graph", op_derive_graph)
        .register("quality_gate", op_quality_gate)
        .register("activate", op_activate)
        .register("finalize", op_finalize)
        .register_expander("extract_blocks", extract_blocks)
    )


def build_seed() -> list[Node]:
    """seed retained docs -> parse changed docs -> extract/embed -> resolve -> publish."""
    return [
        Node(
            id="seed_candidate", kind=TASK, op="seed_candidate",
            name="继承未变更文档", phase="seed", layer=0,
        ),
        Node(
            id="parse", kind=TASK, op="parse", name="结构化切块",
            phase="parse", layer=1, depends_on=["seed_candidate"],
        ),
        Node(
            id="extract", kind=VIRTUAL, expander="extract_blocks",
            name="逐块抽取法规断言", phase="extract", layer=2, depends_on=["parse"],
        ),
        Node(
            id="embed", kind=TASK, op="embed", name="向量化并写入搜索",
            phase="embed", layer=2, depends_on=["parse"],
        ),
        Node(
            id="resolve", kind=TASK, op="resolve_persist", name="精确归一并保存断言",
            phase="resolve", layer=3, depends_on=["extract", "embed"],
        ),
        Node(
            id="derive_graph", kind=TASK, op="derive_graph", name="从断言派生图",
            phase="graph", layer=4, depends_on=["resolve"],
        ),
        Node(
            id="quality_gate", kind=TASK, op="quality_gate", name="索引质量门禁",
            phase="quality", layer=5, depends_on=["derive_graph"],
        ),
        Node(
            id="activate", kind=TASK, op="activate", name="原子发布代次",
            phase="activate", layer=6, depends_on=["quality_gate"],
        ),
        Node(
            id="finalize", kind=TASK, op="finalize", name="汇总完成",
            phase="done", layer=7, depends_on=["activate"],
        ),
    ]
