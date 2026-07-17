import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import test from 'node:test'
import { DreamPathPolicy } from '../src/paths'
import { buildRunDetail } from '../src/runs'
import { enqueueRepairCandidate, FileTauRepairQueue, promoteRevision, writeRepairAttempt } from '../src/repair'
import { buildProviderReturnStage } from '../src/stages'

test('provider return projects active post-mux handoff before provider media exists', () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-audio-handoff-'))
  const revisionId = 'rev_audio'
  const revisionRoot = resolve(root, '.persona-dream', 'revisions', revisionId)
  const preflightRoot = resolve(revisionRoot, 'phase_11_submit_return', 'preflight')
  const canonicalRoot = resolve(revisionRoot, 'phase_11_submit_return', 'canonical')
  mkdirSync(preflightRoot, { recursive: true })
  mkdirSync(canonicalRoot, { recursive: true })
  writeFileSync(resolve(preflightRoot, 'voice_handoff_plan.json'), JSON.stringify({
    schema: 'persona_dream.voice_handoff_plan.v1',
    status: 'BLOCKED_AWAITING_EXACT_LINE_RENDER',
    strategy: 'post_mux',
    lines: [{ speaker: 'Kai', text: "If we paddle now, we're cutting across the lineup." }],
  }))
  writeFileSync(resolve(canonicalRoot, 'phase11_live_request.v1.json'), JSON.stringify({
    approval_bindings: { request_body_sha256: `sha256:${'a'.repeat(64)}` },
    missing_approval_types: ['paid_call_authorization'],
  }))

  const stage = buildProviderReturnStage(root, revisionId)
  assert.equal(stage?.status, 'NOT_EXECUTED')
  assert.match(stage?.failureOrGap ?? '', /Audio strategy post_mux/)
  assert.match(stage?.failureOrGap ?? '', /BLOCKED_AWAITING_EXACT_LINE_RENDER/)
  assert.match(stage?.failureOrGap ?? '', /awaits 1 human hash-bound approvals/)
  assert.ok(stage?.artifacts.some((artifact) => artifact.path.endsWith('voice_handoff_plan.json')))
  rmSync(root, { recursive: true, force: true })
})

test('provider return prefers completed post-mux video and clears stale pre-submit gaps', () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-post-mux-return-'))
  const revisionId = 'rev_audio'
  const requestKey = 'a'.repeat(64)
  const revisionRoot = resolve(root, '.persona-dream', 'revisions', revisionId)
  const returnRoot = resolve(revisionRoot, 'phase_11_submit_return', 'provider_return', requestKey)
  const preflightRoot = resolve(revisionRoot, 'phase_11_submit_return', 'preflight')
  const canonicalRoot = resolve(revisionRoot, 'phase_11_submit_return', 'canonical')
  mkdirSync(returnRoot, { recursive: true })
  mkdirSync(preflightRoot, { recursive: true })
  mkdirSync(canonicalRoot, { recursive: true })
  writeFileSync(resolve(returnRoot, 'provider_return.mp4'), 'silent-source')
  writeFileSync(resolve(returnRoot, 'muxed_provider_return.mp4'), 'voiced-final')
  writeFileSync(resolve(returnRoot, 'ffmpeg_mux_receipt.json'), JSON.stringify({ status: 'PASS_POST_MUX' }))
  writeFileSync(resolve(returnRoot, 'muxed_provider_return_ffprobe_receipt.json'), JSON.stringify({
    status: 'PASS_MUXED_RETURN_HAS_AUDIO_STREAM', output_sha256: 'sha256:final',
    ffprobe: { format: { duration: '10.041667' } },
  }))
  writeFileSync(resolve(returnRoot, 'audible_output_review_receipt.json'), JSON.stringify({ status: 'PASS_DETERMINISTIC_NON_SILENCE' }))
  writeFileSync(resolve(returnRoot, 'phase11_provider_return_envelope.v1.json'), JSON.stringify({ status: 'PASS_PHASE11_PROVIDER_RETURN_RECEIVED' }))
  writeFileSync(resolve(returnRoot, 'phase11_download_ffprobe_receipt.v1.json'), JSON.stringify({ status: 'PASS_PHASE11_PROVIDER_RETURN_DOWNLOADED' }))
  writeFileSync(resolve(preflightRoot, 'voice_handoff_plan.json'), JSON.stringify({
    schema: 'persona_dream.voice_handoff_plan.v1', status: 'PASS_EXACT_LINE_RENDER_READY_FOR_MUX',
    strategy: 'post_mux', lines: [{ speaker: 'Kai', text: 'line' }],
  }))
  writeFileSync(resolve(canonicalRoot, 'phase11_live_request.v1.json'), JSON.stringify({
    approval_bindings: { request_body_sha256: `sha256:${requestKey}` },
    missing_approval_types: ['paid_call_authorization'],
  }))

  const stage = buildProviderReturnStage(root, revisionId)
  assert.equal(stage?.status, 'RETURN_RECEIVED')
  assert.match(stage?.summary ?? '', /Post-mux final MP4/)
  assert.equal(stage?.failureOrGap, null)
  assert.equal(stage?.artifacts[1]?.path.endsWith('muxed_provider_return.mp4'), true)
  assert.ok(stage?.artifacts.some((artifact) => artifact.path.endsWith('audible_output_review_receipt.json')))
  assert.doesNotMatch(stage?.summary ?? '', /awaits .* approvals/)
  rmSync(root, { recursive: true, force: true })
})

