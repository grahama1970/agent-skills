/**
 * Shared types for the Dream workspace.
 *
 * Extracted from DreamWorkspace.tsx, which had grown to 14,767 lines with 173
 * top-level declarations in one module. Types move first because nothing
 * depends on them at runtime, so the split is verifiable by typecheck alone.
 */
export type DreamRun = {
  id: string
  title: string
  source: 'output' | 'report'
  status: string
  runRoot: string
  reportPath?: string
  reportUrl?: string
  statusPath?: string
  validationPath?: string
  manifestPath?: string
  klingCalled: boolean
  paidCallAuthorized: boolean
  updatedAt: string
}

export type DreamRunsResponse = {
  status: string
  mocked: boolean
  live: boolean
  sourceRoots: string[]
  runs: DreamRun[]
  error?: string
}

export type DreamStage = {
  id: string
  title: string
  status: string
  summary: string
  failureOrGap?: string | null
  artifacts: Array<{ label: string; path: string; kind: string }>
  requiredArtifacts?: Record<string, { artifactId?: string; label: string; path: string; kind: string; url?: string; sha256?: string }>
  images: Array<{ label: string; path: string; url: string }>
}

export type RevisionQualification = {
  state: 'MISSING' | 'LEGACY_UNQUALIFIED' | 'ACTIVE_CONSISTENT'
  status: 'BLOCKED_REVISION_NOT_QUALIFIED' | 'PASS_PERSONA_DREAM_SELF_HEAL_ACTIVE_REVISION'
  blockers: string[]
}

export type HumanIdeaProjection = {
  contract: 'dream_human_idea_v1'
  artifactId: 'human_idea'
  ideaId: string
  ideaSha256: string
  text: string
  source: 'explicit_human'
  createdAt: string
  runId: string
  revisionId: string
  lineageManifestSha256: string
  phaseBindingCount: 10
}

export type StoryboardFrameProjection = {
  artifactId: string
  sha256: string
  url: string
}

export type StoryboardPanelProjection = {
  panelId: string
  startFrame: StoryboardFrameProjection
  endFrame: StoryboardFrameProjection
}

export type StoryboardConsumerProjection = {
  contract: 'dream_storyboard_workspace_v1'
  revisionId: string
  packetArtifactId: 'storyboard_packet'
  packetUrl: string
  panelCount: number
  panels: StoryboardPanelProjection[]
}

export type ResearchMemoryResult = {
  title: string
  url: string
  mediaUrl?: string
  snippet: string
  mediaType?: string
  score?: number
  memoryKey?: string
}

export type MemoryConnectionSignal = {
  id: string
  label: string
  tomKind: string
  color: string
  glow: string
}

export type TraceNodeKind = 'idea' | 'memory' | 'media' | 'person' | 'object' | 'place' | 'audio' | 'video'

export type TraceGraphNode = {
  id: string
  label: string
  kind: TraceNodeKind
  hop: 0 | 1 | 2 | 3
  color: string
  radius: number
  thumbnailUrl?: string
  mediaUrl?: string
  tom_state_type?: string
  tom_tags?: string[]
  source_ref?: string
}

export type TraceGraphLink = {
  id: string
  source: string
  target: string
  label: string
  hop: 1 | 2 | 3
  color: string
  relationship_type?: string
  tom_tags?: string[]
  confidence?: number
}

export type TraceGraph = {
  rootId: string
  title: string
  source: 'card-derived' | 'memory-live' | 'memory-tom' | 'mixed'
  memoryKey?: string
  memoryEndpoint?: string
  nodes: TraceGraphNode[]
  links: TraceGraphLink[]
}

export type Phase02MediaGate = {
  status: 'PASS' | 'MISSING'
  describedCount: number
  requiredCount: number
  personaEdgeCount: number
  tomEdgeCount: number
}

export type TraceAnchorRect = {
  left: number
  top: number
  width: number
  height: number
}

export type DreamRunDetailResponse = {
  status: string
  mocked: boolean
  live: boolean
  runRoot: string
  stageReportPath?: string
  stages: DreamStage[]
  revisionQualification?: RevisionQualification
  consumers?: { humanIdea?: HumanIdeaProjection; storyboard?: StoryboardConsumerProjection }
  error?: string
}

export type StatusTone = 'pass' | 'blocked' | 'dry' | 'unknown'

export type StageAction = 'rerun' | 'edit' | 'ask-agent'

export type MediaLockFrame = {
  id: string
  panelId: string
  role: string
  path: string
  url: string
  sha256: string
  status: string
  identityStatus: string
  acceptedAt: string
  timeLabel: string
}

