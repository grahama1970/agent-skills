/**
 * script helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { LinkedStoryAsset, Phase02MediaGate, ResearchMemoryResult, ScriptCoverageStatus } from '../types'
import { phase02RequiredMediaKeys, phase02RequiredTextKeys } from '../constants'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import { parseDreamJson } from './dream'
import { memoryByKeysDocuments } from './graph'
import { readableMemoryText } from './memory'
import { storyContractSummaryFromDraft } from './story'

export function storyAssetDescriptionFromResult(result: ResearchMemoryResult): string {
  const snippet = (result.snippet || '').replace(/\s+/g, ' ').trim()
  if (!snippet) return ''
  const readable = readableMemoryText(snippet)
  if (readable && !/^\s*[{\[]/.test(readable)) return readable
  const descriptionMatch = snippet.match(/\bDescription\s*:?\s*(.+?)(?:\s+(?:Aliases|Title|Persona|Source|Tags|Path|Record|Theory of mind|Live story summary)\b|$)/i)
  if (descriptionMatch?.[1]) return descriptionMatch[1].trim()
  return snippet
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

export function distinctAssetDescription(asset: LinkedStoryAsset): string | null {
  const title = asset.title.replace(/\s+/g, ' ').trim().toLowerCase()
  const description = (asset.description ?? '').replace(/\s+/g, ' ').trim()
  const normalizedDescription = description.toLowerCase()
  if (!description || title === normalizedDescription || title.includes(normalizedDescription) || normalizedDescription.includes(title)) return null
  return description
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

export function hasLiveDescriptionReceipt(doc: Record<string, unknown> | null | undefined): boolean {
  if (!doc) return false
  const receipt = doc.description_receipt && typeof doc.description_receipt === 'object'
    ? doc.description_receipt as Record<string, unknown>
    : null
  const hasDescription = [doc.media_description, doc.vlm_description, doc.audio_caption, doc.text_summary, doc.story_prompt_summary, doc.description]
    .some((value) => value != null && String(value).trim().length > 0)
  return hasDescription && doc.description_status === 'READY' && receipt?.mocked === false && receipt?.live === true
}

export async function loadPhase02MediaGate(): Promise<Phase02MediaGate> {
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
