import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import { relative, resolve } from 'node:path'
import { PHASE_ARTIFACTS_CONTRACT } from '../../contracts/src/index'
import { hydrateStoryboardConsumer } from './consumerContracts'
import { validateIdeaLineage } from './ideaLineage'
import { projectStages } from './stages'

type ArtifactIndex = {
  schema: string
  run_id: string
  revision_id: string
  artifacts: Record<string, { relative_path: string; sha256: string; roles: string[] }>
}

async function listFiles(root: string): Promise<string[]> {
  const files: string[] = []
  async function visit(directory: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__pycache__') continue
      const path = resolve(directory, entry.name)
      if (entry.isDirectory()) await visit(path)
      else if (entry.isFile()) files.push(path)
    }
  }
  await visit(root)
  return files
}

function readObject(path: string): Record<string, unknown> {
  const value = JSON.parse(readFileSync(path, 'utf8')) as unknown
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`json_object_required:${path}`)
  return value as Record<string, unknown>
}

function sha256(path: string): string {
  return `sha256:${createHash('sha256').update(readFileSync(path)).digest('hex')}`
}

export async function qualifyRevisionLocally(runId: string, revisionId: string, revisionRoot: string) {
  const indexPath = resolve(revisionRoot, 'revision_artifact_index.json')
  const artifactIndex = readObject(indexPath) as ArtifactIndex
  if (artifactIndex.schema !== 'persona_dream.revision_artifact_index.v1' || artifactIndex.revision_id !== revisionId || artifactIndex.run_id !== runId) {
    throw new Error('BLOCKED_READ_MODEL_REVISION_MISMATCH')
  }
  const humanIdea = validateIdeaLineage(revisionRoot, runId, revisionId)
  const stages = projectStages(revisionRoot, await listFiles(revisionRoot), '10', revisionId)
  const omittedRequiredIds: string[] = []
  const mismatchedRequiredIds: string[] = []
  for (const [phaseId, phase] of Object.entries(PHASE_ARTIFACTS_CONTRACT.phases)) {
    const stage = stages.find((candidate) => candidate.id === phaseId)
    for (const requirement of phase.required_artifacts) {
      const projected = stage?.requiredArtifacts[requirement.artifact_id]
      const indexed = artifactIndex.artifacts[requirement.artifact_id]
      if (!projected || !indexed) {
        omittedRequiredIds.push(requirement.artifact_id)
        continue
      }
      if (relative(revisionRoot, projected.path) !== indexed.relative_path || sha256(projected.path) !== indexed.sha256) {
        mismatchedRequiredIds.push(requirement.artifact_id)
      }
    }
  }
  const nonCurrentPhases = stages.filter((stage) => stage.evidence.state !== 'present').map((stage) => stage.id)
  const readModelPassed = omittedRequiredIds.length === 0 && mismatchedRequiredIds.length === 0 && nonCurrentPhases.length === 0
  const storyboardPath = stages.find((stage) => stage.id === '07')?.requiredArtifacts.storyboard_packet?.path
  if (!storyboardPath) throw new Error('BLOCKED_READ_MODEL_REQUIRED_ARTIFACT_OMITTED:storyboard_packet')
  const storyboard = hydrateStoryboardConsumer(readObject(storyboardPath), artifactIndex, 4)
  const readModelReceipt = {
    schema: 'persona_dream.revision_read_model_validation_receipt.v1',
    status: readModelPassed ? 'PASS_REVISION_READ_MODEL' : 'BLOCKED_REVISION_READ_MODEL',
    run_id: runId,
    revision_id: revisionId,
    required_artifact_ids: Object.values(PHASE_ARTIFACTS_CONTRACT.phases).flatMap((phase) => phase.required_artifacts.map((artifact) => artifact.artifact_id)),
    omitted_required_ids: omittedRequiredIds,
    mismatched_required_ids: mismatchedRequiredIds,
    non_current_phases: nonCurrentPhases,
    mocked: false,
    live: false,
    actual_provider_call_attempts: 0,
  }
  const consumerReceipt = {
    schema: 'persona_dream.revision_consumer_validation_receipt.v1',
    status: 'PASS_REVISION_CONSUMER_HYDRATION',
    run_id: runId,
    revision_id: revisionId,
    storyboard_packet_artifact_id: 'storyboard_packet',
    storyboard_panel_count: storyboard.panelCount,
    accepted_frame_count: storyboard.frames.length,
    resolved_frame_artifact_ids: storyboard.frames.map((frame) => frame.artifactId),
    hardcoded_fallback_used: false,
    human_idea_artifact_id: humanIdea.artifactId,
    idea_id: humanIdea.ideaId,
    idea_sha256: humanIdea.ideaSha256,
    exact_human_idea_text: humanIdea.text,
    mocked: false,
    live: false,
    actual_provider_call_attempts: 0,
  }
  return { readModelReceipt, consumerReceipt, humanIdea }
}
