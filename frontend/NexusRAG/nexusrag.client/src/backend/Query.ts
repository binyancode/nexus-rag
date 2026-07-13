import { service } from '../common/APIService.js'
import { backendUrl } from '../bff/Config.js'

export interface QueryCollection {
  collection_id: string
  name: string
  description: string | null
  stores: string[]
  is_default: boolean
}

export interface CreateQueryPayload {
  question: string
  collection?: string
  llm_credential: string
  embedding_credential: string
  max_parallel?: number
  budgets?: { max_entities?: number; max_blocks?: number; max_tokens?: number }
}

export interface QueryRunInfo {
  run_id: string
  question: string | null
  answer: string | null
  citations: string | null
  collection_id: string | null
  collection_name: string | null
  collection_selected_by: string | null
  allowed_stores: string | null
  max_parallel: number
  state: string
  current_stage: string | null
  node_count: number
  tokens: string | null
  error: string | null
  cost_ms: number
  created_at: string | null
  updated_at: string | null
}

export interface QueryNodeState {
  node_id: string
  state: string
  op: string | null
  input: string | null
  output: string | null
  value: string | null
  tokens: string | null
  error: string | null
  cost_ms: number | null
  started_at: string | null
  ended_at: string | null
}

export interface QueryStageState {
  stage_id: 'initializer' | 'compiler' | 'optimizer' | 'coordinator' | 'generator'
  ordinal: number
  name: string
  state: string
  input: string | null
  output: string | null
  tokens: string | null
  error: string | null
  cost_ms: number | null
  started_at: string | null
  ended_at: string | null
}

export interface QueryRunData { run: QueryRunInfo; stages: QueryStageState[]; nodes: QueryNodeState[] }

export interface QueryRunListItem {
  run_id: string
  as_user: string | null
  question: string | null
  answer: string | null
  collection_id: string | null
  collection_name: string | null
  collection_selected_by: string | null
  state: string
  node_count: number
  tokens: string | null
  error: string | null
  cost_ms: number
  created_at: string | null
  updated_at: string | null
}

export async function listQueryCollections(): Promise<QueryCollection[]> {
  const url = await backendUrl('query/collections')
  const res = await service.get(url, true, false)
  return res.collections ?? []
}

export async function createQuery(payload: CreateQueryPayload): Promise<{ run_id: string }> {
  const url = await backendUrl('query')
  return service.post(url, payload, true, false)
}

export async function getQueryRun(runId: string): Promise<QueryRunData> {
  return service.get('query-runs/' + encodeURIComponent(runId), true, true, 'application/json', true)
}

export async function listQueryRuns(top = 100): Promise<QueryRunListItem[]> {
  const res = await service.get('query-runs?top=' + top, true, true, 'application/json', true)
  return res?.runs ?? []
}

export async function cancelQuery(runId: string): Promise<{ run_id: string; cancelling: boolean }> {
  const url = await backendUrl('query/runs/' + encodeURIComponent(runId) + '/cancel')
  return service.post(url, {}, true, false)
}
