import assert from 'node:assert/strict'
import test from 'node:test'
import { hydrateStoryboardConsumer } from '../src/consumerContracts'

function fixture() {
  const artifacts: Record<string, { relative_path: string; sha256: string; roles: string[] }> = {}
  const panels = Array.from({ length: 4 }, (_, index) => {
    const panelId = `sb_${String(index + 1).padStart(3, '0')}`
    const frame = (role: 'start' | 'end') => {
      const name = `${panelId}_${role}_frame.png`
      const sha256 = `sha256:${panelId}-${role}`
      artifacts[`${panelId}.${role}_frame`] = { relative_path: `phase_07/generated_storyboard_frames/${name}`, sha256, roles: ['accepted_frame'] }
      return { accepted_frame: { path: `/stale/checkout/${name}`, sha256 } }
    }
    return { panel_id: panelId, start_frame: frame('start'), end_frame: frame('end') }
  })
  return {
    packet: { schema: 'persona_dream.storyboard_packet.v1', status: 'PASS_PANEL_REVIEWED', accepted: true, panel_count: 4, panels },
    index: { artifacts },
  }
}

test('storyboard consumer hydrates four panels and eight indexed frames without source paths', () => {
  const { packet, index } = fixture()
  const projection = hydrateStoryboardConsumer(packet, index)
  assert.equal(projection.panelCount, 4)
  assert.equal(projection.frames.length, 8)
  assert.ok(projection.frames.every((frame) => frame.relativePath.startsWith('phase_07/')))
})

test('storyboard consumer blocks an indexed frame hash mismatch', () => {
  const { packet, index } = fixture()
  index.artifacts['sb_001.start_frame'].sha256 = 'sha256:tampered'
  assert.throws(() => hydrateStoryboardConsumer(packet, index), /BLOCKED_ASSET_FETCH_HASH_MISMATCH/)
})
