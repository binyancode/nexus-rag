"""/api/v1/index —— 建立索引（上传 txt → 异步管线 → 轮询进度）。

- GET  "/stores"          已注册的 block store 列表（下拉用）
- GET  "/collections"     collection 列表
- GET  "/search-indexes"  某 azure_ai_search 凭据下已有的索引名（下拉用）
- POST ""                 上传文件 + 选凭据/类别，启动异步索引，返回 run_id

进度轮询不在这里：那是非敏感的纯 DB 读，由 BFF（.NET）直连 DB 读 nexus.run/run_stage。
说明：UI 选的是「azure_ai_search 凭据」，本端点据此确保一条 search_store 注册
（store_id 由凭据名派生），再把 store_id 交给管线。
"""
from __future__ import annotations

import re
import threading
import uuid

from fastapi import APIRouter, Request

from core.api_handler import api_handler
from services.credential import azure_keyvault_credential_provider
from nexus.index import run_index, cancel_run
from nexus.models.store import Collection, SearchStore
from nexus.stores.store_registry import store_registry

router = APIRouter()

_SLUG = re.compile(r"[^a-zA-Z0-9_-]+")


def _store_id_of(credential_name: str) -> str:
    slug = _SLUG.sub("_", credential_name).strip("_") or "store"
    return f"store_{slug}"[:64]


@router.get("/stores")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_stores(request: Request, reg: store_registry = None):
    return {"stores": [s.model_dump() for s in reg.list_stores()]}


@router.get("/collections")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_collections(request: Request, reg: store_registry = None):
    return {"collections": [c.model_dump() for c in reg.list_collections()]}


@router.get("/search-indexes")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_search_indexes(request: Request, cred: azure_keyvault_credential_provider = None):
    """列出某 azure_ai_search 凭据所指服务下已有的索引名。query: credential（必填）"""
    credential_name = (request.query_params.get("credential") or "").strip()
    if not credential_name:
        return {"state": "error", "message": "credential 必填"}
    c = cred.load(credential_name)
    if c is None:
        return {"state": "error", "message": f"凭据不存在或不可用: {credential_name}"}
    conf = c.to_config()   # {endpoint, key, index_name?, api_version?}
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.indexes import SearchIndexClient
        client = SearchIndexClient(
            conf["endpoint"], AzureKeyCredential(conf["key"]),
            api_version=conf.get("api_version") or "2024-07-01",
        )
        names = sorted(client.list_index_names())
        return {"indexes": names, "default": conf.get("index_name")}
    except Exception as exc:
        return {"state": "error", "message": f"列出索引失败: {exc}"}


@router.post("")
@api_handler.log(sanitize=["files"])
@api_handler.auth()
@api_handler.service()
async def create_index(request: Request, reg: store_registry = None):
    """JSON body:
        files: [{filename, text}]   （前端读取 .txt 文本后提交）
        llm_credential / embedding_credential : 凭据名
        store_credential : azure_ai_search 凭据名（block store）
        index_name       : 目标索引（必填）
        category         : 必填（进入 fullname）
        auto_attach      : bool（实体入网是否自动归一）
        max_parallel     : int（DAG 并行度，默认 8）
    """
    body = await request.json()
    llm = (body.get("llm_credential") or "").strip()
    emb = (body.get("embedding_credential") or "").strip()
    store_credential = (body.get("store_credential") or "").strip()
    index_name = (body.get("index_name") or "").strip() or None
    category = (body.get("category") or "").strip()
    auto_attach = bool(body.get("auto_attach", True))
    overwrite = bool(body.get("overwrite", False))
    try:
        max_parallel = int(body.get("max_parallel", 8))
    except (TypeError, ValueError):
        max_parallel = 8
    max_parallel = max(1, min(64, max_parallel))

    if not (llm and emb and store_credential and category and index_name):
        return {"state": "error",
                "message": "llm_credential / embedding_credential / store_credential / index_name / category 均必填"}

    files: list[tuple[str, str]] = []
    for f in body.get("files", []) or []:
        text = f.get("text")
        if text is None:
            continue
        files.append((f.get("filename") or "untitled.txt", text))
    if not files:
        return {"state": "error", "message": "未收到任何文件"}

    # 确保 store 注册（store_id 由 AI Search 凭据名派生）
    store_id = _store_id_of(store_credential)
    if reg.get_store(store_id) is None or index_name:
        reg.upsert_store(SearchStore(
            store_id=store_id, name=store_credential, credential_name=store_credential,
            index_name=index_name, kind="block", is_default=(reg.default_store() is None),
        ))
    # 系统还没有配置过 Collection 时，创建一个持久化默认范围并纳入所有现有 Store。
    # 一旦用户已有 Collection，绝不擅自修改其成员关系。
    if not reg.list_collections():
        reg.upsert_collection(Collection(
            collection_id="default", name="默认法规库",
            description="系统首次启用查询时创建；可在后续管理功能中调整成员 Store",
            is_public=True, stores=[s.store_id for s in reg.list_stores()],
        ))

    identity = getattr(request.state, "identity", None)
    as_user = identity.user if identity else None
    run_id = uuid.uuid4().hex

    threading.Thread(
        target=run_index,
        args=(run_id, files, llm, emb, store_id, category, max_parallel, auto_attach, overwrite, as_user),
        daemon=True,
    ).start()

    return {"run_id": run_id, "store_id": store_id, "files": [f[0] for f in files]}


@router.post("/runs/{run_id}/cancel")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def cancel_index(request: Request, run_id: str = None):
    """协作式取消一次索引运行。"""
    run_id = run_id or request.path_params.get("run_id")
    ok = cancel_run(run_id)
    return {"run_id": run_id, "cancelling": bool(ok)}