test('path policy rejects prefix collisions and outside files', () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-path-'))
  const allowed = resolve(root, 'allowed')
  const collision = resolve(root, 'allowed-other')
  mkdirSync(allowed)
  mkdirSync(collision)
  writeFileSync(resolve(allowed, 'ok.json'), '{}')
  writeFileSync(resolve(collision, 'bad.json'), '{}')
  const policy = new DreamPathPolicy([allowed])
  assert.equal(policy.resolveFile(resolve(allowed, 'ok.json')), realpathSync(resolve(allowed, 'ok.json')))
  assert.throws(() => policy.resolveFile(resolve(collision, 'bad.json')), /path_not_allowed/)
  rmSync(root, { recursive: true, force: true })
})

test('run detail reports earliest missing phase without writing repair artifacts', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-run-'))
  writeFileSync(resolve(root, 'status.json'), JSON.stringify({ status: 'PASS' }))
  const policy = new DreamPathPolicy([root])
  const detail = await buildRunDetail(policy, root)
  assert.equal(detail.earliestIssue?.phaseId, '01')
  assert.equal(detail.repairCandidate, undefined)
  assert.equal(detail.stages.find((stage) => stage.id === '03')?.effectiveState, 'blocked_by_upstream')
  assert.equal(detail.stages.find((stage) => stage.id === '04')?.effectiveState, 'blocked_by_upstream')
  rmSync(root, { recursive: true, force: true })
})

test('repair-enabled revision exposes one deterministic earliest repair candidate', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-repair-'))
  writeFileSync(resolve(root, 'status.json'), JSON.stringify({ status: 'PASS' }))
  writeFileSync(resolve(root, 'dream_revision_manifest.v1.json'), JSON.stringify({
    schema: 'persona_dream.revision_state.v1',
    run_id: 'repair-fixture',
    active_revision_id: 'rev_0007',
    repair_enabled: true,
  }))
  const policy = new DreamPathPolicy([root])
  const first = await buildRunDetail(policy, root)
  const second = await buildRunDetail(policy, root)
  assert.equal(first.repairCandidate?.earliestRepairPhase, '01')
  assert.equal(first.repairCandidate?.enqueueAllowed, true)
  assert.equal(first.repairCandidate?.dedupKey, second.repairCandidate?.dedupKey)
  assert.deepEqual(first.repairCandidate?.phaseRange, ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10'])
  rmSync(root, { recursive: true, force: true })
})

