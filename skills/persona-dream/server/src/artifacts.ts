import { createHash } from 'node:crypto'
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs'
import { relative, resolve, sep } from 'node:path'
import { DreamPathPolicy, dreamContentType } from './paths'

type ArtifactIndexEntry = {
  relative_path: string
  sha256: string
  size_bytes?: number
  media_type?: string
}

type RevisionArtifactIndex = {
  run_id: string
  revision_id: string
  artifacts: Record<string, ArtifactIndexEntry>
}

export type RevisionArtifactRequest = {
  runId: string
  revisionId: string
  artifactId: string
}

export type RevisionArtifactResolution = RevisionArtifactRequest & {
  path: string
  sha256: string
  sizeBytes: number
  contentType: string
}

function validId(value: string): boolean {
  return /^[A-Za-z0-9._-]+$/.test(value)
}

function parseIndex(path: string): RevisionArtifactIndex {
  const value = JSON.parse(readFileSync(path, 'utf8')) as Partial<RevisionArtifactIndex>
  if (!value || typeof value !== 'object' || !value.artifacts || typeof value.artifacts !== 'object') {
    throw new Error('artifact_index_invalid')
  }
  return value as RevisionArtifactIndex
}

function sha256File(path: string): string {
  return `sha256:${createHash('sha256').update(readFileSync(path)).digest('hex')}`
}

function containedPath(root: string, requested: string): string {
  const realRoot = realpathSync(root)
  const real = realpathSync(requested)
  const rel = relative(realRoot, real)
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`) || rel.includes(`${sep}..${sep}`)) {
    throw new Error('artifact_path_escape')
  }
  if (!statSync(real).isFile()) throw new Error('artifact_not_regular_file')
  return real
}

export function resolveRevisionArtifact(
  roots: readonly string[],
  request: RevisionArtifactRequest,
): RevisionArtifactResolution {
  if (![request.runId, request.revisionId, request.artifactId].every(validId)) {
    throw new Error('artifact_identity_invalid')
  }

  const policy = new DreamPathPolicy(roots)
  const candidates = roots
    .map((root) => resolve(root, request.runId))
    .filter((path) => existsSync(path))
    .map((path) => policy.resolveDirectory(path))
  const uniqueCandidates = [...new Set(candidates)]
  if (uniqueCandidates.length === 0) throw new Error('run_not_found')
  if (uniqueCandidates.length !== 1) throw new Error('run_id_ambiguous')

  const runRoot = uniqueCandidates[0]
  const revisionRoot = policy.resolveDirectory(resolve(
    runRoot,
    '.persona-dream',
    'revisions',
    request.revisionId,
  ))
  const indexPath = containedPath(revisionRoot, resolve(revisionRoot, 'revision_artifact_index.json'))
  const index = parseIndex(indexPath)
  if (index.run_id !== request.runId || index.revision_id !== request.revisionId) {
    throw new Error('artifact_index_identity_mismatch')
  }
  const artifact = index.artifacts[request.artifactId]
  if (!artifact) throw new Error('artifact_not_found')
  if (!artifact.relative_path || resolve(revisionRoot, artifact.relative_path) === revisionRoot) {
    throw new Error('artifact_relative_path_invalid')
  }
  const path = containedPath(revisionRoot, resolve(revisionRoot, artifact.relative_path))
  const observedSha256 = sha256File(path)
  if (observedSha256 !== artifact.sha256) throw new Error('artifact_sha256_mismatch')

  return {
    ...request,
    path,
    sha256: observedSha256,
    sizeBytes: statSync(path).size,
    contentType: artifact.media_type || dreamContentType(path),
  }
}
