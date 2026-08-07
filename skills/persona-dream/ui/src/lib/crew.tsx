/**
 * crew helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { CrewPersonaOption, CrewRole } from '../types'
import { crewGateMatchTerms, crewMissingEvidenceFields } from '../constants'
import { storyContractSummaryFromDraft } from './story'

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
