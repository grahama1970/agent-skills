import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import test from 'node:test'
import { resolveRevisionArtifact } from '../src/artifacts'

function sha256(value: Buffer | string): string {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`
}

test('revision artifact resolves by stable identity and verifies bytes', () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-artifact-'))
  const reports = resolve(root, 'reports')
  const runId = 'pipeline-complete'
  const revisionId = 'rev_test'
  const revisionRoot = resolve(reports, runId, '.persona-dream', 'revisions', revisionId)
  const relativePath = 'phase_07/generated_storyboard_frames/sb_001_start_frame.png'
  const bytes = Buffer.from('real-frame-bytes')
  mkdirSync(resolve(revisionRoot, 'phase_07', 'generated_storyboard_frames'), { recursive: true })
  writeFileSync(resolve(revisionRoot, relativePath), bytes)
  writeFileSync(resolve(revisionRoot, 'revision_artifact_index.json'), JSON.stringify({
    run_id: runId,
    revision_id: revisionId,
    artifacts: {
      'sb_001.start_frame': {
        relative_path: relativePath,
        sha256: sha256(bytes),
        media_type: 'image/png',
      },
    },
  }))

  const artifact = resolveRevisionArtifact([reports], {
    runId,
    revisionId,
    artifactId: 'sb_001.start_frame',
  })
  assert.equal(artifact.sha256, sha256(bytes))
  assert.equal(artifact.contentType, 'image/png')
  assert.equal(artifact.sizeBytes, bytes.length)

  writeFileSync(resolve(revisionRoot, relativePath), 'tampered')
  assert.throws(() => resolveRevisionArtifact([reports], {
    runId,
    revisionId,
    artifactId: 'sb_001.start_frame',
  }), /artifact_sha256_mismatch/)
  rmSync(root, { recursive: true, force: true })
})

test('revision artifact rejects unknown and malformed identities', () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-artifact-id-'))
  mkdirSync(resolve(root, 'reports'), { recursive: true })
  assert.throws(() => resolveRevisionArtifact([resolve(root, 'reports')], {
    runId: '../escape',
    revisionId: 'rev_test',
    artifactId: 'sb_001.start_frame',
  }), /artifact_identity_invalid/)
  rmSync(root, { recursive: true, force: true })
})
