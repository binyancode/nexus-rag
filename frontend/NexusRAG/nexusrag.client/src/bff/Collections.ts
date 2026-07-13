import { service } from '../common/APIService.js'

export interface CollectionItem {
  collection_id: string
  name: string
  description: string | null
  is_public: boolean
  store_count: number
  access_count: number
}
export interface CollectionStore {
  store_id: string
  name: string
  credential_name: string
  index_name: string | null
  kind: string
  is_default: boolean
}
export interface CollectionMember { collection_id: string; store_id: string }
export interface CollectionAccess {
  collection_id: string
  principal_type: 'user' | 'role'
  principal_id: string
  is_default: boolean
}
export interface CollectionAdminData {
  collections: CollectionItem[]
  stores: CollectionStore[]
  members: CollectionMember[]
  access: CollectionAccess[]
}
export interface CollectionSavePayload {
  collection_id: string
  name: string
  description?: string | null
  is_public: boolean
  store_ids: string[]
  access: Omit<CollectionAccess, 'collection_id'>[]
}

export function listCollectionsAdmin(): Promise<CollectionAdminData> {
  return service.get('collections')
}
export function createCollection(payload: CollectionSavePayload): Promise<{ collection_id: string }> {
  return service.post('collections', payload)
}
export function updateCollection(id: string, payload: CollectionSavePayload): Promise<{ collection_id: string }> {
  return service.put('collections/' + encodeURIComponent(id), payload)
}
export function deleteCollection(id: string): Promise<{ collection_id: string }> {
  return service.del('collections/' + encodeURIComponent(id))
}
