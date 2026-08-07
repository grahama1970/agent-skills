/**
 * Non-component helpers for the Dream workspace.
 *
 * Every top-level declaration that is not a React component lives here: status
 * derivation, payload builders, formatters, loaders. None of them reference a
 * component, which is what makes this split acyclic -- panels and the root both
 * import from here, and nothing here imports back.
 */
import React, { useEffect, useState, type CSSProperties , useRef } from 'react'
import * as d3 from 'd3'
import { AlertTriangle, Lock } from 'lucide-react'
import { highlightWithGlossary, type GlossaryTerm } from './highlightEntities'
import type { SimulationNodeDatum, ContactSheetDecision, CrewPersonaOption, CrewRole, DreamArtifact, DreamStage, HumanIdeaProjection, LinkedStoryAsset, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, ScriptCoverageStatus, StatusTone, StoryMatrixRow, StoryboardConsumerProjection, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from './types'
import { CANONICAL_PHASES, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, textEncoder } from './constants'

export function requiredStageArtifact(stage: DreamStage | undefined, artifactId: string) {
  return stage?.requiredArtifacts?.[artifactId]
}

export function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export function parseJsonishText(text: string): unknown | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const candidates = [trimmed]
  const firstBrace = trimmed.indexOf('{')
  const lastBrace = trimmed.lastIndexOf('}')
  if (firstBrace >= 0 && lastBrace > firstBrace) candidates.push(trimmed.slice(firstBrace, lastBrace + 1))
  for (const candidate of candidates) {
    try {
      let parsed: unknown = JSON.parse(candidate)
      for (let i = 0; i < 2 && typeof parsed === 'string' && /^[\s{[]/.test(parsed); i += 1) {
        parsed = JSON.parse(parsed)
      }
      return parsed
    } catch {
      // Keep trying alternate slices; malformed memory text falls back to cleanup.
    }
  }
  return null
}

export function compactDisplayText(text: string, max = 420): string {
  const cleaned = text
    .replace(/Persona media asset key:\s*\S+\.?\s*/gi, '')
    .replace(/\\n/g, ' ')
    .replace(/\\/g, ' ')
    .replace(/["{}[\]]/g, ' ')
    .replace(/[_:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(?:(?:story|asset usage|asset id|description|summary|text|title)\s+){1,4}/i, '')
    .trim()
  if (cleaned.length <= max) return cleaned
  return `${cleaned.slice(0, max - 1).trim()}…`
}

export function stripLeadingMemoryFieldLabels(text: string): string {
  return text
    .replace(/^[\s\\'"{}[\]:,]*(?:(?:story|asset\s+usage|asset\s+id|description|summary|text|title)[\s\\'"{}[\]:,]+){1,6}/i, '')
    .trim()
}

export function decodeJsonStringLiteral(value: string): string {
  try {
    return JSON.parse(`"${value.replace(/"/g, '\\"')}"`)
  } catch {
    return value.replace(/\\"/g, '"').replace(/\\n/g, ' ')
  }
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

export function fnv1a32(input: string): string {
  let hash = 0x811c9dc5
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

export function persistedHumanIdea(projection?: HumanIdeaProjection): string {
  return projection?.source === 'explicit_human' ? projection.text.trim() : ''
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

export function storyAssetDescriptionFromResult(result: ResearchMemoryResult): string {
  const snippet = (result.snippet || '').replace(/\s+/g, ' ').trim()
  if (!snippet) return ''
  const readable = readableMemoryText(snippet)
  if (readable && !/^\s*[{\[]/.test(readable)) return readable
  const descriptionMatch = snippet.match(/\bDescription\s*:?\s*(.+?)(?:\s+(?:Aliases|Title|Persona|Source|Tags|Path|Record|Theory of mind|Live story summary)\b|$)/i)
  if (descriptionMatch?.[1]) return descriptionMatch[1].trim()
  return snippet
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

export function dreamStringField(doc: Record<string, unknown>, fields: string[]): string {
  for (const field of fields) {
    const value = doc[field]
    if (typeof value === 'string' && value.trim().length > 0) return value.trim()
  }
  return ''
}

export function dreamExtractPathFromText(text: string): string {
  const match = text.match(/\/(?:mnt|home)\/[^\s"'<>)]*\.(?:png|jpe?g|webp|gif|mp4|mov|webm|wav|mp3|ogg)\b/i)
  return match?.[0] ?? ''
}

export function dreamInferMediaType(path: string, explicit?: string): string {
  const normalized = String(explicit ?? '').trim().toLowerCase()
  if (normalized === 'image' || normalized === 'photo') return 'png'
  if (normalized === 'audio') return 'wav'
  if (normalized === 'video') return 'mp4'
  const ext = path.match(/\.([a-z0-9]+)(?:$|\?)/i)?.[1]?.toLowerCase()
  return ext ?? normalized
}

export function dreamRenderableMediaUrl(value?: string): boolean {
  const url = String(value ?? '').trim()
  if (!url) return false
  if (/^\/(?:api|assets)\//i.test(url)) return true
  return /\.(?:png|jpe?g|webp|gif|svg|avif|mp4|mov|webm|wav|mp3|ogg|flac|m4a)(?:[?#].*)?$/i.test(url)
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

export function storyAssetDescriptionFromMemoryDocument(doc: Record<string, unknown>): string {
  const candidates = [
    doc.media_description,
    doc.vlm_description,
    doc.audio_caption,
    doc.video_description,
    doc.text_summary,
    doc.story_prompt_summary,
    doc.description,
    doc.retrieval_text,
    doc.evidence_text,
  ]
  const value = candidates.find((candidate) => typeof candidate === 'string' && candidate.trim().length > 0)
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : ''
}

export function inferStoryLocationAndEnvironment(seed: string, artifacts: DreamStage['artifacts']): { location: string; environment: string } {
  const lower = seed.toLowerCase()
  const place = lower.includes('kahalu') ? 'Kahaluʻu Bay, Kona Coast'
    : lower.includes('kona') ? 'Kona Coast, Big Island'
    : lower.includes('big island') || lower.includes('hawaii') ? 'Big Island, Hawaii'
    : artifacts.find((a) => a.label.toLowerCase().includes('environment'))?.label || 'Inferred from context'
  const yearMatch = seed.match(/\b(20\d{2}|19\d{2})\b/)
  const dayMatch = seed.match(/\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b/i)
  const monthMatch = seed.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/i)
  const time = lower.includes('morning') ? 'morning'
    : lower.includes('afternoon') ? 'afternoon'
    : lower.includes('evening') ? 'evening'
    : lower.includes('sunset') || lower.includes('golden hour') ? 'golden hour'
    : 'daylight surf window'
  const weatherParts = [
    lower.includes('swell') ? 'summer swell patterns' : null,
    lower.includes('lava') || lower.includes('reef') ? 'lava rock reef constraints' : null,
    lower.includes('rain') ? 'rain nearby' : null,
    lower.includes('wind') ? 'wind exposure' : null,
    lower.includes('cloud') ? 'cloud cover' : null,
  ].filter(Boolean)
  const weather = weatherParts.length > 0
    ? `Hot, humid coastal air with ${weatherParts.join(', ')}; sweat, glare, wax softness, saltwater, and fatigue change grip, footing, board control, reef caution, and social patience.`
    : 'Hot, humid coastal surf weather inferred from visual references; characters respond to glare, sweat, saltwater, wax softness, board control, fatigue, and the social pressure of a public break.'
  return {
    location: [
    place,
    dayMatch ? dayMatch[1] : null,
      time,
    monthMatch ? monthMatch[1] : null,
    yearMatch ? yearMatch[1] : null,
    ].filter(Boolean).join(' · '),
    environment: weather,
  }
}

export function createMissingStage(id: string, label: string): DreamStage {
  return {
    id,
    title: label,
    status: 'MISSING',
    summary: `No ${label} phase evidence was found in the backend run artifacts.`,
    failureOrGap: `Required preflight evidence is missing for the ${label} phase.`,
    artifacts: [],
    images: [],
  }
}

export function normalizeToCanonicalPhases(backendStages: DreamStage[]): DreamStage[] {
  const normalized: DreamStage[] = []
  let ideaMemorySplitCount = 0
  for (const canonical of CANONICAL_PHASES) {
    const canonicalStage = backendStages.find((stage) => stage.id === canonical.id)
    if (canonicalStage) {
      normalized.push({ ...canonicalStage, title: canonical.label })
      continue
    }
    const matching = (canonical.legacyIds as readonly string[])
      .map((legacyId) => backendStages.find((s) => s.id === legacyId))
      .filter((stage): stage is DreamStage => Boolean(stage))
    if (matching.length === 0) {
      normalized.push(createMissingStage(canonical.id, canonical.label))
      continue
    }
    if (canonical.id === '01' || canonical.id === '02') {
      if (ideaMemorySplitCount === 0) {
        const source = matching[0]
        ideaMemorySplitCount++
        normalized.push({
          ...source,
          id: '01',
          title: 'Idea',
          summary: source.summary || 'Idea core extracted from persona-dream run.',
        })
      } else {
        const source = matching[0]
        const hasMemoryNodes = source.artifacts.some(
          (a) => a.label.toLowerCase().includes('memory') || a.label.toLowerCase().includes('residue')
        )
        normalized.push({
          ...source,
          id: '02',
          title: 'Memories',
          status: hasMemoryNodes ? source.status : 'MISSING',
          summary: hasMemoryNodes ? source.summary : 'No separate memory residue evidence found.',
          failureOrGap: hasMemoryNodes ? source.failureOrGap : 'Memory evidence was not separated from idea. Rerun with residue extraction.',
        })
        ideaMemorySplitCount++
      }
    } else {
      const stage = { ...matching[0], id: canonical.id, title: canonical.label }
      if (canonical.id === '08') {
        stage.summary = 'Accepted storyboard frame evidence, media locks, hashes, dimensions, and identity status before provider-facing distillation.'
        stage.failureOrGap = stage.failureOrGap || 'Media lock evidence is required between Storyboard and Video Provider.'
      }
      if (canonical.id === '09') {
        stage.summary = 'Provider-neutral video scene packet, selected provider routing, prompt, locks, and media staging receipts.'
      }
      if (canonical.id === '10') {
        stage.summary = 'Provider distillation contract, panel-level payload projection, field mapping, omitted context, media publication plan, and live-readiness receipts.'
      }
      if (canonical.id === '11') {
        stage.summary = 'Provider API response, task id, polling receipts, downloaded media, frame sheets, and post-provider review.'
      }
      normalized.push(stage)
    }
  }
  return normalized
}

export const phaseShortLabels: Record<string, string> = {
  '01': 'Idea',
  '02': 'Story',
  '03': 'Crew',
  '04': 'Contact Sheets',
  '05': 'Voices',
  '06': 'Script',
  '07': 'Storyboard',
  '08': 'Media Lock',
  '09': 'Video Provider',
  '10': 'Provider Distillation',
  '11': 'Provider Return',
}

export const dreamPhaseHashAliases: Record<string, string> = {
  idea: '01',
  story: '02',
  crew: '03',
  'contact-sheets': '04',
  voices: '05',
  script: '06',
  storyboard: '07',
  panels: '08',
  'media-lock': '08',
  'kling-packet': '09',
  'video-provider': '09',
  review: '10',
  distillation: '10',
  'provider-contract': '10',
  return: '11',
}

export const dreamPhaseHashById = {
  ...Object.fromEntries(
    Object.entries(dreamPhaseHashAliases).map(([slug, id]) => [id, slug])
  ),
  '10': 'distillation',
} as Record<string, string>

export function activeDreamPhaseFromLocation(): string {
  if (typeof window === 'undefined') return ''
  const path = window.location.pathname.replace(/\/+$/, '')
  const hashParts = window.location.hash.replace(/^#/, '').split('/').filter(Boolean)
  const hashRoute = hashParts[0] ?? ''
  const hashSlug = hashParts[hashParts.length - 1] ?? ''
  if (path === '/dream') return dreamPhaseHashAliases[hashSlug] ?? ''
  if (path === '' || path === '/') {
    if (hashRoute === 'dream') return dreamPhaseHashAliases[hashSlug] ?? ''
  }
  return ''
}

export function phaseNumber(phaseId: string): string {
  return phaseId.length === 2 ? phaseId : '--'
}

export function statusTone(status: string): StatusTone {
  const normalized = status.toUpperCase()
  if (normalized.includes('BLOCK') || normalized.includes('FAIL') || normalized.includes('STALE') || normalized.startsWith('NO_')) return 'blocked'
  if (normalized.includes('DRY_RUN')) return 'dry'
  if (
    normalized.includes('PASS')
    || normalized.includes('RETURN_RECEIVED')
    || normalized.includes('EVIDENCE_FOUND')
    || normalized.includes('READY')
    || normalized.includes('CALLED')
    || normalized.includes('AUTHORIZED')
  ) return 'pass'
  return 'unknown'
}

export function statusLabel(status: string): string {
  const normalized = status.toUpperCase()
  if (
    normalized.includes('PASS')
    || normalized.includes('EVIDENCE_FOUND')
    || normalized.includes('READY')
    || normalized.includes('CALLED')
    || normalized.includes('AUTHORIZED')
  ) return 'Pass'
  if (normalized.includes('MISSING')) return 'Missing evidence'
  if (normalized.includes('BLOCK')) return 'Blocked'
  if (normalized.includes('FAIL')) return 'Fail'
  if (normalized.includes('DRY_RUN')) return 'Dry run'
  return status.replace(/_/g, ' ')
}

export const toneStyles: Record<StatusTone, CSSProperties> = {
  pass: { borderColor: 'rgba(52, 211, 153, 0.38)', background: 'rgba(52, 211, 153, 0.1)', color: '#a7f3d0' },
  dry: { borderColor: 'rgba(56, 189, 248, 0.38)', background: 'rgba(56, 189, 248, 0.1)', color: '#bae6fd' },
  blocked: { borderColor: 'rgba(248, 113, 113, 0.38)', background: 'rgba(248, 113, 113, 0.1)', color: '#fecaca' },
  unknown: { borderColor: 'rgba(148, 163, 184, 0.38)', background: 'rgba(148, 163, 184, 0.1)', color: '#cbd5e1' },
}

export function isStagePassed(stage: DreamStage): boolean {
  return statusTone(effectiveStageStatus(stage)) === 'pass'
}

export function stageMissingMessage(stage: DreamStage): string {
  if (isStagePassed(stage)) return 'Accepted evidence is present for this phase.'
  if (stage.id === '07') {
    if (/PANEL_ASSETS/i.test(stage.status)) {
      return stage.failureOrGap || 'Storyboard references are attached. Remaining blocker: accepted storyboard panel images/start-end frames are not present yet.'
    }
    if (/REFERENCE_GAPS/i.test(stage.status)) {
      return 'Storyboard packet is blocked: missing prop/environment references required by Phase 04 contact-sheet evidence.'
    }
    return stage.failureOrGap || 'Storyboard packet needs accepted storyboard panels and reviewer evidence before provider handoff.'
  }
  return stage.failureOrGap || 'Required preflight evidence was not found for this phase.'
}

export function effectiveStageStatus(stage: DreamStage): string {
  return stage.status
}

export function crewTauRepairNote(): string {
  return [
    '[tau.agent_handoff.v1 requested]',
    'Close missing artifact: phase_03_producer_writer_director.',
    'Dispatch/queue a persona-dream Tau creator-reviewer loop for Phase 03 Crew selection.',
    'Use the full dream.crew.prompt_payload.v1 context: core idea, accepted story, interaction matrix, location, environment, linked assets, persona candidates, and current manual overrides.',
    'Selection order is mandatory: Producer first, then Scriptwriter conditioned on Producer, then Director conditioned on Producer + Scriptwriter.',
    `Write an artifact under the selected run root whose path matches one of the backend terms: ${crewGateMatchTerms.join(', ')}.`,
    `Required fields: ${crewMissingEvidenceFields.join('; ')}.`,
    'Do not mark the gate ready until the artifact exists and the phase matcher can find it.',
  ].join('\n')
}

export function isExecutionReceiptArtifact(artifact: DreamStage['artifacts'][number]): boolean {
  const text = `${artifact.label} ${artifact.path}`.toLowerCase()
  return /\.json($|\?)/.test(text) || /receipt|verdict|manifest|packet|contract|gate|ledger|mapping|audit|linter/.test(text)
}

export function fileNameFromPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? path
}

export function mediaLockStatusLabel(status: string): string {
  return status.startsWith('ACCEPTED_') ? 'ACCEPTED' : status
}

export function mediaLockGroupTimeRange(frames: MediaLockFrame[]): string {
  const first = frames[0]?.timeLabel ?? 'n/a'
  const last = frames[frames.length - 1]?.timeLabel ?? first
  return first === last ? first : `${first} - ${last}`
}

export function mediaLockFrameGroups(frames: MediaLockFrame[]): Array<{ panelId: string; frames: MediaLockFrame[] }> {
  const groups = new Map<string, MediaLockFrame[]>()
  for (const frame of frames) {
    const group = groups.get(frame.panelId) ?? []
    group.push(frame)
    groups.set(frame.panelId, group)
  }
  return Array.from(groups.entries()).map(([panelId, groupFrames]) => ({
    panelId,
    frames: groupFrames,
  }))
}

export function mediaLockFramesFromPacket(packet: unknown, projection?: StoryboardConsumerProjection): MediaLockFrame[] {
  const root = payloadObject(packet)
  const panels = payloadArray(root?.panels)
  const frames: MediaLockFrame[] = []
  for (const panel of panels) {
    const panelId = firstString(panel.panel_id, panel.id) ?? `panel_${frames.length + 1}`
    const projectedPanel = projection?.panels.find((candidate) => candidate.panelId === panelId)
    const timeRange = payloadObject(panel.time_range)
    for (const role of ['start_frame', 'end_frame']) {
      const frameWrapper = payloadObject(panel[role])
      const acceptedFrame = payloadObject(frameWrapper?.accepted_frame) ?? frameWrapper
      const projectedFrame = role === 'start_frame' ? projectedPanel?.startFrame : projectedPanel?.endFrame
      if (!projectedFrame?.url) continue
      const identityReview = payloadObject(acceptedFrame?.identity_continuity_review)
      const timeValue = role === 'start_frame' ? timeRange?.start_s : timeRange?.end_s
      frames.push({
        id: `${panelId}.${role}`,
        panelId,
        role,
        path: projectedFrame.artifactId,
        url: projectedFrame.url,
        sha256: projectedFrame.sha256,
        status: firstString(acceptedFrame?.status) ?? 'ACCEPTED_FRAME',
        identityStatus: firstString(identityReview?.status) ?? 'UNKNOWN',
        acceptedAt: firstString(acceptedFrame?.accepted_at) ?? '',
        timeLabel: typeof timeValue === 'number' ? `${timeValue.toFixed(1)}s` : 'n/a',
      })
    }
  }
  return frames
}

export function videoProviderArtifactRole(artifact: DreamArtifact): string | null {
  const text = `${artifact.label} ${artifact.path}`.toLowerCase()
  if (/provider[_-]?selection|scorecard|video[_-]?provider[_-]?selection/.test(text)) return 'selection'
  if (/kling[_-]?scene[_-]?packet|scene[_-]?packet|video[_-]?provider[_-]?packet/.test(text)) return 'scene_packet'
  if (/provider[_-]?payload[_-]?mapping|request_body|dry_run.*request|provider_request|kling[_-]?request|one_scene_kling_request/.test(text)) return 'payload_mapping'
  if (/final[_-]?gate|provider[_-]?gate|readiness/.test(text)) return 'final_gate'
  if (/fal|registry|capabilit|preflight/.test(text)) return 'registry_preflight'
  return null
}

export function providerContractArtifactRole(artifact: DreamArtifact): string | null {
  const text = `${artifact.label} ${artifact.path}`.toLowerCase()
  if (/phase11[_-]?live[_-]?request\.v1\.json/.test(text)) return 'submitted_request'
  if (/phase11[_-]?provider[_-]?return[_-]?envelope\.v1\.json/.test(text)) return 'return_envelope'
  if (/shot[_-]?bible\.json/.test(text)) return 'shot_bible'
  if (/panel[_-]?distillation[_-]?contract\.json/.test(text)) return 'contract'
  if (/final[_-]?provider[_-]?payload[_-]?by[_-]?panel\.json/.test(text)) return 'payload_by_panel'
  if (/provider[_-]?payload[_-]?field[_-]?mapping\.json/.test(text)) return 'field_mapping'
  if (/provider[_-]?payload[_-]?omitted[_-]?context\.json/.test(text)) return 'omitted_context'
  if (/provider[_-]?media[_-]?publication[_-]?receipt\.json/.test(text)) return 'publication_receipt'
  if (/provider[_-]?media[_-]?probe[_-]?receipt\.json/.test(text)) return 'probe_receipt'
  if (/provider[_-]?schema[_-]?receipt\.json/.test(text)) return 'schema_receipt'
  if (/panel[_-]?distillation[_-]?review[_-]?receipt\.json/.test(text)) return 'review_receipt'
  if (/phase10[_-]?provider[_-]?contract[_-]?receipt\.json/.test(text)) return 'contract_receipt'
  if (/phase10.*check|provider[_-]?contract.*gate|dry[_-]?run[_-]?gate/.test(text)) return 'gate_receipt'
  if (/video[_-]?provider[_-]?packet/.test(text)) return 'video_provider_packet'
  if (/provider[_-]?registry[_-]?refresh|registry[_-]?refresh/.test(text)) return 'registry_refresh'
  if (/video[_-]?provider[_-]?scorecard|scorecard/.test(text)) return 'scorecard'
  return null
}

export function shortProviderHash(value: unknown): string {
  const text = typeof value === 'string' ? value : ''
  if (text.length <= 22) return text || 'missing'
  return `${text.slice(0, 14)}...${text.slice(-6)}`
}

export function providerContractStatusTone(value: unknown): CSSProperties {
  const text = String(value ?? '').toUpperCase()
  if (text.includes('PASS')) return nvis.providerContractPillPass
  if (text.includes('BLOCK') || text.includes('MISSING') || text.includes('FAIL')) return nvis.providerContractPillBlocked
  return nvis.providerContractPillDry
}

export function formatProviderContractBlocker(value: string): string {
  return value
    .replace(/^BLOCKED_/, '')
    .replace(/^NO_/, 'NO ')
    .replace(/_/g, ' ')
    .toLowerCase()
}

export function dreamNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function dreamBooleanLabel(value: unknown): string {
  if (value === true) return 'true'
  if (value === false) return 'false'
  return 'missing'
}

export function dreamList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

export function dreamDisplayCode(value: string): string {
  return value.replace(/_/g, ' ')
}

export function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

export function payloadObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function payloadArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}

export function providerFitValue(provider: Record<string, unknown>, key: string): number | null {
  const fit = payloadObject(provider.fit)
  return dreamNumber(fit?.[key])
}

export function providerFitMax(providers: Array<Record<string, unknown>>, key: string): number | null {
  const values = providers.map((provider) => providerFitValue(provider, key)).filter((value): value is number => value != null)
  return values.length > 0 ? Math.max(...values) : null
}

export function providerFitDelta(provider: Record<string, unknown>, providers: Array<Record<string, unknown>>, key: string): number | null {
  const value = providerFitValue(provider, key)
  const max = providerFitMax(providers, key)
  if (value == null || max == null) return null
  return value - max
}

type PipelineErrorBoundaryProps = { surface?: string; children?: React.ReactNode }
type PipelineErrorBoundaryState = { hasError: boolean; error: unknown }

/**
 * Typed explicitly. It previously extended React.Component with no type
 * parameters, so this.props was Readonly<{}> and this.state.error narrowed to
 * never -- the `surface` prop it is actually passed was invisible to the
 * compiler, and the instanceof check below could not be verified.
 */
export class PipelineErrorBoundary extends React.Component<
  PipelineErrorBoundaryProps,
  PipelineErrorBoundaryState
> {
  state: PipelineErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      const message = this.state.error instanceof Error ? this.state.error.message : String(this.state.error ?? 'Unknown component fault')
      return (
        <div style={nvis.pipelineErrorBoundary}>
          <div style={nvis.pipelineErrorTitle}>
            <AlertTriangle size={18} />
            <span>{String(this.props.surface ?? 'Pipeline')} system fault detected</span>
          </div>
          <p style={nvis.pipelineErrorMessage}>{message}</p>
          <button
            type="button"
            data-qid="dream:pipeline-error-boundary:reboot"
            data-qs-action="DREAM_PIPELINE_ERROR_BOUNDARY_REBOOT"
            style={nvis.pipelineErrorButton}
            title="Reboot this pipeline component"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Reboot component
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export function rebindProviderContractAssetPath(path: string, revisionRoot: string | null): string {
  if (!revisionRoot) return path
  const phaseIndex = path.indexOf('/phase_07_storyboard_live_tau/')
  if (phaseIndex < 0) return path
  return `${revisionRoot}${path.slice(phaseIndex)}`
}

export function highlightJsonForProviderContract(json: string): React.ReactNode[] {
  return json.split('\n').flatMap((line, lineIndex) => {
    const nodes = highlightJsonLineForProviderContract(line, lineIndex)
    return lineIndex === json.split('\n').length - 1 ? nodes : [...nodes, <br key={`json-br-${lineIndex}`} />]
  })
}

export function highlightJsonLineForProviderContract(line: string, lineIndex: number): React.ReactNode[] {
  const tokenRegex = /("(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}\[\],:])/g
  const nodes: React.ReactNode[] = []
  let cursor = 0
  let tokenIndex = 0
  for (const match of line.matchAll(tokenRegex)) {
    const token = match[0]
    const start = match.index ?? 0
    if (start > cursor) nodes.push(line.slice(cursor, start))
    const after = line.slice(start + token.length).trimStart()
    const style = providerContractJsonTokenStyle(token, after)
    nodes.push(<span key={`json-${lineIndex}-${tokenIndex++}`} style={style}>{token}</span>)
    cursor = start + token.length
  }
  if (cursor < line.length) nodes.push(line.slice(cursor))
  return nodes
}

export function providerContractJsonTokenStyle(token: string, after: string): CSSProperties {
  if (/^"/.test(token) && after.startsWith(':')) return nvis.providerContractSyntaxKey
  if (/^"/.test(token)) return nvis.providerContractSyntaxString
  if (/^(true|false|null)$/.test(token)) return nvis.providerContractSyntaxBoolean
  if (/^-?\d/.test(token)) return nvis.providerContractSyntaxNumber
  return nvis.providerContractSyntaxPunctuation
}

export function parseProviderContractAudioSummary(value: string): Array<{ label: string; value: string }> {
  return String(value ?? '')
    .split('/')
    .map((part) => part.trim())
    .map((part) => {
      const [label, ...rest] = part.split('=')
      return { label: label?.trim(), value: rest.join('=').trim() }
    })
    .filter((pair): pair is { label: string; value: string } => Boolean(pair.label && pair.value))
}

export function providerContractAudioValueTone(value: string): 'warning' | 'neutral' {
  return /missing|false|no_dialogue|not[_\s-]?run/i.test(value) ? 'warning' : 'neutral'
}

export function panelHasAcceptedStoryboardFrames(panel: Record<string, unknown>): boolean {
  const startFrame = storyboardRecord(panel.start_frame)
  const endFrame = storyboardRecord(panel.end_frame)
  return Boolean(acceptedStoryboardFrame(startFrame) && acceptedStoryboardFrame(endFrame))
}

export function storyboardTargetPanelIds(packet: Record<string, unknown> | null): string[] {
  const generationScope = storyboardRecord(packet?.generation_scope)
  const targetPanelIds = generationScope.target_panel_ids
  if (!Array.isArray(targetPanelIds)) return []
  return targetPanelIds.map(String).filter(Boolean)
}

export function acceptedStoryboardFrame(frame: Record<string, unknown>): Record<string, unknown> | null {
  const accepted = storyboardRecord(frame.accepted_frame)
  const status = String(accepted.status ?? '')
  const path = String(accepted.path ?? accepted.image_path ?? '')
  if (!path) return null
  if (!/^ACCEPTED_(START|END)_FRAME$|^ACCEPTED_STORYBOARD_FRAME$|^PASS_PANEL_REVIEWED$/.test(status)) return null
  return accepted
}

export function storyboardRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

export function storyboardStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

export function storyboardShotCode(shot: string): string {
  const value = shot.toLowerCase()
  if (value.includes('extreme wide')) return 'EWS'
  if (value.includes('wide') || value.includes('establish')) return 'WS'
  if (value.includes('medium')) return 'MS'
  if (value.includes('close')) return 'CU'
  if (value.includes('waterline')) return 'POV'
  if (value.includes('two-character') || value.includes('two character')) return 'MWS'
  return 'SHOT'
}

export function authorStyleGuide(authorLabel: string, memoryStyle: string): string {
  const sourceStyle = memoryStyle.trim()
  const author = authorLabel.trim() || 'the selected author persona'
  return [
    `Requested author reference: ${author}. Do not imitate this author directly. Translate the reference into high-level craft traits for an original Phase 02 story treatment.`,
    sourceStyle ? `Stored persona style context: ${sourceStyle}` : 'Stored persona style context: none returned.',
    'Use a competent, practical protagonist solving concrete physical problems under pressure. The problems should be real, specific, and visible in the scene. Solutions should be earned through observation, trial, failure, iteration, and clear causal reasoning.',
    'Technical detail must function as plot, not decoration. Exposition should feel like active problem-solving rather than lecturing. Every detail about swell timing, reef depth, softened wax, glare, heat, fatigue, phones, and etiquette should have consequences for character choices.',
    'Humor should come from intelligence, stress, and self-awareness, not from pasted-on jokes. Keep the tone conversational, optimistic, precise, propulsive, and human.',
    'Pacing should move through problem, constraint, attempted solution, complication, and embodied decision. The reader should understand the practical problem well enough to feel the satisfaction of the choice or solution.',
    'Avoid direct prose imitation, signature phrasing, borrowed character types, borrowed plots, or fan-fiction echoes. Use the craft traits only.',
  ].join(' ')
}

export const contactSheetDecisionForStoryRow = (row: Pick<StoryMatrixRow, 'name' | 'objects' | 'dynamics' | 'note'>): ContactSheetDecision => {
  const name = row.name.toLowerCase()
  const text = `${row.name} ${row.objects} ${row.dynamics} ${row.note}`.toLowerCase()
  if (/\b(shortboard|surfboard|board|rashguard|phone)\b/.test(name)) {
    return {
      required: true,
      kind: 'prop',
      status: 'missing',
      send_to_kling: true,
      priority: 'conditional',
      rationale: 'Visually specific props or wardrobe affect staging; include a reference sheet when visible in the panel.',
    }
  }
  if (/\b(kahalu|kona|bay|coast|reef|beach|lineup|bed|bedroom|garage|swell)\b/.test(name)) {
    return {
      required: true,
      kind: 'environment',
      status: 'missing',
      send_to_kling: true,
      priority: 'recommended',
      rationale: 'Stable scene geometry should use a compact environment reference when it anchors the panel.',
    }
  }
  if (/^(embry|embry lawson|kai|kai akana)$/.test(name.trim())) {
    return {
      required: true,
      kind: 'character',
      status: 'existing_or_required',
      send_to_kling: true,
      priority: 'required',
      rationale: 'Character identity continuity must be locked before video provider generation.',
    }
  }
  if (/\b(shortboard|surfboard|board|rashguard|phone)\b/.test(text)) {
    return {
      required: true,
      kind: 'prop',
      status: 'missing',
      send_to_kling: true,
      priority: 'conditional',
      rationale: 'Visually specific props or wardrobe affect staging; include a reference sheet when visible in the panel.',
    }
  }
  if (/\b(kahalu|kona|bay|coast|reef|beach|lineup|bed|bedroom|garage)\b/.test(text)) {
    return {
      required: true,
      kind: 'environment',
      status: 'missing',
      send_to_kling: true,
      priority: 'recommended',
      rationale: 'Stable scene geometry should use a compact environment reference when it anchors the panel.',
    }
  }
  return {
    required: false,
    kind: 'prompt_only',
    status: 'not_needed',
    send_to_kling: false,
    priority: 'prompt_only',
    rationale: 'Abstract forces such as heat, humidity, glare, etiquette, or fatigue should be described in the prompt, not as contact sheets.',
  }
}

export function parseStoryDraftJson(draft: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(draft)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

export function storyDisplayText(draft: string): string {
  const parsed = parseStoryDraftJson(draft)
  if (!parsed) return draft
  const story = parsed.story
  if (typeof story === 'string' && story.trim()) return story
  const panel = parsed.panel
  if (panel && typeof panel === 'object' && !Array.isArray(panel)) {
    const pieces = ['shot', 'action', 'emotional_turn', 'dialogue']
      .map((key) => (panel as Record<string, unknown>)[key])
      .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    if (pieces.length > 0) return pieces.join(' ')
  }
  return draft
}

export function storyEntityGlossary(draft: string): GlossaryTerm[] {
  const parsed = parseStoryDraftJson(draft)
  const terms = new Map<string, GlossaryTerm>()
  const addTerm = (term: unknown) => {
    const text = String(term ?? '').trim()
    if (text.length < 3) return
    const key = text.toLowerCase()
    if (!terms.has(key)) terms.set(key, { term: text, type: 'domain_term' })
  }
  ;[
    'Embry',
    'Kai',
    'Hawaii',
    'Hawaiʻi',
    'Big Island',
    'Kahaluʻu Bay',
    'Kona Coast',
    'surfboard',
    'shortboard',
    'reef',
    'lava reef',
    'swell',
    'June swell',
    'heat',
    'humidity',
    'glare',
    'wax',
    'phone',
    'local etiquette',
  ].forEach(addTerm)
  const matrix = Array.isArray(parsed?.interaction_matrix) ? parsed?.interaction_matrix as Array<Record<string, unknown>> : []
  matrix.forEach((row) => {
    addTerm(row.entity)
    const objects = Array.isArray(row.objects_used) ? row.objects_used : Array.isArray(row.objects) ? row.objects : []
    objects.forEach((object) => addTerm(object))
  })
  return [...terms.values()]
}

export function compactStoryStatus(value: string): string {
  const trimmed = value.trim()
  if (trimmed.startsWith('Loaded latest Tau story')) return 'Loaded latest Tau story'
  if (trimmed.startsWith('Tau story loop')) return trimmed.split(':')[0] || trimmed
  return trimmed
}

export function storyContractSummaryFromDraft(draft: string): {
  parsed: Record<string, unknown> | null
  story: string
  interactionMatrix: unknown[]
  location: unknown
  environment: unknown
} {
  const parsed = parseStoryDraftJson(draft)
  const story = typeof parsed?.story === 'string' ? parsed.story : draft
  return {
    parsed,
    story,
    interactionMatrix: Array.isArray(parsed?.interaction_matrix) ? parsed.interaction_matrix : [],
    location: parsed?.location ?? null,
    environment: parsed?.environment ?? null,
  }
}

export function personaText(value: Record<string, unknown>): string {
  return [
    value.title,
    value.template,
    value.persona_type,
    value.writing_style,
    value.runtime_persona_card,
    value.summary,
    value.content,
    value.retrieval_text,
    value.evidence_text,
    value.description,
    value.visual_philosophy,
    value.use_when,
    value.source_path,
  ].map((item) => String(item ?? '').trim()).filter(Boolean).join(' ').replace(/\s+/g, ' ').trim()
}

async function loadCrewPersonaCandidates(): Promise<CrewPersonaOption[]> {
  const byId = new Map<string, CrewPersonaOption>()
  const mergePersonaOption = (item: Record<string, unknown>, source: CrewPersonaOption['source']) => {
    if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return
    const id = String(item.persona_id || item.canonical_persona_id || item._key || '').replace(/^persona_/, '').replace(/_root$/, '').trim()
    if (!id) return
    const existing = byId.get(id)
    const text = personaText(item)
    const label = String(item.canonical_name || item.display_name || item.name || id.replace(/_/g, ' ')).trim()
    const description = [existing?.description, text].filter(Boolean).join(' ').replace(/\s+/g, ' ').slice(0, 2200)
    const rawRoles = [item.role, item.template, item.persona_type, item.roles, item.crew_roles].flatMap((value) => Array.isArray(value) ? value : [value])
    const roles = new Set([...(existing?.roles ?? []), ...rawRoles.map((value) => String(value ?? '').trim().toLowerCase()).filter(Boolean)])
    const rawPaths = [item.source_path, item.path, item.file_path, item.source_paths].flatMap((value) => Array.isArray(value) ? value : [value])
    const sourcePaths = new Set([...(existing?.sourcePaths ?? []), ...rawPaths.map((value) => String(value ?? '').trim()).filter(Boolean)])
    const thumbnailPath = String(item.thumbnail_path || existing?.thumbnailPath || '').trim()
    const thumbnailConfidence = String(item.thumbnail_confidence || existing?.thumbnailConfidence || '').trim()
    byId.set(id, {
      id,
      label: existing?.label || label,
      description,
      source: existing?.source === 'personas' ? existing.source : source,
      roles: [...roles],
      sourcePaths: [...sourcePaths],
      thumbnailPath: thumbnailPath || undefined,
      thumbnailConfidence: thumbnailConfidence || undefined,
    })
  }

  const personasResponse = await fetch('/api/memory/list', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      collection: 'personas',
      filters: { doc_type: 'persona_profile' },
      limit: 500,
    }),
  })
  if (personasResponse.ok) {
    const data = await personasResponse.json()
    const documents = Array.isArray(data.documents) ? data.documents as Array<Record<string, unknown>> : []
    documents.forEach((item) => mergePersonaOption(item, 'personas'))
  }

  const [sourceResponse, identityResponse, styleResponse] = await Promise.all([
    fetch('/api/memory/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection: 'persona_memory', filters: { record_type: 'persona_source_file' }, limit: 500 }),
    }),
    fetch('/api/memory/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection: 'persona_memory', filters: { record_type: 'persona_identity' }, limit: 300 }),
    }),
    fetch('/api/memory/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection: 'persona_memory', filters: { record_type: 'persona_style' }, limit: 300 }),
    }),
  ])
  for (const response of [sourceResponse, identityResponse, styleResponse]) {
    if (!response.ok) continue
    const data = await response.json()
    const documents = Array.isArray(data.documents) ? data.documents as Array<Record<string, unknown>> : []
    documents.forEach((item) => mergePersonaOption(item, 'persona_memory'))
  }
  return [...byId.values()].filter((option) => option.description)
}

export function scoreCrewPersona(role: CrewRole, option: CrewPersonaOption): number {
  const haystack = `${option.id} ${option.label} ${option.description}`.toLowerCase()
  const roleSet = new Set(option.roles.map((item) => item.toLowerCase()))
  const paths = option.sourcePaths.join(' ').toLowerCase()
  const isFilmmakingSource = paths.includes('/directors/') || paths.includes('/writers/') || paths.includes('/producers/') || paths.includes('/sound_designers/')
  if (role === 'producer' && !paths.includes('/producers/')) return -999
  if (role === 'director' && !paths.includes('/directors/')) return -999
  if (role === 'scriptwriter' && !(paths.includes('/writers/') || paths.includes('/directors/'))) return -999
  const terms: Record<CrewRole, string[]> = {
    producer: ['producer', 'showrunner', 'production', 'budget', 'low budget', 'high budget', 'financing', 'genre', 'scope', 'logistics', 'feasibility', 'schedule', 'safety', 'continuity', 'packaging'],
    scriptwriter: ['scriptwriter', 'screenwriter', 'screenplay', 'writer', 'dialogue', 'script', 'scene', 'character', 'beat', 'adaptation', 'structure'],
    director: ['director', 'filmmaker', 'cinematic', 'visual', 'performance', 'blocking', 'camera', 'shot', 'staging', 'action', 'water', 'surf', 'thriller', 'kinetic', 'point break', 'bigelow'],
  }
  if (/\bandy\s+weir\b|\bweir\b/.test(haystack)) return -999
  const explicitRoleScore = roleSet.has(role) ? 120 : 0
  const pathRoleScore =
    role === 'director' && paths.includes('/directors/') ? 80
      : role === 'scriptwriter' && (paths.includes('/writers/') || roleSet.has('writer')) ? 60
        : role === 'producer' && paths.includes('/producers/') ? 100
          : 0
  const roleFloor =
    role === 'producer'
      ? (isFilmmakingSource && (explicitRoleScore || pathRoleScore) ? 0 : -180)
      : role === 'scriptwriter'
        ? (explicitRoleScore || pathRoleScore || roleSet.has('writer') ? 0 : -40)
        : (explicitRoleScore || pathRoleScore ? 0 : -30)
  const storyFit = role === 'producer'
    ? (haystack.includes('blue crush') ? 80 : 0)
      + (haystack.includes('female-athlete') || haystack.includes('female athlete') ? 45 : 0)
      + (haystack.includes('hawaii') ? 30 : 0)
      + (haystack.includes('surf') ? 24 : 0)
      + (haystack.includes('water') ? 14 : 0)
      + (haystack.includes('point break') ? 12 : 0)
      + (haystack.includes('action-thriller') ? 4 : 0)
    : (haystack.includes('surf') ? 18 : 0)
      + (haystack.includes('hawaii') ? 16 : 0)
      + (haystack.includes('blue crush') ? 28 : 0)
      + (haystack.includes('point break') ? 22 : 0)
      + (haystack.includes('female protagonist') ? 10 : 0)
      + (haystack.includes('water') ? 8 : 0)
  return terms[role].reduce((score, term) => score + (haystack.includes(term) ? 10 : 0), 0)
    + explicitRoleScore
    + pathRoleScore
    + roleFloor
    + storyFit
}

export function chooseCrewPersona(role: CrewRole, candidates: CrewPersonaOption[], avoid: string[] = []): CrewPersonaOption | null {
  const usable = candidates.filter((candidate) => !avoid.includes(candidate.id))
  const ranked = usable
    .map((candidate) => ({ candidate, score: scoreCrewPersona(role, candidate) }))
    .sort((a, b) => b.score - a.score || a.candidate.label.localeCompare(b.candidate.label))
  return ranked.find((item) => item.score > 0)?.candidate ?? null
}

export function roleFitCandidates(role: CrewRole, candidates: CrewPersonaOption[], avoid: string[] = []): CrewPersonaOption[] {
  return candidates
    .filter((candidate) => !avoid.includes(candidate.id))
    .map((candidate) => ({ candidate, score: scoreCrewPersona(role, candidate) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.candidate.label.localeCompare(b.candidate.label))
    .map((item) => item.candidate)
}

export function crewRoleCriteria(role: CrewRole): string {
  if (role === 'producer') return 'budget scale, genre fit, logistics, feasibility, water safety, continuity, and whether the story can become an executable production package'
  if (role === 'scriptwriter') return 'screenplay structure, dialogue restraint, character fidelity, physical staging, and continuity with the selected producer rationale'
  return 'visual grammar, waterline action staging, performance direction, tone, pacing, camera logic, and continuity with the producer plus scriptwriter choices'
}

export function crewFitRationale(role: CrewRole, selected: CrewPersonaOption | null, storyContract: ReturnType<typeof storyContractSummaryFromDraft>): string {
  if (!selected) return `No role-fit ${role} persona was selected from memory. The selector is fail-closed until a candidate has explicit ${role} relevance.`
  const context = `${selected.id} ${selected.label} ${selected.description}`.toLowerCase()
  const hits = [
    'budget',
    'genre',
    'production',
    'screenplay',
    'dialogue',
    'director',
    'camera',
    'action',
    'water',
    'surf',
    'continuity',
    'feasibility',
    'performance',
    'staging',
  ].filter((term) => context.includes(term)).slice(0, 4)
  const storyAnchor = storyContract.story ? 'using the accepted story beat and interaction matrix' : 'with the story contract still missing'
  return `${selected.label} is selected for ${crewRoleCriteria(role)} ${storyAnchor}. Evidence terms from memory: ${hits.length ? hits.join(', ') : 'role metadata is thin; review before dispatch'}.`
}

export function compactCrewText(value: string, max = 360): string {
  const clean = value.replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}

export function personaThumbnailUrl(option: CrewPersonaOption | null): string {
  if (!option?.thumbnailPath) return ''
  const root = '/mnt/storage12tb/media/personas/'
  if (!option.thumbnailPath.startsWith(root)) return ''
  const relative = option.thumbnailPath.slice(root.length)
  const [persona, ...rest] = relative.split('/')
  if (!persona || rest.length === 0) return ''
  return `/api/persona-media?persona=${encodeURIComponent(persona)}&path=${encodeURIComponent(rest.join('/'))}`
}

export function productionTechniquePackage(storyContract: ReturnType<typeof storyContractSummaryFromDraft>, linkedAssets: LinkedStoryAsset[]) {
  const hasWaterAssets = linkedAssets.some((asset) => `${asset.title} ${asset.description ?? ''}`.toLowerCase().includes('surf'))
  return {
    camera_package: 'ARRI ALEXA 35 or Sony VENICE 2 in a compact water-safe configuration; use a smaller action/water housing camera only for board-level inserts.',
    lens_package: '35mm spherical for waterline realism, 50mm for restrained character compression, and a wide 24mm insert option for reef/board proximity.',
    lighting_strategy: 'Natural daylight surf window with hard glare, negative fill from the waterline, polarizing reflection control, and no artificial glossy studio lighting.',
    movement_rules: 'Restrained handheld or stabilized waterline tracking; no random fast cuts. Movement should follow swell timing, paddle rhythm, and reef caution.',
    color_grade: 'Naturalistic Kona daylight, controlled highlights, warm skin tones, blue-green water, visible salt haze, and subtle documentary grain.',
    continuity_locks: [
      'same daylight surf window',
      'same navy Embry rashguard and black Kai rashguard',
      'same lava reef constraint',
      'same softened wax and board grip pressure',
      'same public beach/social etiquette pressure',
      hasWaterAssets ? 'reuse linked surf media descriptions for visual continuity' : 'do not invent media details without stored descriptions',
    ],
  }
}

export function rolePrompt(role: CrewRole, contextLabel: string): string {
  const roleTitle = role === 'scriptwriter' ? 'Scriptwriter' : role[0].toUpperCase() + role.slice(1)
  const criteria: Record<CrewRole, string> = {
    producer: 'scope control, continuity, feasibility, downstream readiness, environmental constraints, and whether the story contract is ready for adaptation',
    scriptwriter: 'prose-to-script adaptation, sparse dialogue, physical staging, character fidelity, surf/environment causality, and continuity with the selected producer rationale',
    director: 'visual grammar, performance direction, waterline staging, reef/surf safety realism, tone, pacing, and continuity with producer plus scriptwriter choices',
  }
  return [
    `Select the best ${roleTitle} persona for ${contextLabel}.`,
    `Use only the provided persona candidate pool and the full upstream story context.`,
    `Choose based on ${criteria[role]}.`,
    role === 'producer'
      ? 'This is the first selection. Choose the Producer only. The selected Producer rationale becomes required context for selecting the Scriptwriter and Director.'
      : role === 'scriptwriter'
        ? 'This is the second selection. Use the selected Producer and producer rationale as context, then choose the Scriptwriter.'
        : 'This is the third selection. Use the selected Producer, producer rationale, selected Scriptwriter, and scriptwriter rationale as context, then choose the Director.',
    'Return strict JSON with selected_persona_id, selected_persona_name, role_fit_score, evidence_from_story_contract, relevant_persona_traits, rejected_alternatives, risks_or_gaps, and downstream_instruction.',
  ].join(' ')
}

export function distinctAssetDescription(asset: LinkedStoryAsset): string | null {
  const title = asset.title.replace(/\s+/g, ' ').trim().toLowerCase()
  const description = (asset.description ?? '').replace(/\s+/g, ' ').trim()
  const normalizedDescription = description.toLowerCase()
  if (!description || title === normalizedDescription || title.includes(normalizedDescription) || normalizedDescription.includes(title)) return null
  return description
}

export function parseDreamJson(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

export function scriptContractFromDraft(draft: string): Record<string, unknown> | null {
  const parsed = parseDreamJson(draft)
  if (!parsed) return null
  if (typeof parsed.script === 'string' || Array.isArray(parsed.entity_environment_script_table)) return parsed
  const nested = parsed.script_contract
  return nested && typeof nested === 'object' && !Array.isArray(nested) ? nested as Record<string, unknown> : parsed
}

export function scriptStringFromContract(contract: Record<string, unknown> | null, draft: string): string {
  const script = contract?.script
  return typeof script === 'string' && script.trim().length > 0 ? script.trim() : draft.trim()
}

export function scriptEntityRows(contract: Record<string, unknown> | null, storyContract: ReturnType<typeof storyContractSummaryFromDraft>): Array<Record<string, unknown>> {
  if (Array.isArray(contract?.entity_environment_script_table)) return contract.entity_environment_script_table as Array<Record<string, unknown>>
  if (Array.isArray(contract?.interaction_matrix)) return contract.interaction_matrix as Array<Record<string, unknown>>
  return storyContract.interactionMatrix.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object' && !Array.isArray(row))
}

export function scriptGlossaryFromContract(contract: Record<string, unknown> | null, storyContract: ReturnType<typeof storyContractSummaryFromDraft>): GlossaryTerm[] {
  const terms = new Map<string, GlossaryTerm>()
  const add = (value: unknown) => {
    const term = String(value ?? '').trim()
    if (term.length < 3) return
    const key = term.toLowerCase()
    if (!terms.has(key)) terms.set(key, { term, type: 'domain_term' })
  }
  scriptEntityRows(contract, storyContract).forEach((row) => {
    add(row.entity ?? row.name)
    const objects = Array.isArray(row.objects_used) ? row.objects_used : Array.isArray(row.objects) ? row.objects : []
    objects.forEach(add)
  })
  return [...terms.values()]
}

export function splitScriptIntoRows(script: string): Array<{ element: string; content: string }> {
  const lines = script.split(/\r?\n/)
  const rows: Array<{ element: string; content: string }> = []
  let currentElement = 'ACTION'
  let buffer: string[] = []
  let mode: 'scene' | 'action' | 'dialogue' = 'action'
  const flush = () => {
    const content = buffer.join('\n').trim()
    if (content) rows.push({ element: currentElement, content })
    buffer = []
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    const trimmed = line.trim()
    if (!trimmed) {
      if (buffer.length) buffer.push('')
      continue
    }
    if (/^(?:INT\.|EXT\.|INT\/EXT\.|EST\.)\b/i.test(trimmed)) {
      flush()
      currentElement = 'SCENE'
      mode = 'scene'
      buffer.push(trimmed)
      continue
    }
    if (/^ACTION$/i.test(trimmed)) {
      flush()
      currentElement = 'ACTION'
      mode = 'action'
      continue
    }
    if (/^DIALOGUE$/i.test(trimmed)) {
      flush()
      mode = 'dialogue'
      currentElement = 'DIALOGUE'
      continue
    }
    if (mode === 'dialogue' && /^[A-Z][A-Z0-9 .'-]{1,32}$/.test(trimmed)) {
      flush()
      rows.push({ element: 'CHARACTER', content: trimmed })
      currentElement = 'DIALOGUE'
      continue
    }
    buffer.push(trimmed)
  }
  flush()
  return rows
}

export function coverageNoteForScriptRow(index: number, rows: Array<Record<string, unknown>>): string {
  if (rows.length === 0) return 'No persisted interaction-matrix coverage is loaded for this script row.'
  const row = rows[index % rows.length]
  const entity = String(row.entity ?? row.name ?? row.source_seed_id ?? 'Matrix row').trim()
  const interaction = String(row.environment_interaction ?? row.script_evidence ?? row.script_function ?? row.dynamics ?? '').trim()
  const missing = Array.isArray(row.missing_script_details) ? row.missing_script_details : []
  const missingText = missing.length > 0 ? ` Missing: ${missing.map((item) => String(item)).join(', ')}.` : ''
  return [entity ? `${entity}:` : '', interaction || 'Coverage row is present but has no script evidence note.', missingText].join(' ').replace(/\s+/g, ' ').trim()
}

export function scriptCoverageStatusForRow(index: number, rows: Array<Record<string, unknown>>): ScriptCoverageStatus {
  if (rows.length === 0) return 'pending'
  const row = rows[index % rows.length]
  const missing = Array.isArray(row.missing_script_details) ? row.missing_script_details : []
  const hasEvidence = Boolean(
    String(row.environment_interaction ?? row.script_evidence ?? row.script_function ?? row.dynamics ?? '').trim(),
  )
  if (row.described_in_script === false || row.covered_in_script === false || missing.length > 0) return 'failed'
  if (row.described_in_script === true || row.covered === true || row.covered_in_script === true || hasEvidence) return 'verified'
  return 'pending'
}

export function scriptCoverageStatusTitle(status: ScriptCoverageStatus, index: number, rows: Array<Record<string, unknown>>): string {
  if (rows.length === 0) return 'Pending: no persisted interaction-matrix coverage is loaded.'
  const row = rows[index % rows.length]
  const entity = String(row.entity ?? row.name ?? row.source_seed_id ?? 'matrix row').trim()
  const missing = Array.isArray(row.missing_script_details) ? row.missing_script_details.map((item) => String(item)).join(', ') : ''
  if (status === 'failed') return missing ? `Failed: ${entity} missing ${missing}` : `Failed: ${entity} needs script coverage`
  if (status === 'verified') return `Verified: ${entity} is described in the script coverage`
  return `Pending: ${entity} has not been reviewed yet`
}

export function stageArtifactSummary(stage: DreamStage | undefined): Array<{ label: string; path: string; kind: string }> {
  return (stage?.artifacts ?? []).map((artifact) => ({
    label: artifact.label,
    path: artifact.path,
    kind: artifact.kind,
  }))
}

export function stageImageSummary(stage: DreamStage | undefined): Array<{ label: string; path: string; url: string }> {
  return (stage?.images ?? []).map((image) => ({
    label: image.label,
    path: image.path,
    url: image.url,
  }))
}

export function groupResearchContext(research: ResearchMemoryResult[]): Array<{ label: string; items: ResearchMemoryResult[] }> {
  const groups = new Map<string, ResearchMemoryResult[]>([
    ['Story & Script Contracts', []],
    ['Entity & Env References', []],
    ['Rich Media References', []],
  ])
  for (const item of research) {
    const text = `${item.title ?? ''} ${item.memoryKey ?? ''} ${item.snippet ?? ''} ${item.url ?? ''}`.toLowerCase()
    const label = /audio|video|wav|mp3|mp4|mov|surfing clip|drone/.test(text)
      ? 'Rich Media References'
      : /character|sheet|reference|embry|kai|lava|reef|environment|asset|image|photo|png|jpg|jpeg/.test(text)
        ? 'Entity & Env References'
        : 'Story & Script Contracts'
    groups.get(label)?.push(item)
  }
  return Array.from(groups.entries())
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }))
}

export function nodeKindColor(kind: TraceNodeKind): string {
  switch (kind) {
    case 'idea': return '#4a9eff'
    case 'media': return '#a78bfa'
    case 'video': return '#a78bfa'
    case 'audio': return '#8b5cf6'
    case 'person': return '#60a5fa'
    case 'object': return '#4ade80'
    case 'place': return '#f59e0b'
    default: return '#94a3b8'
  }
}

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

export function extractPersonaMemoryKey(memory: { id: string; label: string; subtitle?: string; imageUrl?: string; mediaType?: string; memoryKey?: string }): string | undefined {
  if (memory.memoryKey) return memory.memoryKey
  const haystack = [memory.subtitle, memory.id, memory.label, memory.imageUrl, memory.mediaType].filter(Boolean).join(' ')
  const direct = haystack.match(/\b((?:embry|kai_akana|embry_kai)[a-z0-9_]*?(?:media_asset|memory)[a-z0-9_.-]*)\b/i)
  if (direct?.[1]) return direct[1].replace(/[),.;:'"\]]+$/g, '')
  const endpoint = haystack.match(/\bpersona_memory\/([a-zA-Z0-9_.:-]+)\b/)
  if (endpoint?.[1]) return endpoint[1].replace(/[),.;:'"\]]+$/g, '')
  return undefined
}

export function endpointParts(endpoint: string): { collection: string; key: string } | null {
  const match = endpoint.match(/^([a-zA-Z0-9_-]+)\/(.+)$/)
  if (!match?.[1] || !match?.[2]) return null
  return { collection: match[1], key: match[2] }
}

async function memoryByKeysDocuments(collection: string, keys: string[], keyField?: string, returnFields?: string[]): Promise<Array<Record<string, unknown>>> {
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

async function memoryListByEndpoint(endpoint: string): Promise<Record<string, unknown> | null> {
  const parts = endpointParts(endpoint)
  if (!parts) return null
  const docs = await memoryByKeysDocuments(parts.collection, [parts.key])
  return docs[0] ?? null
}

async function memoryEdgeDocuments(collection: string, endpoint: string, keyField: '_from' | '_to'): Promise<Array<Record<string, unknown>>> {
  return memoryByKeysDocuments(collection, [endpoint], keyField)
}

async function memoryRecallDocuments(q: string, collections: string[], k = 18): Promise<Array<Record<string, unknown>>> {
  const response = await fetch('/api/memory/recall', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q, collections, tags: ['persona:embry'], k }),
  })
  if (!response.ok) throw new Error(`memory/recall HTTP ${response.status}`)
  const data = await response.json()
  return Array.isArray(data.items) ? data.items as Array<Record<string, unknown>> : []
}

export function hasLiveDescriptionReceipt(doc: Record<string, unknown> | null | undefined): boolean {
  if (!doc) return false
  const receipt = doc.description_receipt && typeof doc.description_receipt === 'object'
    ? doc.description_receipt as Record<string, unknown>
    : null
  const hasDescription = [doc.media_description, doc.vlm_description, doc.audio_caption, doc.text_summary, doc.story_prompt_summary, doc.description]
    .some((value) => value != null && String(value).trim().length > 0)
  return hasDescription && doc.description_status === 'READY' && receipt?.mocked === false && receipt?.live === true
}

async function loadPhase02MediaGate(): Promise<Phase02MediaGate> {
  const requiredKeys = [...phase02RequiredMediaKeys, ...phase02RequiredTextKeys]
  const docs = await memoryByKeysDocuments('persona_memory', requiredKeys)
  const docsByKey = new Map(docs.map((doc) => [String(doc._key ?? ''), doc]))
  const describedCount = requiredKeys.filter((key) => hasLiveDescriptionReceipt(docsByKey.get(key))).length
  const mediaEndpoints = phase02RequiredMediaKeys.map((key) => `persona_memory/${key}`)
  const [
    personaFromEdges,
    personaToEdges,
    tomFromEdges,
    tomToEdges,
  ] = await Promise.all([
    memoryByKeysDocuments('persona_memory_edges', mediaEndpoints, '_from').catch(() => []),
    memoryByKeysDocuments('persona_memory_edges', mediaEndpoints, '_to').catch(() => []),
    memoryByKeysDocuments('tom_edges', mediaEndpoints, '_from').catch(() => []),
    memoryByKeysDocuments('tom_edges', mediaEndpoints, '_to').catch(() => []),
  ])
  const personaEdgeCount = personaFromEdges.length + personaToEdges.length
  const tomEdgeCount = tomFromEdges.length + tomToEdges.length
  return {
    status: describedCount === requiredKeys.length && personaEdgeCount >= 8 && tomEdgeCount >= 8 ? 'PASS' : 'MISSING',
    describedCount,
    requiredCount: requiredKeys.length,
    personaEdgeCount,
    tomEdgeCount,
  }
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

export function dreamAssetUrl(value?: string): string | undefined {
  if (!value) return undefined
  if (/^(https?:\/\/|\/api\/|\/assets\/)/i.test(value)) return value
  if (value.startsWith('/mnt/storage12tb/media/personas/')) return `/api/projects/dream/asset?path=${encodeURIComponent(value)}`
  if (value.startsWith('/home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/')) return `/api/projects/dream/asset?path=${encodeURIComponent(value)}`
  if (value.startsWith('/mnt/storage12tb/skills/persona-dream/outputs/')) return `/api/projects/dream/asset?path=${encodeURIComponent(value)}`
  return value.startsWith('/') ? `/api/projects/dream/asset?path=${encodeURIComponent(value)}` : undefined
}

export function graphMediaSourceFromDocument(doc?: Record<string, unknown> | null): string | undefined {
  const candidates = [doc?.source_path, doc?.url, doc?.asset_url, doc?.public_url, doc?.path, doc?.poster_path, doc?.keyframe_path, doc?.thumbnail_path, doc?.thumbnail_url]
  const value = candidates.find((candidate) => typeof candidate === 'string' && /\.(png|jpe?g|webp|gif|mp4|mov|wav|mp3)$/i.test(candidate))
  return typeof value === 'string' ? dreamAssetUrl(value) : undefined
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

export function storyboardPanelPromptText(payload: Record<string, unknown>): string {
  const prompt = storyboardRecord(payload.generation_prompt)
  const startFrame = storyboardRecord(payload.start_frame)
  const endFrame = storyboardRecord(payload.end_frame)
  const lines = [
    `Panel: ${String(payload.panel_id ?? 'unknown')}`,
    `Time range: ${JSON.stringify(payload.time_range ?? {})}`,
    '',
    'SHOT',
    String(payload.shot ?? ''),
    '',
    'ACTION',
    String(payload.action ?? ''),
    '',
    payload.dialogue ? `DIALOGUE\n${String(payload.dialogue)}\n` : '',
    'PANEL GENERATION PROMPT',
    String(prompt.panel_prompt ?? ''),
    '',
    'START FRAME PROMPT',
    String(prompt.start_frame_prompt ?? startFrame.description ?? ''),
    '',
    'END FRAME PROMPT',
    String(prompt.end_frame_prompt ?? endFrame.description ?? ''),
    '',
    'NEGATIVE PROMPT',
    String(prompt.negative_prompt ?? ''),
    '',
    'REQUIRED ENTITIES',
    storyboardStringList(payload.required_entities).join(', '),
    '',
    'COVERAGE SEED IDS',
    storyboardStringList(payload.coverage_seed_ids).join(', '),
    '',
    'REVIEWER HARD GATE',
    'Reject when Embry or Kai are required but missing, generic, wrong, occluded, too distant, or not reference-matched.',
  ]
  return lines.filter((line) => line !== '').join('\n')
}

export function sanitizeZipName(value: string): string {
  return value
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 120) || 'asset'
}

export function assetExtension(path: string, contentType?: string | null): string {
  const fromPath = path.match(/\.(png|jpe?g|webp|gif|mp4|mov|wav|mp3)(?:[?#].*)?$/i)?.[1]
  if (fromPath) return fromPath.toLowerCase().replace('jpeg', 'jpg')
  if (contentType?.includes('png')) return 'png'
  if (contentType?.includes('jpeg')) return 'jpg'
  if (contentType?.includes('webp')) return 'webp'
  if (contentType?.includes('gif')) return 'gif'
  if (contentType?.includes('mp4')) return 'mp4'
  if (contentType?.includes('mpeg')) return 'mp3'
  if (contentType?.includes('wav')) return 'wav'
  return 'bin'
}

export function crc32(data: Uint8Array): number {
  let crc = 0xffffffff
  for (let index = 0; index < data.length; index += 1) {
    crc ^= data[index]
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

export function writeUint16(output: number[], value: number): void {
  output.push(value & 0xff, (value >>> 8) & 0xff)
}

export function writeUint32(output: number[], value: number): void {
  output.push(value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff)
}

export function createStoredZip(entries: ZipFileEntry[]): Blob {
  const local: number[] = []
  const central: number[] = []
  const now = new Date()
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | Math.floor(now.getSeconds() / 2)
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()
  let offset = 0

  for (const entry of entries) {
    const name = textEncoder.encode(entry.name)
    const checksum = crc32(entry.data)
    const size = entry.data.length
    const localOffset = offset

    writeUint32(local, 0x04034b50)
    writeUint16(local, 20)
    writeUint16(local, 0)
    writeUint16(local, 0)
    writeUint16(local, dosTime)
    writeUint16(local, dosDate)
    writeUint32(local, checksum)
    writeUint32(local, size)
    writeUint32(local, size)
    writeUint16(local, name.length)
    writeUint16(local, 0)
    local.push(...name, ...entry.data)
    offset += 30 + name.length + size

    writeUint32(central, 0x02014b50)
    writeUint16(central, 20)
    writeUint16(central, 20)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint16(central, dosTime)
    writeUint16(central, dosDate)
    writeUint32(central, checksum)
    writeUint32(central, size)
    writeUint32(central, size)
    writeUint16(central, name.length)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint32(central, 0)
    writeUint32(central, localOffset)
    central.push(...name)
  }

  const centralOffset = local.length
  writeUint32(central, 0x06054b50)
  writeUint16(central, 0)
  writeUint16(central, 0)
  writeUint16(central, entries.length)
  writeUint16(central, entries.length)
  writeUint32(central, central.length)
  writeUint32(central, centralOffset)
  writeUint16(central, 0)

  return new Blob([new Uint8Array(local), new Uint8Array(central)], { type: 'application/zip' })
}

async function fetchZipAsset(rawPath: string, zipPath: string): Promise<ZipFileEntry | null> {
  const url = dreamAssetUrl(rawPath)
  if (!url) return null
  const response = await fetch(url)
  if (!response.ok) return null
  const blob = await response.blob()
  const data = new Uint8Array(await blob.arrayBuffer())
  const extension = assetExtension(rawPath, blob.type)
  const normalized = zipPath.includes('.') ? zipPath : `${zipPath}.${extension}`
  return { name: normalized, data }
}

async function copyPanelBundleToDesktopClipboard(filename: string, entries: Array<Record<string, string>>): Promise<boolean> {
  const response = await fetch('/api/projects/dream/panel-prompt-bundle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, entries }),
  })
  if (!response.ok) return false
  const result = await response.json()
  return result?.status === 'ok' && result?.copiedToClipboard === true
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function copyZipBlobToClipboard(blob: Blob): Promise<boolean> {
  const clipboard = navigator.clipboard as Clipboard & {
    write?: (items: ClipboardItem[]) => Promise<void>
  }
  if (!clipboard?.write || typeof ClipboardItem === 'undefined') return false
  await clipboard.write([
    new ClipboardItem({
      'application/zip': blob,
    }),
  ])
  return true
}

export function relationshipColor(relationship: string): string {
  const rel = relationship.toLowerCase()
  if (rel.includes('tom') || rel.includes('belief') || rel.includes('relationship')) return '#f472b6'
  if (rel.includes('audio')) return nodeKindColor('audio')
  if (rel.includes('video')) return nodeKindColor('video')
  if (rel.includes('visual') || rel.includes('image')) return nodeKindColor('media')
  if (rel.includes('environment') || rel.includes('surf')) return nodeKindColor('place')
  return '#4a9eff'
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

export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const [size, setSize] = useState({ width: 960, height: 620 })

  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(520, entry.contentRect.width)
      const height = Math.max(460, entry.contentRect.height)
      setSize({ width, height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return [ref, size] as const
}

export function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
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

export function shouldIgnoreDreamPaneArrowKey(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return true
  const target = event.target
  if (!(target instanceof Element)) return false
  return Boolean(target.closest([
    'input',
    'textarea',
    'select',
    'button',
    '[contenteditable="true"]',
    '[role="button"]',
    '[role="combobox"]',
    '[role="dialog"]',
    '[role="listbox"]',
    '[role="menu"]',
    '[role="slider"]',
    '[role="spinbutton"]',
    '[role="tab"]',
    '[role="textbox"]',
    '[data-arrow-key-scope="local"]',
  ].join(',')))
}

export const nvis: Record<string, CSSProperties> = {
  pipelineNav: {
    display: 'flex',
    height: 40,
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 8px',
    background: '#111111',
    flexShrink: 0,
    position: 'sticky',
    top: 0,
    zIndex: 10,
  },
  pipelineNavInner: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    height: '100%',
    background: '#111111',
    position: 'relative' as const,
    isolation: 'isolate' as const,
  },
  pipelinePhaseBtn: {
    position: 'relative' as const,
    zIndex: 1,
    height: 40,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 40,
    gap: 8,
    border: 0,
    background: '#111111',
    color: '#64748b',
    cursor: 'pointer',
    transition: 'color 150ms ease',
  },
  pipelinePhaseBtnActive: {
    color: '#4a9eff',
    width: 'auto',
    minWidth: 96,
    padding: '0 12px',
  },
  pipelinePhaseLabel: {
    lineHeight: 1,
    color: '#e2e8f0',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
  pipelineUnderline: {
    position: 'absolute' as const,
    bottom: 0,
    left: 0,
    width: '100%',
    height: 2,
    background: '#4a9eff',
  },
  klingDeployBtn: {
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 0,
    border: 0,
    background: '#334155',
    color: '#64748b',
    padding: '0 14px',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    cursor: 'pointer',
  },
  klingDeployBtnReady: {
    background: '#10b981',
    color: '#022c22',
    boxShadow: '0 0 12px rgba(16, 185, 129, 0.3)',
    cursor: 'pointer',
  },
  disabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  blockedCard: {
    borderColor: '#ff4444',
  },
  blockedBorder: {
    borderColor: '#ff4444',
  },
  evidenceCard: {
    background: '#0b1220',
    border: '1px solid rgba(255,255,255,0.13)',
    borderRadius: 10,
    padding: 14,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  evidenceCardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  evidenceCardTitle: {
    color: '#64748b',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  codeText: {
    color: '#e2e8f0',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 13,
    lineHeight: 1.4,
  },
  stageGateAlert: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    margin: '8px 0 0',
    padding: '8px 28px',
    borderTop: '1px solid rgba(247,200,111,0.10)',
    borderBottom: '1px solid rgba(247,200,111,0.10)',
    background: 'rgba(247,200,111,0.035)',
  },
  stageGateAlertText: {
    color: '#aab7c9',
    fontSize: 12,
    lineHeight: 1.35,
  },
  dimUppercase: {
    color: '#64748b',
    fontSize: 10,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  },
  matrixCard: {
    background: 'transparent',
    padding: '28px 0 0',
    borderRadius: 0,
    border: 0,
    borderTop: '1px solid rgba(255,255,255,0.08)',
  },
  crewConsole: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    marginBottom: 28,
    padding: '14px 0 18px',
    borderRadius: 0,
    border: 0,
    borderBottom: '1px solid rgba(255,255,255,0.10)',
    background: 'rgba(5,5,5,0.72)',
    boxShadow: 'none',
    backdropFilter: 'blur(14px)',
  },
  crewTopBar: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr)',
    alignItems: 'start',
    gap: 14,
    padding: '0 16px 16px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  crewTopMeta: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 10,
  },
  crewStepPill: {
    display: 'inline-flex',
    alignItems: 'center',
    minHeight: 22,
    padding: '0 9px',
    borderRadius: 999,
    border: '1px solid rgba(122,167,232,0.18)',
    background: 'rgba(74,158,255,0.06)',
    color: '#9fb7d7',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  crewGatePill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    minHeight: 22,
    padding: '0 9px',
    borderRadius: 999,
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  crewGatePillMissing: {
    color: '#f7c86f',
    border: '1px solid rgba(247,200,111,0.30)',
    background: 'rgba(247,200,111,0.08)',
  },
  crewGatePillReady: {
    color: '#6ee7b7',
    border: '1px solid rgba(110,231,183,0.26)',
    background: 'rgba(16,185,129,0.10)',
  },
  crewIntro: {
    margin: '8px 0 0',
    color: '#dbe4ef',
    fontSize: 16,
    lineHeight: 1.55,
    maxWidth: 980,
  },
  scriptPhaseDescription: {
    margin: 0,
    color: '#9ca3af',
    fontSize: 13,
    lineHeight: 1.5,
    maxWidth: '75ch',
  },
  crewActions: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    flexWrap: 'wrap',
    gap: 12,
    minWidth: 0,
    width: '100%',
  },
  crewButtonGroup: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 0,
    border: '1px solid rgba(122,167,232,0.14)',
    borderRadius: 12,
    overflow: 'hidden',
    background: 'rgba(5,5,5,0.42)',
  },
  crewStatusBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    minHeight: 36,
    margin: '0 16px',
    padding: '8px 0 10px',
    borderBottom: '1px solid rgba(247,200,111,0.14)',
  },
  crewStatusBannerText: {
    color: '#aab7c9',
    fontSize: 11,
    lineHeight: 1.35,
    minWidth: 0,
    flex: 1,
    maxWidth: 720,
  },
  crewMissingStrong: {
    color: '#e2e8f0',
    fontWeight: 800,
  },
  crewMissingCode: {
    color: '#f7c86f',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    background: 'rgba(247,200,111,0.07)',
    border: '1px solid rgba(247,200,111,0.14)',
    borderRadius: 5,
    padding: '1px 5px',
  },
  crewStatusBannerHint: {
    color: '#7f8fa5',
    fontSize: 10,
    marginTop: 2,
  },
  crewStatusBannerButton: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 28,
    padding: '0 10px',
    borderRadius: 999,
    border: '1px solid rgba(247,200,111,0.24)',
    background: 'rgba(247,200,111,0.06)',
    color: '#f7c86f',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
  crewRoleGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
    gap: 14,
    padding: '0 16px',
  },
  crewRoleCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    minWidth: 0,
    minHeight: 198,
    padding: 14,
    borderRadius: 12,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(16,16,16,0.72)',
    overflow: 'hidden',
  },
  crewRoleCardDisabled: {
    opacity: 0.52,
  },
  crewRoleLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    color: '#64748b',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
  },
  crewRoleDescription: {
    margin: 0,
    color: '#94a3b8',
    fontSize: 12,
    lineHeight: 1.55,
    maxHeight: 112,
    overflow: 'auto',
    paddingRight: 4,
  },
  crewRationale: {
    margin: 0,
    color: '#b7c4d8',
    fontSize: 12,
    lineHeight: 1.55,
    maxWidth: '55ch',
  },
  crewRoleHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
    width: '100%',
    minHeight: 34,
  },
  crewRepairBridge: {
    display: 'grid',
    gridTemplateColumns: '40px minmax(0, 1fr) auto',
    alignItems: 'center',
    gap: 18,
    margin: '0 16px 4px',
    padding: '14px 0',
    borderTop: '1px solid rgba(247,200,111,0.22)',
    borderBottom: '1px solid rgba(247,200,111,0.14)',
  },
  crewRepairIcon: {
    width: 32,
    height: 32,
    borderRadius: 999,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#f7c86f',
    border: '1px solid rgba(247,200,111,0.30)',
    background: 'rgba(247,200,111,0.08)',
  },
  crewRepairCopy: {
    display: 'flex',
    flexDirection: 'column',
    gap: 5,
    minWidth: 0,
  },
  crewRepairButton: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 34,
    padding: '0 12px',
    borderRadius: 10,
    border: '1px solid rgba(247,200,111,0.28)',
    background: 'rgba(247,200,111,0.07)',
    color: '#f7c86f',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    cursor: 'pointer',
  },
  contextSummaryBar: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
    gap: 12,
    margin: '0 16px 10px',
    padding: 14,
    border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: 6,
    background: 'rgba(8,8,8,0.88)',
  },
  crewContextCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    minWidth: 0,
    minHeight: 0,
    padding: 0,
    borderRadius: 0,
    border: 0,
    background: 'transparent',
    overflow: 'hidden',
  },
  crewContextText: {
    margin: 0,
    color: '#aab7c9',
    fontSize: 12,
    lineHeight: 1.5,
  },
  crewThumbStrip: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    minHeight: 54,
    overflow: 'hidden',
  },
  crewThumb: {
    width: 56,
    height: 42,
    objectFit: 'cover' as const,
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#111111',
    flex: '0 0 auto',
  },
  crewProductionSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    padding: '0 16px',
  },
  crewProductionGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
    gap: 12,
  },
  crewProductionCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    minHeight: 130,
    padding: 12,
    borderRadius: 12,
    border: '1px solid rgba(74,158,255,0.14)',
    background: 'rgba(8,13,22,0.64)',
    overflow: 'hidden',
  },
  crewPromptGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
    gap: 14,
    padding: '0 16px',
  },
  crewPromptCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    minWidth: 0,
    minHeight: 148,
    padding: 14,
    borderRadius: 12,
    border: '1px solid rgba(74,158,255,0.14)',
    background: 'rgba(8,13,22,0.64)',
    overflow: 'hidden',
  },
  crewPromptTitle: {
    color: '#7aa7e8',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  crewPromptText: {
    margin: 0,
    color: '#cbd5e1',
    fontSize: 12,
    lineHeight: 1.55,
    maxHeight: 142,
    overflow: 'auto',
    paddingRight: 4,
  },
  crewMainWorkspace: {
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
    padding: '0 16px',
  },
  crewSectionHeader: {
    color: '#e2e8f0',
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    padding: '14px 0 8px',
  },
  dataSpine: {
    display: 'grid',
    gridTemplateColumns: '40px minmax(0, 1fr)',
    gap: 20,
    padding: '20px 0',
    borderTop: '1px solid rgba(255,255,255,0.08)',
  },
  spineIconSlot: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingTop: 3,
  },
  spineIconCircle: {
    width: 32,
    height: 32,
    borderRadius: 999,
    border: '1px solid rgba(122,167,232,0.26)',
    background: 'rgba(8,13,22,0.62)',
    color: '#7aa7e8',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  crewPersonaThumb: {
    width: 34,
    height: 34,
    objectFit: 'cover' as const,
    borderRadius: 999,
    border: '1px solid rgba(122,167,232,0.32)',
    background: '#111111',
  },
  spineContent: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 7,
    minWidth: 0,
  },
  moduleLabel: {
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.2em',
    textTransform: 'uppercase',
  },
  moduleTitle: {
    color: '#f8fafc',
    fontSize: 15,
    fontWeight: 650,
    lineHeight: 1.25,
  },
  moduleBody: {
    margin: 0,
    color: '#aab7c9',
    fontSize: 13,
    lineHeight: 1.58,
    maxWidth: '55ch',
  },
  directorConsole: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    marginBottom: 28,
    padding: '14px 0 18px',
    borderRadius: 0,
    border: 0,
    borderBottom: '1px solid rgba(255,255,255,0.10)',
    background: 'rgba(5,5,5,0.72)',
    boxShadow: 'none',
    backdropFilter: 'blur(14px)',
    transition: 'border-color 220ms ease, box-shadow 220ms ease',
  },
  directorHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
  },
  directorEyebrow: {
    color: '#e2e8f0',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.2em',
    textTransform: 'uppercase',
    paddingLeft: 12,
    borderLeft: '3px solid #4a9eff',
  },
  directorTitle: {
    margin: '4px 0 0',
    color: '#e2e8f0',
    fontSize: 18,
    fontWeight: 500,
    letterSpacing: 0,
  },
  directorGenerateBtn: {
    height: 30,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    minWidth: 112,
    padding: '0 16px',
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.10)',
    background: 'transparent',
    color: 'rgba(255,255,255,0.72)',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
    transition: 'color 260ms ease, border-color 260ms ease, background 260ms ease, box-shadow 260ms ease',
  },
  directorBtnDisabled: {
    cursor: 'wait',
    opacity: 0.62,
  },
  directorDebugBtn: {
    height: 30,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    minWidth: 98,
    padding: '0 11px',
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.10)',
    background: 'transparent',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
    transition: 'color 220ms ease, border-color 220ms ease, background 220ms ease',
  },
  directorControls: {
    display: 'grid',
    gridTemplateColumns: '120px minmax(0, 1fr)',
    alignItems: 'start',
    gap: 18,
    padding: '0 16px',
    width: '100%',
  },
  directorCommandColumn: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    minWidth: 0,
    width: '100%',
  },
  directorCommandStrip: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    flexWrap: 'wrap',
    gap: 16,
    minWidth: 0,
    width: '100%',
  },
  directorIdeaBand: {
    display: 'grid',
    gridTemplateColumns: '120px minmax(0, 1fr)',
    alignItems: 'start',
    gap: 18,
    padding: '0 16px 16px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  directorIdeaText: {
    margin: 0,
    color: '#dbe4ef',
    fontSize: 17,
    lineHeight: 1.55,
    fontWeight: 400,
    letterSpacing: 0,
  },
  directorControlGroup: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minWidth: 0,
    flex: '1 1 190px',
  },
  directorAuthorGroup: {
    display: 'inline-flex',
    alignItems: 'center',
    minWidth: 150,
    flex: '0 0 auto',
  },
  directorLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
  },
  directorSliderGroup: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    minWidth: 0,
    flex: '1 1 220px',
    maxWidth: 560,
  },
  directorSliderHeader: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 8,
    flex: '0 0 auto',
  },
  directorRange: {
    width: '100%',
    height: 1,
    accentColor: '#4a9eff',
    cursor: 'pointer',
  },
  directorNumberGroup: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 9,
    flex: '0 0 auto',
  },
  directorNumberInput: {
    width: 52,
    height: 30,
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.10)',
    background: 'rgba(255,255,255,0.03)',
    color: '#e2e8f0',
    padding: '0 8px',
    fontSize: 12,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    outline: 'none',
    boxShadow: 'none',
  },
  directorInlineStylePreview: {
    display: 'grid',
    gridTemplateColumns: '110px minmax(0, 1fr)',
    alignItems: 'start',
    gap: 12,
    padding: '10px 0 0',
    borderTop: '1px solid rgba(255,255,255,0.05)',
  },
  directorInlineStyleLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  directorStyleText: {
    margin: 0,
    color: '#94a3b8',
    fontSize: 12,
    lineHeight: 1.55,
    maxWidth: 980,
  },
  directorValue: {
    color: '#94a3b8',
    fontSize: 11,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  directorSelect: {
    height: 30,
    borderRadius: 0,
    border: 0,
    background: 'transparent',
    color: '#e2e8f0',
    padding: '0 20px 0 2px',
    fontSize: 12,
    minWidth: 0,
    width: '100%',
    outline: 'none',
    boxShadow: 'none',
    WebkitAppearance: 'none' as const,
    appearance: 'none' as const,
    cursor: 'pointer',
  },
  directorSelectWrap: {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    minWidth: 150,
    maxWidth: 220,
  },
  directorSelectIcon: {
    position: 'absolute',
    right: 2,
    color: '#64748b',
    pointerEvents: 'none' as const,
  },
  directorStatusRow: {
    display: 'grid',
    gridTemplateColumns: '120px minmax(0, 1fr)',
    alignItems: 'start',
    gap: 18,
    padding: '0 16px',
  },
  directorStatus: {
    color: '#94a3b8',
    fontSize: 11,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    paddingTop: 2,
  },
  directorStoryAreaWrap: {
    display: 'grid',
    gridTemplateColumns: '120px minmax(0, 1fr)',
    alignItems: 'start',
    gap: 18,
    padding: '0 16px',
  },
  scriptStoryAreaWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 18,
    padding: '0 16px',
    minWidth: 0,
  },
  scriptSectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    marginTop: 18,
    marginBottom: 2,
  },
  scriptSectionRule: {
    flex: '0 0 56px',
    height: 1,
    background: 'rgba(255,255,255,0.10)',
  },
  scriptSectionRuleWide: {
    flex: 1,
    height: 1,
    background: 'rgba(255,255,255,0.10)',
  },
  scriptSectionTitle: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    color: '#f3f4f6',
    fontSize: 12,
    fontWeight: 850,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
    whiteSpace: 'nowrap' as const,
  },
  directorStoryContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    minWidth: 0,
  },
  directorStoryCanvas: {
    minHeight: 156,
    padding: 0,
    borderRadius: 12,
    border: 'none',
    background: 'transparent',
    color: '#d1d5db',
    fontSize: 16,
    lineHeight: 1.7,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    whiteSpace: 'pre-wrap' as const,
    overflow: 'hidden',
  },
  directorStoryPlaceholder: {
    color: '#64748b',
    display: 'block',
    padding: 20,
  },
  scriptTableShell: {
    display: 'flex',
    flexDirection: 'column',
    width: '100%',
    marginTop: 2,
    paddingLeft: 22,
    position: 'relative',
    background: 'transparent',
    overflow: 'hidden',
  },
  scriptTableShellBefore: {},
  scriptTableRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    position: 'relative',
    padding: '20px 0 20px 22px',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    borderLeft: '1px solid rgba(74,158,255,0.18)',
  },
  scriptTableRowFailed: {
    borderLeft: '1px solid rgba(239,68,68,0.55)',
  },
  scriptTableHeader: {
    background: 'rgba(255,255,255,0.035)',
    color: '#64748b',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  scriptCell: {
    minWidth: 0,
    padding: 0,
    color: '#dbe4ef',
    fontSize: 13,
    lineHeight: 1.58,
    whiteSpace: 'pre-wrap' as const,
    overflowWrap: 'break-word' as const,
  },
  scriptContentBlock: {
    minWidth: 0,
    padding: '8px 0 0',
    marginLeft: 0,
    borderLeft: 'none',
    color: '#d1d5db',
    fontSize: 15,
    lineHeight: 1.72,
    fontFamily: '"Courier Prime", "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    whiteSpace: 'pre-wrap' as const,
    overflowWrap: 'break-word' as const,
  },
  scriptNotesCell: {
    paddingTop: 12,
    borderTop: '1px solid rgba(255,255,255,0.06)',
    color: '#94a3b8',
    fontSize: 12,
    lineHeight: 1.5,
    background: 'transparent',
  },
  scriptBeatHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    position: 'relative',
  },
  scriptStatusNodeBase: {
    position: 'absolute',
    left: -5,
    top: 30,
    width: 8,
    height: 8,
    borderRadius: 999,
    display: 'inline-block',
    zIndex: 2,
  },
  scriptStatusNodeVerified: {
    background: '#10B981',
    boxShadow: '0 0 8px rgba(16,185,129,0.4)',
  },
  scriptStatusNodeFailed: {
    background: '#EF4444',
    boxShadow: '0 0 8px rgba(239,68,68,0.5)',
  },
  scriptStatusNodePending: {
    background: 'transparent',
    border: '1px solid #6B7280',
  },
  scriptBeatHeaderDot: {},
  scriptElementTag: {
    display: 'inline-flex',
    alignItems: 'center',
    width: 'fit-content',
    padding: '4px 8px',
    borderRadius: 7,
    background: 'rgba(255,255,255,0.055)',
    color: '#aab7c9',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    whiteSpace: 'nowrap' as const,
  },
  scriptDurationTag: {
    display: 'inline-flex',
    alignItems: 'center',
    width: 'fit-content',
    padding: '4px 8px',
    borderRadius: 999,
    border: '1px solid rgba(74,158,255,0.22)',
    background: 'rgba(74,158,255,0.08)',
    color: '#93c5fd',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    whiteSpace: 'nowrap' as const,
  },
  scriptCoverage: {
    padding: 16,
    background: 'transparent',
  },
  scriptCoverageTitle: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    marginBottom: 12,
    color: '#64748b',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase' as const,
  },
  scriptCoverageGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
    gap: 10,
  },
  scriptCoverageRow: {
    padding: 12,
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.025)',
  },
  scriptCoverageMeta: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    marginBottom: 8,
  },
  scriptCoverageReady: {
    color: '#5eead4',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
  },
  scriptCoverageMissing: {
    color: '#fbbf24',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
  },
  scriptCoverageEntity: {
    color: '#e2e8f0',
    fontSize: 13,
    fontWeight: 700,
    marginBottom: 6,
  },
  scriptCoverageText: {
    color: '#aab7c9',
    fontSize: 12,
    lineHeight: 1.45,
  },
  scriptCoverageBlocker: {
    marginTop: 8,
    color: '#fbbf24',
    fontSize: 10,
    lineHeight: 1.45,
  },
  scriptCoverageObjects: {
    marginTop: 8,
    color: '#64748b',
    fontSize: 10,
    lineHeight: 1.4,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  scriptAssetGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 12,
    padding: 12,
    borderRadius: 10,
    border: '1px dashed rgba(255,255,255,0.12)',
    background: 'rgba(255,255,255,0.02)',
  },
  scriptAssetTile: {
    width: 128,
    minHeight: 104,
    padding: 0,
    overflow: 'hidden',
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.10)',
    background: 'rgba(10,12,16,0.74)',
    color: '#d1d5db',
    display: 'grid',
    gridTemplateRows: '72px auto auto',
    textAlign: 'left' as const,
    cursor: 'pointer',
  },
  scriptAssetThumb: {
    width: '100%',
    height: 72,
    objectFit: 'cover' as const,
    background: '#111827',
    display: 'block',
  },
  scriptAssetFallback: {
    height: 72,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#93c5fd',
    background: 'linear-gradient(135deg, rgba(74,158,255,0.14), rgba(255,255,255,0.025))',
  },
  scriptAssetTitle: {
    padding: '8px 9px 2px',
    color: '#d1d5db',
    fontSize: 11,
    lineHeight: 1.25,
    fontWeight: 700,
  },
  scriptAssetMeta: {
    padding: '0 9px 8px',
    color: '#64748b',
    fontSize: 9,
    lineHeight: 1.2,
    fontWeight: 800,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
  },
  scriptActionBar: {
    position: 'sticky' as const,
    bottom: 0,
    zIndex: 8,
    display: 'flex',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 12,
    marginTop: 12,
    padding: '14px 16px',
    borderTop: '1px solid rgba(255,255,255,0.10)',
    background: 'rgba(5,5,5,0.92)',
    backdropFilter: 'blur(12px)',
    boxShadow: '0 -10px 28px rgba(0,0,0,0.32)',
  },
  scriptPayloadGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    margin: '0 16px 24px',
  },
  scriptPayloadCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    minWidth: 0,
    padding: 16,
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.05)',
    borderLeft: '3px solid rgba(100,116,139,0.78)',
    background: 'rgba(255,255,255,0.03)',
  },
  scriptPayloadLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    color: '#8b9ab1',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
  },
  scriptPayloadContent: {
    margin: 0,
    color: '#d4dbe7',
    fontSize: 13,
    lineHeight: 1.6,
  },
  directorJsonDetails: {
    border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: 10,
    background: 'rgba(255,255,255,0.02)',
    padding: '8px 10px',
  },
  directorJsonSummary: {
    cursor: 'pointer',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
  },
  directorStoryArea: {
    minHeight: 140,
    resize: 'vertical' as const,
    width: '100%',
    margin: 0,
    marginTop: 10,
    padding: 16,
    borderRadius: 12,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#101010',
    color: '#e2e8f0',
    fontSize: 14,
    lineHeight: 1.65,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    outline: 'none',
  },
  matrixMetaGrid: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 0.8fr) minmax(0, 1.2fr)',
    gap: 14,
    marginBottom: 24,
  },
  matrixReadyPill: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    minWidth: 58,
    height: 20,
    borderRadius: 999,
    border: '1px solid rgba(34,197,94,0.24)',
    background: 'rgba(34,197,94,0.10)',
    color: '#4ade80',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  matrixMutedPill: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    minWidth: 58,
    height: 20,
    borderRadius: 999,
    border: '1px solid rgba(148,163,184,0.18)',
    background: 'rgba(148,163,184,0.08)',
    color: '#94a3b8',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  matrixPendingPill: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    minWidth: 0,
    height: 24,
    borderRadius: 5,
    border: '1px solid rgba(255,255,255,0.06)',
    background: 'rgba(26,26,26,0.72)',
    color: 'rgba(255,255,255,0.72)',
    padding: '0 8px',
    fontSize: 8,
    fontWeight: 800,
    letterSpacing: '0.10em',
    textTransform: 'uppercase' as const,
    cursor: 'pointer',
  },
  pathTraceHop: {
    color: '#4a9eff',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontWeight: 800,
  },
  pathTraceTarget: {
    color: '#fca5a5',
    fontWeight: 900,
  },
  matrixMetaItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    padding: 14,
    borderRadius: 14,
    border: '1px solid rgba(255,255,255,0.07)',
    background: 'rgba(20,20,20,0.62)',
  },
  matrixMetaLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
  },
  matrixMetaValue: {
    color: '#e2e8f0',
    fontSize: 13,
    lineHeight: 1.5,
  },
  matrixSectionTitle: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    margin: '0 0 12px',
    color: '#64748b',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
  },
  videoProviderPanel: {
    display: 'grid',
    gap: 18,
  },
  videoProviderGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
    gap: 12,
  },
  videoProviderCard: {
    minHeight: 126,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    gap: 12,
    padding: 16,
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.08)',
    borderLeft: '8px solid #4a9eff',
    background: '#0a0a0a',
  },
  videoProviderLabel: {
    color: '#94a3b8',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
  },
  videoProviderValue: {
    color: '#f8fafc',
    fontSize: 24,
    lineHeight: 1.05,
    fontWeight: 900,
    letterSpacing: 0,
    overflowWrap: 'anywhere',
  },
  videoProviderSubtle: {
    color: '#94a3b8',
    fontSize: 11,
    lineHeight: 1.35,
    overflowWrap: 'anywhere',
  },
  videoProviderSplit: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1.15fr) minmax(0, 0.85fr)',
    gap: 14,
  },
  videoProviderSection: {
    minWidth: 0,
    padding: 16,
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#0a0a0a',
  },
  videoProviderScoreRows: {
    display: 'grid',
    gap: 8,
  },
  videoProviderScoreMatrix: {
    display: 'grid',
    overflow: 'hidden',
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.06)',
    background: '#050505',
  },
  videoProviderScoreHeader: {
    display: 'grid',
    gridTemplateColumns: '1.35fr 1.55fr repeat(5, minmax(44px, 0.7fr)) minmax(72px, 0.8fr)',
    gap: 10,
    alignItems: 'center',
    padding: '10px 12px',
    borderBottom: '1px solid rgba(255,255,255,0.07)',
    background: 'rgba(255,255,255,0.02)',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
  },
  videoProviderFeatureHeader: {
    textAlign: 'center' as const,
    cursor: 'help',
  },
  videoProviderScoreHeaderCell: {
    textAlign: 'right' as const,
  },
  videoProviderScoreMatrixRow: {
    display: 'grid',
    gridTemplateColumns: '1.35fr 1.55fr repeat(5, minmax(44px, 0.7fr)) minmax(72px, 0.8fr)',
    gap: 10,
    alignItems: 'center',
    padding: '12px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    borderLeft: '2px solid transparent',
    color: '#e2e8f0',
    fontSize: 11,
  },
  videoProviderScoreMatrixRowSelected: {
    borderLeftColor: '#22c55e',
    background: 'rgba(34,197,94,0.08)',
  },
  videoProviderRecommendedName: {
    color: '#22c55e',
  },
  videoProviderTinyMuted: {
    marginTop: 2,
    color: '#64748b',
    fontSize: 9,
    fontFamily: 'JetBrains Mono, monospace',
  },
  videoProviderNeutralCell: {
    textAlign: 'center' as const,
    color: '#334155',
    fontSize: 12,
    fontWeight: 800,
    fontFamily: 'JetBrains Mono, monospace',
  },
  videoProviderPenaltyCell: {
    justifySelf: 'center',
    minWidth: 28,
    padding: '3px 5px',
    borderRadius: 5,
    background: 'rgba(245,158,11,0.14)',
    color: '#f59e0b',
    textAlign: 'center' as const,
    fontSize: 10,
    fontWeight: 900,
    fontFamily: 'JetBrains Mono, monospace',
  },
  videoProviderScoreFinalCell: {
    textAlign: 'right' as const,
  },
  videoProviderScoreRow: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) auto',
    gap: 12,
    alignItems: 'center',
    padding: '10px 0',
    borderTop: '1px solid rgba(255,255,255,0.06)',
    color: '#e2e8f0',
    fontSize: 12,
  },
  videoProviderScoreMeta: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 8,
    flexWrap: 'wrap',
  },
  videoProviderBlockerList: {
    display: 'grid',
    gap: 8,
    margin: 0,
    padding: 0,
    listStyle: 'none',
    color: '#fca5a5',
    fontSize: 12,
    lineHeight: 1.35,
  },
  videoProviderReceiptRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(138px, 1fr))',
    gap: 8,
  },
  videoProviderReceiptReady: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    padding: '9px 10px',
    borderRadius: 6,
    border: '1px solid rgba(34,197,94,0.18)',
    background: 'rgba(34,197,94,0.06)',
    color: '#4ade80',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  videoProviderReceiptMissing: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    padding: '9px 10px',
    borderRadius: 6,
    border: '1px solid rgba(148,163,184,0.14)',
    background: 'rgba(148,163,184,0.05)',
    color: '#94a3b8',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  providerContractPanel: {
    display: 'grid',
    gap: 16,
  },
  providerContractMissing: {
    display: 'grid',
    gap: 12,
    padding: 16,
    borderRadius: 8,
    border: '1px solid rgba(251, 191, 36, 0.32)',
    borderLeft: '8px solid #f59e0b',
    background: 'rgba(120, 53, 15, 0.18)',
    color: '#fde68a',
    lineHeight: 1.45,
  },
  providerContractCommand: {
    margin: 0,
    padding: 12,
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(0,0,0,0.42)',
    color: '#e5e7eb',
    fontSize: 11,
    lineHeight: 1.45,
    whiteSpace: 'pre-wrap',
    overflowX: 'auto',
  },
  providerContractKpiGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: 12,
  },
  providerContractKpiCard: {
    minHeight: 96,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    gap: 10,
    padding: 14,
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#0a0a0a',
    overflow: 'hidden',
  },
  providerContractKpiPass: {
    borderLeft: '6px solid #22c55e',
  },
  providerContractKpiDry: {
    borderLeft: '6px solid #4a9eff',
  },
  providerContractKpiBlocked: {
    borderLeft: '6px solid #f59e0b',
    background: 'rgba(120, 53, 15, 0.12)',
  },
  providerContractKpiLabel: {
    color: '#a8b3c7',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  providerContractKpiValue: {
    color: '#f8fafc',
    fontSize: 18,
    lineHeight: 1.08,
    fontWeight: 900,
    letterSpacing: 0,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  providerContractKpiDetail: {
    color: '#a8b3c7',
    fontSize: 11,
    lineHeight: 1.3,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  providerContractRibbon: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, minmax(160px, 1fr))',
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(2,6,23,0.48)',
    overflowX: 'auto',
    overflowY: 'hidden',
  },
  providerContractRibbonMetric: {
    minWidth: 0,
    display: 'grid',
    gap: 6,
    padding: '12px 14px',
    borderRight: '1px solid rgba(255,255,255,0.07)',
  },
  providerContractRibbonLabel: {
    color: '#64748b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  providerContractRibbonValue: {
    minWidth: 0,
    fontSize: 12,
    lineHeight: 1.25,
    fontWeight: 800,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  providerContractRibbonValuePass: {
    color: '#4ade80',
  },
  providerContractRibbonValueDry: {
    color: '#facc15',
  },
  providerContractRibbonValueBlocked: {
    color: '#fb7185',
  },
  providerContractSplit: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: 14,
  },
  providerContractValidationGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
    gap: 14,
    alignItems: 'start',
  },
  providerContractBlockersPanel: {
    borderColor: 'rgba(245,158,11,0.22)',
    background: 'rgba(120,53,15,0.08)',
  },
  providerContractNonClaimsPanel: {
    borderColor: 'rgba(148,163,184,0.16)',
    background: 'rgba(15,23,42,0.22)',
  },
  providerContractSection: {
    minWidth: 0,
    padding: 16,
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#0a0a0a',
  },
  providerContractPanelPayloadList: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(520px, 1fr))',
    gap: 12,
  },
  providerContractPanelPayload: {
    minWidth: 0,
    display: 'grid',
    gap: 10,
    padding: 12,
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.018)',
  },
  providerContractPanelPayloadSelected: {
    minWidth: 0,
    display: 'grid',
    gap: 10,
    padding: 12,
    borderRadius: 6,
    border: '1px solid rgba(34,197,94,0.28)',
    borderLeft: '6px solid #22c55e',
    background: 'rgba(20,83,45,0.12)',
  },
  providerContractPanelPayloadHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    color: '#f8fafc',
    fontSize: 12,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  providerContractPanelPayloadFrames: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: 10,
  },
  providerContractFrameState: {
    minWidth: 0,
    display: 'grid',
    gap: 8,
    padding: 10,
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.07)',
    background: 'rgba(0,0,0,0.28)',
  },
  providerContractFrameHeader: {
    display: 'grid',
    gridTemplateColumns: '52px minmax(0, 1fr)',
    gap: 10,
    alignItems: 'center',
    color: '#dbeafe',
    fontSize: 11,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    overflow: 'hidden',
  },
  providerContractFramePreview: {
    position: 'relative',
    display: 'grid',
    gap: 6,
  },
  providerContractFrameImage: {
    width: '100%',
    aspectRatio: '16 / 9',
    objectFit: 'cover',
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#020617',
  },
  providerContractFrameCaption: {
    minHeight: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    padding: '0 7px',
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(15,23,42,0.46)',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  providerContractFrameCaptionIcon: {
    color: 'rgba(245,158,11,0.76)',
    flex: '0 0 auto',
  },
  providerContractFrameRows: {
    display: 'grid',
    gap: 0,
    padding: 10,
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.06)',
    background: 'rgba(2,6,23,0.46)',
  },
  providerContractMetadataRow: {
    display: 'grid',
    gridTemplateColumns: '92px minmax(0, 1fr)',
    alignItems: 'center',
    gap: 14,
    minWidth: 0,
    padding: '5px 0',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    fontSize: 10,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  providerContractMetaLabel: {
    color: '#64748b',
    fontWeight: 850,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
  providerContractMetaValue: {
    minWidth: 0,
    color: '#cbd5e1',
    fontWeight: 650,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'left',
  },
  providerContractMetaValueSuccess: {
    minWidth: 0,
    color: '#22c55e',
    fontWeight: 850,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'left',
  },
  providerContractMetaValueWarning: {
    minWidth: 0,
    color: '#f59e0b',
    fontWeight: 850,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'left',
  },
  providerContractMetaValueMuted: {
    minWidth: 0,
    color: '#64748b',
    fontWeight: 650,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'left',
  },
  providerContractPanelPayloadJson: {
    display: 'grid',
    gap: 8,
    padding: 10,
    borderRadius: 4,
    border: '1px solid rgba(74,158,255,0.18)',
    background: 'rgba(74,158,255,0.07)',
    color: '#bfdbfe',
    fontSize: 10,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflow: 'hidden',
  },
  providerContractPanelPayloadJsonMuted: {
    display: 'grid',
    gap: 8,
    padding: 10,
    borderRadius: 4,
    border: '1px solid rgba(148,163,184,0.16)',
    background: 'rgba(15,23,42,0.36)',
    color: '#94a3b8',
    fontSize: 10,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflow: 'hidden',
  },
  providerContractDistillationTextBlock: {
    display: 'grid',
    gap: 9,
    padding: 10,
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.07)',
    background: 'rgba(2,6,23,0.42)',
  },
  providerContractDistillationTextItem: {
    display: 'grid',
    gap: 5,
    minWidth: 0,
  },
  providerContractDistillationLabel: {
    color: '#64748b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  providerContractDistillationText: {
    whiteSpace: 'pre-wrap',
    margin: 0,
    color: '#cbd5e1',
    fontSize: 11,
    lineHeight: 1.45,
    overflowWrap: 'anywhere',
  },
  providerContractDistillationAudio: {
    justifySelf: 'start',
    maxWidth: '100%',
    padding: '3px 7px',
    borderRadius: 4,
    border: '1px solid rgba(34,211,238,0.22)',
    background: 'rgba(8,145,178,0.12)',
    color: '#67e8f9',
    fontSize: 10,
    fontWeight: 850,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  providerContractPanelSummary: {
    display: 'block',
    minWidth: 0,
    color: '#8ba1bd',
    fontSize: 10,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  providerContractAudioPillRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
    minWidth: 0,
  },
  providerContractAudioPill: {
    display: 'inline-flex',
    alignItems: 'stretch',
    minHeight: 22,
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(2,6,23,0.42)',
    overflow: 'hidden',
  },
  providerContractAudioPillLabel: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '0 6px',
    borderRight: '1px solid rgba(255,255,255,0.08)',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  providerContractAudioPillValue: {
    display: 'inline-flex',
    alignItems: 'center',
    maxWidth: 160,
    padding: '0 7px',
    fontSize: 10,
    fontWeight: 850,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  providerContractAudioPillValueNeutral: {
    color: '#67e8f9',
  },
  providerContractAudioPillValueWarning: {
    color: '#fbbf24',
  },
  providerContractPanelPayloadDetails: {
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(0,0,0,0.24)',
    overflow: 'hidden',
  },
  providerContractPanelPayloadSummary: {
    minHeight: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    padding: '0 10px',
    color: '#bfdbfe',
    cursor: 'pointer',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    userSelect: 'none',
  },
  providerContractPanelPayloadPre: {
    margin: 0,
    maxHeight: 260,
    overflow: 'auto',
    padding: 10,
    borderTop: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(0,0,0,0.38)',
    color: '#dbeafe',
    fontSize: 10,
    lineHeight: 1.45,
    whiteSpace: 'pre',
  },
  providerContractSyntaxShell: {
    borderRadius: 4,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#1e1e1e',
    overflow: 'hidden',
  },
  providerContractSyntaxToolbar: {
    minHeight: 32,
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    padding: '0 10px',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(15,23,42,0.72)',
    color: '#94a3b8',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
  },
  providerContractSyntaxHighlighter: {
    margin: 0,
    padding: 12,
    background: 'transparent',
    fontSize: 10,
    lineHeight: 1.45,
    overflow: 'auto',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
  },
  providerContractSyntaxCode: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  providerContractSyntaxKey: {
    color: '#9cdcfe',
  },
  providerContractSyntaxString: {
    color: '#ce9178',
  },
  providerContractSyntaxNumber: {
    color: '#b5cea8',
  },
  providerContractSyntaxBoolean: {
    color: '#569cd6',
  },
  providerContractSyntaxPunctuation: {
    color: '#d4d4d4',
  },
  providerContractMapping: {
    display: 'grid',
    borderRadius: 6,
    overflow: 'hidden',
    border: '1px solid rgba(255,255,255,0.07)',
  },
  providerContractMappingHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '9px 10px',
    background: 'rgba(255,255,255,0.04)',
    color: '#a8b3c7',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
  },
  providerContractMappingHeaderField: {
    flex: '0 1 34%',
    minWidth: 132,
  },
  providerContractMappingHeaderSource: {
    flex: '1 1 auto',
    minWidth: 0,
  },
  providerContractMappingHeaderStatus: {
    flex: '0 0 auto',
    minWidth: 170,
    textAlign: 'right' as const,
  },
  providerContractMappingRow: {
    display: 'flex',
    gap: 12,
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px',
    borderTop: '1px solid rgba(255,255,255,0.06)',
    color: '#dbeafe',
    fontSize: 11,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    minWidth: 0,
  },
  providerContractMappingField: {
    flex: '0 1 34%',
    minWidth: 132,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  providerContractMappingSource: {
    flex: '1 1 auto',
    minWidth: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: '#8ba1bd',
  },
  providerContractMappingStatus: {
    flex: '0 0 auto',
    display: 'flex',
    justifyContent: 'flex-end',
    minWidth: 170,
  },
  providerContractBoundaryGrid: {
    display: 'grid',
    gap: 0,
    padding: '4px 2px',
    borderRadius: 5,
    border: '1px solid rgba(255,255,255,0.06)',
    background: 'rgba(15,23,42,0.20)',
  },
  providerContractStateCard: {
    display: 'grid',
    gridTemplateColumns: '116px minmax(0, 1fr)',
    alignItems: 'center',
    gap: 12,
    padding: '9px 10px',
    borderTop: '1px solid rgba(255,255,255,0.055)',
  },
  providerContractStateLabel: {
    color: '#a8b3c7',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  providerContractStateDetail: {
    gridColumn: '2',
    color: '#a8b3c7',
    fontSize: 11,
    lineHeight: 1.3,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  providerContractPillPass: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 24,
    borderRadius: 5,
    border: '1px solid rgba(34,197,94,0.28)',
    background: 'rgba(34,197,94,0.10)',
    color: '#86efac',
    padding: '3px 8px',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    justifySelf: 'end',
  },
  providerContractPillDry: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 24,
    borderRadius: 5,
    border: '1px solid rgba(74,158,255,0.28)',
    background: 'rgba(74,158,255,0.10)',
    color: '#bfdbfe',
    padding: '3px 8px',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    justifySelf: 'end',
  },
  providerContractPillBlocked: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 24,
    borderRadius: 5,
    border: '1px solid rgba(245,158,11,0.35)',
    background: 'rgba(245,158,11,0.12)',
    color: '#fcd34d',
    padding: '3px 8px',
    fontSize: 9,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    justifySelf: 'end',
  },
  providerContractBlockerGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
    gap: 8,
  },
  providerContractBlockerPill: {
    borderRadius: 5,
    border: '1px solid rgba(248,113,113,0.32)',
    background: 'rgba(127,29,29,0.18)',
    color: '#fecaca',
    padding: '8px 9px',
    fontSize: 10,
    fontWeight: 800,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflowWrap: 'anywhere',
    textTransform: 'uppercase',
  },
  providerContractLiveBlockerPill: {
    borderRadius: 5,
    border: '1px solid rgba(245,158,11,0.32)',
    background: 'rgba(120,53,15,0.18)',
    color: '#fde68a',
    padding: '8px 9px',
    fontSize: 10,
    fontWeight: 800,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflowWrap: 'anywhere',
    textTransform: 'uppercase',
  },
  providerContractNeutralPill: {
    borderRadius: 5,
    border: '1px solid rgba(34,197,94,0.22)',
    background: 'rgba(20,83,45,0.14)',
    color: '#bbf7d0',
    padding: '8px 9px',
    fontSize: 10,
    fontWeight: 800,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflowWrap: 'anywhere',
    textTransform: 'uppercase',
  },
  providerContractNonClaims: {
    display: 'grid',
    gap: 8,
    margin: 0,
    padding: 0,
    listStyle: 'none',
    color: '#94a3b8',
    fontSize: 12,
    lineHeight: 1.45,
  },
  providerContractNonClaimItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    minWidth: 0,
    color: '#94a3b8',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
  },
  providerContractNonClaimIcon: {
    flex: '0 0 auto',
    marginTop: 1,
    color: '#475569',
  },
  providerContractDetails: {
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#0a0a0a',
    overflow: 'hidden',
  },
  providerContractSummary: {
    minHeight: 48,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '0 14px',
    cursor: 'pointer',
    color: '#cbd5e1',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    userSelect: 'none',
  },
  providerContractSummaryMeta: {
    color: '#8ba1bd',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    whiteSpace: 'nowrap',
  },
  providerContractJsonToolbar: {
    minHeight: 44,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '0 14px',
    borderTop: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.03)',
    color: '#8ba1bd',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  providerContractCopyButton: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    height: 30,
    padding: '0 10px',
    borderRadius: 4,
    border: '1px solid rgba(74,158,255,0.34)',
    background: 'rgba(74,158,255,0.10)',
    color: '#bfdbfe',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: 'pointer',
  },
  providerContractJsonPre: {
    margin: 0,
    padding: 14,
    maxHeight: 360,
    overflow: 'auto',
    borderTop: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(0,0,0,0.36)',
    color: '#dbeafe',
    fontSize: 11,
    lineHeight: 1.45,
  },

  matrixEnv: {
    marginBottom: 14,
    fontSize: 11,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  matrixTable: {
    width: '100%',
    fontSize: 12,
    color: '#e2e8f0',
    borderCollapse: 'collapse' as const,
  },
  matrixHeaderRow: {
    color: '#64748b',
    textAlign: 'left' as const,
    borderBottom: '1px solid #334155',
  },
  matrixTh: {
    padding: '6px 4px',
    fontWeight: 600,
  },
  matrixRow: {
    borderBottom: '1px solid #334155',
  },
  matrixTd: {
    padding: '8px 4px',
  },
  assetStrip: {
    marginTop: 30,
    paddingTop: 24,
    borderTop: '1px solid rgba(255,255,255,0.08)',
  },
  assetStripTitle: {
    margin: '0 0 14px',
    color: '#64748b',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.2em',
    textTransform: 'uppercase',
  },
  assetStripEmpty: {
    color: '#64748b',
    fontSize: 12,
    padding: '12px 0',
  },
  assetTable: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    tableLayout: 'fixed' as const,
  },
  assetTableHeaderRow: {
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  assetTableTh: {
    padding: '0 10px 9px 0',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
    textAlign: 'left' as const,
  },
  assetTableRow: {
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  assetTableThumbCell: {
    width: 86,
    padding: '12px 14px 12px 0',
    verticalAlign: 'top',
  },
  assetTableDescription: {
    padding: '12px 14px 12px 0',
    verticalAlign: 'top',
  },
  assetTableTitle: {
    display: 'block',
    color: '#e2e8f0',
    fontSize: 12,
    lineHeight: 1.35,
    fontWeight: 650,
    marginBottom: 5,
  },
  assetTableCaption: {
    display: 'block',
    color: '#94a3b8',
    fontSize: 11,
    lineHeight: 1.45,
  },
  assetTableSource: {
    width: 160,
    padding: '12px 0',
    verticalAlign: 'top',
    color: '#64748b',
    fontSize: 10,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflowWrap: 'anywhere' as const,
  },
  assetThumbButton: {
    width: 72,
    height: 52,
    display: 'flex',
    padding: 0,
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 10,
    background: '#141414',
    cursor: 'pointer',
    overflow: 'hidden',
  },
  assetThumbImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
  },
  voicePlugin: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  voiceHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  voiceChannelCard: {
    background: 'rgba(12,12,12,0.72)',
    padding: 18,
    borderRadius: 18,
    display: 'flex',
    alignItems: 'stretch',
    gap: 18,
    border: '1px solid rgba(255,255,255,0.08)',
    backdropFilter: 'blur(12px)',
  },
  voicePortraitFrame: {
    width: 148,
    minHeight: 148,
    borderRadius: 16,
    overflow: 'hidden',
    border: '1px solid rgba(74,158,255,0.24)',
    background: '#050505',
    flexShrink: 0,
  },
  voicePortrait: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
  },
  voiceCardBody: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    minWidth: 0,
    flex: 1,
  },
  voiceCardTopline: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 12,
  },
  voiceName: {
    color: '#f8fafc',
    fontSize: 22,
    fontWeight: 600,
    letterSpacing: '0.01em',
  },
  voiceRole: {
    color: '#64748b',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.2em',
    textTransform: 'uppercase' as const,
  },
  voiceStatus: {
    color: '#94a3b8',
    fontSize: 12,
    lineHeight: 1.5,
  },
  voiceAuditionTextarea: {
    background: '#050505',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 12,
    color: '#e2e8f0',
    fontSize: 14,
    lineHeight: 1.55,
    minHeight: 74,
    resize: 'vertical' as const,
    padding: '12px 14px',
    outline: 'none',
  },
  voicePerformanceRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(120px, 1fr))',
    gap: 10,
  },
  voiceControlLabel: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase' as const,
  },
  voiceSelect: {
    height: 34,
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.08)',
    background: '#050505',
    color: '#cbd5e1',
    padding: '0 10px',
    outline: 'none',
    fontSize: 12,
    letterSpacing: '0.02em',
  },
  voiceActionRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap' as const,
  },
  voiceGhostBtn: {
    height: 34,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.1)',
    background: 'transparent',
    color: '#94a3b8',
    cursor: 'pointer',
    padding: '0 12px',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
  },
  voicePrimaryBtn: {
    height: 34,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 10,
    border: '1px solid rgba(74,158,255,0.38)',
    background: 'rgba(74,158,255,0.08)',
    color: '#93c5fd',
    cursor: 'pointer',
    padding: '0 14px',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
  },
  voiceRenderStatus: {
    color: '#64748b',
    fontSize: 11,
    lineHeight: 1.4,
  },
  voiceCommitRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '4px 0',
  },
  voiceMeta: {
    color: '#64748b',
    fontSize: 10,
    letterSpacing: '0.04em',
  },
  voiceCommitBtn: {
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    borderRadius: 6,
    border: '1px solid #334155',
    background: 'transparent',
    color: '#e2e8f0',
    padding: '0 10px',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
  },
  storyboardConsole: {
    display: 'flex',
    flexDirection: 'column',
    gap: 20,
  },
  storyboardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    gap: 18,
    alignItems: 'flex-start',
    paddingBottom: 16,
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  storyboardEyebrow: {
    color: '#7f9bbd',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
  },
  storyboardTitle: {
    margin: '8px 0 0',
    color: '#e2e8f0',
    fontSize: 20,
    fontWeight: 650,
    lineHeight: 1.25,
  },
  storyboardMetaRow: {
    display: 'flex',
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
    gap: 8,
  },
  storyboardStatusBlocked: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    border: '1px solid rgba(245,158,11,0.45)',
    color: '#facc15',
    background: 'rgba(245,158,11,0.08)',
    borderRadius: 999,
    padding: '7px 12px',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  storyboardStatusPass: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    border: '1px solid rgba(16,185,129,0.45)',
    color: '#34d399',
    background: 'rgba(16,185,129,0.08)',
    borderRadius: 999,
    padding: '7px 12px',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  storyboardMetaPill: {
    border: '1px solid rgba(148,163,184,0.28)',
    color: '#a8b6ca',
    borderRadius: 999,
    padding: '7px 12px',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  storyboardBlockerBox: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    border: '1px solid rgba(245,158,11,0.32)',
    borderRadius: 10,
    background: 'rgba(245,158,11,0.06)',
    color: '#f8d78a',
    padding: '14px 16px',
    fontSize: 13,
    lineHeight: 1.45,
  },
  storyboardBlockerList: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: 12,
    padding: '10px 0 18px',
  },
  storyboardBlockerTitle: {
    color: '#7f9bbd',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  storyboardBlockerItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    minWidth: 0,
    border: '1px solid rgba(180,83,9,0.72)',
    borderRadius: 10,
    background: 'rgba(217,119,6,0.1)',
    padding: 14,
  },
  storyboardBlockerErrorText: {
    color: '#facc15',
    fontSize: 12,
    fontWeight: 800,
    lineHeight: 1.5,
    wordBreak: 'break-all',
    overflowWrap: 'anywhere',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  storyboardBlockerVerdict: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    borderTop: '1px solid rgba(180,83,9,0.42)',
    paddingTop: 10,
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  storyboardBlockerVerdictLabel: {
    color: '#9ca3af',
    fontWeight: 700,
  },
  storyboardBlockerVerdictStatus: {
    color: '#f87171',
    fontWeight: 900,
    textAlign: 'right',
    overflowWrap: 'anywhere',
  },
  storyboardBlockerMore: {
    color: '#a8b7ca',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.04em',
    padding: '4px 2px',
  },
  storyboardPanelGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))',
    gap: 18,
  },
  storyboardPanelCard: {
    border: '1px solid rgba(148,163,184,0.24)',
    borderRadius: 12,
    overflow: 'hidden',
    background: '#0d1117',
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
    boxShadow: '0 4px 14px rgba(0,0,0,0.26)',
  },
  storyboardFrame: {
    position: 'relative',
    aspectRatio: '16 / 9',
    background: 'linear-gradient(135deg, rgba(15,23,42,0.95), rgba(2,6,23,0.95))',
    overflow: 'hidden',
  },
  storyboardFrameImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
    filter: 'saturate(0.88) contrast(0.95)',
  },
  storyboardFrameMissing: {
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    color: '#64748b',
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  storyboardFrameGuideLabel: {
    color: '#f59e0b',
    fontSize: 18,
    fontWeight: 850,
    letterSpacing: '0.02em',
    textTransform: 'uppercase' as const,
  },
  storyboardFrameGuideLine: {
    color: '#cbd5e1',
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase' as const,
  },
  storyboardFrameShade: {
    position: 'absolute',
    inset: 0,
    background: 'linear-gradient(180deg, rgba(2,6,23,0.58) 0%, rgba(2,6,23,0.06) 36%, rgba(2,6,23,0.76) 100%)',
    pointerEvents: 'none',
  },
  storyboardFrameTop: {
    position: 'absolute',
    top: 10,
    left: 10,
    right: 10,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  storyboardPanelFrameActions: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 8,
    minWidth: 0,
  },
  storyboardCopyButton: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    border: '1px solid rgba(125,211,252,0.22)',
    background: 'rgba(2,6,23,0.70)',
    color: '#c7e8ff',
    borderRadius: 999,
    width: 28,
    height: 28,
    padding: 0,
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    cursor: 'pointer',
  },
  storyboardFrameBottom: {
    position: 'absolute',
    left: 10,
    right: 10,
    bottom: 10,
    display: 'grid',
    gap: 7,
  },
  storyboardShotCode: {
    justifySelf: 'start',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    border: '1px solid rgba(74,158,255,0.32)',
    background: 'rgba(2,6,23,0.70)',
    color: '#bfdbfe',
    borderRadius: 999,
    padding: '4px 8px',
    fontSize: 10,
    fontWeight: 900,
    letterSpacing: '0.12em',
  },
  storyboardFrameCaption: {
    color: '#f8fafc',
    fontSize: 13,
    lineHeight: 1.3,
    fontWeight: 750,
    textShadow: '0 1px 12px rgba(0,0,0,0.75)',
  },
  storyboardPanelTopline: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  storyboardPanelId: {
    color: '#dbeafe',
    background: 'rgba(2,6,23,0.66)',
    border: '1px solid rgba(219,234,254,0.18)',
    borderRadius: 999,
    padding: '4px 8px',
    fontSize: 11,
    fontWeight: 850,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  storyboardPanelTime: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    color: '#7dd3fc',
    background: 'rgba(2,6,23,0.66)',
    border: '1px solid rgba(125,211,252,0.20)',
    borderRadius: 999,
    padding: '4px 6px',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    fontWeight: 800,
  },
  storyboardShot: {
    color: '#cbd5e1',
    fontSize: 14,
    lineHeight: 1.35,
    fontWeight: 700,
  },
  storyboardAction: {
    margin: 0,
    color: '#cbd5e1',
    fontSize: 13,
    lineHeight: 1.55,
  },
  storyboardDialogue: {
    margin: 0,
    color: '#e2e8f0',
    fontSize: 13,
    lineHeight: 1.45,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  storyboardSupportGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: 10,
    paddingTop: 2,
  },
  storyboardAccordion: {
    background: '#0d1117',
    border: '1px solid #374151',
    borderRadius: 6,
    marginTop: 4,
    overflow: 'hidden',
  },
  storyboardAccordionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    padding: '12px 18px',
    fontSize: 12,
    fontWeight: 800,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.08em',
    color: '#9ca3af',
    background: 'rgba(255,255,255,0.03)',
    cursor: 'pointer',
    userSelect: 'none' as const,
    listStyle: 'none',
  },
  storyboardAccordionChevron: {
    flex: '0 0 auto',
    color: '#6b7280',
    transition: 'transform 0.22s ease, color 0.2s ease',
  },
  storyboardAccordionContent: {
    padding: 20,
    borderTop: '1px solid #374151',
    display: 'flex',
    flexDirection: 'column',
    gap: 20,
    background: '#0a0e14',
  },
  storyboardSupportBlock: {
    minWidth: 0,
    border: 'none',
    borderLeft: '3px solid rgba(59,130,246,0.74)',
    borderRadius: '0 6px 6px 0',
    background: 'rgba(59,130,246,0.055)',
    padding: '10px 11px',
    display: 'flex',
    flexDirection: 'column',
    gap: 7,
  },
  storyboardSupportTitle: {
    color: '#f59e0b',
    fontSize: 10,
    fontWeight: 900,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
  },
  storyboardSupportBody: {
    margin: 0,
    color: '#dbeafe',
    fontSize: 12,
    lineHeight: 1.45,
  },
  storyboardSupportList: {
    margin: 0,
    paddingLeft: 15,
    color: '#93a4bb',
    fontSize: 11,
    lineHeight: 1.35,
  },
  storyboardPromptBlock: {
    border: 'none',
    borderLeft: '3px solid #eab308',
    borderRadius: '0 6px 6px 0',
    background: 'rgba(234,179,8,0.055)',
    padding: '12px 14px',
    display: 'grid',
    gap: 9,
  },
  storyboardPromptHeader: {
    color: '#fbbf24',
    fontSize: 10,
    fontWeight: 900,
    letterSpacing: '0.16em',
    textTransform: 'uppercase' as const,
  },
  storyboardPromptText: {
    margin: 0,
    color: '#e2e8f0',
    fontSize: 12,
    lineHeight: 1.48,
  },
  storyboardPromptPair: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: 9,
    color: '#b6c4d6',
    fontSize: 11,
    lineHeight: 1.38,
  },
  storyboardPromptLabel: {
    display: 'block',
    marginBottom: 3,
    color: '#f59e0b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
  },
  storyboardPromptRequirements: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
  },
  storyboardNegativePrompt: {
    color: '#fca5a5',
    fontSize: 11,
    lineHeight: 1.38,
  },
  storyboardSeedRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
  },
  storyboardPanelBody: {
    display: 'grid',
    gap: 18,
    padding: 20,
    borderTop: '1px solid rgba(148,163,184,0.18)',
  },
  storyboardTrackRow: {
    display: 'grid',
    gap: 10,
    paddingTop: 2,
  },
  storyboardTagGroup: {
    display: 'grid',
    gap: 6,
  },
  storyboardTagLabel: {
    color: '#64748b',
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: '0.18em',
    textTransform: 'uppercase' as const,
  },
  storyboardSeed: {
    color: '#9ed0ff',
    background: 'rgba(74,158,255,0.08)',
    border: '1px solid rgba(74,158,255,0.18)',
    borderRadius: 999,
    padding: '3px 7px',
    fontSize: 10,
    fontWeight: 800,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  storyboardEntityRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
  },
  storyboardEntity: {
    color: '#f9a8d4',
    background: 'rgba(244,114,182,0.075)',
    border: '1px solid rgba(244,114,182,0.20)',
    borderRadius: 999,
    padding: '3px 8px',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.03em',
  },
  storyboardReferenceRail: {
    display: 'flex',
    gap: 8,
    overflowX: 'auto' as const,
    paddingTop: 4,
  },
  storyboardReferenceGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
  },
  storyboardReferenceCard: {
    display: 'grid',
    gridTemplateColumns: '64px 1fr',
    gap: 9,
    alignItems: 'center',
    flex: '0 0 220px',
    minWidth: 0,
    border: '1px solid rgba(255,255,255,0.07)',
    borderRadius: 8,
    background: 'rgba(255,255,255,0.025)',
    padding: 7,
  },
  storyboardReferenceThumb: {
    width: 64,
    height: 44,
    borderRadius: 6,
    objectFit: 'cover' as const,
    display: 'block',
    background: 'rgba(15,23,42,0.78)',
  },
  storyboardReferenceFallback: {
    width: 64,
    height: 44,
    borderRadius: 6,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#7f9bbd',
    background: 'rgba(148,163,184,0.08)',
  },
  storyboardReferenceText: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    minWidth: 0,
    color: '#dbeafe',
    fontSize: 11,
    lineHeight: 1.25,
  },
  storyboardCandidateStrip: {
    borderTop: '1px solid rgba(255,255,255,0.09)',
    paddingTop: 14,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  storyboardCandidateRow: {
    display: 'grid',
    gridTemplateColumns: '88px 1fr',
    gap: 12,
    alignItems: 'center',
    color: '#a8b6ca',
    fontSize: 12,
    lineHeight: 1.45,
  },
  storyboardCandidateThumb: {
    width: 88,
    height: 58,
    objectFit: 'cover' as const,
    borderRadius: 8,
    border: '1px solid rgba(255,255,255,0.09)',
    filter: 'saturate(0.75)',
  },
  storyboardCandidateStatus: {
    color: '#facc15',
    fontSize: 11,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  storyboardCandidateReason: {
    color: '#94a3b8',
    marginTop: 3,
  },
  contactSheetGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 16,
    padding: 0,
    background: 'transparent',
    borderRadius: 0,
  },
  contactSheetCard: {
    position: 'relative' as const,
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 14,
    overflow: 'hidden',
    background: 'rgba(255,255,255,0.025)',
    cursor: 'zoom-in',
  },
  contactSheetThumb: {
    width: '100%',
    height: 128,
    objectFit: 'cover' as const,
    opacity: 0.92,
    display: 'block',
  },
  contactSheetCaption: {
    position: 'absolute' as const,
    left: 8,
    right: 8,
    bottom: 8,
    display: 'flex',
    justifyContent: 'space-between',
    gap: 8,
    color: '#e2e8f0',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    textShadow: '0 1px 10px rgba(0,0,0,0.85)',
    pointerEvents: 'none' as const,
  },
  contactSheetOverlay: {
    position: 'absolute' as const,
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    opacity: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'opacity 200ms ease',
  },
  contactSheetAction: {
    color: '#fff',
    fontSize: 11,
    padding: '4px 10px',
    background: '#7c3aed',
    borderRadius: 6,
    border: 0,
    cursor: 'pointer',
  },
  contactSheetEmpty: {
    gridColumn: '1 / -1',
    padding: '48px 0',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    border: '1px dashed #64748b',
    borderRadius: 8,
    gap: 8,
  },
  contactSheetTrigger: {
    color: '#4a9eff',
    fontSize: 11,
    textDecoration: 'underline',
    background: 'transparent',
    border: 0,
    cursor: 'pointer',
  },
  researchPane: {
    minHeight: 0,
    overflow: 'auto',
    borderLeft: '1px solid #334155',
    background: '#111111',
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  researchPaneHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  researchPaneTitle: {
    color: '#4a9eff',
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  researchPaneBadge: {
    fontSize: 9,
    color: '#64748b',
    border: '1px solid #334155',
    borderRadius: 4,
    padding: '2px 6px',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  researchList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  researchAccordion: {
    border: '1px solid rgba(75, 85, 99, 0.9)',
    background: '#090909',
  },
  researchAccordionSummary: {
    minHeight: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 10px',
    color: '#d1d5db',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    userSelect: 'none',
  },
  researchAccordionContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    borderTop: '1px solid rgba(75, 85, 99, 0.65)',
    padding: 8,
  },
  researchCard: {
    background: '#1a1a1a',
    padding: 10,
    borderRadius: 0,
    border: '1px solid rgba(255,255,255,0.08)',
  },
  researchLink: {
    color: '#4a9eff',
    fontSize: 11,
    fontWeight: 600,
    textDecoration: 'underline',
    display: 'block',
    marginBottom: 4,
  },
  researchSnippet: {
    color: '#64748b',
    fontSize: 10,
    lineHeight: 1.45,
    margin: 0,
  },
  inspectorPrompt: {
    borderColor: '#7c3aed',
  },
  ideaMemoryCanvas: {
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
    padding: 0,
    background: 'transparent',
    borderRadius: 0,
    transition: 'background 420ms ease',
  },
  ideaMemoryCanvasEditing: {
    background: 'linear-gradient(180deg, rgba(23, 24, 21, 0.72) 0%, rgba(20, 20, 20, 0) 42%)',
  },
  memoryBoardSection: {
    minHeight: '100%',
    width: '100%',
  },
  storyMatrixBelowBoard: {
    width: '100%',
    margin: '24px 0 0',
  },
  ideaComposer: {
    position: 'relative' as const,
    width: 'min(896px, calc(100% - 64px))',
    margin: '0 auto',
    padding: '34px 32px 22px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 18,
    borderRadius: 0,
    border: 0,
    background: 'transparent',
  },
  ideaComposerHeader: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  ideaEditAffordance: {
    minWidth: 0,
    height: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    borderRadius: 999,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.035)',
    color: '#64748b',
    cursor: 'pointer',
    padding: '0 9px',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    transition: 'color 180ms ease, border-color 180ms ease, background 180ms ease',
  },
  ideaComposerLabel: {
    color: '#64748b',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.25em',
    lineHeight: 1,
    textTransform: 'uppercase' as const,
  },
  ideaComposerInput: {
    width: '100%',
    resize: 'none' as const,
    overflow: 'hidden',
    minHeight: 0,
    border: 0,
    outline: 0,
    background: 'transparent',
    color: '#e2e8f0',
    fontSize: 30,
    fontWeight: 300,
    lineHeight: 1.4,
    textAlign: 'center' as const,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    borderBottom: 0,
    padding: '14px 18px',
    borderRadius: 14,
    transition: 'border-color 220ms ease, color 220ms ease, opacity 420ms ease, background 220ms ease, box-shadow 220ms ease',
    animation: 'dream-soft-fade 420ms ease-out both',
  },
  ideaComposerActions: {
    minHeight: 18,
    display: 'flex',
    justifyContent: 'center',
    marginTop: 8,
    opacity: 0.6,
    transition: 'opacity 180ms ease',
  },
  ideaComposerAction: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 10,
    color: '#4a9eff',
    background: 'transparent',
    border: 0,
    padding: 0,
    cursor: 'pointer',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  },
  ideaComposerDot: {
    width: 32,
    height: 1,
    borderRadius: 0,
    background: '#4a9eff',
  },
  ideaComposerStatus: {
    color: '#ffaa00',
    fontSize: 10,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
    animation: 'dream-pulse 1.5s ease-in-out infinite',
  },
  rerunIdeaBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    color: '#4a9eff',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    background: 'transparent',
    border: 0,
    cursor: 'pointer',
    padding: 0,
    textDecoration: 'none',
  },
  memoryNode: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'flex-start',
    alignItems: 'flex-start',
    gap: 12,
    padding: 24,
    borderRadius: 24,
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.05)',
    backdropFilter: 'blur(20px)',
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
    transition: 'all 300ms ease',
    cursor: 'default',
    overflow: 'hidden',
  },
  memoryTextNode: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'flex-start',
    alignItems: 'flex-start',
    gap: 12,
    padding: 24,
    borderRadius: 20,
    background: 'rgba(26,26,26,0.4)',
    border: '1px solid transparent',
    boxShadow: 'none',
    transition: 'all 300ms ease',
    cursor: 'grab',
    overflow: 'hidden',
  },
  memoryMediaNode: {
    width: '100%',
    position: 'relative' as const,
    display: 'block',
    padding: 0,
    borderRadius: 14,
    background: 'transparent',
    border: 'none',
    boxShadow: 'none',
    transition: 'transform 300ms ease, filter 300ms ease',
    cursor: 'default',
    overflow: 'hidden',
  },
  memoryMediaCard: {
    width: '100%',
    position: 'relative' as const,
    display: 'block',
    padding: 0,
    borderRadius: 18,
    background: '#141414',
    border: '1px solid rgba(255,255,255,0.05)',
    boxShadow: 'none',
    transition: 'transform 300ms ease, border-color 300ms ease, box-shadow 300ms ease',
    cursor: 'default',
    overflow: 'hidden',
  },
  memoryTextCard: {
    width: '100%',
    position: 'relative' as const,
    display: 'block',
    padding: 20,
    borderRadius: 18,
    background: '#141414',
    border: '1px solid rgba(255,255,255,0.05)',
    boxShadow: 'none',
    transition: 'transform 300ms ease, border-color 300ms ease, box-shadow 300ms ease',
    cursor: 'grab',
    overflow: 'hidden',
  },
  memoryUnifiedCard: {
    width: '100%',
    position: 'relative' as const,
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
    padding: 0,
    borderRadius: 18,
    background: 'rgba(26,26,26,0.4)',
    border: '1px solid rgba(255,255,255,0.05)',
    boxShadow: 'none',
    transition: 'transform 300ms ease, background 300ms ease, border-color 300ms ease, box-shadow 300ms ease',
    cursor: 'grab',
    overflow: 'hidden',
  },
  memoryMediaButton: {
    width: '100%',
    display: 'block',
    padding: 0,
    margin: 0,
    border: 0,
    background: 'transparent',
    borderRadius: 0,
    overflow: 'hidden',
    cursor: 'zoom-in',
  },
  memoryFullBleedMedia: {
    width: '100%',
    height: 'auto',
    objectFit: 'contain' as const,
    display: 'block',
    pointerEvents: 'none' as const,
    transition: 'transform 700ms ease',
  },
  memoryAudioPreview: {
    width: '100%',
    minHeight: 160,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    margin: 0,
    padding: 16,
    borderRadius: 0,
    background: 'rgba(26,26,26,0.4)',
    cursor: 'zoom-in',
  },
  memoryMediaShelf: {
    position: 'absolute' as const,
    left: 0,
    right: 0,
    bottom: 0,
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) auto',
    alignItems: 'center',
    gap: 10,
    minHeight: 44,
    padding: '9px 12px 10px',
    background: 'linear-gradient(to top, rgba(0,0,0,0.74), rgba(0,0,0,0.34))',
    backdropFilter: 'blur(10px)',
    pointerEvents: 'auto' as const,
    transition: 'transform 260ms ease',
  },
  memoryOverlayText: {
    margin: 0,
    color: '#f8fafc',
    fontSize: 12,
    lineHeight: 1.38,
    fontWeight: 500,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  memoryTextCardBody: {
    display: 'block',
  },
  memoryTextParagraph: {
    margin: 0,
    color: '#a0aec0',
    fontSize: 13,
    lineHeight: 1.62,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  },
  memoryTextDisclosure: {
    position: 'relative' as const,
    alignSelf: 'flex-end' as const,
    marginTop: 14,
    padding: '4px 8px',
    borderTop: 0,
    background: 'rgba(20,20,20,0.88)',
    backdropFilter: 'blur(8px)',
    borderRadius: 10,
    display: 'inline-flex',
    alignItems: 'center',
    transition: 'transform 260ms ease',
  },
  traceOverlayBackdrop: {
    position: 'fixed' as const,
    inset: 0,
    zIndex: 10000,
    background: 'transparent',
    pointerEvents: 'auto' as const,
  },
  traceOverlayPanel: {
    position: 'fixed' as const,
    display: 'grid',
    gridTemplateRows: 'auto minmax(0, 1fr)',
    overflow: 'hidden',
    borderRadius: 18,
    border: '1px solid rgba(148, 163, 184, 0.42)',
    background: 'radial-gradient(circle at 44% 36%, rgba(30, 41, 59, 0.92), rgba(3, 7, 18, 0.96) 58%, rgba(0, 0, 0, 0.98))',
    boxShadow: '0 34px 110px rgba(0,0,0,0.66), inset 0 1px 0 rgba(255,255,255,0.06)',
    pointerEvents: 'auto' as const,
  },
  traceHeader: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) auto auto',
    alignItems: 'center',
    gap: 10,
    padding: '8px 10px',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  traceHeaderText: {
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 2,
  },
  traceEyebrow: {
    color: '#e2e8f0',
    fontSize: 13,
    fontWeight: 800,
    letterSpacing: '0.02em',
  },
  traceTitle: {
    margin: 0,
    color: '#f8fafc',
    fontSize: 18,
    fontWeight: 720,
    letterSpacing: 0,
    lineHeight: 1.18,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  traceSubtitle: {
    margin: 0,
    color: '#60a5fa',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.12em',
    lineHeight: 1.2,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  traceToolbar: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  traceHopCycle: {
    height: 32,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    padding: '0 12px',
    borderRadius: 999,
    border: '1px solid rgba(148,163,184,0.2)',
    background: 'rgba(2,6,23,0.54)',
    color: '#dbeafe',
    fontSize: 11,
    fontWeight: 820,
    letterSpacing: '0.02em',
    cursor: 'pointer',
    boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
  },
  traceSegment: {
    height: 34,
    minWidth: 66,
    border: 0,
    borderRight: '1px solid rgba(255,255,255,0.07)',
    background: 'transparent',
    color: '#cbd5e1',
    fontSize: 12,
    fontWeight: 750,
    cursor: 'pointer',
  },
  traceSegmentActive: {
    color: '#ffffff',
    background: 'linear-gradient(135deg, rgba(124,58,237,0.9), rgba(74,158,255,0.32))',
    boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.12)',
  },
  traceIconBar: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
  },
  traceIconButton: {
    width: 32,
    height: 32,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    border: '1px solid rgba(148,163,184,0.22)',
    background: 'rgba(15,23,42,0.44)',
    color: '#cbd5e1',
    cursor: 'pointer',
  },
  traceBody: {
    minHeight: 0,
    display: 'block',
    padding: '8px 10px 10px',
  },
  traceGraphCanvas: {
    position: 'relative' as const,
    width: '100%',
    height: '100%',
    minHeight: 0,
    borderRadius: 16,
    overflow: 'hidden',
    background: 'radial-gradient(circle at 50% 50%, rgba(74,158,255,0.13), rgba(45,212,191,0.05) 34%, rgba(2,6,23,0.04) 58%, rgba(0,0,0,0.16))',
  },
  traceSvg: {
    width: '100%',
    height: '100%',
    display: 'block',
  },
  traceEdgeLabel: {
    fill: '#c4b5fd',
    fontSize: 11,
    fontWeight: 650,
    pointerEvents: 'none' as const,
  },
  traceNodeGlyph: {
    fill: '#e2e8f0',
    fontSize: 10,
    fontWeight: 900,
    letterSpacing: '0.08em',
    pointerEvents: 'none' as const,
  },
  traceNodeLabel: {
    fill: '#f8fafc',
    fontSize: 12,
    fontWeight: 700,
    pointerEvents: 'none' as const,
  },
  traceNodePill: {
    fill: '#94a3b8',
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase' as const,
    pointerEvents: 'none' as const,
  },
  traceNodeGlyphPanel: {
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    color: '#e2e8f0',
    fontSize: 8,
    fontWeight: 900,
    letterSpacing: '0.06em',
    lineHeight: 1,
    pointerEvents: 'none' as const,
    borderRadius: 999,
    background: 'rgba(2,6,23,0.5)',
    border: '1px solid rgba(226,232,240,0.18)',
  },
  traceNodeMediaPanel: {
    position: 'relative' as const,
    width: '100%',
    height: '100%',
    borderRadius: 999,
    overflow: 'hidden',
    background: 'rgba(2,6,23,0.5)',
    border: '1px solid rgba(226,232,240,0.16)',
    pointerEvents: 'none' as const,
  },
  traceNodeMediaImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
    opacity: 0.78,
  },
  traceNodeIconOverlay: {
    position: 'absolute' as const,
    left: '50%',
    top: '50%',
    transform: 'translate(-50%, -50%)',
    width: 24,
    height: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    color: '#e2e8f0',
    background: 'rgba(0,0,0,0.5)',
    border: '1px solid rgba(255,255,255,0.24)',
    boxShadow: '0 6px 16px rgba(0,0,0,0.34)',
  },
  traceNodeTypeBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2px 5px',
    borderRadius: 999,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(2,6,23,0.72)',
    color: '#e2e8f0',
    fontSize: 7,
    fontWeight: 850,
    letterSpacing: '0.06em',
  },
  traceNodeLabelBox: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: 2,
    pointerEvents: 'none' as const,
  },
  traceNodeLabelText: {
    maxWidth: 176,
    color: '#f8fafc',
    fontSize: 11,
    fontWeight: 760,
    lineHeight: 1.15,
    textAlign: 'center' as const,
    overflow: 'hidden',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    textShadow: '0 1px 8px rgba(0,0,0,0.8)',
  },
  traceNodeKindText: {
    color: '#94a3b8',
    fontSize: 9,
    fontWeight: 800,
    lineHeight: 1,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  },
  traceTextPreview: {
    width: 230,
    maxHeight: 112,
    padding: '10px 11px',
    borderRadius: 12,
    border: '1px solid rgba(148,163,184,0.22)',
    background: 'rgba(2,6,23,0.92)',
    color: '#dbeafe',
    fontSize: 11,
    lineHeight: 1.35,
    boxShadow: '0 16px 40px rgba(0,0,0,0.42)',
    overflow: 'hidden',
  },
  traceTextPreviewMeta: {
    marginBottom: 5,
    color: '#4a9eff',
    fontSize: 8,
    fontWeight: 900,
    letterSpacing: '0.1em',
    textTransform: 'uppercase' as const,
  },
  traceTextPreviewFloating: {
    position: 'absolute' as const,
    left: 14,
    top: 14,
    zIndex: 5,
    width: 'min(320px, calc(100% - 28px))',
    maxHeight: 132,
    padding: '10px 12px',
    borderRadius: 13,
    border: '1px solid rgba(148,163,184,0.22)',
    background: 'rgba(2,6,23,0.9)',
    color: '#dbeafe',
    fontSize: 12,
    lineHeight: 1.38,
    boxShadow: '0 18px 48px rgba(0,0,0,0.42)',
    backdropFilter: 'blur(12px)',
    overflow: 'hidden',
    pointerEvents: 'none' as const,
  },
  traceVideoPlayer: {
    position: 'absolute' as const,
    right: 14,
    top: 14,
    zIndex: 7,
    width: 'min(360px, calc(100% - 28px))',
    borderRadius: 14,
    overflow: 'hidden',
    border: '1px solid rgba(148,163,184,0.24)',
    background: 'rgba(2,6,23,0.94)',
    boxShadow: '0 22px 62px rgba(0,0,0,0.52)',
    backdropFilter: 'blur(12px)',
  },
  traceVideoHeader: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) auto',
    alignItems: 'center',
    gap: 8,
    padding: '8px 9px',
    color: '#e2e8f0',
    fontSize: 11,
    fontWeight: 750,
    lineHeight: 1.2,
  },
  traceVideoClose: {
    width: 26,
    height: 26,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 9,
    border: '1px solid rgba(148,163,184,0.18)',
    background: 'rgba(15,23,42,0.62)',
    color: '#cbd5e1',
    cursor: 'pointer',
  },
  traceVideoElement: {
    width: '100%',
    display: 'block',
    maxHeight: 240,
    background: '#000',
  },
  traceGestureHint: {
    position: 'absolute' as const,
    left: '50%',
    bottom: 14,
    transform: 'translateX(-50%)',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 9,
    padding: '8px 13px',
    borderRadius: 12,
    border: '1px solid rgba(148,163,184,0.16)',
    background: 'rgba(15,23,42,0.72)',
    color: '#cbd5e1',
    fontSize: 11,
    backdropFilter: 'blur(10px)',
  },
  traceMiniHud: {
    position: 'absolute' as const,
    right: 14,
    top: 14,
    width: 220,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    padding: 11,
    borderRadius: 14,
    border: '1px solid rgba(148,163,184,0.14)',
    background: 'rgba(2,6,23,0.58)',
    backdropFilter: 'blur(12px)',
    boxShadow: '0 18px 40px rgba(0,0,0,0.24)',
  },
  traceMiniHudDots: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
  },
  traceGraphStatus: {
    position: 'absolute' as const,
    right: 14,
    bottom: 14,
    display: 'inline-flex',
    alignItems: 'center',
    padding: '6px 9px',
    borderRadius: 999,
    border: '1px solid rgba(148,163,184,0.12)',
    background: 'rgba(2,6,23,0.5)',
    color: '#94a3b8',
    fontSize: 10,
    fontWeight: 700,
    backdropFilter: 'blur(10px)',
  },
  traceLegend: {
    minHeight: 0,
    overflow: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
  },
  traceLegendCard: {
    borderRadius: 14,
    border: '1px solid rgba(148,163,184,0.14)',
    background: 'rgba(15,23,42,0.46)',
    padding: 16,
  },
  traceLegendTitle: {
    margin: '0 0 10px',
    color: '#f8fafc',
    fontSize: 13,
    fontWeight: 800,
  },
  traceLegendCopy: {
    margin: 0,
    color: '#cbd5e1',
    fontSize: 12,
    lineHeight: 1.55,
  },
  traceLegendRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '7px 0',
  },
  traceLegendDot: {
    width: 11,
    height: 11,
    borderRadius: 999,
    flexShrink: 0,
  },
  traceLegendKind: {
    color: '#cbd5e1',
    fontSize: 12,
    fontWeight: 700,
    textTransform: 'capitalize' as const,
  },
  tracePathPreview: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  tracePathChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    color: '#cbd5e1',
    fontSize: 10,
    fontWeight: 750,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  traceLegendMeta: {
    margin: '12px 0 0',
    color: '#64748b',
    fontSize: 11,
  },
  traceHiddenTable: {
    position: 'absolute' as const,
    width: 1,
    height: 1,
    overflow: 'hidden',
    clipPath: 'inset(50%)',
    whiteSpace: 'nowrap' as const,
  },
  graphBtn: {
    position: 'absolute' as const,
    bottom: 8,
    right: 8,
    width: 28,
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(0,0,0,0.4)',
    color: '#64748b',
    cursor: 'pointer',
    padding: 0,
    transition: 'color 200ms ease, border-color 200ms ease',
  },
  graphInlineBtn: {
    width: 24,
    height: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    border: '1px solid rgba(74,158,255,0.24)',
    background: 'transparent',
    color: '#4a9eff',
    cursor: 'pointer',
    padding: 0,
    flexShrink: 0,
    transition: 'color 200ms ease, border-color 200ms ease, background 200ms ease',
  },
  graphGhostBtn: {
    width: 28,
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 6,
    border: 'none',
    background: 'transparent',
    color: 'rgba(255,255,255,0.5)',
    cursor: 'pointer',
    padding: 0,
    flexShrink: 0,
    transition: 'color 150ms ease, background 150ms ease',
  },
  chevronBtn: {
    width: 24,
    height: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 6,
    border: 'none',
    background: 'transparent',
    color: 'rgba(255,255,255,0.5)',
    cursor: 'pointer',
    padding: 0,
    flexShrink: 0,
    transition: 'color 150ms ease, transform 150ms ease',
  },
  memorySemanticSignal: {
    position: 'absolute' as const,
    left: 16,
    bottom: 16,
    zIndex: 4,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 5,
    pointerEvents: 'auto' as const,
  },
  memoryTraceNodeRow: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    opacity: 0,
    transform: 'translateY(4px)',
    transition: 'opacity 180ms ease, transform 180ms ease',
  },
  memoryTraceNode: {
    height: 22,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    borderRadius: 999,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(0,0,0,0.46)',
    backdropFilter: 'blur(8px)',
    color: 'rgba(255,255,255,0.78)',
    padding: '0 7px',
    cursor: 'help',
    flex: '0 0 auto',
  },
  memoryTraceNodeDot: {
    width: 7,
    height: 7,
    borderRadius: 999,
    flex: '0 0 auto',
  },
  memoryTraceNodeDepth: {
    color: '#f8fafc',
    fontSize: 8,
    fontWeight: 900,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    letterSpacing: '0.05em',
  },
  memoryTraceNodeLabel: {
    maxWidth: 78,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    color: '#cbd5e1',
    fontSize: 8,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
  },
  memoryPathTraceStack: {
    display: 'inline-flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 3,
    opacity: 0,
    transform: 'translateY(4px)',
    transition: 'opacity 180ms ease, transform 180ms ease',
    pointerEvents: 'none' as const,
  },
  memoryPathTraceChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 3,
    color: 'rgba(255,255,255,0.74)',
    background: 'rgba(0,0,0,0.52)',
    backdropFilter: 'blur(8px)',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 5,
    padding: '3px 6px',
    fontSize: 8,
    fontWeight: 800,
    letterSpacing: '0.10em',
    textTransform: 'uppercase' as const,
    whiteSpace: 'nowrap' as const,
  },
  memoryPathTraceHop: {
    color: '#4a9eff',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
  memoryPathTraceTarget: {
    color: '#f8fafc',
    fontWeight: 900,
  },
  memorySemanticActive: {
    borderColor: 'rgba(74,158,255,0.42)',
    boxShadow: '0 0 0 1px rgba(74,158,255,0.14), 0 18px 42px rgba(74,158,255,0.10)',
  },
  memoryCardBody: {
    width: '100%',
    padding: '16px 16px 10px',
  },
  memoryCardActions: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    padding: '0 16px 16px',
  },
  memoryMediaOverlay: {
    position: 'absolute' as const,
    inset: '8px 8px auto auto',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 6,
    pointerEvents: 'auto' as const,
  },
  memoryTextActions: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
  },
  pinPillBtn: {
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(0,0,0,0.55)',
    color: '#fff',
    padding: '0 12px',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    cursor: 'pointer',
    backdropFilter: 'blur(10px)',
  },
  pinCallout: {
    position: 'absolute',
    left: 'calc(100% + 10px)',
    top: 0,
    width: 240,
    background: '#050505',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: 12,
    padding: 16,
    zIndex: 1000,
    pointerEvents: 'none',
    boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
  },
  pinHudHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    borderBottom: '1px solid rgba(255,255,255,0.05)',
    paddingBottom: 8,
    marginBottom: 8,
  },
  pinHudTitle: {
    color: '#e2e8f0',
    fontSize: 11,
    fontWeight: 600,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  pinHudBody: {
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    fontSize: 11,
    lineHeight: 1.6,
    color: '#94a3b8',
  },
  pinHudFooter: {
    marginTop: 12,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 9,
    color: '#4a9eff',
    textTransform: 'uppercase',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  pinTextBtn: {
    height: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 0,
    border: 0,
    background: 'transparent',
    color: '#4a9eff',
    padding: 0,
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
    cursor: 'pointer',
  },
  memoryLabel: {
    color: '#a0aec0',
    fontSize: 13,
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    lineHeight: 1.6,
    display: '-webkit-box',
    WebkitLineClamp: 8,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  memoryScore: {
    color: '#64748b',
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    marginTop: 2,
  },
  memorySelect: {
    background: 'transparent',
    color: '#4a9eff',
    fontSize: 10,
    padding: '4px 6px',
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.08)',
    cursor: 'pointer',
    flexShrink: 0,
  },
  memoryList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  memoryMasonry: {
    width: '100%',
    maxWidth: 1240,
    margin: '0 auto',
    padding: '18px 32px 80px',
    overflow: 'visible',
  },
  memoryInspectorModal: {
    position: 'relative' as const,
    width: 'min(720px, calc(100vw - 48px))',
    maxHeight: 'calc(100vh - 48px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    borderRadius: 24,
    border: '1px solid rgba(255,255,255,0.1)',
    background: 'rgba(20,20,20,0.9)',
    boxShadow: '0 28px 80px rgba(0,0,0,0.48)',
    backdropFilter: 'blur(22px)',
    cursor: 'default',
  },
  memoryInspectorMedia: {
    width: '100%',
    maxHeight: 'calc(100vh - 120px)',
    objectFit: 'contain' as const,
    borderRadius: 16,
    background: 'rgba(0,0,0,0.22)',
    display: 'block',
  },
  memoryInspectorAudio: {
    width: '100%',
    padding: '52px 24px 24px',
    borderRadius: 18,
    background: 'rgba(255,255,255,0.04)',
  },
  modalCloseBtn: {
    position: 'absolute' as const,
    top: 12,
    right: 12,
    zIndex: 2,
    width: 34,
    height: 34,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(0,0,0,0.35)',
    color: '#e2e8f0',
    cursor: 'pointer',
    backdropFilter: 'blur(14px)',
  },
  pulseIcon: {
    animation: 'dream-pulse 1.5s ease-in-out infinite',
  },
}

export const styles: Record<string, CSSProperties> = {
  workspace: {
    flex: 1,
    height: '100%',
    minHeight: 0,
    display: 'grid',
    gridTemplateColumns: '320px minmax(0, 1fr) 340px',
    overflow: 'hidden',
    background: 'radial-gradient(circle at top right, #0f172a, #030711 62%, #05070a)',
    color: '#e5e7eb',
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  rail: {
    minWidth: 0,
    minHeight: 0,
    display: 'flex',
    flexDirection: 'column',
    borderRight: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'linear-gradient(180deg, rgba(13, 17, 23, 0.96), rgba(5, 7, 10, 0.98))',
    boxShadow: '16px 0 38px rgba(0, 0, 0, 0.24)',
  },
  railCollapsed: {
    alignItems: 'center',
  },
  railHeader: {
    padding: 16,
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  },
  railCollapsedHeader: {
    width: '100%',
    display: 'flex',
    justifyContent: 'center',
    padding: '12px 8px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
  },
  railTitleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  eyebrow: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: '#7dd3fc',
  },
  railTitle: {
    margin: '4px 0 0',
    fontSize: 18,
    lineHeight: 1.25,
    fontWeight: 700,
    color: '#fff',
  },
  iconButton: {
    width: 40,
    height: 40,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 6,
    border: '1px solid rgba(255, 255, 255, 0.09)',
    background: 'rgba(255, 255, 255, 0.045)',
    color: '#cbd5e1',
    cursor: 'pointer',
  },
  spinIcon: {
    animation: 'spin 1s linear infinite',
  },
  searchWrap: {
    marginTop: 16,
    height: 38,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'rgba(255, 255, 255, 0.045)',
    padding: '0 12px',
  },
  searchInput: {
    minWidth: 0,
    flex: 1,
    border: 0,
    outline: 0,
    background: 'transparent',
    color: '#f8fafc',
    fontSize: 14,
  },
  runList: {
    minHeight: 0,
    flex: 1,
    overflow: 'auto',
    padding: 12,
  },
  runCard: {
    width: '100%',
    display: 'block',
    margin: '0 0 10px',
    padding: 12,
    textAlign: 'left',
    borderRadius: 14,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'rgba(13, 17, 23, 0.72)',
    color: '#f8fafc',
    cursor: 'pointer',
    boxShadow: '0 10px 28px rgba(0, 0, 0, 0.22)',
  },
  runCardSelected: {
    borderColor: 'rgba(96, 165, 250, 0.48)',
    background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.18), rgba(13, 17, 23, 0.84))',
    boxShadow: '0 0 0 1px rgba(96, 165, 250, 0.08), 0 16px 36px rgba(37, 99, 235, 0.12)',
  },
  runCardTop: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  runTitle: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    fontSize: 14,
    fontWeight: 700,
    color: '#f8fafc',
  },
  runSource: {
    marginTop: 4,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    color: '#64748b',
  },
  badgeRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    border: '1px solid',
    borderRadius: 999,
    padding: '5px 9px',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    fontSize: 11,
    letterSpacing: '0',
    textTransform: 'uppercase',
    lineHeight: 1,
  },
  stateBox: {
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: 7,
    background: 'rgba(255, 255, 255, 0.035)',
    padding: 14,
    color: '#94a3b8',
    fontSize: 14,
  },
  errorBox: {
    border: '1px solid rgba(248, 113, 113, 0.35)',
    borderRadius: 7,
    background: 'rgba(248, 113, 113, 0.1)',
    padding: 14,
    color: '#fecaca',
    fontSize: 14,
  },
  emptyBox: {
    border: '1px solid rgba(251, 191, 36, 0.35)',
    borderRadius: 7,
    background: 'rgba(251, 191, 36, 0.1)',
    padding: 14,
    color: '#fde68a',
    fontSize: 14,
  },
  detail: {
    minWidth: 0,
    minHeight: 0,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: 'radial-gradient(circle at 50% 0%, rgba(59, 130, 246, 0.1), transparent 34%), #05070a',
  },
  detailHeader: {
    minHeight: 72,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'rgba(5, 7, 10, 0.9)',
    padding: '16px 20px',
  },
  detailEyebrow: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    letterSpacing: '0.2em',
    textTransform: 'uppercase',
    color: '#64748b',
  },
  detailTitle: {
    margin: '4px 0 0',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    fontSize: 20,
    lineHeight: 1.25,
    color: '#fff',
  },
  reportLink: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    borderRadius: 6,
    border: '1px solid rgba(255, 255, 255, 0.12)',
    padding: '8px 10px',
    color: '#e2e8f0',
    textDecoration: 'none',
    fontSize: 13,
    whiteSpace: 'nowrap',
  },
  stageBoard: {
    minHeight: 0,
    flex: 1,
    overflow: 'auto',
    overflowX: 'hidden',
    padding: '0 0 20px',
    display: 'grid',
    gap: 14,
    alignContent: 'start',
    background: 'transparent',
  },
  stageAnchor: {
    scrollMarginTop: 76,
  },
  gateStrip: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: 14,
    background: 'rgba(13, 17, 23, 0.62)',
    padding: 12,
  },
  gateNote: {
    color: '#cbd5e1',
    fontSize: 13,
    lineHeight: 1.35,
  },
  runMetadata: {
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: 12,
    background: 'rgba(13, 17, 23, 0.48)',
    overflow: 'hidden',
  },
  runMetadataSummary: {
    minHeight: 34,
    display: 'flex',
    alignItems: 'center',
    padding: '0 12px',
    color: '#94a3b8',
    cursor: 'pointer',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
    userSelect: 'none',
  },
  sourceLine: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
    gap: 12,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: 14,
    background: 'rgba(13, 17, 23, 0.7)',
    padding: 12,
  },
  stageCard: {
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: 16,
    background: 'rgba(13, 17, 23, 0.7)',
    padding: 24,
    display: 'grid',
    gap: 20,
    boxShadow: '0 20px 40px -10px rgba(0, 0, 0, 0.5)',
    backdropFilter: 'blur(20px)',
    maxWidth: 'none',
    width: '100%',
    justifySelf: 'stretch',
    outline: '2px solid rgba(59, 130, 246, 0.12)',
    outlineOffset: 0,
    willChange: 'opacity, transform',
  },
  stageCardHeader: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 14,
  },
  stageHeaderStack: {
    display: 'grid',
    gap: 10,
  },
  stageIdentity: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 10,
    minWidth: 0,
  },
  stageHeaderActions: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 10,
    flexWrap: 'wrap',
    flex: '0 0 auto',
  },
  stageHeaderCopyBtn: {
    height: 32,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    padding: '0 12px',
    borderRadius: 999,
    border: '1px solid rgba(148, 163, 184, 0.22)',
    background: 'rgba(15, 23, 42, 0.42)',
    color: '#9fb5d1',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
    transition: 'color 180ms ease, border-color 180ms ease, background 180ms ease',
  },
  stageHeaderCopyLabel: {
    display: 'inline-block',
  },
  stageStatusHelp: {
    justifySelf: 'end',
    maxWidth: 760,
    borderRadius: 12,
    border: '1px solid rgba(251, 191, 36, 0.28)',
    background: 'rgba(251, 191, 36, 0.08)',
    padding: '10px 12px',
    color: '#fde68a',
    fontSize: 12,
    lineHeight: 1.45,
  },
  phaseHeaderText: {
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 7,
  },
  stageIcon: {
    width: 42,
    height: 42,
    flex: '0 0 auto',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    border: '1px solid rgba(96, 165, 250, 0.26)',
    background: 'rgba(59, 130, 246, 0.14)',
    color: '#93c5fd',
  },
  stageId: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    letterSpacing: '0.25em',
    textTransform: 'uppercase',
    color: 'rgba(59, 130, 246, 0.72)',
    lineHeight: 1.1,
  },
  stageTitle: {
    margin: 0,
    padding: 0,
    color: '#f9fafb',
    fontSize: 30,
    lineHeight: 1.1,
    fontWeight: 300,
    letterSpacing: '-0.02em',
  },
  stageTitleRule: {
    width: 64,
    height: 2,
    borderRadius: 999,
    marginTop: 4,
    background: 'rgba(37, 99, 235, 0.55)',
  },
  stageContentWell: {
    minHeight: 220,
    display: 'grid',
    gap: 14,
    borderRadius: 14,
    border: '1px solid rgba(255, 255, 255, 0.055)',
    background: 'rgba(0, 0, 0, 0.22)',
    padding: 16,
  },
  stageSummary: {
    margin: 0,
    color: '#cbd5e1',
    fontSize: 14,
    lineHeight: 1.45,
  },
  gapBox: {
    borderRadius: 12,
    border: '1px solid rgba(251, 191, 36, 0.28)',
    background: 'rgba(251, 191, 36, 0.1)',
    padding: 12,
    color: '#fde68a',
    fontSize: 13,
    lineHeight: 1.45,
    minWidth: 0,
    overflowWrap: 'anywhere',
  },
  agentSuccessBox: {
    borderRadius: 12,
    border: '1px solid rgba(52, 211, 153, 0.24)',
    background: 'rgba(52, 211, 153, 0.08)',
    padding: 12,
    color: '#a7f3d0',
    fontSize: 13,
    lineHeight: 1.45,
  },
  imageGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
    gap: 10,
  },
  imageFigure: {
    margin: 0,
    borderRadius: 12,
    border: '1px solid rgba(255, 255, 255, 0.1)',
    background: 'rgba(0, 0, 0, 0.35)',
    overflow: 'hidden',
  },
  stageImage: {
    width: '100%',
    aspectRatio: '16 / 10',
    objectFit: 'cover',
    display: 'block',
    background: '#000',
  },
  imageCaption: {
    padding: '7px 9px',
    color: '#cbd5e1',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    overflowWrap: 'anywhere',
  },
  artifactChips: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
  },
  artifactChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    maxWidth: '100%',
    borderRadius: 5,
    border: '1px solid rgba(125, 211, 252, 0.28)',
    background: 'rgba(125, 211, 252, 0.08)',
    padding: '6px 8px',
    color: '#bae6fd',
    textDecoration: 'none',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    overflowWrap: 'anywhere',
  },
  receiptAccordion: {
    borderRadius: 8,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'rgba(0, 0, 0, 0.28)',
    padding: 0,
  },
  receiptAccordionSummary: {
    cursor: 'pointer',
    padding: '12px 14px',
    color: '#94a3b8',
    fontSize: 10,
    fontWeight: 850,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
    userSelect: 'none',
  },
  receiptGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: 8,
    padding: '0 14px 14px',
  },
  receiptPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    minWidth: 0,
    maxWidth: '100%',
    borderRadius: 4,
    border: '1px solid rgba(75, 85, 99, 0.9)',
    background: 'rgba(255, 255, 255, 0.03)',
    padding: '7px 9px',
    color: '#9ca3af',
    textDecoration: 'none',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    transition: 'background 160ms ease, border-color 160ms ease, color 160ms ease',
    overflow: 'hidden',
  },
  receiptPillLabel: {
    minWidth: 0,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  mediaLockPanel: {
    display: 'grid',
    gap: 14,
  },
  mediaLockStatusBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderRadius: 0,
    border: '1px solid rgba(74, 158, 255, 0.28)',
    borderLeft: '8px solid #4a9eff',
    background: 'rgba(74, 158, 255, 0.08)',
    padding: '11px 13px',
    color: '#bfdbfe',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.10em',
    textTransform: 'uppercase',
  },
  mediaLockGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))',
    gap: 18,
  },
  mediaLockFrameGroup: {
    display: 'grid',
    gridTemplateRows: 'auto 1fr',
    minWidth: 0,
    borderRadius: 8,
    border: '1px solid rgba(148, 163, 184, 0.18)',
    background: 'rgba(15, 23, 42, 0.28)',
    overflow: 'hidden',
  },
  mediaLockGroupHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    background: '#050505',
    padding: '9px 11px',
    color: '#f8fafc',
    fontSize: 12,
    fontWeight: 850,
    letterSpacing: '0.11em',
    textTransform: 'uppercase',
  },
  mediaLockGroupTitle: {
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  mediaLockLockedBadge: {
    flex: '0 0 auto',
    border: '1px solid rgba(16, 185, 129, 0.3)',
    background: 'rgba(16, 185, 129, 0.1)',
    color: '#10b981',
    padding: '2px 8px',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.05em',
  },
  mediaLockGroupFrames: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: 8,
    padding: 8,
  },
  mediaLockFrame: {
    display: 'grid',
    gridTemplateRows: 'auto 1fr',
    minWidth: 0,
    borderRadius: 0,
    border: '1px solid rgba(255,255,255,0.10)',
    background: '#070707',
    overflow: 'hidden',
  },
  mediaLockThumb: {
    width: '100%',
    aspectRatio: '16 / 9',
    objectFit: 'cover',
    display: 'block',
    background: '#000',
  },
  mediaLockFrameBody: {
    display: 'grid',
    gap: 10,
    padding: 10,
    minWidth: 0,
  },
  mediaLockFrameTitle: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    color: '#f8fafc',
    fontSize: 12,
    fontWeight: 850,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  mediaLockFacts: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    margin: 0,
    color: '#94a3b8',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    lineHeight: 1.25,
  },
  mediaLockFactRow: {
    minWidth: 0,
    width: '100%',
    maxWidth: '100%',
    boxSizing: 'border-box',
    display: 'grid',
    gridTemplateColumns: '58px minmax(0, 1fr)',
    alignItems: 'center',
    columnGap: 8,
    overflow: 'hidden',
    borderBottom: '1px solid rgba(55, 65, 81, 0.42)',
    paddingBottom: 4,
  },
  mediaLockFactLabel: {
    flex: '0 0 auto',
    color: '#9ca3af',
    fontWeight: 600,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  },
  mediaLockFactValue: {
    minWidth: 0,
    justifySelf: 'end',
    maxWidth: '100%',
    color: '#e5e7eb',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'right',
  },
  mediaLockPassValue: {
    color: '#d1d5db',
    fontWeight: 600,
  },
  mediaLockHashValue: {
    minWidth: 0,
    justifySelf: 'end',
    maxWidth: 'min(180px, 100%)',
    display: 'inline-block',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    color: '#9ca3af',
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    textAlign: 'right',
    verticalAlign: 'middle',
  },
  stageActionBox: {
    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
    paddingTop: 18,
    display: 'grid',
    gap: 10,
  },
  stageTextarea: {
    width: '100%',
    minHeight: 78,
    resize: 'vertical',
    borderRadius: 12,
    border: '1px solid rgba(255, 255, 255, 0.12)',
    background: 'rgba(0, 0, 0, 0.25)',
    color: '#f8fafc',
    padding: 10,
    font: 'inherit',
    fontSize: 13,
    lineHeight: 1.4,
    outline: 'none',
  },
  stageActionRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
  },
  stageActionButton: {
    minHeight: 36,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    borderRadius: 999,
    border: '1px solid rgba(255, 255, 255, 0.1)',
    background: 'rgba(255, 255, 255, 0.055)',
    color: '#f8fafc',
    padding: '0 13px',
    cursor: 'pointer',
    fontSize: 13,
  },
  disabledButton: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  stageActionMeta: {
    color: '#94a3b8',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 11,
    lineHeight: 1.35,
    overflowWrap: 'anywhere',
  },
  legacyReportLink: {
    justifySelf: 'start',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    borderRadius: 6,
    border: '1px solid rgba(255, 255, 255, 0.12)',
    color: '#e2e8f0',
    textDecoration: 'none',
    padding: '8px 10px',
    fontSize: 13,
  },

  agentPane: {
    minWidth: 0,
    minHeight: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'linear-gradient(180deg, rgba(13, 17, 23, 0.96), rgba(5, 7, 10, 0.98))',
    padding: 16,
    overflow: 'auto',
    boxShadow: '-16px 0 38px rgba(0, 0, 0, 0.24)',
  },
  agentPaneHeader: {
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
    paddingBottom: 12,
  },
  agentPaneTitle: {
    margin: '4px 0 0',
    color: '#fff',
    fontSize: 17,
    lineHeight: 1.25,
  },
  agentContext: {
    display: 'grid',
    gap: 10,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: 14,
    background: 'rgba(255, 255, 255, 0.045)',
    padding: 10,
  },
  agentContextMotion: {
    display: 'grid',
    gap: 12,
    animation: 'dream-agent-slide 240ms ease-out both',
    willChange: 'opacity, transform',
  },
  agentTextarea: {
    width: '100%',
    minHeight: 146,
    resize: 'vertical',
    borderRadius: 12,
    border: '1px solid rgba(255, 255, 255, 0.12)',
    background: 'rgba(0, 0, 0, 0.28)',
    color: '#f8fafc',
    padding: 10,
    font: 'inherit',
    fontSize: 13,
    lineHeight: 1.4,
    outline: 'none',
  },
  workOrderConstructor: {
    marginTop: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
    background: 'rgba(17, 24, 39, 0.46)',
    paddingTop: 14,
  },
  workOrderLabel: {
    color: '#6b7280',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    lineHeight: 1.35,
  },
  commitWorkOrderButton: {
    minHeight: 38,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 8,
    border: '1px solid rgba(96, 165, 250, 0.48)',
    background: 'rgba(37, 99, 235, 0.88)',
    color: '#fff',
    padding: '0 12px',
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 760,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  },
  klingGate: {
    height: 54,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: 14,
    background: 'rgba(13, 17, 23, 0.72)',
    padding: '0 16px',
    overflow: 'hidden',
  },
  gateStatusGroup: {
    flex: '0 1 auto',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    whiteSpace: 'nowrap',
  },
  gateStatusIcon: {
    width: 32,
    height: 32,
    flex: '0 0 auto',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    border: '1px solid rgba(248, 113, 113, 0.34)',
    background: 'rgba(248, 113, 113, 0.1)',
    color: '#fecaca',
  },
  gateStatusCopy: {
    minWidth: 0,
    display: 'block',
  },
  gateStatusText: {
    display: 'block',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    color: '#f8fafc',
    fontSize: 12,
    fontWeight: 820,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
  gateBadgesRow: {
    flex: '0 1 auto',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'nowrap',
    gap: 8,
    overflowX: 'auto',
    scrollbarWidth: 'none',
  },
  gateMiniBadge: {
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    border: '1px solid',
    borderRadius: 999,
    padding: '0 9px',
    fontSize: 10,
    fontWeight: 760,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    lineHeight: 1,
  },
  deployButton: {
    flex: '0 0 auto',
    maxWidth: 220,
    minHeight: 34,
    borderRadius: 999,
    border: '1px solid rgba(255, 255, 255, 0.14)',
    background: '#1f2937',
    color: '#e5e7eb',
    padding: '0 12px',
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  deployButtonReady: {
    borderColor: 'rgba(52, 211, 153, 0.55)',
    background: 'rgba(21, 128, 61, 0.9)',
    color: '#dcfce7',
    cursor: 'pointer',
  },
  detailBody: {
    minHeight: 0,
    flex: 1,
    display: 'grid',
    gridTemplateColumns: 'minmax(310px, 420px) minmax(0, 1fr)',
  },
  inspector: {
    minHeight: 0,
    overflow: 'auto',
    borderRight: '1px solid rgba(255, 255, 255, 0.1)',
    padding: 20,
  },
  inspectorSection: {
    marginBottom: 16,
  },
  sectionLabel: {
    marginBottom: 8,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    letterSpacing: '0.2em',
    textTransform: 'uppercase',
    color: '#64748b',
  },
  artifactBox: {
    borderRadius: 7,
    border: '1px solid rgba(255, 255, 255, 0.1)',
    background: 'rgba(255, 255, 255, 0.025)',
    padding: 14,
  },
  artifactTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 10,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: '#cbd5e1',
  },
  artifactList: {
    display: 'grid',
    gap: 12,
    margin: 0,
  },
  artifactLabel: {
    color: '#64748b',
    fontSize: 11,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  artifactValue: {
    margin: '4px 0 0',
    color: '#cbd5e1',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 12,
    lineHeight: 1.35,
    overflowWrap: 'anywhere',
  },
  warningBox: {
    marginTop: 16,
    borderRadius: 7,
    border: '1px solid rgba(251, 191, 36, 0.28)',
    background: 'rgba(251, 191, 36, 0.1)',
    padding: 14,
    color: '#fde68a',
    fontSize: 13,
    lineHeight: 1.45,
  },
  reportPane: {
    minWidth: 0,
    minHeight: 0,
    background: '#030608',
  },
  iframe: {
    width: '100%',
    height: '100%',
    border: 0,
    background: '#fff',
  },
  noReport: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    textAlign: 'center',
    color: '#94a3b8',
  },
  noReportTitle: {
    marginTop: 12,
    color: '#f8fafc',
    fontSize: 16,
    fontWeight: 700,
  },
  noReportCopy: {
    maxWidth: 420,
    margin: '8px 0 0',
    fontSize: 14,
    lineHeight: 1.45,
  },
}
