/**
 * story helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { DreamStage } from '../types'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'

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