test('repair enqueue deduplicates work order and file-backed Tau queue item', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-enqueue-'))
  writeFileSync(resolve(root, 'status.json'), JSON.stringify({ status: 'PASS' }))
  writeFileSync(resolve(root, 'dream_revision_manifest.v1.json'), JSON.stringify({ active_revision_id: 'rev_0007', repair_enabled: true }))
  const detail = await buildRunDetail(new DreamPathPolicy([root]), root)
  const queue = new FileTauRepairQueue()
  const first = await enqueueRepairCandidate(detail, queue)
  const second = await enqueueRepairCandidate(detail, queue)
  assert.equal(first.reused, false)
  assert.equal(second.reused, true)
  assert.equal(first.workOrder.workOrderId, second.workOrder.workOrderId)
  assert.equal(first.queueReceiptPath, second.queueReceiptPath)
  rmSync(root, { recursive: true, force: true })
})

test('attempt four is blocked and failed target cannot promote', () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-promotion-'))
  assert.throws(() => writeRepairAttempt(root, {
    schemaVersion: 'persona_dream.repair_attempt.v1',
    workOrderId: 'repair-1',
    phaseId: '03',
    attemptNumber: 4 as 3,
    status: 'FAILED_REPAIR_PHASE',
    startedAt: new Date(0).toISOString(),
    completedAt: new Date(0).toISOString(),
    inputHashes: {},
    outputHashes: {},
    gateReceipts: [],
    blockers: ['test'],
  }), /BLOCKED_REPAIR_MAX_ATTEMPTS/)
  mkdirSync(resolve(root, '.persona-dream', 'state'), { recursive: true })
  writeFileSync(resolve(root, '.persona-dream', 'state', 'active_revision.json'), JSON.stringify({ runId: 'run', revisionId: 'rev_0001' }))
  writeFileSync(resolve(root, 'target.json'), JSON.stringify({ revisionId: 'rev_0002', status: 'BLOCKED' }))
  assert.throws(() => promoteRevision({ runRoot: root, expectedSourceRevisionId: 'rev_0001', targetRevisionId: 'rev_0002', targetManifestPath: resolve(root, 'target.json') }), /BLOCKED_REPAIR_TARGET_REVISION_NOT_ACCEPTED/)
  rmSync(root, { recursive: true, force: true })
})

test('run detail reads only the atomically promoted revision', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-active-revision-'))
  const revisionRoot = resolve(root, '.persona-dream', 'revisions', 'rev_0002')
  mkdirSync(resolve(root, '.persona-dream', 'state'), { recursive: true })
  mkdirSync(revisionRoot, { recursive: true })
  writeFileSync(resolve(root, 'status.json'), JSON.stringify({ status: 'PASS' }))
  writeFileSync(resolve(root, 'dream_revision_manifest.v1.json'), JSON.stringify({ active_revision_id: 'rev_0001', repair_enabled: true }))
  writeFileSync(resolve(root, 'dream_request.json'), JSON.stringify({ stale: true }))
  const fixtureFiles = {
    'phase_01': ['dream_request.json', 'residue_links.json'],
    'phase_02': ['story_contract.json'],
    'phase_03': ['crew_contract.json', 'crew_gate_receipt.json'],
    'phase_04': ['contact_sheet_requirements.json', 'contact_sheet_manifest.json', 'contact_sheet_gate_receipt.json'],
    'phase_05': ['voice_evidence.json'],
    'phase_06': ['script_contract.json'],
    'phase_07': ['storyboard_packet.json'],
    'phase_08': ['media_lock.json'],
    'phase_09': ['video_provider_scorecard.json', 'provider_final_gate.json'],
    'phase_10': ['panel_distillation_contract.json', 'provider_schema_receipt.json'],
  }
  for (const [directory, filenames] of Object.entries(fixtureFiles)) {
    mkdirSync(resolve(revisionRoot, directory), { recursive: true })
    for (const filename of filenames) {
      const value = filename === 'storyboard_packet.json'
        ? { schema: 'persona_dream.storyboard_packet.v1', status: 'PASS_PANEL_REVIEWED', accepted: true, panel_count: 1, panels: [{ panel_id: 'sb_001' }] }
        : {}
      writeFileSync(resolve(revisionRoot, directory, filename), JSON.stringify(value))
    }
  }
  writeFileSync(resolve(root, '.persona-dream', 'state', 'active_revision.json'), JSON.stringify({
    runId: 'run', revisionId: 'rev_0002', revisionRoot,
    revisionManifestSha256: 'sha256:test',
  }))
  const detail = await buildRunDetail(new DreamPathPolicy([root]), root)
  assert.equal(detail.activeRevision?.revisionId, 'rev_0002')
  assert.equal(detail.revisionQualification.state, 'LEGACY_UNQUALIFIED')
  assert.equal(detail.revisionQualification.status, 'BLOCKED_REVISION_NOT_QUALIFIED')
  assert.equal(detail.earliestIssue, undefined)
  assert.equal(detail.repairCandidate, undefined)
  assert.ok(detail.stages.every((stage) => stage.effectiveState === 'blocked_by_upstream'))
  assert.ok(detail.stages.every((stage) => stage.acceptance.state === 'blocked'))
  assert.ok(detail.stages.every((stage) => stage.status === 'BLOCKED_REVISION_NOT_QUALIFIED'))
  rmSync(root, { recursive: true, force: true })
})

