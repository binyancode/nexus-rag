"""索引 DAG 的节点处理器(ops)。

每个函数 = 一个 op:ctx -> NodeResult。
- parse   :切块 + 增量判定(产出 blocks,供下游)
- embed   :向量化 + 写块 + 文档路由(单节点,批处理)
- extract :单块抽取实体/关系(展开后并行,每块一个)
- attach  :实体入网 + 建边（reduce：汇总所有 extract，按类批量归一——一类一次 LLM）
- finalize:收尾

token:每个 op 先 reset_usage() 再干活、结束 pop_usage() 取本节点用量(线程本地,并行不串号)。
所有循环都查 cancel_token,支持协作式取消。
"""
from __future__ import annotations

import json

from core.services import services
from services.workflow import NodeContext, NodeResult
from utils.logger import get_logger

from ...models.document import Document
from ...models.edge import Edge
from ...models.evidence import Evidence
from ...stores.block_store import block_store
from ...stores.document_store import document_store
from ...stores.edge_store import edge_store
from ..chunker import chunk_document, content_hash, make_doc_id, sanitize

_logger = get_logger("nexus.index.ops")

_EMBED_BATCH = 64


def op_parse(ctx: NodeContext) -> NodeResult:
    files = ctx.res("files") or []
    category = ctx.res("category")
    store_id = ctx.res("store_id")
    overwrite = bool(ctx.res("overwrite"))
    docs: list[dict] = []
    blocks_flat: list = []
    skipped = 0
    ds = services[document_store]
    for filename, text in files:
        ctx.raise_if_cancelled()
        title = filename.rsplit(".", 1)[0].strip() or filename
        doc_id = make_doc_id(category, title)
        h = content_hash(text)
        if not overwrite and ds.unchanged(doc_id, h):
            skipped += 1
            continue
        blocks = chunk_document(text, category, title, doc_id)
        for b in blocks:
            b.store_id = store_id
        docs.append({"doc_id": doc_id, "title": title, "hash": h, "blocks": blocks})
        blocks_flat.extend(blocks)
    # 切块一完成就把 run 级计数写进 index_run（不等整个流程结束）
    rec = ctx.res("recorder")
    if rec is not None:
        try:
            rec.set_counts(ctx.run_id, len(docs), len(blocks_flat))
        except Exception:  # noqa: BLE001
            pass
    return NodeResult(
        output={"docs": docs, "blocks": blocks_flat, "skipped": skipped},
        value=f"{len(docs)} 文档 / {len(blocks_flat)} 块（跳过 {skipped}）",
    )


def op_embed(ctx: NodeContext) -> NodeResult:
    parse_out = ctx.dep("parse") or {}
    docs = parse_out.get("docs", [])
    store_id = ctx.res("store_id")
    dims = ctx.res("dims")
    category = ctx.res("category")
    embedder = ctx.res("embedder")
    embedder.reset_usage()
    bs = services[block_store]
    ds = services[document_store]
    written = 0
    for d in docs:
        ctx.raise_if_cancelled()
        blocks = d["blocks"]
        for i in range(0, len(blocks), _EMBED_BATCH):
            ctx.raise_if_cancelled()
            batch = blocks[i:i + _EMBED_BATCH]
            vectors = embedder.embed([b.text for b in batch])
            for b, v in zip(batch, vectors):
                b.vector = v
        written += bs.write_blocks(store_id, blocks, dims)
        ds.upsert(Document(
            doc_id=d["doc_id"], title=d["title"], category=category,
            store_id=store_id, content_hash=d["hash"], block_count=len(blocks),
        ))
    return NodeResult(output={"written": written}, value=f"写入 {written} 块", tokens=embedder.pop_usage())


def op_extract(ctx: NodeContext) -> NodeResult:
    ctx.raise_if_cancelled()
    chat = ctx.res("chat")
    chat.reset_usage()
    block = ctx.param("block")
    entities, relations = ctx.res("extractor").extract(block)
    return NodeResult(
        output={"block": block, "entities": entities, "relations": relations},
        value=f"实体 {len(entities)} / 关系 {len(relations)}",
        tokens=chat.pop_usage(),
    )


