import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  assertCleanWorktree,
  runCommand,
  sha256File,
  writeProofManifest,
} from './proofUtils'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(uiRoot, '..', '..', '..')
const args = new Set(process.argv.slice(2))
const persistProof = args.has('--persist-proof')

function argValue(name: string): string | null {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || null : null
}

async function gitSha(): Promise<string> {
  const result = await runCommand({
    command: 'git',
    args: ['rev-parse', 'HEAD'],
    cwd: repoRoot,
  })
  assert.equal(result.exit_code, 0, result.stderr || result.stdout)
  return result.stdout.trim()
}

function redactUrl(value: string): string {
  try {
    const parsed = new URL(value)
    parsed.username = ''
    parsed.password = ''
    return parsed.toString()
  } catch {
    return value.replace(/\/\/[^/@]+@/, '//')
  }
}

async function main(): Promise<void> {
  await assertCleanWorktree(repoRoot)
  const sha = await gitSha()
  const proofDir = persistProof
    ? path.resolve(repoRoot, 'skills/watch/proofs/immutable-goal', sha)
    : path.resolve(argValue('--proof-dir') || process.env.WATCH_PROOF_DIR || '/tmp/watch-immutable-goal-live-proof')
  await mkdir(proofDir, { recursive: true })

  const env = {
    ...process.env,
    WATCH_PROOF_DIR: proofDir,
  }
  const commands = [
    { name: 'npm_run_test_backend_immutable', args: ['run', 'test:backend-immutable'] },
    { name: 'npm_run_typecheck', args: ['run', 'typecheck'] },
    { name: 'npm_run_build', args: ['run', 'build'] },
    { name: 'npm_run_test_memory_suggestion_live', args: ['run', 'test:memory-suggestion-live'] },
    { name: 'npm_run_test_immutable_browser_live', args: ['run', 'test:immutable-browser-live'] },
    { name: 'npm_run_test_pyannote_immutable_live', args: ['run', 'test:pyannote-immutable-live'] },
  ]
  const results = []
  for (const command of commands) {
    const result = await runCommand({
      command: 'npm',
      args: command.args,
      cwd: uiRoot,
      env,
    })
    results.push({ name: command.name, ...result })
    if (result.exit_code !== 0) {
      await writeFile(path.join(proofDir, 'command-results.json'), `${JSON.stringify(results, null, 2)}\n`)
      throw new Error(`${command.name} failed with exit ${result.exit_code}\n${result.stdout}\n${result.stderr}`)
    }
  }
  await writeFile(path.join(proofDir, 'command-results.json'), `${JSON.stringify(results, null, 2)}\n`)

  const requiredArtifacts = [
    'command-results.json',
    'api-row9-memory-suggestion.json',
    'api-row10-final-receipt.json',
    'api-row10-projection-before-accept.json',
    'api-row10-projection-after-marcus.json',
    'api-row10-projection-after-stop.json',
    'api-row10-projection-after-willie.json',
    '01-row9-tentative-marcus.png',
    '02-row10-marcus-accepted.png',
    '03-row10-after-stop-unassigned.png',
    '04-row10-willie-reassigned.png',
    '05-row10-reloaded.png',
    'pyannote-immutable-e2e/source-video.mp4',
    'pyannote-immutable-e2e/source-audio.wav',
    'pyannote-immutable-e2e/captions.srt',
    'pyannote-immutable-e2e/pyannote-diarization.json',
    'pyannote-immutable-e2e/pyannote-report-speaker-rows.json',
    'pyannote-immutable-e2e/pyannote-e2e-summary.json',
  ]
  for (const artifact of requiredArtifacts) {
    const artifactPath = path.join(proofDir, artifact)
    const hash = await sha256File(artifactPath)
    assert.match(hash, /^[a-f0-9]{64}$/)
  }

  const row10Receipt = JSON.parse(await import('node:fs/promises').then(({ readFile }) => readFile(path.join(proofDir, 'api-row10-final-receipt.json'), 'utf-8')))
  assert.equal(row10Receipt.labels?.track_15?.characterName, 'Willie')
  assert.ok(row10Receipt.events?.some((event: any) => event.action === 'reject_box'))
  assert.ok(row10Receipt.events?.filter((event: any) => event.action === 'accept').every((event: any) => event.memory_sync?.state === 'stored'))
  const pyannoteSummary = JSON.parse(await import('node:fs/promises').then(({ readFile }) => readFile(path.join(proofDir, 'pyannote-immutable-e2e/pyannote-e2e-summary.json'), 'utf-8')))
  assert.equal(pyannoteSummary.mocked, false)
  assert.equal(pyannoteSummary.live, true)
  assert.equal(pyannoteSummary.service?.device, 'cuda')
  assert.equal(pyannoteSummary.assertions?.diarization_receipt_complete, true)
  assert.equal(pyannoteSummary.assertions?.anonymous_speakers_not_promoted_to_identity, true)

  if (persistProof) {
    await writeProofManifest({
      proofDir,
      manifest: {
        schema: 'watch.immutable_goal_proof.v1',
        goal_id: 'watch-yolo-memory-identity',
        status: 'PASS',
        mocked: false,
        live: true,
        commit_sha: sha,
        created_at: new Date().toISOString(),
        memory_daemon_url: redactUrl(process.env.MEMORY_DAEMON_URL || 'http://127.0.0.1:8601'),
        asset_uid: 'bad_santa_unrated_2003_brrip_xvidhd_720p_npw',
        proof_only_row10_asset_uid: 'watch_immutable_proof_asset',
        rows: [9, 10],
        tracks: ['track_2', 'track_15'],
        assertions: {
          live_qdrant_suggestion: true,
          suggestion_tentative: true,
          human_accept_persisted: true,
          stop_persisted: true,
          identity_absent_after_stop: true,
          explicit_reassignment_persisted: true,
          reload_hydration_passed: true,
          memory_sync_stored: true,
          suggestion_query_did_not_mutate_receipt: true,
          pyannote_live_cuda_diarization: true,
          anonymous_speaker_evidence_written: true,
          pyannote_does_not_promote_identity: true,
        },
      },
    })
    const manifestPath = path.relative(repoRoot, path.join(proofDir, 'manifest.json'))
    await writeFile(
      path.resolve(repoRoot, 'skills/watch/proofs/immutable-goal/latest.json'),
      `${JSON.stringify({
        schema: 'watch.immutable_goal_latest.v1',
        commit_sha: sha,
        manifest: manifestPath,
      }, null, 2)}\n`,
    )
  }

  console.log('watchImmutableGoalLive smoke passed')
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