test('required artifacts are projected before optional artifact limits', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-required-artifact-'))
  const revisionRoot = resolve(root, '.persona-dream', 'revisions', 'rev_0002')
  const storyboardRoot = resolve(revisionRoot, 'phase_07')
  mkdirSync(resolve(root, '.persona-dream', 'state'), { recursive: true })
  mkdirSync(storyboardRoot, { recursive: true })
  writeFileSync(resolve(root, 'status.json'), JSON.stringify({ status: 'PASS' }))
  writeFileSync(resolve(root, 'dream_revision_manifest.v1.json'), JSON.stringify({ active_revision_id: 'rev_0001', repair_enabled: true }))
  writeFileSync(resolve(root, '.persona-dream', 'state', 'active_revision.json'), JSON.stringify({
    runId: 'run', revisionId: 'rev_0002', revisionRoot,
    revisionManifestSha256: 'sha256:test',
  }))
  for (let index = 0; index < 40; index += 1) {
    writeFileSync(resolve(storyboardRoot, `storyboard_optional_${String(index).padStart(2, '0')}.json`), '{}')
  }
  writeFileSync(resolve(storyboardRoot, 'phase_07_storyboard_packet_tau_dag_contract.json'), '{}')
  const requiredPath = resolve(storyboardRoot, 'storyboard_packet.json')
  writeFileSync(requiredPath, JSON.stringify({ schema: 'persona_dream.storyboard_packet.v1', status: 'PASS_PANEL_REVIEWED', accepted: true, panel_count: 1, panels: [{ panel_id: 'sb_001' }] }))

  const detail = await buildRunDetail(new DreamPathPolicy([root]), root)
  const storyboard = detail.stages.find((stage) => stage.id === '07')
  assert.equal(storyboard?.evidence.state, 'present')
  assert.ok(storyboard?.artifacts.some((artifact) => artifact.path === requiredPath))
  assert.equal(storyboard?.artifacts[0]?.path, requiredPath)
  assert.equal(storyboard?.artifacts.length, 30)
  assert.equal(storyboard?.requiredArtifacts.storyboard_packet.path, requiredPath)
  assert.equal(storyboard?.requiredArtifacts.storyboard_packet.artifactId, 'storyboard_packet')
  rmSync(root, { recursive: true, force: true })
})

test('storyboard filename presence cannot accept an empty packet', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-semantic-artifact-'))
  const storyboardRoot = resolve(root, 'phase_07')
  mkdirSync(storyboardRoot, { recursive: true })
  writeFileSync(resolve(storyboardRoot, 'storyboard_packet.json'), '{}')
  const detail = await buildRunDetail(new DreamPathPolicy([root]), root)
  const storyboard = detail.stages.find((stage) => stage.id === '07')
  assert.equal(storyboard?.evidence.state, 'semantic_invalid')
  assert.deepEqual(storyboard?.evidence.semanticInvalidIds, ['storyboard_packet'])
  rmSync(root, { recursive: true, force: true })
})

