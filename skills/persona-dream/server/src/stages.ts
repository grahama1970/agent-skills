import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { basename, relative } from 'node:path'
import type { DreamArtifactRef, DreamPhaseProjection } from '../../contracts/src/index'

type PhaseSpec = {
  id: string
  title: string
  summary: string
  required: string[]
  matches: RegExp
}

export const PHASES: PhaseSpec[] = [
  { id: '01', title: 'Idea and Memory Residue', summary: 'Grounded dream request and selected memory residue.', required: ['dream_request', 'residue_links'], matches: /dream_request|residue_links|dream_packet/i },
  { id: '02', title: 'Story', summary: 'Accepted story and entity contracts.', required: ['story_contract'], matches: /story_contract|dream_story|character_scene_bible|visual_entities/i },
  { id: '03', title: 'Crew', summary: 'Producer, writer, director, and reviewer authority contract.', required: ['crew_contract', 'crew_gate_receipt'], matches: /phase_03|crew_contract|crew_prompt|validate_crew|producer|script_writer|director/i },
  { id: '04', title: 'Contact Sheets', summary: 'Accepted character, prop, and environment reference sheets.', required: ['contact_sheet_requirements', 'contact_sheet_manifest', 'contact_sheet_gate_receipt'], matches: /phase_04|contact_sheet|reference_sheet|chosen_reference/i },
  { id: '05', title: 'Voices', summary: 'Voice references and audition evidence.', required: ['voice_evidence'], matches: /phase_05|voice|tts|audio|wav|waveform/i },
  { id: '06', title: 'Script', summary: 'Timed script and dialogue/action evidence.', required: ['script_contract'], matches: /phase_06|script_contract|timed_transcript|dialogue/i },
  { id: '07', title: 'Storyboard', summary: 'Reviewed storyboard panels and frame evidence.', required: ['storyboard_packet'], matches: /phase_07|storyboard/i },
  { id: '08', title: 'Media Lock', summary: 'Accepted locked provider-facing media.', required: ['media_lock'], matches: /phase_08|media_lock|accepted_frame/i },
  { id: '09', title: 'Video Provider', summary: 'Provider selection and scene packet.', required: ['video_provider_scorecard', 'provider_final_gate'], matches: /phase_09|video_provider|provider_scorecard|provider_final_gate|kling_scene_packet/i },
  { id: '10', title: 'Provider Distillation', summary: 'Per-panel provider payload distillation and dry-run contract.', required: ['panel_distillation_contract', 'provider_schema_receipt'], matches: /phase_10|panel_distillation|provider_schema_receipt|final_provider_payload/i },
]

function readJson(path: string): Record<string, unknown> | null {
  try { return JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown> } catch { return null }
}

function artifactKind(path: string): DreamArtifactRef['kind'] {
  if (path.endsWith('.json')) return 'json'
  if (path.endsWith('.md')) return 'markdown'
  if (path.endsWith('.txt')) return 'text'
  if (path.endsWith('.html')) return 'html'
  if (/\.(png|jpe?g|webp|gif|wav|mp3|mp4)$/i.test(path)) return 'media'
  return 'other'
}

function requirementPresent(requirement: string, files: string[]): boolean {
  const normalized = requirement.replace(/_/g, '.*')
  return files.some((path) => new RegExp(normalized, 'i').test(path))
}

export function projectStages(runRoot: string, files: string[], selectedThroughPhase = '10'): DreamPhaseProjection[] {
  const revisionPath = `${runRoot}/dream_revision_manifest.v1.json`
  const revision = existsSync(revisionPath) ? readJson(revisionPath) : null
  const activeRevisionId = typeof revision?.active_revision_id === 'string' ? revision.active_revision_id : undefined
  let earliestIssue: string | undefined

  return PHASES.map((phase) => {
    const matched = files.filter((path) => phase.matches.test(relative(runRoot, path)))
    const missingIds = phase.required.filter((id) => !requirementPresent(id, matched))
    const malformedIds = matched
      .filter((path) => path.endsWith('.json') && readJson(path) === null)
      .map((path) => basename(path))
    const evidenceState = malformedIds.length > 0 ? 'malformed' : missingIds.length > 0 ? 'missing' : 'present'
    if (!earliestIssue && evidenceState !== 'present') earliestIssue = phase.id
    const blockedByUpstream = Boolean(earliestIssue && earliestIssue !== phase.id)
    const artifacts = matched
      .filter((path) => !/\.(png|jpe?g|webp|gif)$/i.test(path))
      .slice(0, 30)
      .map((path) => ({ label: relative(runRoot, path), path, kind: artifactKind(path) }))
    const images = matched
      .filter((path) => /\.(png|jpe?g|webp|gif)$/i.test(path))
      .slice(0, 20)
      .map((path) => ({ label: relative(runRoot, path), path, url: `/api/projects/dream/asset?path=${encodeURIComponent(path)}` }))
    const effectiveState = blockedByUpstream
      ? 'blocked_by_upstream'
      : evidenceState === 'missing'
        ? 'missing'
        : evidenceState === 'malformed'
          ? 'malformed'
          : activeRevisionId
            ? 'accepted_current'
            : 'unknown'
    const repairEligible = Boolean(activeRevisionId && earliestIssue === phase.id && Number(phase.id) <= Number(selectedThroughPhase))
    const dedupKey = repairEligible
      ? createHash('sha256').update(`${basename(runRoot)}\0${activeRevisionId}\0${phase.id}`).digest('hex')
      : undefined

    return {
      id: phase.id,
      title: phase.title,
      status: effectiveState === 'accepted_current' ? 'EVIDENCE_FOUND' : effectiveState.toUpperCase(),
      summary: phase.summary,
      failureOrGap: evidenceState === 'present' ? null : `Required evidence missing or malformed: ${[...missingIds, ...malformedIds].join(', ')}`,
      artifacts,
      images,
      acceptance: { state: evidenceState === 'present' ? 'accepted' : 'not_evaluated' },
      evidence: { state: evidenceState, required: phase.required, observed: artifacts, missingIds, malformedIds },
      lineage: {
        state: activeRevisionId ? 'current' : 'unknown',
        activeRevisionId,
        sourceRevisionIds: [],
        staleReasons: activeRevisionId ? [] : [{ code: 'REVISION_LINEAGE_NOT_DECLARED' }],
      },
      effectiveState,
      repair: {
        eligible: repairEligible,
        reason: repairEligible ? 'earliest_issue_in_repair_enabled_revision' : activeRevisionId ? 'blocked_by_earlier_issue_or_out_of_scope' : 'revision_state_missing',
        earliestRepairPhase: earliestIssue,
        dedupKey,
      },
    }
  })
}
