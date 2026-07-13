import { service } from '../common/APIService.js'
import { backendUrl } from '../bff/Config.js'

// Assertion-supported entity/action graph. All calls carry one Collection scope.

export interface GraphNode {
  id: string
  kind: 'entity' | 'action'
  type: string
  name: string
  status: string | null
  origin: string          // seed | manual | llm
  locked: boolean
  aliases: string[]
  degree?: number
}

export interface GraphEdge {
  id: number
  source: string
  source_kind: 'entity' | 'action'
  target: string
  target_kind: 'entity' | 'action'
  type: string
  weight: number
  origin: string
  locked?: boolean
  assertion_ids: string[]
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  collection: string | null
  generation_scope?: Record<string, string>
}

export interface EntityCatalogData {
  nodes: GraphNode[]
  collection: string | null
}

export interface GraphNeighborhood extends GraphData {
  expandable: string[]
  root: string
  depth: number
}

export interface AssertionSupportItem {
  edge_id: number
  store_id: string
  generation_id: string
  assertion_id: string
  assertion_kind: string
  predicate: string
  modality: string
  condition: string | null
  exception: string | null
  scope: string | null
  block_key: string
  block_id: string
  evidence_role: string
  quote: string
  document_id: string
  title: string
  category: string
  heading_path: string | null
  ordinal: number
}

export interface NodeDetail {
  node: GraphNode
  entity: GraphNode
  support: AssertionSupportItem[]
  evidence: AssertionSupportItem[]
  edges: GraphEdge[]
  collection: string
}

export interface BlockView {
  block_key: string
  block_id: string
  text: string
  title: string | null
  category: string | null
  heading_path: string | null
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

export async function getEntityCatalog(collection?: string, type?: string): Promise<EntityCatalogData> {
  const q = new URLSearchParams()
  if (collection) q.set('collection', collection)
  if (type) q.set('type', type)
  const qs = q.toString()
  const url = await backendUrl('graph/catalog' + (qs ? '?' + qs : ''))
  return service.get(url, true, false)
}

export async function getGraphNeighborhood(nodeId: string, depth = 3, collection?: string): Promise<GraphNeighborhood> {
  const q = new URLSearchParams({ depth: String(depth) })
  if (collection) q.set('collection', collection)
  const url = await backendUrl('graph/neighborhood/' + encodeURIComponent(nodeId) + '?' + q.toString())
  // The caller handles 409 stale-Generation recovery and shows a specific message.
  return service.get(url, true, false, 'application/json', true)
}

export async function getNodeDetail(nodeId: string, collection?: string): Promise<NodeDetail> {
  const q = new URLSearchParams()
  if (collection) q.set('collection', collection)
  const url = await backendUrl('graph/node/' + encodeURIComponent(nodeId) + (q.size ? '?' + q.toString() : ''))
  return service.get(url, true, false, 'application/json', true)
}

export async function getBlock(blockKey: string, collection?: string): Promise<BlockView> {
  const q = new URLSearchParams({ block_key: blockKey })
  if (collection) q.set('collection', collection)
  const url = await backendUrl('graph/block?' + q.toString())
  return service.get(url, true, false)
}