test('run detail projects revision-scoped storyboard artifact URLs while qualification remains blocked', async () => {
  const root = mkdtempSync(resolve(tmpdir(), 'persona-dream-storyboard-projection-'))
  const runId = 'pipeline-complete'
  const revisionId = 'rev_projection'
  const runRoot = resolve(root, runId)
  const revisionRoot = resolve(runRoot, '.persona-dream', 'revisions', revisionId)
  const storyboardRoot = resolve(revisionRoot, 'phase_07_storyboard_live_tau')
  const framesRoot = resolve(storyboardRoot, 'generated_storyboard_frames')
  mkdirSync(resolve(runRoot, '.persona-dream', 'state'), { recursive: true })
  mkdirSync(framesRoot, { recursive: true })
  writeFileSync(resolve(runRoot, 'status.json'), JSON.stringify({ status: 'PASS' }))
  writeFileSync(resolve(runRoot, '.persona-dream', 'state', 'active_revision.json'), JSON.stringify({
    runId,
    revisionId,
    revisionRoot: '/stale/checkout/pipeline-complete/.persona-dream/revisions/rev_projection',
  }))

  const artifacts: Record<string, { relative_path: string; sha256: string; roles: string[] }> = {}
  const panels = Array.from({ length: 4 }, (_, index) => {
    const panelId = `sb_${String(index + 1).padStart(3, '0')}`
    const frame = (role: 'start' | 'end') => {
      const filename = `${panelId}_${role}_frame.png`
      const relativePath = `phase_07_storyboard_live_tau/generated_storyboard_frames/${filename}`
      const bytes = Buffer.from(`${panelId}-${role}-bytes`)
      const digest = `sha256:${createHash('sha256').update(bytes).digest('hex')}`
      writeFileSync(resolve(revisionRoot, relativePath), bytes)
      artifacts[`${panelId}.${role}_frame`] = { relative_path: relativePath, sha256: digest, roles: ['accepted_frame'] }
      return { accepted_frame: { path: `/stale/checkout/${filename}`, sha256: digest } }
    }
    return { panel_id: panelId, start_frame: frame('start'), end_frame: frame('end') }
  })
  const packet = {
    schema: 'persona_dream.storyboard_packet.v1',
    status: 'PASS_PANEL_REVIEWED',
    accepted: true,
    panel_count: 4,
    panels,
  }
  const packetPath = resolve(storyboardRoot, 'storyboard_packet.json')
  writeFileSync(packetPath, JSON.stringify(packet))
  artifacts.storyboard_packet = {
    relative_path: 'phase_07_storyboard_live_tau/storyboard_packet.json',
    sha256: `sha256:${createHash('sha256').update(JSON.stringify(packet)).digest('hex')}`,
    roles: ['required_evidence', 'consumer_input'],
  }
  writeFileSync(resolve(revisionRoot, 'revision_artifact_index.json'), JSON.stringify({
    run_id: runId,
    revision_id: revisionId,
    artifacts,
  }))

  const detail = await buildRunDetail(new DreamPathPolicy([root]), runRoot)
  assert.equal(detail.revisionQualification.state, 'LEGACY_UNQUALIFIED')
  assert.equal(detail.consumers?.storyboard?.panelCount, 4)
  assert.equal(detail.consumers?.storyboard?.panels.length, 4)
  assert.equal(detail.consumers?.storyboard?.panels[0].startFrame.artifactId, 'sb_001.start_frame')
  assert.equal(
    detail.consumers?.storyboard?.panels[0].startFrame.url,
    '/api/projects/dream/runs/pipeline-complete/revisions/rev_projection/artifacts/sb_001.start_frame',
  )
  assert.equal(detail.stages.some((stage) => stage.effectiveState === 'accepted_current'), false)
  rmSync(root, { recursive: true, force: true })
})
