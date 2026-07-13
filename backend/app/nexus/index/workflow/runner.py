"""索引 workflow 组装与运行(替代旧 pipeline)。

- build_index_workflow():注册 ops + expander,返回通用 Workflow。
- build_seed():预生成的种子 DAG(parse → {embed ∥ extract(virtual)} → attach → finalize)。
- run_index():建 index_run 行 → 注入运行期资源 → 跑 workflow(可取消)。
- cancel_run():协作式取消某次运行。
"""
from __future__ import annotations

import time

from core.cancellation_token import cancellation_token
from core.services import services
from services.workflow import Node, Workflow
from services.workflow.node import TASK, VIRTUAL
from utils.logger import get_logger

from ...llm.resolve import make_chat, make_embedder
from ...stores.block_store import block_store
from ..attach_entity import attach_entity
from ..entity_extract import entity_extractor
from .expanders import extract_expander
from .ops import (op_attach, op_delete_blocks, op_delete_evidence, op_embed,
                  op_extract, op_finalize, op_parse)
from .recorder import index_run_recorder

_logger = get_logger("nexus.index.runner")

# 运行中的取消令牌注册表:run_id -> token
_RUNS: dict[str, cancellation_token] = {}


def build_index_workflow() -> Workflow:
    wf = Workflow()
    wf.register("parse", op_parse)
    wf.register("embed", op_embed)
    wf.register("extract", op_extract)
    wf.register("attach", op_attach)
    wf.register("finalize", op_finalize)
    wf.register("delete_evidence", op_delete_evidence)
    wf.register("delete_blocks", op_delete_blocks)
    wf.register_expander("extract_expander", extract_expander)
    return wf


def build_seed(overwrite: bool = False, store_id: str | None = None) -> list[Node]:
    """覆盖与不覆盖生成不同的 DAG（不覆盖时没有任何清理节点）。"""
    parse = Node(id="parse", kind=TASK, op="parse", name="切块", phase="parse", layer=0)
    if not overwrite:
        return [
            parse,
            Node(id="extract", kind=VIRTUAL, expander="extract_expander", name="抽取实体/关系",
                 phase="extract", layer=1, depends_on=["parse"]),
            Node(id="embed", kind=TASK, op="embed", name="向量化写块", phase="embed", layer=1, depends_on=["parse"]),
            Node(id="attach", kind=TASK, op="attach", name="实体入网+建边", phase="attach", layer=2, depends_on=["extract"]),
            Node(id="finalize", kind=TASK, op="finalize", name="完成", phase="done", layer=3, depends_on=["attach", "embed"]),
        ]
    # 覆盖：只删本次这几篇文档自己的旧数据——旧块(按 doc_id) + 旧出处(按 fullname 前缀)；
    # 共享的实体/结构边不动，重建时走 upsert 合并。
    # 删除节点只是「排序闸门」：写节点仍按名字从 parse/extract 读数据，不消费删除节点的输出。
    #   embed(写块) 依赖 [parse(取数据), del_blocks(等删块)]
    #   extract/attach(写出处) 依赖链等 del_evidence：让 extract 等删旧出处完再开始重建
    return [
        parse,
        Node(id="del_evidence", kind=TASK, op="delete_evidence", name="删旧出处", phase="cleanup", layer=1, depends_on=["parse"]),
        Node(id="del_blocks", kind=TASK, op="delete_blocks", name="删旧块", phase="cleanup", layer=1, depends_on=["parse"]),
        Node(id="extract", kind=VIRTUAL, expander="extract_expander", name="抽取实体/关系",
             phase="extract", layer=2, depends_on=["parse", "del_evidence"]),
        Node(id="embed", kind=TASK, op="embed", name="向量化写块", phase="embed", layer=2, depends_on=["parse", "del_blocks"]),
        Node(id="attach", kind=TASK, op="attach", name="实体入网+建边", phase="attach", layer=3, depends_on=["extract"]),
        Node(id="finalize", kind=TASK, op="finalize", name="完成", phase="done", layer=4, depends_on=["attach", "embed"]),
    ]


def cancel_run(run_id: str) -> bool:
    """协作式取消:置位令牌,引擎停止派发新节点、在途节点在循环里自行退出。"""
    token = _RUNS.get(run_id)
    if token is None:
        return False
    token.cancel()
    return True


def run_index(run_id: str, files: list[tuple[str, str]], llm_credential: str,
              embedding_credential: str, store_id: str, category: str,
              max_parallel: int = 8, auto_attach: bool = True, overwrite: bool = False,
              as_user: str | None = None) -> None:
    """建立索引:后台线程调用。"""
    rec = index_run_recorder()
    rec.create_run(run_id, as_user, store_id, category, llm_credential, embedding_credential, max_parallel)
    token = cancellation_token()
    _RUNS[run_id] = token
    t0 = time.time()
    try:
        embedder = make_embedder(embedding_credential)
        chat = make_chat(llm_credential)
        dims = embedder.dimensions
        services[block_store].ensure_index(store_id, dims)

        shared = {
            "files": files, "category": category, "store_id": store_id, "dims": dims,
            "auto_attach": auto_attach, "overwrite": overwrite, "chat": chat, "embedder": embedder,
            "extractor": entity_extractor(chat), "attach": services[attach_entity],
            "recorder": rec,
        }
        wf = build_index_workflow()
        res = wf.run(run_id, build_seed(overwrite, store_id), max_parallel, rec, shared, cancel_token=token)

        parse_out = (res.get("outputs") or {}).get("parse") or {}
        rec.set_counts(run_id, len(parse_out.get("docs", [])), len(parse_out.get("blocks", [])))
    except Exception as exc:  # noqa: BLE001
        _logger.exception(f"index run failed: {exc}")
        rec.finish_run(run_id, "failed", str(exc), int((time.time() - t0) * 1000))
    finally:
        _RUNS.pop(run_id, None)