export type DreamArtifact = DreamStage['artifacts'][number]

export type LoadedVideoArtifact = {
  role: string
  artifact: DreamArtifact
  payload: Record<string, unknown> | null
  error?: string
}

export type StoryMatrixRow = {
  id: string
  name: string
  objects: string
  environment: string
  dynamics: string
  note: string
  isComplete: boolean
}

export type ContactSheetDecision = {
  required: boolean
  kind: 'character' | 'prop' | 'environment' | 'prompt_only'
  status: 'existing_or_required' | 'missing' | 'not_needed'
  send_to_kling: boolean
  priority: 'required' | 'recommended' | 'conditional' | 'prompt_only'
  rationale: string
}

export type StoryWriterOption = {
  id: string
  label: string
  description: string
}

export type CrewPersonaOption = {
  id: string
  label: string
  description: string
  source: 'personas' | 'persona_memory'
  roles: string[]
  sourcePaths: string[]
  thumbnailPath?: string
  thumbnailConfidence?: string
}

export type CrewRole = 'producer' | 'scriptwriter' | 'director'

export type LinkedStoryAsset = {
  id: string
  title: string
  url: string
  description?: string
  source?: string
  memoryKey?: string
  mediaType?: string
}

export type StoryPromptPayload = {
  schema: 'dream.story.prompt_payload.v1'
  rationale: {
    purpose: string
    consumer: string
    why_this_matters: string
    input: string[]
    output: string
    last_reviewed: string
  }
  metadata: {
    phase: '02'
    timestamp: string
    gate_state: string
  }
  model: {
    provider: 'tau'
    model: 'gpt-5.5'
    reasoning_effort: 'medium'
    temperature: number
  }
  task: {
    kind: string
    panel_count: number
    target_duration_seconds: number
    target_story_length_words: { min: number; max: number }
    output_format: 'strict_json'
  }
  generation_directives: Record<string, unknown>
  source_context: Record<string, unknown>
  asset_policy: Record<string, unknown>
  context: {
    core_idea: string
    thematic_pivot: string
    location: string
    environment: string
    interaction_rows: StoryMatrixRow[]
    linked_assets: LinkedStoryAsset[]
  }
  author_profile: {
    persona_id: string | null
    persona: string | null
    persona_context: string | null
    creativity_index: number
  }
  response_contract: Record<string, unknown>
  output_contract: Record<string, unknown>
  validation: {
    deterministic_checks: string[]
    invalid_if: string[]
  }
  example: Record<string, unknown>
  messages: Array<{ role: 'system' | 'user'; content: string }>
}

export type ScriptCoverageStatus = 'verified' | 'failed' | 'pending'

export type ZipFileEntry = {
  name: string
  data: Uint8Array
}

export type ContactSheetRequirementAsset = {
  id: string
  url: string
  label: string
  entity: string
  entityType: string
}

export type ContactSheetDisplayAsset = {
  id: string
  url: string
  label: string
  entity?: string
  entityType?: string
}


/**
 * Minimal structural stand-in for d3's SimulationNodeDatum.
 *
 * deps.d.ts declares 'd3' as an untyped ambient module, so d3's own type
 * namespace is not reliably available -- whether it resolves depends on which
 * of the shim or @types/d3 wins, which differed between modules. Only these
 * fields are used by the force layout here, so they are declared explicitly
 * rather than left to ambient resolution.
 */
export type SimulationNodeDatum = {
  index?: number
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}


/** Minimal stand-in for d3's ZoomTransform; see SimulationNodeDatum above. */
export type ZoomTransform = { k: number; x: number; y: number }


/** Minimal stand-in for d3's SimulationLinkDatum; see SimulationNodeDatum. */
export type SimulationLinkDatum<T> = { source: T | string | number; target: T | string | number; index?: number }


/**
 * One row of the provider-contract panel table.
 *
 * Two `.map()` branches build these with different shapes, so inference produced
 * a union whose members lacked each other's fields. Declaring the row once makes
 * the optional members explicit instead of an accident of which branch ran.
 */
export type ProviderContractPanelRow = {
  panelId: string
  start?: Record<string, unknown>
  end?: Record<string, unknown>
  duration?: unknown
  selected: boolean
  sourceEvidence?: Record<string, unknown> | null
  distillation?: Record<string, unknown> | null
  dialogue?: Record<string, unknown>[]
  submittedPrompt?: Record<string, unknown> | null
  sourceShot?: Record<string, unknown> | null
  lookLock?: Record<string, unknown> | null
  panelRequestJson: string
  panelSummary: string
}
