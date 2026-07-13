import { service } from '../common/APIService.js'
import { backendUrl } from '../bff/Config.js'

// 两层图浏览与手工维护。均走 Python 后端（unwrap=false）。

export interface GraphNode {
  id: string
  type: string
  name: string
  status: string | null
  origin: string          // seed | manual | llm
  locked: boolean
  aliases: string[]
}

export interface GraphEdge {
  id: number | null
  source: string
  target: string
  type: string
  weight: number
  origin: string
  locked?: boolean
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  collection: string | null
}

export interface EvidenceItem {
  fullname: string
  store_id: string
  weight: number
  origin: string
}

export interface EntityDetail {
  entity: GraphNode
  evidence: EvidenceItem[]
  edges: GraphEdge[]
}

export interface BlockView {
  fullname: string
  text: string
  title: string | null
  category: string | null
  section: string | null
  ordinal: number | null
  store_id: string
}

export async function getGraph(collection?: string, type?: string): Promise<GraphData> {
  const q = new URLSearchParams()
  if (collection) q.set('collection', collection)
  if (type) q.set('type', type)
  const qs = q.toString()
  const url = await backendUrl('graph' + (qs ? '?' + qs : ''))
  return service.get(url, true, false)
}

export async function getEntityDetail(entityId: string): Promise<EntityDetail> {
  const url = await backendUrl('graph/entity/' + encodeURIComponent(entityId))
  return service.get(url, true, false)
}

export async function getBlock(fullname: string, storeId: string): Promise<BlockView> {
  const q = new URLSearchParams({ fullname, store_id: storeId })
  const url = await backendUrl('graph/block?' + q.toString())
  return service.get(url, true, false)
}

export async function addEntity(payload: {
  name: string; type: string; aliases?: string[]; auto?: boolean
}): Promise<{ entity_id: string }> {
  const url = await backendUrl('graph/entities')
  return service.post(url, payload, true, false)
}

export async function attachEvidence(entityId: string, payload: {
  fullname: string; store_id: string
}): Promise<any> {
  const url = await backendUrl('graph/entities/' + encodeURIComponent(entityId) + '/attach')
  return service.post(url, payload, true, false)
}
