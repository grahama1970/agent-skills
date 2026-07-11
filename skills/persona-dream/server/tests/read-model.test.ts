import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import test from 'node:test'
import { DreamPathPolicy } from '../src/paths'
import { buildRunDetail } from '../src/runs'

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
