/**
 * trace helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { MemoryConnectionSignal, SimulationNodeDatum, TraceGraph, TraceGraphNode, TraceNodeKind } from '../types'
import { extractPersonaMemoryKey, personaMemoryThumbCache } from './memory'
import { nodeKindColor } from './status'

export function inferTraceKind(memory: { imageUrl?: string; mediaType?: string; label: string; subtitle?: string }): TraceNodeKind {
  if (['wav', 'mp3', 'ogg'].includes(memory.mediaType || '')) return 'audio'
  if (['mp4', 'mov', 'avi', 'webm'].includes(memory.mediaType || '')) return 'video'
  if (memory.imageUrl) return 'media'
  const text = `${memory.label} ${memory.subtitle ?? ''}`.toLowerCase()
  if (/\b(kona|kahalu|bay|coast|reef|beach|island|place|location)\b/.test(text)) return 'place'
  if (/\b(board|surfboard|phone|wax|rashguard|object)\b/.test(text)) return 'object'
  if (/\b(embry|kai|lawson|akana|tommy|market[a-z]*)\b/.test(text)) return 'person'
  return 'memory'
}

export function buildCardTraceGraph(
  memory: { id: string; label: string; subtitle?: string; imageUrl?: string; mediaType?: string; memoryKey?: string; mediaUrl?: string },
  ideaText: string,
  _signals: MemoryConnectionSignal[],
): TraceGraph {
  const memoryKey = extractPersonaMemoryKey(memory)
  const rootId = memoryKey ? `persona_memory/${memoryKey}` : `card:${memory.id}`
  if (memoryKey && memory.imageUrl) personaMemoryThumbCache.set(`persona_memory/${memoryKey}`, memory.imageUrl)
  const kind = inferTraceKind(memory)
  const nodes: TraceGraphNode[] = [
    {
      id: rootId,
      label: memory.label,
      kind,
      hop: 0,
      color: nodeKindColor(kind),
      radius: memory.imageUrl ? 44 : 36,
      thumbnailUrl: memory.imageUrl,
      mediaUrl: memory.mediaUrl || memory.imageUrl,
      source_ref: memory.subtitle || ideaText.slice(0, 180) || memory.id,
    },
  ]

  return {
    rootId,
    title: memory.label,
    source: 'card-derived',
    memoryKey,
    memoryEndpoint: memoryKey ? `persona_memory/${memoryKey}` : undefined,
    nodes,
    links: [],
  }
}

export function isDisplayableTraceEdge(edge: Record<string, unknown>, rootEndpoint: string): boolean {
  const from = String(edge._from || '')
  const to = String(edge._to || '')
  if (!from || !to) return false
  if (from === rootEndpoint || to === rootEndpoint) return true
  const relationship = String(edge.relationship_type || edge.edge_type || edge.tom_state_type || '').toLowerCase()
  const edgeKind = String(edge.edge_kind || '').toLowerCase()
  const tags = Array.isArray(edge.tags) ? edge.tags.map(String).join(' ').toLowerCase() : ''
  if (relationship === 'persona_has_record' || relationship === 'same_record_type_sequence') return false
  if (edgeKind === 'media_to_story_memory') return true
  if (relationship.includes('media') || relationship.includes('visual') || relationship.includes('audio') || relationship.includes('video')) return true
  if (relationship.includes('tom') && (tags.includes('surf') || tags.includes('kai') || tags.includes('embry') || tags.includes('persona_dream'))) return true
  return false
}

export function relaxTraceNodeOverlaps(nodes: Array<TraceGraphNode & SimulationNodeDatum>, width: number, height: number) {
  for (let iteration = 0; iteration < 18; iteration += 1) {
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i]
        const b = nodes[j]
        const ax = a.x ?? width * 0.5
        const ay = a.y ?? height * 0.5
        const bx = b.x ?? width * 0.5
        const by = b.y ?? height * 0.5
        const dx = bx - ax || 0.01
        const dy = by - ay || 0.01
        const distance = Math.hypot(dx, dy)
        const minDistance = a.radius + b.radius + 30
        if (distance >= minDistance) continue
        const push = (minDistance - distance) / 2
        const ux = dx / distance
        const uy = dy / distance
        if (!a.fx) {
          a.x = ax - ux * push
          a.y = ay - uy * push
        }
        if (!b.fx) {
          b.x = bx + ux * push
          b.y = by + uy * push
        }
      }
    }
  }
}
