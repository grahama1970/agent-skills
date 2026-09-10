export type RouteStatus =
  | 'MATCHED'
  | 'AMBIGUOUS'
  | 'NO_MATCH'

export type Confidence =
  | 'high'
  | 'medium'
  | 'low'

export type IntegrationStatus =
  | 'READY'
  | 'STALE'
  | 'FAILED'
  | 'NOT_CONFIGURED'

export interface SourceRange {
  file: string
  start_line: number
  end_line: number
  symbol?: string | null
}

export interface DebuggerStop {
  file: string
  line: number
  locals: string[]
  watches: string[]
  proves: string
}

export interface SourceRevealIntent {
  schema: 'explain_project.source_reveal_intent.v1'
  revision: number
  adapter: 'debugger_vscode_bridge'
  operation: 'source_reveal'
  target: SourceRange
  preserve_focus: true
  bridge_required: true
  execute: false
}

export interface DebuggerTargetIntent {
  schema: 'explain_project.debugger_target_intent.v1'
  revision: number
  adapter: 'debugger'
  operation: 'prepare_target'
  target: DebuggerStop
  execution_allowed: false
  explicit_user_control_required: true
}

export interface DiagramHighlightIntent {
  schema: 'explain_project.diagram_highlight_intent.v1'
  revision: number
  source_kind: 'excalidraw' | 'svg'
  source_path: string
  rendered_svg_path?: string | null
  active_node_ids: string[]
  mode: 'display_highlight_only'
  mutation_allowed: false
}

export interface RouteDecision {
  schema: 'explain_project.route_decision.v1'
  status: RouteStatus
  question: string
  scores: Record<string, number>
  matched_feature?: string | null
  candidates: string[]
}

export interface QuestionInput {
  schema: 'explain_project.question_input.v1'
  input_id: string
  source:
    | 'manual'
    | 'live_evidence_replay'
    | 'live_evidence_live'
  text: string
  source_ref?: string | null
  source_fingerprint?: string | null
  provenance:
    | 'manual'
    | 'replay'
    | 'live_fingerprint'
    | 'live_receipt'
}

export interface CockpitState {
  schema: 'explain_project.cockpit_state.v1'
  revision: number

  route: RouteDecision | null

  question: QuestionInput | null

  selection: {
    feature_id: string
    step_id: string
    step_index: number
    step_count: number
  } | null

  teleprompter: {
    revision: number
    title?: string | null
    bullets: string[]
    proof_boundary?: string | null
    confidence?: Confidence | null
    verification:
      | 'not_live_proof'
      | 'debugger_proof_received'
  }

  source: {
    revision: number
    location?: SourceRange | null
    explanation?: string | null
    reveal_intent?: SourceRevealIntent | null
  }

  debugger: {
    revision: number
    target?: DebuggerStop | null
    status:
      | 'NONE'
      | 'TARGET_READY'
      | 'PREPARE_INTENT'
      | 'BLOCKED'
      | 'PROOF_RECEIVED'
    prepare_intent?: DebuggerTargetIntent | null
    proof?: {
      schema: 'explain_project.debugger_proof_reference.v1'
      proof_path: string
      sha256: string
      validated: true
      proves: string
    } | null
  }

  diagram: {
    revision: number
    source_kind?: 'excalidraw' | 'svg' | null
    source_path?: string | null
    rendered_svg_path?: string | null
    node_ids: string[]
    active_node_ids: string[]
    verified_binding: boolean
    highlight_intent?: DiagramHighlightIntent | null
  }

  integration_health: {
    live_evidence: IntegrationStatus
    source_reveal: IntegrationStatus
    debugger_target: IntegrationStatus
    diagram: IntegrationStatus
  }

  adapter_receipts: unknown[]
}

export interface ExplainerSummary {
  feature_id: string
  title: string
  question_family: string
  question: string
  steps: number
  diagram_source?: string | null
  diagram_verified?: boolean
  diagram_nodes?: number
}

export interface BootstrapResponse {
  schema: 'explain_project.bootstrap.v1'
  state: CockpitState
  explainers: ExplainerSummary[]
}

export interface ActionDefinition {
  element_id: string
  app: 'explain-project'
  action: string
  label: string
  description: string
  params?: Record<string, unknown>
  tags?: string[]
}

export type ServiceStatusKind =
  | 'ONLINE'
  | 'DEGRADED'
  | 'OFFLINE'
  | 'NOT_CONFIGURED'

export interface SkillServiceHealth {
  service: 'live_evidence' | 'debugger' | 'surf'
  status: ServiceStatusKind
  detail: string
}

export interface ServiceHealthResponse {
  schema: 'explain_project.service_health.v1'
  services: SkillServiceHealth[]
}
