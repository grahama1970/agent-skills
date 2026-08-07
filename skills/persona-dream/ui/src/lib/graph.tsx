/**
 * graph helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { TraceGraphNode, TraceNodeKind } from '../types'
import { dreamAssetUrl } from './asset'
import { graphMediaSourceFromDocument } from './media'
import { personaMemoryThumbCache } from './memory'
import { nodeKindColor } from './status'

export function endpointParts(endpoint: string): { collection: string; key: string } | null {
  const match = endpoint.match(/^([a-zA-Z0-9_-]+)\/(.+)$/)
  if (!match?.[1] || !match?.[2]) return null
  return { collection: match[1], key: match[2] }
}

export async function memoryByKeysDocuments(collection: string, keys: string[], keyField?: string, returnFields?: string[]): Promise<Array<Record<string, unknown>>> {
  if (keys.length === 0) return []
  const response = await fetch('/api/memory/recall/by-keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      collection,
      keys,
      ...(keyField ? { key_field: keyField } : {}),
      ...(returnFields ? { return_fields: returnFields } : {}),
    }),
  })
  if (!response.ok) throw new Error(`memory/recall/by-keys ${collection} HTTP ${response.status}`)
  const data = await response.json()
  return Array.isArray(data.documents) ? data.documents as Array<Record<string, unknown>> : []
}

export async function memoryListByEndpoint(endpoint: string): Promise<Record<string, unknown> | null> {
  const parts = endpointParts(endpoint)
  if (!parts) return null
  const docs = await memoryByKeysDocuments(parts.collection, [parts.key])
  return docs[0] ?? null
}

export async function memoryEdgeDocuments(collection: string, endpoint: string, keyField: '_from' | '_to'): Promise<Array<Record<string, unknown>>> {
  return memoryByKeysDocuments(collection, [endpoint], keyField)
}

export async function memoryRecallDocuments(q: string, collections: string[], k = 18): Promise<Array<Record<string, unknown>>> {
  const response = await fetch('/api/memory/recall', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q, collections, tags: ['persona:embry'], k }),
  })
  if (!response.ok) throw new Error(`memory/recall HTTP ${response.status}`)
  const data = await response.json()
  return Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : []
}

export function graphLabelFromDocument(endpoint: string, doc?: Record<string, unknown> | null): string {
  if (!doc) return endpointParts(endpoint)?.key ?? endpoint
  const candidates = [doc.title, doc.name, doc.label, doc.description, doc.text, doc.snippet, doc._key]
  const value = candidates.find((candidate) => typeof candidate === 'string' && candidate.trim().length > 0)
  return String(value ?? endpoint).replace(/\s+/g, ' ').trim()
}

export function graphKindFromDocument(endpoint: string, doc?: Record<string, unknown> | null): TraceNodeKind {
  const text = `${endpoint} ${String(doc?.media_type ?? '')} ${String(doc?.asset_type ?? '')} ${String(doc?.record_type ?? '')} ${String(doc?.description ?? '')} ${String(doc?.title ?? '')}`.toLowerCase()
  if (/\b(audio|wav|mp3|sound)\b/.test(text)) return 'audio'
  if (/\b(video|mp4|mov|clip)\b/.test(text)) return 'video'
  if (/\b(image|png|jpg|jpeg|photo|contact_sheet)\b/.test(text)) return 'media'
  if (/\b(person|character|embry|kai|lawson|akana)\b/.test(text) && !endpoint.includes('memory_')) return 'person'
  if (/\b(place|location|bay|kona|kahalu)\b/.test(text)) return 'place'
  if (/\b(object|surfboard|board|wax|phone)\b/.test(text)) return 'object'
  return 'memory'
}

export function graphThumbFromDocument(doc?: Record<string, unknown> | null): string | undefined {
  const candidates = [doc?.thumbnail_url, doc?.thumbnail_path, doc?.poster_path, doc?.keyframe_path, doc?.image_path, doc?.url, doc?.asset_url, doc?.public_url, doc?.path]
  const value = candidates.find((candidate) => typeof candidate === 'string' && /(\.png|\.jpe?g|\.webp|\.gif|\/assets\/|\/api\/)/i.test(candidate))
  if (typeof value !== 'string') return undefined
  return dreamAssetUrl(value)
}

export function graphNodeFromEndpoint(endpoint: string, rootEndpoint: string, doc?: Record<string, unknown> | null): TraceGraphNode {
  const kind = graphKindFromDocument(endpoint, doc)
  const isRoot = endpoint === rootEndpoint
  const cachedThumb = personaMemoryThumbCache.get(endpoint)
  const sourceRef = [doc?.text, doc?.snippet, doc?.description, doc?.summary, doc?.title, doc?._key]
    .find((value) => typeof value === 'string' && value.trim().length > 0)
  return {
    id: endpoint,
    label: graphLabelFromDocument(endpoint, doc).slice(0, 92),
    kind,
    hop: isRoot ? 0 : 1,
    color: nodeKindColor(kind),
    radius: isRoot ? 46 : kind === 'media' || kind === 'video' || kind === 'audio' ? 32 : 28,
    thumbnailUrl: cachedThumb || graphThumbFromDocument(doc) || graphMediaSourceFromDocument(doc),
    mediaUrl: graphMediaSourceFromDocument(doc) || graphThumbFromDocument(doc),
    tom_state_type: typeof doc?.tom_state_type === 'string' ? doc.tom_state_type : undefined,
    tom_tags: Array.isArray(doc?.tom_tags) ? doc.tom_tags.map(String) : undefined,
    source_ref: typeof sourceRef === 'string' ? sourceRef.replace(/\s+/g, ' ').trim() : endpoint,
  }
}
