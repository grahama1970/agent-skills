/**
 * phase helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { DreamStage } from '../types'
import { CANONICAL_PHASES } from '../constants'
import { Lock } from 'lucide-react'
import { createMissingStage } from './stage'

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
