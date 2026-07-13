import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import test from 'node:test'
import { DreamPathPolicy } from '../src/paths'
import { buildRunDetail } from '../src/runs'
import { enqueueRepairCandidate, FileTauRepairQueue, promoteRevision, writeRepairAttempt } from '../src/repair'

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
    for (const filename of filenames) writeFileSync(resolve(revisionRoot, directory, filename), '{}')
  }
  writeFileSync(resolve(root, '.persona-dream', 'state', 'active_revision.json'), JSON.stringify({
    runId: 'run', revisionId: 'rev_0002', revisionRoot,
    revisionManifestSha256: 'sha256:test',
  }))
  const detail = await buildRunDetail(new DreamPathPolicy([root]), root)
  assert.equal(detail.activeRevision?.revisionId, 'rev_0002')
  assert.equal(detail.earliestIssue, undefined)
  assert.equal(detail.repairCandidate, undefined)
  assert.ok(detail.stages.every((stage) => stage.effectiveState === 'accepted_current'))
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
  const requiredPath = resolve(storyboardRoot, 'storyboard_packet.json')
  writeFileSync(requiredPath, JSON.stringify({ schema: 'persona_dream.storyboard_packet.v1', panels: [] }))

  const detail = await buildRunDetail(new DreamPathPolicy([root]), root)
  const storyboard = detail.stages.find((stage) => stage.id === '07')
  assert.equal(storyboard?.evidence.state, 'present')
  assert.ok(storyboard?.artifacts.some((artifact) => artifact.path === requiredPath))
  assert.equal(storyboard?.artifacts.length, 30)
  rmSync(root, { recursive: true, force: true })
})
