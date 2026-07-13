import { service } from '../common/APIService.js'
import { backendUrl } from '../bff/Config.js'

// 建立索引：上传文本 → 异步管线 → 轮询进度。均走 Python 后端（unwrap=false）。

export interface IndexFile {
  filename: string
  text: string
  category?: string
}

export interface CreateIndexPayload {
  files: IndexFile[]
  llm_credential: string
  embedding_credential: string
  store_credential: string
  index_name?: string
  category: string
  max_parallel?: number
}

export interface CreateIndexResult {
  run_id: string
  store_id: string
  files: string[]
}

// —— DAG 结构（来自 index_run.dag，前端据此画图；不从 node 表拼依赖）——
export interface DagNode {
  id: string
  kind: string                 // task | virtual
  name: string
  phase: string
  layer: number
  sibling_group?: string       // 同父兄弟折叠键（>8 折叠）
  depends_on: string[]
  op?: string
  expander?: string
}
export interface Dag {
  version: number
  nodes: DagNode[]
}

// token 明细（各维独立，无 total）
export interface TokenUsage {
  input?: number
  output?: number
  cached?: number
  embedding?: number
}

// —— 节点运行态（来自 index_node，按 node_id 合并进 DAG）——
export interface IndexNodeState {
  node_id: string
  state: string                // running | succeeded | failed | skipped | cancelled
  tokens: string | null        // JSON
  output: string | null
  error: string | null
  cost_ms: number | null
  started_at: string | null
  ended_at: string | null
}

export interface IndexRunInfo {
  run_id: string
  state: string                // running | succeeded | failed | cancelled
  category: string | null
  store_id: string | null
  max_parallel: number
  doc_count: number
  block_count: number
  node_count: number
  tokens: string | null        // JSON 聚合
  dag: string | null           // JSON 结构
  error: string | null
  cost_ms: number
  created_at: string | null
  updated_at: string | null
}

export interface IndexRunData {
  run: IndexRunInfo
  nodes: IndexNodeState[]
}

// —— 运行历史列表项（来自 index_run，不含 dag 大字段）——
export interface IndexRunListItem {
  run_id: string
  as_user: string | null
  category: string | null
  store_id: string | null
  state: string
  doc_count: number
  block_count: number
  node_count: number
  tokens: string | null        // JSON 聚合
  cost_ms: number
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface StoreInfo {
  store_id: string
  name: string
  credential_name: string
  index_name: string | null
  kind: string
  is_default: boolean
}

export async function createIndex(payload: CreateIndexPayload): Promise<CreateIndexResult> {
  const url = await backendUrl('index')
  return service.post(url, payload, true, false)
}

export async function getIndexRun(runId: string): Promise<IndexRunData> {
  // 进度是非敏感纯 DB 读 → 走 BFF（.NET 直连 DB），不打 Python。
  return service.get('index-runs/' + encodeURIComponent(runId), true, true, 'application/json', true)
}

export async function listIndexRuns(top = 100): Promise<IndexRunListItem[]> {
  // 运行历史列表：非敏感 DB 读 → 走 BFF。
  const res = await service.get('index-runs?top=' + top, true, true, 'application/json', true)
  return res?.runs ?? []
}

export async function cancelIndex(runId: string): Promise<{ run_id: string; cancelling: boolean }> {
  // 取消要走 Python（取消令牌在 workflow 进程内）。
  const url = await backendUrl('index/runs/' + encodeURIComponent(runId) + '/cancel')
  return service.post(url, {}, true, false)
}

export async function listStores(): Promise<StoreInfo[]> {
  const url = await backendUrl('index/stores')
  const res = await service.get(url, true, false)
  return res.stores ?? []
}

export async function listSearchIndexes(credential: string): Promise<{ indexes: string[]; default: string | null }> {
  const url = await backendUrl('index/search-indexes?credential=' + encodeURIComponent(credential))
  const res = await service.get(url, true, false)
  return { indexes: res.indexes ?? [], default: res.default ?? null }
}
