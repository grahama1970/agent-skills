export type EntityType =
  | 'attack-technique'
  | 'capec'
  | 'control'
  | 'cwe'
  | 'entity'
  | 'standard'
  | string

export interface EvidenceGateTraceEntry {
  gate?: string
  detail?: string
  id?: string
  name?: string
  label?: string
  passed?: boolean
  reason?: string
  [key: string]: unknown
}

export interface EvidenceCaseData {
  case_id?: string | number
  qraKey?: string | number
  evidence_case_version?: {
    case_id?: string | number
    [key: string]: unknown
  }
  verdict?: string
  approval_state?: string
  human_review_state?: string
  artifact?: {
    name?: string
    sha256?: string
    [key: string]: unknown
  }
  bound_artifact?: string
  artifact_hash?: string
  gate_summary?: string
  summary?: string
  evidence_tier?: string
  trace_state?: string
  control_ids?: string[]
  claims?: string[]
  citations?: string[]
  source_traceability?: Record<string, unknown>
  gate_trace?: EvidenceGateTraceEntry[]
  gates_total?: number
  gates_passed?: number
  metadata?: {
    evidence_tier?: string
    gate_summary?: string
    gate_trace?: EvidenceGateTraceEntry[]
    gates_total?: number
    gates_passed?: number
    [key: string]: unknown
  }
  [key: string]: unknown
}
