"""虚拟节点展开器。"""
from __future__ import annotations

from services.workflow import Node
from services.workflow.node import TASK


def extract_expander(ctx) -> list[Node]:
    """把虚拟的 extract 节点展开成「每块一个」的抽取节点(并行)。

    全部打同一个 sibling_group='extract' → 前端 >8 折叠成一个进度节点。
    """
    parse_out = ctx.dep("parse") or {}
    blocks = parse_out.get("blocks", [])
    nodes: list[Node] = []
    for i, b in enumerate(blocks):
        label = f"抽取·{b.title}·{b.section}"[:60]
        nodes.append(Node(
            id=f"extract#{i}", kind=TASK, op="extract", name=label,
            phase="extract", layer=1, sibling_group="extract", params={"block": b},
        ))
    return nodes
