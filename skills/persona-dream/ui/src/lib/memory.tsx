/**
 * memory helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { LinkedStoryAsset, MemoryConnectionSignal, ResearchMemoryResult, TraceGraph, TraceGraphLink, TraceGraphNode } from '../types'
import { dreamAssetUrl } from './asset'
import { dreamExtractPathFromText, dreamInferMediaType, dreamStringField } from './dream'
import { graphNodeFromEndpoint } from './graph'
import { storyAssetDescriptionFromResult } from './script'
import { relationshipColor } from './status'
import { compactDisplayText, decodeJsonStringLiteral, parseJsonishText } from './text'

export function stripLeadingMemoryFieldLabels(text: string): string {
  return text
    .replace(/^[\s\\'"{}[\]:,]*(?:(?:story|asset\s+usage|asset\s+id|description|summary|text|title)[\s\\'"{}[\]:,]+){1,6}/i, '')
    .trim()
}

export function extractKnownMemoryFieldText(text: string): string {
  const preferredFields = [
    'visual_consistency_note',
    'use_in_story',
    'used_for',
    'media_description',
    'vlm_description',
    'video_description',
    'audio_caption',
    'text_summary',
    'story_prompt_summary',
    'description',
    'summary',
    'story',
    'title',
  ]
  for (const field of preferredFields) {
    const pattern = new RegExp(`"${field}"\\s*:\\s*"((?:\\\\.|[^"\\\\]){12,})"`, 'i')
    const match = text.match(pattern)
    if (!match?.[1]) continue
    const decoded = decodeJsonStringLiteral(match[1])
    const parsed = parseJsonishText(decoded)
    const readable = parsed ? readableMemoryValue(parsed) : compactDisplayText(decoded)
    if (readable) return readable
  }
  return ''
}

export function readableMemoryValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') {
    const parsed = parseJsonishText(value)
    if (parsed && parsed !== value) return readableMemoryValue(parsed)
    return compactDisplayText(value)
  }
  if (Array.isArray(value)) {
    return value.map(readableMemoryValue).filter(Boolean).join(' ')
  }
  if (typeof value !== 'object') return compactDisplayText(String(value))

  const obj = value as Record<string, unknown>
  const assetUsage = obj.asset_usage
  if (Array.isArray(assetUsage) && assetUsage.length > 0) {
    const rows = assetUsage
      .map((item) => {
        if (!item || typeof item !== 'object') return ''
        const row = item as Record<string, unknown>
        return readableMemoryValue(row.visual_consistency_note || row.use_in_story || row.used_for || row.title)
      })
      .filter(Boolean)
    if (rows.length > 0) return compactDisplayText(rows.join(' '))
  }

  const story = obj.story
  if (story) {
    const parsedStory = typeof story === 'string' ? parseJsonishText(story) : null
    const storyText = parsedStory ? readableMemoryValue(parsedStory) : readableMemoryValue(story)
    if (storyText) return storyText
  }

  for (const key of [
    'visual_consistency_note',
    'use_in_story',
    'used_for',
    'media_description',
    'vlm_description',
    'video_description',
    'audio_caption',
    'text_summary',
    'story_prompt_summary',
    'description',
    'summary',
    'title',
    'name',
    'label',
    'text',
    'content',
  ]) {
    const text = readableMemoryValue(obj[key])
    if (text) return text
  }
  return ''
}

export function readableMemoryText(text: string): string {
  const extracted = extractKnownMemoryFieldText(text)
  if (extracted) return stripLeadingMemoryFieldLabels(extracted)
  const parsed = parseJsonishText(text)
  const fromJson = parsed ? readableMemoryValue(parsed) : ''
  return stripLeadingMemoryFieldLabels(fromJson || compactDisplayText(text))
}

export const personaMemoryThumbCache = new Map<string, string>()

export function humanMemoryCaption(result: ResearchMemoryResult): string {
  const text = [result.snippet, result.title].filter(Boolean).join('\n')
  const readable = readableMemoryText(text)
  if (readable && !/^\s*[{\[]/.test(readable)) return readable
  const titleMatch = text.match(/\bTitle\s*:?\s*([^\n]+?)(?:\s+(?:Aliases|Description|Persona|Source|Tags|Path|Record)\b|$)/i)
  if (titleMatch?.[1]) return titleMatch[1].trim()
  const descriptionMatch = text.match(/\bDescription\s*:?\s*([^\n]+?)(?:\s+(?:Aliases|Title|Persona|Source|Tags|Path|Record)\b|$)/i)
  if (descriptionMatch?.[1]) return descriptionMatch[1].trim()
  const cleaned = (result.snippet || result.title || 'Memory residue')
    .replace(/Persona media asset key:\s*\S+/gi, '')
    .replace(/[_:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return cleaned || 'Memory residue'
}

export function linkedStoryAssetFromMemoryResult(result: ResearchMemoryResult, index: number): LinkedStoryAsset {
  const title = humanMemoryCaption(result)
  const memoryKey = extractPersonaMemoryKey({
    id: result.title || `asset-${index}`,
    label: title,
    subtitle: result.snippet,
    imageUrl: result.url,
    mediaType: result.mediaType,
  })
  return {
    id: memoryKey || `asset-${index}`,
    title,
    url: result.url,
    description: storyAssetDescriptionFromResult(result),
    source: result.title || memoryKey || `asset-${index}`,
    memoryKey,
    mediaType: result.mediaType,
  }
}

export function dreamMemoryResultFromDocument(doc: Record<string, unknown>, index: number): ResearchMemoryResult {
  const title = dreamStringField(doc, ['title', 'name', 'label', '_key']) || `Memory residue ${index + 1}`
  const rawSnippet = dreamStringField(doc, [
    'media_description',
    'vlm_description',
    'video_description',
    'audio_caption',
    'text_summary',
    'story_prompt_summary',
    'description',
    'summary',
    'text',
    'retrieval_text',
    'content',
  ])
  const key = typeof doc._key === 'string' && doc._key.trim().length > 0 ? doc._key.trim() : ''
  const snippet = key ? `Persona media asset key: ${key}. ${rawSnippet}` : rawSnippet
  const mediaType = dreamInferMediaType(
    dreamStringField(doc, ['source_path', 'image_path', 'thumbnail_path', 'poster_path', 'keyframe_path', 'url', 'asset_url', 'public_url', 'path'])
      || dreamExtractPathFromText(snippet),
    dreamStringField(doc, ['media_type', 'mime_type', 'asset_type'])
  )
  const isVideo = mediaType === 'mp4' || mediaType === 'mov' || mediaType === 'webm'
  const isAudio = mediaType === 'wav' || mediaType === 'mp3' || mediaType === 'ogg'
  const rawPlaybackPath = dreamStringField(doc, ['source_path', 'url', 'asset_url', 'public_url', 'path']) || dreamExtractPathFromText(snippet)
  const rawThumbPath = dreamStringField(doc, ['thumbnail_path', 'poster_path', 'keyframe_path', 'thumbnail_url', 'image_path'])
  const rawPath = isVideo ? (rawThumbPath || rawPlaybackPath) : isAudio ? rawPlaybackPath : (rawThumbPath || rawPlaybackPath)
  return {
    title,
    url: dreamAssetUrl(rawPath) ?? '',
    mediaUrl: dreamAssetUrl(rawPlaybackPath) ?? dreamAssetUrl(rawPath) ?? undefined,
    snippet,
    mediaType,
    memoryKey: key || undefined,
    score: typeof doc.score === 'number' ? doc.score : undefined,
  }
}

export function dreamMemoryResultPriority(result: ResearchMemoryResult): number {
  const haystack = `${result.title} ${result.snippet} ${result.url} ${result.mediaType ?? ''}`.toLowerCase()
  if (haystack.includes('embry_media_asset__assets_surfing_embry_surfing_big_island_2024_png')) return 0
  if (haystack.includes('embry_media_asset__assets_surfing_embry_barrel_wave_big_island_2024_png')) return 1
  if (haystack.includes('kai_akana_media_asset__assets_surfing_kai_surfing_big_island_2024_png')) return 2
  if (haystack.includes('embry_kai_media_asset__assets_surfing_embry_and_kai_looking_for_waves_big_island_2024_png')) return 3
  if (haystack.includes('embry_media_asset__assets_character_sheet_montage_jpg')) return 4
  if (haystack.includes('kai_akana_media_asset__assets_contact_sheets_kai_akana_character_sheet_png')) return 5
  if (haystack.includes('youtube') && (haystack.includes('video') || haystack.includes('mp4'))) return 6
  if (haystack.includes('youtube') && (haystack.includes('audio') || haystack.includes('wav'))) return 7
  if (haystack.includes('contact_sheet')) return 20
  if (result.url) return 10
  return 30
}

export function extractPersonaMemoryKey(memory: { id: string; label: string; subtitle?: string; imageUrl?: string; mediaType?: string; memoryKey?: string }): string | undefined {
  if (memory.memoryKey) return memory.memoryKey
  const haystack = [memory.subtitle, memory.id, memory.label, memory.imageUrl, memory.mediaType].filter(Boolean).join(' ')
  const direct = haystack.match(/\b((?:embry|kai_akana|embry_kai)[a-z0-9_]*?(?:media_asset|memory)[a-z0-9_.-]*)\b/i)
  if (direct?.[1]) return direct[1].replace(/[),.;:'"\]]+$/g, '')
  const endpoint = haystack.match(/\bpersona_memory\/([a-zA-Z0-9_.:-]+)\b/)
  if (endpoint?.[1]) return endpoint[1].replace(/[),.;:'"\]]+$/g, '')
  return undefined
}

export function buildLiveMemoryTraceGraph(
  baseGraph: TraceGraph,
  edgeRows: Array<Record<string, unknown>>,
  docsByEndpoint: Map<string, Record<string, unknown> | null>,
): TraceGraph {
  const rootEndpoint = baseGraph.memoryEndpoint ?? baseGraph.rootId
  const nodesById = new Map<string, TraceGraphNode>()
  const rootDoc = docsByEndpoint.get(rootEndpoint)
  const fallbackRoot = baseGraph.nodes.find((node) => node.id === baseGraph.rootId) ?? baseGraph.nodes[0]
  const rootNode = graphNodeFromEndpoint(rootEndpoint, rootEndpoint, rootDoc)
  nodesById.set(rootEndpoint, {
    ...rootNode,
    label: fallbackRoot?.label || rootNode.label,
    thumbnailUrl: fallbackRoot?.thumbnailUrl || rootNode.thumbnailUrl,
  })
  const linksById = new Map<string, TraceGraphLink>()

  edgeRows.forEach((edge, index) => {
    const from = String(edge._from || '')
    const to = String(edge._to || '')
    if (!from || !to) return
    const relationship = String(edge.relationship_type || edge.edge_type || edge.tom_state_type || 'memory edge')
    const connectedToRoot = from === rootEndpoint || to === rootEndpoint
    const hop = connectedToRoot ? 1 : 2
    ;[from, to].forEach((endpoint) => {
      if (!nodesById.has(endpoint)) {
        const node = graphNodeFromEndpoint(endpoint, rootEndpoint, docsByEndpoint.get(endpoint))
        nodesById.set(endpoint, { ...node, hop: endpoint === rootEndpoint ? 0 : hop })
      }
    })
    const key = typeof edge._key === 'string' ? edge._key : `${from}->${to}:${relationship}:${index}`
    linksById.set(key, {
      id: key,
      source: from,
      target: to,
      label: relationship.replace(/_/g, ' '),
      hop,
      color: relationshipColor(relationship),
      relationship_type: relationship,
      tom_tags: Array.isArray(edge.tom_tags) ? edge.tom_tags.map(String) : undefined,
      confidence: typeof edge.confidence === 'number' ? edge.confidence : undefined,
    })
  })

  return {
    ...baseGraph,
    rootId: rootEndpoint,
    source: edgeRows.length > 0 ? 'memory-live' : baseGraph.source,
    nodes: Array.from(nodesById.values()),
    links: Array.from(linksById.values()),
  }
}

export function mergeMemoryTomGraph(baseGraph: TraceGraph, items: Array<Record<string, unknown>>): TraceGraph {
  if (items.length === 0) return baseGraph
  const nodesById = new Map(baseGraph.nodes.map((node) => [node.id, node]))
  const linksById = new Map(baseGraph.links.map((link) => [link.id, link]))
  let addedLinks = 0

  items.slice(0, 18).forEach((item, index) => {
    const from = String(item._from || item.from || item.source || '')
    const to = String(item._to || item.to || item.target || item.record_id || item._key || `memory-edge-${index}`)
    const relationship = String(item.relationship_type || item.edge_type || item.tom_state_type || 'memory edge')
    const tags = Array.isArray(item.tom_tags) ? item.tom_tags.map(String) : []
    const sourceId = from || baseGraph.rootId
    const targetId = to || `memory-edge-${index}`
    if (!nodesById.has(sourceId) || !nodesById.has(targetId)) return
    const linkId = `${sourceId}->${targetId}:${relationship}`
    if (!linksById.has(linkId)) {
      linksById.set(linkId, {
        id: linkId,
        source: sourceId,
        target: targetId,
        label: relationship,
        hop: 2,
        color: '#f472b6',
        relationship_type: relationship,
        tom_tags: tags,
        confidence: typeof item.confidence === 'number' ? item.confidence : undefined,
      })
      addedLinks += 1
    }
  })

  if (addedLinks === 0) return baseGraph
  return {
    ...baseGraph,
    source: 'mixed',
    nodes: Array.from(nodesById.values()),
    links: Array.from(linksById.values()),
  }
}

export const memoryConnectionPalette: Record<string, MemoryConnectionSignal> = {
  autonomy: {
    id: 'autonomy',
    label: 'Autonomy',
    tomKind: 'goal',
    color: '#4a9eff',
    glow: '0 0 9px rgba(74,158,255,0.74)',
  },
  ritual: {
    id: 'ritual',
    label: 'Family rituals',
    tomKind: 'boundary',
    color: '#f59e0b',
    glow: '0 0 9px rgba(245,158,11,0.66)',
  },
  surf: {
    id: 'surf',
    label: 'Surf environment',
    tomKind: 'knowledge_gap',
    color: '#2dd4bf',
    glow: '0 0 9px rgba(45,212,191,0.68)',
  },
  character: {
    id: 'character',
    label: 'Embry/Kai connection',
    tomKind: 'relationship',
    color: '#a78bfa',
    glow: '0 0 9px rgba(167,139,250,0.66)',
  },
}

export function memoryConnectionSignals(memory: { label: string; subtitle?: string; imageUrl?: string; mediaType?: string }): MemoryConnectionSignal[] {
  const haystack = `${memory.label} ${memory.subtitle ?? ''} ${memory.imageUrl ?? ''} ${memory.mediaType ?? ''}`.toLowerCase()
  const signals: MemoryConnectionSignal[] = []
  const add = (id: keyof typeof memoryConnectionPalette) => {
    if (!signals.some((signal) => signal.id === id)) signals.push(memoryConnectionPalette[id])
  }

  if (/\b(surf|surfer|wave|swell|reef|lava|kahalu|kona|ocean|tide|weather|humidity|heat|salt|water|board|surfboard)\b/.test(haystack)) add('surf')
  if (/\b(family|ritual|lawson|obligation|garage|tommy|call|leave|restrictive)\b/.test(haystack)) add('ritual')
  if (/\b(autonomy|freedom|independent|fake|sick day|summer job|choice|chose|obligation)\b/.test(haystack)) add('autonomy')
  if (/\b(embry|kai|connection|shared|together|relationship|preserves|accepts)\b/.test(haystack)) add('character')

  if (signals.length === 0) add('character')
  return signals.slice(0, 2)
}
