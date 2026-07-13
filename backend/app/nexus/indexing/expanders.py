"""Runtime expansion of one extraction task per block."""
from __future__ import annotations

from services.workflow import Node
from services.workflow.node import TASK


def extract_blocks(ctx) -> list[Node]:
    parsed = ctx.dep("parse") or {}
    blocks = parsed.get("blocks") or []
    nodes: list[Node] = []
    for index, block in enumerate(blocks):
        location = block.article_no or str(block.ordinal)
        nodes.append(Node(
            id=f"extract#{index}",
            kind=TASK,
            op="extract_block",
            name=f"抽取·{block.title}·{location}"[:80],
            phase="extract",
            layer=1,
            sibling_group="extract",
            params={"block": block},
        ))
    return nodes
