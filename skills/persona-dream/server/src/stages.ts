import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { basename, relative } from 'node:path'
import { PHASE_ARTIFACTS_CONTRACT } from '../../contracts/src/index'
import type { DreamArtifactRef, DreamPhaseProjection, PhaseArtifactRequirement } from '../../contracts/src/index'

type PhaseSpec = {
  id: string
  title: string
  summary: string
  required: PhaseArtifactRequirement[]
  matches: RegExp
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export const PHASES: PhaseSpec[] = Object.entries(PHASE_ARTIFACTS_CONTRACT.phases)
  .sort(([left], [right]) => Number(left) - Number(right))
  .map(([id, phase]) => ({
  id,
  title: phase.title,
  summary: phase.summary,
  required: phase.required_artifacts,
  matches: new RegExp([
    ...phase.directory_patterns,
    ...phase.required_artifacts.flatMap((artifact) => [artifact.artifact_id, ...artifact.basenames]),
  ].map(escapeRegExp).join('|'), 'i'),
  }))

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

function requirementMatches(requirement: PhaseArtifactRequirement, path: string): boolean {
  if (requirement.basenames.some((name) => basename(path).toLowerCase() === name.toLowerCase())) return true
  const normalized = requirement.artifact_id.replace(/_/g, '.*')
  return new RegExp(normalized, 'i').test(path)
}

function requirementPresent(requirement: PhaseArtifactRequirement, files: string[]): boolean {
  return files.some((path) => requirementMatches(requirement, path))
}

function requiredArtifact(requirement: PhaseArtifactRequirement, files: string[]): string | undefined {
  return files.find((path) => requirement.basenames.some((name) => basename(path).toLowerCase() === name.toLowerCase()))
    ?? files.find((path) => requirementMatches(requirement, path))
}

function semanticBlockers(requirement: PhaseArtifactRequirement, path: string): string[] {
  if (!requirement.semantic_validator) return []
  const value = readJson(path)
  if (!value) return ['json_object_required']
  if (requirement.semantic_validator === 'storyboard_packet_v1') {
    const panels = Array.isArray(value.panels) ? value.panels : []
    const panelIds = panels.map((panel) => typeof panel === 'object' && panel !== null ? String((panel as Record<string, unknown>).panel_id ?? '') : '')
    return [
      ...(value.schema === requirement.schema ? [] : ['schema']),
      ...(value.accepted === true ? [] : ['accepted']),
      ...(requirement.accepted_statuses?.includes(String(value.status)) ? [] : ['status']),
      ...(panels.length > 0 ? [] : ['panels']),
      ...(value.panel_count === panels.length ? [] : ['panel_count']),
      ...(panelIds.every(Boolean) && new Set(panelIds).size === panels.length ? [] : ['panel_ids']),
    ]
  }
  return [`unknown_semantic_validator:${requirement.semantic_validator}`]
}

export function projectStages(
  runRoot: string,
  files: string[],
  selectedThroughPhase = '10',
  declaredRevisionId?: string,
): DreamPhaseProjection[] {
  const revisionPath = `${runRoot}/dream_revision_manifest.v1.json`
  const revision = existsSync(revisionPath) ? readJson(revisionPath) : null
  const activeRevisionId = declaredRevisionId ?? (typeof revision?.active_revision_id === 'string' ? revision.active_revision_id : undefined)
  let earliestIssue: string | undefined

  return PHASES.map((phase) => {
    const matched = files.filter((path) => phase.matches.test(relative(runRoot, path)))
    const missingIds = phase.required.filter((requirement) => !requirementPresent(requirement, matched)).map((requirement) => requirement.artifact_id)
    const malformedIds = matched
      .filter((path) => path.endsWith('.json') && readJson(path) === null)
      .map((path) => basename(path))
    const semanticInvalidIds = phase.required.flatMap((requirement) => {
      const path = requiredArtifact(requirement, matched)
      if (!path || semanticBlockers(requirement, path).length === 0) return []
      return [requirement.artifact_id]
    })
    const evidenceState = malformedIds.length > 0 ? 'malformed' : missingIds.length > 0 ? 'missing' : semanticInvalidIds.length > 0 ? 'semantic_invalid' : 'present'
    if (!earliestIssue && evidenceState !== 'present') earliestIssue = phase.id
    const blockedByUpstream = Boolean(earliestIssue && earliestIssue !== phase.id)
    const nonImageArtifacts = matched.filter((path) => !/\.(png|jpe?g|webp|gif)$/i.test(path))
    const requiredArtifacts = phase.required
      .map((requirement) => requiredArtifact(requirement, nonImageArtifacts))
      .filter((path): path is string => Boolean(path))
    const artifacts = [...new Set([
      ...requiredArtifacts,
      ...nonImageArtifacts,
    ])]
      .slice(0, 30)
      .map((path) => ({ label: relative(runRoot, path), path, kind: artifactKind(path), url: `/api/projects/dream/asset?path=${encodeURIComponent(path)}` }))
    const requiredArtifactMap = Object.fromEntries(phase.required.flatMap((requirement) => {
      const path = requiredArtifact(requirement, nonImageArtifacts)
      if (!path) return []
      return [[requirement.artifact_id, {
        artifactId: requirement.artifact_id,
        label: relative(runRoot, path),
        path,
        kind: artifactKind(path),
        url: `/api/projects/dream/asset?path=${encodeURIComponent(path)}`,
      }]]
    }))
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
          : evidenceState === 'semantic_invalid'
            ? 'semantic_invalid'
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
      failureOrGap: evidenceState === 'present' ? null : `Required evidence is not current: ${[...missingIds, ...malformedIds, ...semanticInvalidIds].join(', ')}`,
      artifacts,
      requiredArtifacts: requiredArtifactMap,
      images,
      acceptance: { state: evidenceState === 'present' ? 'accepted' : 'not_evaluated' },
      evidence: { state: evidenceState, required: phase.required.map((requirement) => requirement.artifact_id), observed: artifacts, missingIds, malformedIds, semanticInvalidIds },
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
