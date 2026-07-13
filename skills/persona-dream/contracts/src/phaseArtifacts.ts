import { readFileSync } from 'node:fs'

export type PhaseArtifactRequirement = {
  artifact_id: string
  basenames: string[]
  kind: 'json' | 'media' | 'other'
  schema?: string
  accepted_statuses?: string[]
  semantic_validator?: string
  consumer_contract?: string
  ui_priority: 'required' | 'optional'
}

export type PhaseArtifactContract = {
  title: string
  summary: string
  directory_patterns: string[]
  required_artifacts: PhaseArtifactRequirement[]
  invalidates: string[]
}

export type PersonaDreamPhaseArtifactsContract = {
  schema: 'persona_dream.phase_artifacts.v1'
  selected_through_phase: string
  phases: Record<string, PhaseArtifactContract>
}

const contractUrl = new URL('../persona_dream_phase_artifacts.v1.json', import.meta.url)

export function loadPhaseArtifactsContract(): PersonaDreamPhaseArtifactsContract {
  const contract = JSON.parse(readFileSync(contractUrl, 'utf8')) as PersonaDreamPhaseArtifactsContract
  if (contract.schema !== 'persona_dream.phase_artifacts.v1') {
    throw new Error(`unsupported_phase_artifacts_contract:${contract.schema}`)
  }
  return contract
}

export const PHASE_ARTIFACTS_CONTRACT = loadPhaseArtifactsContract()
