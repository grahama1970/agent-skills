import { createHash } from 'node:crypto'
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs'
import { relative, resolve, sep } from 'node:path'
import type { HumanIdeaProjection } from '../../contracts/src/index'

type JsonRecord = Record<string, unknown>
type ArtifactEntry = { relative_path?: string; sha256?: string; phase_id?: string }

const EXPECTED_PHASE_IDS = Array.from({ length: 10 }, (_, index) => String(index + 1).padStart(2, '0'))

function record(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : null
}

function readJson(path: string): JsonRecord {
  const value = JSON.parse(readFileSync(path, 'utf8')) as unknown
  const object = record(value)
  if (!object) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
  return object
}

function canonicalText(value: string): string {
  return value.normalize('NFC').replace(/\s+/g, ' ').trim()
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as JsonRecord)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(',')}}`
  }
  return JSON.stringify(value)
}

function sha256Bytes(value: string | Buffer): string {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`
}

function sha256File(path: string): string {
  return sha256Bytes(readFileSync(path))
}

function ideaSha256(text: string): string {
  return sha256Bytes(Buffer.from(canonicalText(text), 'utf8'))
}

function ideaId(text: string): string {
  return `pd_idea_${ideaSha256(text).slice('sha256:'.length, 'sha256:'.length + 32)}`
}

function containedFile(root: string, requested: string): string {
  const realRoot = realpathSync(root)
  const real = realpathSync(requested)
  const rel = relative(realRoot, real)
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`) || rel.includes(`${sep}..${sep}`)) {
    throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
  }
  if (!statSync(real).isFile()) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
  return real
}

function artifactFile(
  revisionRoot: string,
  artifacts: Record<string, ArtifactEntry>,
  artifactId: string,
): { path: string; sha256: string; phaseId: string } {
  const entry = artifacts[artifactId]
  const relativePath = String(entry?.relative_path ?? '')
  const expectedSha256 = String(entry?.sha256 ?? '')
  if (!entry || !relativePath || !/^sha256:[a-f0-9]{64}$/.test(expectedSha256)) {
    throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
  }
  const path = containedFile(revisionRoot, resolve(revisionRoot, relativePath))
  if (sha256File(path) !== expectedSha256) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
  return { path, sha256: expectedSha256, phaseId: String(entry.phase_id ?? '') }
}

function bindingSha256(binding: JsonRecord): string {
  const unsigned = Object.fromEntries(Object.entries(binding).filter(([key]) => key !== 'binding_sha256'))
  return sha256Bytes(stableJson(unsigned))
}

export function validateIdeaLineage(
  revisionRoot: string,
  runId: string,
  revisionId: string,
): HumanIdeaProjection {
  try {
    const index = readJson(resolve(revisionRoot, 'revision_artifact_index.json'))
    const artifactsRaw = record(index.artifacts)
    if (!artifactsRaw) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
    const artifacts = artifactsRaw as Record<string, ArtifactEntry>

    const humanRef = artifactFile(revisionRoot, artifacts, 'human_idea')
    const manifestRef = artifactFile(revisionRoot, artifacts, 'idea_lineage_manifest')
    const human = readJson(humanRef.path)
    const text = canonicalText(String(human.text ?? ''))
    const expectedIdeaSha256 = ideaSha256(text)
    const expectedIdeaId = ideaId(text)
    if (
      human.schema !== 'persona_dream.human_idea.v1'
      || human.source !== 'explicit_human'
      || human.run_id !== runId
      || human.revision_id !== revisionId
      || human.idea_id !== expectedIdeaId
      || human.idea_sha256 !== expectedIdeaSha256
    ) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')

    const requestRef = artifactFile(revisionRoot, artifacts, 'dream_request')
    const request = readJson(requestRef.path)
    if (
      request.run_id !== runId
      || request.write_memory !== true
      || request.idea_id !== expectedIdeaId
      || request.idea_sha256 !== expectedIdeaSha256
      || canonicalText(String(request.about ?? '')) !== text
    ) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')

    const manifest = readJson(manifestRef.path)
    const bindings = record(manifest.phase_bindings)
    if (
      manifest.schema !== 'persona_dream.phase_idea_lineage_manifest.v1'
      || manifest.status !== 'PASS_PHASE_IDEA_LINEAGE'
      || manifest.run_id !== runId
      || manifest.revision_id !== revisionId
      || manifest.idea_id !== expectedIdeaId
      || manifest.idea_sha256 !== expectedIdeaSha256
      || manifest.phase_binding_count !== 10
      || !bindings
      || Object.keys(bindings).sort().join(',') !== EXPECTED_PHASE_IDS.join(',')
    ) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')

    let previous: string | null = null
    const bindingHashes: string[] = []
    for (const phaseId of EXPECTED_PHASE_IDS) {
      const ref = record(bindings[phaseId])
      if (!ref) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
      const relativePath = String(ref.relative_path ?? '')
      const path = containedFile(revisionRoot, resolve(revisionRoot, relativePath))
      if (sha256File(path) !== ref.sha256) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
      const binding = readJson(path)
      const observedBindingSha256 = bindingSha256(binding)
      if (
        binding.schema !== 'persona_dream.phase_idea_binding.v1'
        || binding.status !== 'PASS_PHASE_IDEA_BOUND'
        || binding.run_id !== runId
        || binding.revision_id !== revisionId
        || binding.phase_id !== phaseId
        || binding.idea_id !== expectedIdeaId
        || binding.idea_sha256 !== expectedIdeaSha256
        || binding.previous_phase_binding_sha256 !== previous
        || binding.binding_sha256 !== observedBindingSha256
        || ref.binding_sha256 !== observedBindingSha256
      ) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
      const artifactHashes = record(binding.required_artifact_hashes)
      if (!artifactHashes || Object.keys(artifactHashes).length === 0) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
      for (const [artifactId, expectedHash] of Object.entries(artifactHashes)) {
        const observed = artifactFile(revisionRoot, artifacts, artifactId)
        if (observed.phaseId !== phaseId || observed.sha256 !== expectedHash) {
          throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
        }
      }
      bindingHashes.push(observedBindingSha256)
      previous = observedBindingSha256
    }

    const expectedChain = sha256Bytes(stableJson(bindingHashes))
    if (manifest.lineage_chain_sha256 !== expectedChain) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')

    const story = readJson(artifactFile(revisionRoot, artifacts, 'story_contract').path)
    if (
      story.idea_id !== expectedIdeaId
      || story.idea_sha256 !== expectedIdeaSha256
      || !canonicalText(String(story.story ?? story.seed ?? '')).includes(text)
    ) throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')

    const crew = readJson(artifactFile(revisionRoot, artifacts, 'crew_contract').path)
    const sourceContext = record(crew.source_context)
    if (canonicalText(String(sourceContext?.core_idea ?? '')) !== text) {
      throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
    }

    return {
      contract: 'dream_human_idea_v1',
      artifactId: 'human_idea',
      ideaId: expectedIdeaId,
      ideaSha256: expectedIdeaSha256,
      text,
      source: 'explicit_human',
      createdAt: String(human.created_at ?? ''),
      runId,
      revisionId,
      lineageManifestSha256: manifestRef.sha256,
      phaseBindingCount: 10,
    }
  } catch (error) {
    if (error instanceof Error && error.message === 'BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH') throw error
    throw new Error('BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')
  }
}
