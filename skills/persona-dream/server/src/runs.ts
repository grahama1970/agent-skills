import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { readdir, stat } from 'node:fs/promises'
import { basename, resolve } from 'node:path'
import type { DreamRunDetailResponse, StoryboardConsumerProjection } from '../../contracts/src/index'
import { hydrateStoryboardConsumer } from './consumerContracts'
import { DreamPathPolicy } from './paths'
import { projectStages } from './stages'

async function listFiles(root: string, maxFiles = 4000): Promise<string[]> {
  const files: string[] = []
  async function visit(dir: string, depth: number): Promise<void> {
    if (depth > 7 || files.length >= maxFiles) return
    const entries = await readdir(dir, { withFileTypes: true }).catch(() => [])
    for (const entry of entries) {
      if (files.length >= maxFiles || entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__pycache__') continue
      const path = resolve(dir, entry.name)
      if (entry.isDirectory()) await visit(path, depth + 1)
      else if (entry.isFile()) files.push(path)
    }
  }
  await visit(root, 0)
  return files
}

function readJson(path: string): Record<string, unknown> | null {
  try { return JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown> } catch { return null }
}

export async function collectRuns(reportRoots: readonly string[], outputRoots: readonly string[]) {
  const runs: Array<Record<string, unknown>> = []
  for (const [source, roots] of [['report', reportRoots], ['output', outputRoots]] as const) {
    for (const root of roots) {
      const entries = await readdir(root, { withFileTypes: true }).catch(() => [])
      for (const entry of entries) {
        if (!entry.isDirectory()) continue
        const runRoot = resolve(root, entry.name)
        const statusPath = resolve(runRoot, 'status.json')
        const validationPath = resolve(runRoot, 'validation.json')
        const manifestPath = resolve(runRoot, 'manifest.json')
        if (![statusPath, validationPath, manifestPath, resolve(runRoot, 'report.html')].some(existsSync)) continue
        const statusDoc = readJson(statusPath)
        const validationDoc = readJson(validationPath)
        const rawStatus = String(validationDoc?.status ?? statusDoc?.status ?? 'UNKNOWN')
        const stats = await Promise.all([statusPath, validationPath, manifestPath].map((path) => stat(path).catch(() => null)))
        const updatedAt = stats.find(Boolean)?.mtime.toISOString() ?? new Date(0).toISOString()
        runs.push({
          id: entry.name,
          title: entry.name.replace(/[-_]+/g, ' '),
          source,
          status: rawStatus,
          runRoot,
          reportPath: existsSync(resolve(runRoot, 'report.html')) ? resolve(runRoot, 'report.html') : undefined,
          reportUrl: existsSync(resolve(runRoot, 'report.html')) ? `/api/projects/dream/report?path=${encodeURIComponent(resolve(runRoot, 'report.html'))}` : undefined,
          statusPath: existsSync(statusPath) ? statusPath : undefined,
          validationPath: existsSync(validationPath) ? validationPath : undefined,
          manifestPath: existsSync(manifestPath) ? manifestPath : undefined,
          klingCalled: false,
          paidCallAuthorized: false,
          updatedAt,
        })
      }
    }
  }
  return runs.sort((a, b) => Date.parse(String(b.updatedAt)) - Date.parse(String(a.updatedAt))).slice(0, 40)
}

export async function buildRunDetail(policy: DreamPathPolicy, requestedRoot: string): Promise<DreamRunDetailResponse> {
  const runRoot = policy.resolveDirectory(requestedRoot)
  const revision = readJson(resolve(runRoot, 'dream_revision_manifest.v1.json'))
  const pointerPath = resolve(runRoot, '.persona-dream', 'state', 'active_revision.json')
  const pointer = readJson(pointerPath)
  const sourceRevisionId = typeof pointer?.revisionId === 'string'
    ? pointer.revisionId
    : typeof revision?.active_revision_id === 'string'
      ? revision.active_revision_id
      : ''
  const localRevisionRoot = sourceRevisionId
    ? resolve(runRoot, '.persona-dream', 'revisions', sourceRevisionId)
    : ''
  const evidenceRoot = localRevisionRoot && existsSync(localRevisionRoot)
    ? policy.resolveDirectory(realpathSync(localRevisionRoot))
    : runRoot
  const files = await listFiles(evidenceRoot)
  const projectedStages = projectStages(evidenceRoot, files, '10', sourceRevisionId || undefined)
  const revisionQualification: DreamRunDetailResponse['revisionQualification'] = sourceRevisionId
    ? {
        state: 'LEGACY_UNQUALIFIED',
        status: 'BLOCKED_REVISION_NOT_QUALIFIED',
        blockers: [
          'BLOCKED_REVISION_QUALIFICATION_RECEIPT_MISSING',
          'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN',
          'BLOCKED_QUEUE_TERMINAL_STATE_UNPROVEN',
        ],
      }
    : {
        state: 'MISSING',
        status: 'BLOCKED_REVISION_NOT_QUALIFIED',
        blockers: ['BLOCKED_ACTIVE_REVISION_MISSING'],
      }
  const stages = projectedStages.map((stage) => {
    if (revisionQualification.state === 'ACTIVE_CONSISTENT' || stage.effectiveState !== 'accepted_current') return stage
    return {
      ...stage,
      status: 'BLOCKED_REVISION_NOT_QUALIFIED',
      failureOrGap: 'The active revision has not passed consumer hydration and Memory-backed revision qualification.',
      acceptance: { ...stage.acceptance, state: 'blocked' as const },
      effectiveState: 'blocked_by_upstream' as const,
      lineage: {
        ...stage.lineage,
        state: 'stale' as const,
        staleReasons: [
          ...stage.lineage.staleReasons,
          { code: 'REVISION_QUALIFICATION_NOT_ACTIVE_CONSISTENT' },
        ],
      },
      repair: {
        ...stage.repair,
        eligible: false,
        reason: 'revision_qualification_transaction_required',
      },
    }
  })
  const earliest = stages.find((stage) => ['missing', 'malformed', 'semantic_invalid', 'accepted_stale', 'blocked_current', 'blocked_stale'].includes(stage.effectiveState))
  const repairEnabled = Boolean(revision?.repair_enabled === true || revision?.pipeline_complete === true)
  const phaseRange = earliest ? stages.filter((stage) => Number(stage.id) >= Number(earliest.id) && Number(stage.id) <= 10).map((stage) => stage.id) : []
  const candidate = earliest && sourceRevisionId
    ? {
        sourceRevisionId,
        earliestRepairPhase: earliest.id,
        selectedThroughPhase: '10',
        phaseRange,
        dedupKey: String(earliest.repair.dedupKey ?? ''),
        enqueueAllowed: repairEnabled && earliest.repair.eligible,
        blockers: repairEnabled ? [] : ['REPAIR_NOT_ENABLED'],
      }
    : undefined
  const runId = basename(runRoot)
  let storyboard: StoryboardConsumerProjection | undefined
  if (sourceRevisionId) {
    const index = readJson(resolve(evidenceRoot, 'revision_artifact_index.json'))
    const artifacts = index?.artifacts && typeof index.artifacts === 'object' && !Array.isArray(index.artifacts)
      ? index.artifacts as Record<string, { relative_path: string; sha256: string; roles: string[] }>
      : null
    const packetEntry = artifacts?.storyboard_packet
    if (artifacts && packetEntry?.relative_path) {
      try {
        const revisionPolicy = new DreamPathPolicy([evidenceRoot])
        const packetPath = revisionPolicy.resolveFile(resolve(evidenceRoot, packetEntry.relative_path))
        const packet = readJson(packetPath)
        if (packet) {
          const hydrated = hydrateStoryboardConsumer(packet, { artifacts })
          const artifactUrl = (artifactId: string) => [
            '/api/projects/dream/runs',
            encodeURIComponent(runId),
            'revisions',
            encodeURIComponent(sourceRevisionId),
            'artifacts',
            encodeURIComponent(artifactId),
          ].join('/')
          storyboard = {
            contract: 'dream_storyboard_workspace_v1',
            revisionId: sourceRevisionId,
            packetArtifactId: 'storyboard_packet',
            packetUrl: artifactUrl('storyboard_packet'),
            panelCount: hydrated.panelCount,
            panels: hydrated.panelIds.map((panelId) => {
              const start = hydrated.frames.find((frame) => frame.panelId === panelId && frame.role === 'start_frame')
              const end = hydrated.frames.find((frame) => frame.panelId === panelId && frame.role === 'end_frame')
              if (!start || !end) throw new Error(`BLOCKED_ASSET_RESOLUTION:${panelId}`)
              return {
                panelId,
                startFrame: { artifactId: start.artifactId, sha256: start.sha256, url: artifactUrl(start.artifactId) },
                endFrame: { artifactId: end.artifactId, sha256: end.sha256, url: artifactUrl(end.artifactId) },
              }
            }),
          }
        }
      } catch {
        storyboard = undefined
      }
    }
  }
  return {
    schemaVersion: 'persona_dream.run_detail.v2',
    status: 'ok',
    mocked: false,
    live: false,
    runRoot,
    stageReportPath: existsSync(resolve(evidenceRoot, 'pipeline_stage_report.json')) ? resolve(evidenceRoot, 'pipeline_stage_report.json') : undefined,
    stages,
    sourceGroupedStages: [],
    runId,
    runKind: revision?.fixture === true ? 'fixture' : revision?.historical === true ? 'historical' : 'active',
    repairEnabled,
    activeRevision: sourceRevisionId ? {
      revisionId: sourceRevisionId,
      manifestSha256: typeof pointer?.revisionManifestSha256 === 'string' ? pointer.revisionManifestSha256 : undefined,
    } : undefined,
    revisionQualification,
    consumers: storyboard ? { storyboard } : undefined,
    earliestIssue: earliest ? {
      phaseId: earliest.id,
      kind: earliest.evidence.state === 'malformed' || earliest.evidence.state === 'semantic_invalid' ? 'malformed' : 'missing',
      reasons: [...earliest.evidence.missingIds, ...earliest.evidence.malformedIds, ...earliest.evidence.semanticInvalidIds],
    } : undefined,
    repairCandidate: candidate,
  }
}
