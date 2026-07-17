import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { basename, relative, resolve } from 'node:path'
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

type ProviderReturnCandidate = {
  revisionId: string
  requestKey: string
  returnRoot: string
  mp4Path: string
  envelope: Record<string, unknown> | null
  ffprobe: Record<string, unknown> | null
  review: Record<string, unknown> | null
  contactSheetPath?: string
  mtimeMs: number
}

function listDirectories(path: string): string[] {
  try {
    return readdirSync(path, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
  } catch {
    return []
  }
}

function collectProviderReturns(runRoot: string): ProviderReturnCandidate[] {
  const revisionsRoot = resolve(runRoot, '.persona-dream', 'revisions')
  const candidates: ProviderReturnCandidate[] = []
  for (const revisionId of listDirectories(revisionsRoot)) {
    const returnsRoot = resolve(revisionsRoot, revisionId, 'phase_11_submit_return', 'provider_return')
    for (const requestKey of listDirectories(returnsRoot)) {
      const returnRoot = resolve(returnsRoot, requestKey)
      const mp4Path = resolve(returnRoot, 'provider_return.mp4')
      if (!existsSync(mp4Path)) continue
      const contactSheetPath = resolve(returnRoot, 'frame_contact_sheet.png')
      candidates.push({
        revisionId,
        requestKey,
        returnRoot,
        mp4Path,
        envelope: readJson(resolve(returnRoot, 'phase11_provider_return_envelope.v1.json')),
        ffprobe: readJson(resolve(returnRoot, 'phase11_download_ffprobe_receipt.v1.json')),
        review: readJson(resolve(returnRoot, 'post_kling_continuity_review_receipt.v1.json')),
        contactSheetPath: existsSync(contactSheetPath) ? contactSheetPath : undefined,
        mtimeMs: statSync(mp4Path).mtimeMs,
      })
    }
  }
  return candidates.sort((left, right) => right.mtimeMs - left.mtimeMs)
}

function pendingRequestGap(runRoot: string, activeRevisionId?: string): string | null {
  if (!activeRevisionId) return null
  const canonical = readJson(resolve(
    runRoot, '.persona-dream', 'revisions', activeRevisionId,
    'phase_11_submit_return', 'canonical', 'phase11_live_request.v1.json',
  ))
  if (!canonical) return null
  const bindings = canonical.approval_bindings as Record<string, unknown> | undefined
  const requestHash = typeof bindings?.request_body_sha256 === 'string' ? bindings.request_body_sha256 : ''
  const missing = Array.isArray(canonical.missing_approval_types) ? canonical.missing_approval_types : []
  if (!requestHash) return null
  return missing.length > 0
    ? `A repaired request ${requestHash} is compiled with zero provider calls and awaits ${missing.length} human hash-bound approvals before one paid submit.`
    : `A compiled request ${requestHash} exists for this revision and has not returned provider media yet.`
}

/**
 * Build the Provider Return stage from real returned provider media.
 *
 * The Phase 01-10 artifact contract never covers post-qualification provider
 * returns, so without this projection the UI "Provider Return" page has no
 * data source even when a returned MP4 exists on disk. Returns from a
 * non-active revision are surfaced with an explicit superseded label instead
 * of being hidden or silently claimed current.
 */
export function buildProviderReturnStage(runRoot: string, activeRevisionId?: string): DreamPhaseProjection | null {
  const candidates = collectProviderReturns(runRoot)
  const gap = pendingRequestGap(runRoot, activeRevisionId)
  if (candidates.length === 0 && !gap) return null
  const active = candidates.find((candidate) => candidate.revisionId === activeRevisionId)
  const chosen = active ?? candidates[0]

  const assetUrl = (path: string) => `/api/projects/dream/asset?path=${encodeURIComponent(path)}`
  const artifacts: DreamArtifactRef[] = []
  const images: DreamPhaseProjection['images'] = []
  let status = 'NOT_EXECUTED'
  let summary = 'No provider return has been received for the active revision.'
  const gaps: string[] = []

  if (chosen) {
    const superseded = chosen.revisionId !== activeRevisionId
    const reviewStatus = typeof chosen.review?.status === 'string' ? chosen.review.status : ''
    const format = (chosen.ffprobe?.ffprobe as Record<string, unknown> | undefined)?.format as Record<string, unknown> | undefined
    const duration = typeof format?.duration === 'string' ? `${format.duration}s` : ''
    const sizeBytes = typeof chosen.ffprobe?.size_bytes === 'number' ? chosen.ffprobe.size_bytes : undefined
    const mp4Sha = typeof chosen.ffprobe?.downloaded_sha256 === 'string' ? chosen.ffprobe.downloaded_sha256 : ''
    status = superseded
      ? 'RETURN_RECEIVED_SUPERSEDED_PRIOR_REVISION'
      : reviewStatus.includes('FAIL')
        ? 'RETURN_RECEIVED_CONTINUITY_FAILED'
        : 'RETURN_RECEIVED'
    summary = [
      `Real provider MP4 returned for request ${chosen.requestKey.slice(0, 16)}… in revision ${chosen.revisionId}`,
      duration && sizeBytes ? `(${duration}, ${sizeBytes.toLocaleString()} bytes${mp4Sha ? `, ${mp4Sha.slice(0, 23)}…` : ''})` : '',
      superseded ? 'This return is bound to a superseded revision and is shown as historical evidence, not as the current deliverable.' : '',
    ].filter(Boolean).join(' ')
    if (reviewStatus.includes('FAIL')) {
      const findings = Array.isArray(chosen.review?.blocking_findings) ? chosen.review.blocking_findings : []
      const codes = findings
        .map((finding) => (finding && typeof finding === 'object' ? String((finding as Record<string, unknown>).code ?? '') : ''))
        .filter(Boolean)
      gaps.push(`Post-provider continuity review failed${codes.length ? `: ${codes.join(', ')}` : ''}.`)
    }
    artifacts.push({ label: relative(runRoot, chosen.mp4Path), path: chosen.mp4Path, kind: 'media', url: assetUrl(chosen.mp4Path) })
    for (const [name, value] of Object.entries({
      'phase11_provider_return_envelope.v1.json': chosen.envelope,
      'phase11_download_ffprobe_receipt.v1.json': chosen.ffprobe,
      'post_kling_continuity_review_receipt.v1.json': chosen.review,
    })) {
      if (!value) continue
      const path = resolve(chosen.returnRoot, name)
      artifacts.push({ label: relative(runRoot, path), path, kind: 'json', url: assetUrl(path) })
    }
    if (chosen.contactSheetPath) {
      images.push({ label: relative(runRoot, chosen.contactSheetPath), path: chosen.contactSheetPath, url: assetUrl(chosen.contactSheetPath) })
    }
  }
  if (gap) gaps.push(gap)

  return {
    id: '11',
    title: 'Provider Return',
    status,
    summary,
    failureOrGap: gaps.length > 0 ? gaps.join(' ') : null,
    artifacts,
    requiredArtifacts: {},
    images,
    acceptance: { state: 'not_evaluated' },
    evidence: {
      state: chosen ? 'present' : 'missing',
      required: [],
      observed: artifacts,
      missingIds: chosen ? [] : ['provider_return_mp4'],
      malformedIds: [],
      semanticInvalidIds: [],
    },
    lineage: {
      state: chosen && chosen.revisionId === activeRevisionId ? 'current' : 'stale',
      activeRevisionId,
      sourceRevisionIds: chosen ? [chosen.revisionId] : [],
      staleReasons: chosen && chosen.revisionId !== activeRevisionId
        ? [{ code: 'PROVIDER_RETURN_BOUND_TO_SUPERSEDED_REVISION', observed: chosen.revisionId }]
        : [],
    },
    effectiveState: chosen && chosen.revisionId === activeRevisionId ? 'accepted_current' : 'accepted_stale',
    repair: { eligible: false, reason: 'provider_return_projection_is_read_only' },
  }
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
