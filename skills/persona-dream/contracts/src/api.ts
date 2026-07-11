export type AcceptanceState = 'accepted' | 'blocked' | 'not_evaluated'
export type EvidenceState = 'present' | 'missing' | 'malformed'
export type LineageState = 'current' | 'stale' | 'unknown'

export type DreamArtifactRef = {
  label: string
  path: string
  kind: 'json' | 'markdown' | 'text' | 'html' | 'media' | 'other'
}

export type DreamImageRef = {
  label: string
  path: string
  url: string
}

export type DreamPhaseProjection = {
  id: string
  title: string
  status: string
  summary: string
  failureOrGap: string | null
  artifacts: DreamArtifactRef[]
  images: DreamImageRef[]
  acceptance: { state: AcceptanceState; rawStatus?: string }
  evidence: {
    state: EvidenceState
    required: string[]
    observed: DreamArtifactRef[]
    missingIds: string[]
    malformedIds: string[]
  }
  lineage: {
    state: LineageState
    activeRevisionId?: string
    artifactRevisionId?: string
    sourceRevisionIds: string[]
    staleReasons: Array<{ code: string; expected?: string; observed?: string }>
  }
  effectiveState:
    | 'accepted_current'
    | 'accepted_stale'
    | 'blocked_current'
    | 'blocked_stale'
    | 'missing'
    | 'malformed'
    | 'unknown'
    | 'blocked_by_upstream'
  repair: {
    eligible: boolean
    reason?: string
    earliestRepairPhase?: string
    dedupKey?: string
    activeWorkOrderId?: string
  }
}

export type DreamRunDetailResponse = {
  schemaVersion: 'persona_dream.run_detail.v2'
  status: string
  mocked: false
  live: false
  runRoot: string
  stageReportPath?: string
  stages: DreamPhaseProjection[]
  sourceGroupedStages: unknown[]
  runId: string
  runKind: 'active' | 'historical' | 'fixture'
  repairEnabled: boolean
  activeRevision?: {
    revisionId: string
    manifestSha256?: string
  }
  earliestIssue?: {
    phaseId: string
    kind: 'missing' | 'malformed' | 'stale' | 'blocked'
    reasons: string[]
  }
  repairCandidate?: {
    sourceRevisionId: string
    earliestRepairPhase: string
    selectedThroughPhase: string
    phaseRange: string[]
    dedupKey: string
    enqueueAllowed: boolean
    blockers: string[]
  }
}

export type PersonaDreamRepairWorkOrder = {
  schemaVersion: 'persona_dream.repair_work_order.v1'
  workOrderId: string
  dedupKey: string
  runId: string
  runRoot: string
  sourceRevisionId: string
  targetRevisionId: string
  createdAt: string
  detection: {
    earliestStalePhase: string
    selectedThroughPhase: string
    phaseRange: string[]
    reasons: Array<{ phaseId: string; code: string }>
  }
  policy: {
    maxAttemptsPerPhase: 3
    forbiddenSideEffects: string[]
    stopBeforePhase: '11'
  }
  status: 'REQUESTED'
}
