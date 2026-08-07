/**
 * persona helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { CrewPersonaOption, CrewRole, LinkedStoryAsset, ResearchMemoryResult } from '../types'
import { scoreCrewPersona } from './crew'
import { storyContractSummaryFromDraft } from './story'

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

export async function loadCrewPersonaCandidates(): Promise<CrewPersonaOption[]> {
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

export function roleFitCandidates(role: CrewRole, candidates: CrewPersonaOption[], avoid: string[] = []): CrewPersonaOption[] {
  return candidates
    .filter((candidate) => !avoid.includes(candidate.id))
    .map((candidate) => ({ candidate, score: scoreCrewPersona(role, candidate) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.candidate.label.localeCompare(b.candidate.label))
    .map((item) => item.candidate)
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
