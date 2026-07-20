"""/api/v1/index —— 建立隔离的完整索引代次。

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
import json
import threading
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api_handler import api_handler
from services.credential import azure_keyvault_credential_provider
from nexus.domain import Collection, SearchStore
from nexus.indexing import cancel_run, run_delete_documents, run_index
from nexus.infrastructure import (
    DocumentRepository,
    GenerationRepository,
    GenerationSearchAdapter,
    StoreCollectionRepository,
)

router = APIRouter()

_SLUG = re.compile(r"[^a-zA-Z0-9_-]+")


def _store_id_of(credential_name: str) -> str:
    slug = _SLUG.sub("_", credential_name).strip("_") or "store"
    return f"store_{slug}"[:64]


def _is_admin(request: Request, registry: StoreCollectionRepository) -> bool:
    identity = getattr(request.state, "identity", None)
    user = identity.user if identity else None
    if not user:
        return False
    rows = registry.db.execute_query(
        "SELECT TOP 1 is_admin FROM nexus.app_user WHERE user_name=?",
        (user,),
    )
    return bool(rows and rows[0].get("is_admin"))


def _forbidden() -> JSONResponse:
    return JSONResponse(
        {"state": "error", "message": "仅管理员可以管理索引文档"},
        status_code=403,
    )


def _document_payload(row: dict) -> dict:
    item = dict(row)
    raw_metadata = item.get("raw_metadata")
    if isinstance(raw_metadata, str):
        try:
            item["raw_metadata"] = json.loads(raw_metadata)
        except json.JSONDecodeError:
            pass
    count_keys = (
        "block_count", "manifest_blocks", "quarantined_blocks", "failed_blocks",
        "unwritten_blocks", "entity_mentions", "action_mentions", "assertions",
        "evidence_count", "graph_edges",
    )
    for key in count_keys:
        item[key] = int(item.get(key) or 0)
    item["health"] = (
        "degraded"
        if item["manifest_blocks"] != item["block_count"]
        or item["failed_blocks"] > 0
        or item["unwritten_blocks"] > 0
        else "warning" if item["quarantined_blocks"] > 0 else "healthy"
    )
    return item


def _quarantine_reason(validation_errors) -> tuple[str, str, list[str]]:
    errors = validation_errors
    if isinstance(errors, str):
        try:
            errors = json.loads(errors)
        except json.JSONDecodeError:
            errors = [{"message": errors}]
    if not isinstance(errors, list):
        errors = []
    messages = [
        str(item.get("message") or item.get("msg") or item)
        for item in errors if item is not None
    ]
    combined = " ".join(messages).casefold()
    if "at least one legal assertion" in combined or "no assertion survived" in combined:
        return (
            "no_valid_assertion",
            "模型识别了实体或行动，但没有生成任何符合契约的完整法规事实（Assertion）。",
            messages,
        )
    if "quote" in combined and ("span" in combined or "source" in combined):
        return (
            "quote_not_grounded",
            "模型给出的事实引文无法在该条原文中连续、逐字定位。",
            messages,
        )
    if "unknown" in combined and "reference" in combined:
        return (
            "invalid_reference",
            "模型输出的事实引用了未声明的实体或行动，内部引用不完整。",
            messages,
        )
    if "modality" in combined and "lexical support" in combined:
        return (
            "unsupported_modality",
            "模型判断的“应当、不得、可以”等法律语气缺少原文词汇支持。",
            messages,
        )
    if "conditional_may" in combined and "condition" in combined:
        return (
            "missing_condition",
            "模型判断为附条件许可，但没有提取出许可成立的条件。",
            messages,
        )
    if messages:
        return "validation_failed", "模型输出未通过结构或原文一致性校验。", messages
    return "audit_unavailable", "该隔离状态从历史代次继承，但没有找到原始校验审计。", []


def _extraction_summary(raw_output) -> dict:
    raw = raw_output
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, dict):
        return {"entities": [], "actions": [], "candidate_assertions": []}

    entities = []
    entity_by_id = {}
    for item in raw.get("entities") or []:
        if not isinstance(item, dict):
            continue
        entity = {
            "local_id": item.get("local_id"),
            "mention_text": item.get("mention_text"),
            "canonical_name": item.get("canonical_name"),
            "entity_type": item.get("entity_type"),
        }
        entities.append(entity)
        if entity["local_id"]:
            entity_by_id[entity["local_id"]] = entity

    actions = []
    action_by_id = {}
    for item in raw.get("actions") or []:
        if not isinstance(item, dict):
            continue
        participants = []
        for participant in item.get("participants") or []:
            if not isinstance(participant, dict):
                continue
            entity = entity_by_id.get(participant.get("entity_local_id")) or {}
            participants.append({
                "role": participant.get("role"),
                "value": (
                    entity.get("canonical_name")
                    or participant.get("value_text")
                    or participant.get("entity_local_id")
                ),
            })
        action = {
            "local_id": item.get("local_id"),
            "canonical_text": item.get("canonical_text"),
            "verb": item.get("verb"),
            "participants": participants,
        }
        actions.append(action)
        if action["local_id"]:
            action_by_id[action["local_id"]] = action

    candidate_assertions = []
    for item in raw.get("assertions") or []:
        if not isinstance(item, dict):
            continue
        reasons = []
        kind = item.get("kind")
        action_local_id = item.get("action_local_id")
        participants = [
            participant for participant in (item.get("participants") or [])
            if isinstance(participant, dict)
        ]
        if kind in {"norm", "deadline", "penalty"} and action_local_id not in action_by_id:
            reasons.append("缺少有效行动")
        if kind == "norm":
            subjects = [participant for participant in participants if participant.get("role") == "subject"]
            if not subjects:
                reasons.append("缺少责任主体")
            elif not any(
                participant.get("entity_local_id")
                or str(participant.get("value_text") or "").strip()
                for participant in subjects
            ):
                reasons.append("责任主体为空")
        candidate_assertions.append({
            "local_id": item.get("local_id"),
            "kind": kind,
            "predicate": item.get("predicate"),
            "modality": item.get("modality"),
            "action": (action_by_id.get(action_local_id) or {}).get("canonical_text"),
            "rejection_reasons": reasons,
        })
    return {
        "entities": entities,
        "actions": actions,
        "candidate_assertions": candidate_assertions,
    }


def _quarantine_payload(row: dict) -> dict:
    item = dict(row)
    code, reason, messages = _quarantine_reason(item.pop("validation_errors", None))
    summary = _extraction_summary(item.pop("raw_output", None))
    rejected_reasons = sorted({
        value
        for assertion in summary["candidate_assertions"]
        for value in assertion["rejection_reasons"]
    })
    if code == "no_valid_assertion" and summary["candidate_assertions"] and rejected_reasons:
        reason = (
            f"模型生成了 {len(summary['candidate_assertions'])} 条候选事实，"
            f"但因{'、'.join(rejected_reasons)}被全部丢弃。"
        )
    item["reason_code"] = code
    item["reason"] = reason
    item["validation_messages"] = messages
    item["extracted_entities"] = summary["entities"]
    item["extracted_actions"] = summary["actions"]
    item["candidate_assertions"] = summary["candidate_assertions"]
    for key in ("ordinal", "attempt_no", "attempt_count", "cost_ms"):
        item[key] = int(item.get(key) or 0)
    return item


@router.get("/stores")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_stores(request: Request, reg: StoreCollectionRepository = None):
    return {"stores": [s.model_dump() for s in reg.list_stores()]}


@router.get("/stores/{store_id}/documents")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_indexed_documents(
    request: Request,
    store_id: str = None,
    reg: StoreCollectionRepository = None,
    generations: GenerationRepository = None,
    documents: DocumentRepository = None,
):
    if not _is_admin(request, reg):
        return _forbidden()
    store_id = store_id or request.path_params.get("store_id")
    store = reg.get_store(store_id)
    if store is None:
        return JSONResponse({"state": "error", "message": "Store 不存在"}, status_code=404)
    generation = generations.active_generation(store_id)
    if generation is None:
        return {
            "store": store.model_dump(mode="json"),
            "generation": None,
            "documents": [],
        }
    rows = documents.generation_document_summaries(generation["generation_id"])
    return {
        "store": store.model_dump(mode="json"),
        "generation": generation,
        "documents": [_document_payload(row) for row in rows],
    }


@router.get("/stores/{store_id}/documents/{document_id}")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def indexed_document_detail(
    request: Request,
    store_id: str = None,
    document_id: str = None,
    reg: StoreCollectionRepository = None,
    generations: GenerationRepository = None,
    documents: DocumentRepository = None,
):
    if not _is_admin(request, reg):
        return _forbidden()
    store_id = store_id or request.path_params.get("store_id")
    document_id = document_id or request.path_params.get("document_id")
    generation = generations.active_generation(store_id)
    if generation is None:
        return JSONResponse({"state": "error", "message": "Store 尚无活动索引"}, status_code=404)
    rows = documents.generation_document_summaries(generation["generation_id"], document_id)
    if not rows:
        return JSONResponse({"state": "error", "message": "活动索引中不存在该文档"}, status_code=404)
    return {"generation": generation, "document": _document_payload(rows[0])}


@router.get("/stores/{store_id}/documents/{document_id}/blocks")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def indexed_document_blocks(
    request: Request,
    store_id: str = None,
    document_id: str = None,
    reg: StoreCollectionRepository = None,
    generations: GenerationRepository = None,
    documents: DocumentRepository = None,
    search: GenerationSearchAdapter = None,
):
    if not _is_admin(request, reg):
        return _forbidden()
    store_id = store_id or request.path_params.get("store_id")
    document_id = document_id or request.path_params.get("document_id")
    generation = generations.active_generation(store_id)
    if generation is None:
        return JSONResponse({"state": "error", "message": "Store 尚无活动索引"}, status_code=404)
    if not documents.generation_document_summaries(generation["generation_id"], document_id):
        return JSONResponse({"state": "error", "message": "活动索引中不存在该文档"}, status_code=404)
    try:
        page = int(request.query_params.get("page") or 1)
        page_size = int(request.query_params.get("page_size") or 20)
    except (TypeError, ValueError):
        page, page_size = 1, 20
    result = search.list_document_blocks(
        store_id,
        generation["generation_id"],
        document_id,
        page=page,
        page_size=page_size,
        dimensions=int(generation["embedding_dimensions"]),
    )
    result["generation_id"] = generation["generation_id"]
    result["document_id"] = document_id
    return result


@router.get("/stores/{store_id}/documents/{document_id}/quarantined-blocks")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def indexed_document_quarantined_blocks(
    request: Request,
    store_id: str = None,
    document_id: str = None,
    reg: StoreCollectionRepository = None,
    generations: GenerationRepository = None,
    documents: DocumentRepository = None,
    search: GenerationSearchAdapter = None,
):
    if not _is_admin(request, reg):
        return _forbidden()
    store_id = store_id or request.path_params.get("store_id")
    document_id = document_id or request.path_params.get("document_id")
    generation = generations.active_generation(store_id)
    if generation is None:
        return JSONResponse({"state": "error", "message": "Store 尚无活动索引"}, status_code=404)
    if not documents.generation_document_summaries(generation["generation_id"], document_id):
        return JSONResponse({"state": "error", "message": "活动索引中不存在该文档"}, status_code=404)
    rows = documents.generation_quarantined_blocks(generation["generation_id"], document_id)
    items = []
    for row in rows:
        item = _quarantine_payload(row)
        block = search.get_block(
            store_id=store_id,
            generation_id=generation["generation_id"],
            block_key=row["block_key"],
            dimensions=int(generation["embedding_dimensions"]),
        )
        item["text"] = (block or {}).get("text")
        items.append(item)
    return {
        "generation_id": generation["generation_id"],
        "document_id": document_id,
        "items": items,
        "total": len(items),
    }


@router.post("/stores/{store_id}/document-deletion-runs")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def delete_indexed_documents(
    request: Request,
    store_id: str = None,
    reg: StoreCollectionRepository = None,
    generations: GenerationRepository = None,
    documents: DocumentRepository = None,
):
    if not _is_admin(request, reg):
        return _forbidden()
    store_id = store_id or request.path_params.get("store_id")
    body = await request.json()
    document_ids = list(dict.fromkeys(
        str(value).strip() for value in (body.get("document_ids") or []) if str(value).strip()
    ))
    expected_generation_id = str(body.get("expected_generation_id") or "").strip()
    reason = str(body.get("reason") or "").strip()[:1000]
    try:
        max_parallel = max(1, min(64, int(body.get("max_parallel") or 8)))
    except (TypeError, ValueError):
        max_parallel = 8
    if not document_ids or not expected_generation_id:
        return JSONResponse(
            {"state": "error", "message": "document_ids 和 expected_generation_id 必填"},
            status_code=400,
        )
    active = generations.active_generation(store_id)
    if active is None:
        return JSONResponse({"state": "error", "message": "Store 尚无活动索引"}, status_code=404)
    if active["generation_id"] != expected_generation_id:
        return JSONResponse(
            {"state": "stale_generation", "message": "活动索引已变化，请刷新文档列表后重试"},
            status_code=409,
        )
    base_documents = {
        row["document_id"]: row
        for row in documents.generation_documents(expected_generation_id)
    }
    missing = sorted(set(document_ids) - set(base_documents))
    if missing:
        return JSONResponse(
            {"state": "error", "message": "以下文档不在活动索引中：" + ", ".join(missing)},
            status_code=400,
        )
    if len(document_ids) >= len(base_documents):
        return JSONResponse(
            {"state": "error", "message": "不能删除 Store 中的全部文档"},
            status_code=400,
        )
    identity = getattr(request.state, "identity", None)
    run_id = uuid.uuid4().hex
    threading.Thread(
        target=run_delete_documents,
        kwargs={
            "run_id": run_id,
            "store_id": store_id,
            "base_generation_id": expected_generation_id,
            "deleted_document_ids": document_ids,
            "max_parallel": max_parallel,
            "as_user": identity.user if identity else None,
            "reason": reason or None,
        },
        daemon=True,
    ).start()
    return JSONResponse(
        {
            "run_id": run_id,
            "store_id": store_id,
            "base_generation_id": expected_generation_id,
            "deleted_document_ids": document_ids,
            "retained_document_count": len(base_documents) - len(document_ids),
            "mode": "delete_documents",
        },
        status_code=202,
    )


@router.get("/collections")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def list_collections(request: Request, reg: StoreCollectionRepository = None):
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
async def create_index(request: Request, reg: StoreCollectionRepository = None):
    """JSON body:
        files: [{filename, text, category?}]（每份文档可覆盖默认 category）
        llm_credential / embedding_credential : 凭据名
        store_credential : azure_ai_search 凭据名（block store）
        index_name       : 目标索引（必填）
        category         : 必填（进入文档与 Block 元数据）
        默认语义：按 category + 文件标题新增或替换文档；未上传文档继承到新代次
        auto_attach / overwrite : 兼容字段，已忽略
        max_parallel     : int（DAG 并行度，默认 8）
    """
    body = await request.json()
    llm = (body.get("llm_credential") or "").strip()
    emb = (body.get("embedding_credential") or "").strip()
    store_credential = (body.get("store_credential") or "").strip()
    index_name = (body.get("index_name") or "").strip() or None
    category = (body.get("category") or "").strip()
    try:
        max_parallel = int(body.get("max_parallel", 8))
    except (TypeError, ValueError):
        max_parallel = 8
    max_parallel = max(1, min(64, max_parallel))

    if not (llm and emb and store_credential and category and index_name):
        return {"state": "error",
                "message": "llm_credential / embedding_credential / store_credential / index_name / category 均必填"}

    files: list[tuple[str, str, str]] = []
    for f in body.get("files", []) or []:
        text = f.get("text")
        if text is None:
            continue
        file_category = (f.get("category") or category).strip()
        if not file_category:
            return {"state": "error", "message": "每份文档必须指定 category，或提供默认 category"}
        files.append((f.get("filename") or "untitled.txt", text, file_category))
    if not files:
        return {"state": "error", "message": "未收到任何文件"}

    # 确保 store 注册（store_id 由 AI Search 凭据名派生）
    store_id = _store_id_of(store_credential)
    existing_store = reg.get_store(store_id)
    if (
        existing_store is not None
        and existing_store.active_generation_id
        and existing_store.index_name != index_name
    ):
        return {
            "state": "error",
            "message": "该 Store 已有活动代次，增量索引不能切换到另一个 AI Search 索引名",
        }
    if existing_store is None or index_name:
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
        kwargs={
            "run_id": run_id,
            "files": files,
            "llm_credential": llm,
            "embedding_credential": emb,
            "store_id": store_id,
            "category": category,
            "max_parallel": max_parallel,
            "as_user": as_user,
        },
        daemon=True,
    ).start()

    return {
        "run_id": run_id,
        "store_id": store_id,
        "files": [f[0] for f in files],
        "mode": "merge_documents",
    }


@router.post("/runs/{run_id}/cancel")
@api_handler.log()
@api_handler.auth()
@api_handler.service()
async def cancel_index(request: Request, run_id: str = None):
    """协作式取消一次索引运行。"""
    run_id = run_id or request.path_params.get("run_id")
    ok = cancel_run(run_id)
    return {"run_id": run_id, "cancelling": bool(ok)}