def op_attach(ctx: NodeContext) -> NodeResult:
    chat = ctx.res("chat")
    embedder = ctx.res("embedder")
    attach = ctx.res("attach")
    store_id = ctx.res("store_id")
    auto = ctx.res("auto_attach")
    recorder = ctx.res("recorder")
    chat.reset_usage()
    embedder.reset_usage()
    es = services[edge_store]
    blocks = [out for out in ctx.deps.values() if out]

    # 1) 汇总所有块的实体提及 + 各自的出处 fullname
    mentions: list[dict] = []
    ent_fullnames: dict[tuple[str, str], set] = {}
    for out in blocks:
        block = out["block"]
        for e in out["entities"]:
            mentions.append({"name": e.name, "type": e.type, "aliases": e.aliases})
            ent_fullnames.setdefault((e.type, e.name), set()).add(block.fullname)

    # 2) 批量归一 + 入网（一类一次 LLM）
    ctx.raise_if_cancelled()
    if recorder is not None:
        try:
            recorder.progress_node(ctx.run_id, ctx.node.id, f"归一 {len(ent_fullnames)} 个实体…")
        except Exception:  # noqa: BLE001
            pass
    key2id = attach.attach_batch(mentions, chat=chat, embedder=embedder, auto=auto)
    n_nodes = len(set(key2id.values()))

    # 3) 出处 evidence
    for (type_, name), fullnames in ent_fullnames.items():
        eid = key2id.get((type_, name))
        if not eid:
            continue
        for fullname in fullnames:
            es.add_evidence(Evidence(entity_id=eid, fullname=fullname, store_id=store_id, source="llm"))

    # 4) 建边（按块内 relations，名字→id 用块内映射）
    ctx.raise_if_cancelled()
    if recorder is not None:
        try:
            recorder.progress_node(ctx.run_id, ctx.node.id, f"建边…（实体 {n_nodes}）")
        except Exception:  # noqa: BLE001
            pass
    n_edges = 0
    for out in blocks:
        block = out["block"]
        local: dict[str, str] = {}
        for e in out["entities"]:
            eid = key2id.get((e.type, e.name))
            if not eid:
                continue
            local[e.name] = eid
            for a in e.aliases:
                local.setdefault(a, eid)
        for r in out["relations"]:
            src_id = local.get(r.src)
            dst_id = local.get(r.dst)
            if not src_id or not dst_id or src_id == dst_id:
                continue
            es.upsert_edge(Edge(
                src=src_id, type=r.type, dst=dst_id,
                evidence=json.dumps([block.fullname], ensure_ascii=False), source="llm",
            ))
            n_edges += 1

    tokens = chat.pop_usage()
    for k, v in embedder.pop_usage().items():
        tokens[k] = tokens.get(k, 0) + v
    return NodeResult(output={"nodes": n_nodes, "edges": n_edges},
                      value=f"节点 {n_nodes} / 边 {n_edges}", tokens=tokens)


def op_finalize(ctx: NodeContext) -> NodeResult:
    attach_out = ctx.dep("attach") or {}
    embed_out = ctx.dep("embed") or {}
    return NodeResult(
        output={"ok": True},
        value=f"完成 · 写入 {embed_out.get('written', 0)} 块 · 节点 {attach_out.get('nodes', 0)} / 边 {attach_out.get('edges', 0)}",
    )


# ---- 覆盖：只删本次这几篇文档自己的数据（块 + 出处），共享实体/边不动（走 upsert 合并）----
def op_delete_evidence(ctx: NodeContext) -> NodeResult:
    docs = (ctx.dep("parse") or {}).get("docs", [])
    category = ctx.res("category")
    prefixes = [f"{sanitize(category)}.{sanitize(d['title'])}." for d in docs]
    n = services[edge_store].delete_evidence_by_docs(prefixes)
    return NodeResult(output={"deleted": n, "docs": len(docs)},
                      value=f"删除旧出处 {n}（{len(docs)} 文档）")


def op_delete_blocks(ctx: NodeContext) -> NodeResult:
    docs = (ctx.dep("parse") or {}).get("docs", [])
    store_id = ctx.res("store_id")
    doc_ids = [d["doc_id"] for d in docs]
    n = services[block_store].delete_docs(store_id, doc_ids)
    return NodeResult(output={"deleted": n, "docs": len(doc_ids)},
                      value=f"删除旧块 · {n} 文档")
