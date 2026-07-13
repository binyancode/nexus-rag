"""Business operations for the full isolated-generation indexing DAG."""
from __future__ import annotations

from services.workflow import NodeContext, NodeResult

from .chunker import chunk_document
from .extractor import ExtractionValidationError

_EMBED_BATCH = 64


def op_parse(ctx: NodeContext) -> NodeResult:
    bundles = []
    blocks = []
    seen_documents: set[str] = set()
    documents = ctx.res("documents")
    for item in ctx.res("files") or []:
        ctx.raise_if_cancelled()
        filename, text, file_category = item
        title = filename.rsplit(".", 1)[0].strip() or filename
        bundle = chunk_document(
            text=text,
            category=file_category,
            title=title,
            generation_id=ctx.res("generation_id"),
            raw_metadata={"filename": filename},
        )
        if bundle.document.document_id in seen_documents:
            raise ValueError(f"duplicate logical document in generation: {title}")
        seen_documents.add(bundle.document.document_id)
        bundles.append(bundle)
        blocks.extend(bundle.blocks)
    if not blocks:
        raise ValueError("full generation contains no blocks")
    for bundle in bundles:
        ctx.raise_if_cancelled()
        documents.save_bundle(bundle)
    ctx.res("generations").set_counts(ctx.run_id, ctx.res("generation_id"), {
        "documents": len(bundles), "blocks": len(blocks),
    })
    return NodeResult(
        output={"blocks": blocks},
        value=f"{len(bundles)} 文档 / {len(blocks)} 块",
    )


def op_embed(ctx: NodeContext) -> NodeResult:
    parsed = ctx.dep("parse") or {}
    blocks = parsed.get("blocks") or []
    embedder = ctx.res("embedder")
    search = ctx.res("search")
    documents = ctx.res("documents")
    dimensions = ctx.res("dimensions")
    embedder.reset_usage()
    written = 0
    written_keys: set[str] = set()
    try:
        for offset in range(0, len(blocks), _EMBED_BATCH):
            ctx.raise_if_cancelled()
            batch = blocks[offset:offset + _EMBED_BATCH]
            vectors = embedder.embed([block.text for block in batch])
            count = search.write(ctx.res("store_id"), batch, vectors, dimensions)
            if count != len(batch):
                raise RuntimeError(f"AI Search wrote {count} of {len(batch)} blocks")
            documents.set_search_state([block.block_key for block in batch], "written")
            written_keys.update(block.block_key for block in batch)
            written += count
            ctx.res("recorder").progress_node(
                ctx.run_id, ctx.node.id, f"已写入 {written}/{len(blocks)} 块",
            )
        return NodeResult(
            output={"written": written},
            value=f"写入 {written} 块",
            tokens=embedder.pop_usage(),
        )
    except Exception:
        documents.set_search_state(
            [block.block_key for block in blocks if block.block_key not in written_keys], "failed",
        )
        raise


def op_extract_block(ctx: NodeContext) -> NodeResult:
    block = ctx.param("block")
    documents = ctx.res("documents")
    try:
        ctx.raise_if_cancelled()
        result = ctx.res("extractor").extract(
            ctx.run_id, ctx.res("generation_id"), block,
        )
        state = (
            "quarantined" if result.quarantined
            else ("empty" if result.extraction.empty else "succeeded")
        )
        documents.set_extraction_state(block.block_key, state)
        warning_suffix = f" / 隔离 {len(result.warnings)} 项" if result.warnings else ""
        return NodeResult(
            output={
                "block": block,
                "extraction": result.extraction,
                "warning_count": len(result.warnings),
                "quarantined": bool(result.quarantined),
            },
            value=(
                f"隔离 Block · {result.extraction.empty_reason}"
                if result.quarantined
                else f"显式空结果 · {result.extraction.empty_reason}"
                if result.extraction.empty
                else (
                    f"实体 {len(result.extraction.entities)} / "
                    f"行动 {len(result.extraction.actions)} / "
                    f"断言 {len(result.extraction.assertions)}{warning_suffix}"
                )
            ),
            tokens=result.tokens,
        )
    except Exception as exc:
        documents.set_extraction_state(block.block_key, "failed")
        if isinstance(exc, ExtractionValidationError):
            return NodeResult(error=str(exc), tokens=exc.tokens)
        raise


def op_resolve_persist(ctx: NodeContext) -> NodeResult:
    extraction_results = [
        output for node_id, output in ctx.deps.items()
        if node_id.startswith("extract#") and output
    ]
    ctx.res("recorder").progress_node(
        ctx.run_id, ctx.node.id, f"正在归一 {len(extraction_results)} 个块的抽取结果",
    )
    counts = ctx.res("resolution").persist(ctx.res("generation_id"), extraction_results)
    return NodeResult(
        output=counts,
        value=(
            f"新增实体 {counts.get('entities_created', 0)} / "
            f"行动 {counts.get('actions_created', 0)} / 断言 {counts.get('assertions_created', 0)}"
        ),
    )


def op_derive_graph(ctx: NodeContext) -> NodeResult:
    edge_count = ctx.res("assertions").derive_graph(ctx.res("generation_id"))
    return NodeResult(output={"graph_edges": edge_count}, value=f"派生 {edge_count} 条边")


def op_quality_gate(ctx: NodeContext) -> NodeResult:
    generation_id = ctx.res("generation_id")
    dimensions = ctx.res("dimensions")
    ai_count = ctx.res("search").count_generation(ctx.res("store_id"), generation_id, dimensions)
    passed, metrics = ctx.res("quality").evaluate(ctx.run_id, generation_id, ai_count)
    failed = [metric.code for metric in metrics if not metric.passed]
    if not passed:
        raise ValueError("generation quality gate failed: " + ", ".join(failed))
    counts = ctx.res("assertions").counts(generation_id)
    ctx.res("generations").set_counts(ctx.run_id, generation_id, counts)
    return NodeResult(
        output={
            "passed": True,
            "metrics": [metric.code for metric in metrics],
            "counts": counts,
        },
        value=f"质量门禁通过 · {len(metrics)} 项",
    )


def op_activate(ctx: NodeContext) -> NodeResult:
    ctx.res("generations").activate(ctx.res("store_id"), ctx.res("generation_id"))
    quality = ctx.dep("quality_gate") or {}
    return NodeResult(
        output={
            "generation_id": ctx.res("generation_id"),
            "active": True,
            "counts": quality.get("counts") or {},
        },
        value="已原子切换活动代次",
    )


def op_finalize(ctx: NodeContext) -> NodeResult:
    counts = (ctx.dep("activate") or {}).get("counts") or {}
    return NodeResult(output=counts, value=(
        f"完成 · {counts.get('documents', 0)} 文档 / {counts.get('blocks', 0)} 块 / "
        f"{counts.get('assertions', 0)} 断言 / {counts.get('graph_edges', 0)} 边"
    ))
