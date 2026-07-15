import assert from 'node:assert/strict'
import { yoloLabelForOverlay } from '../components/WatchReportView'

const overlay = {
  overlay_id: 'track_15',
  segment_id: 'row10',
  track_id: 'track_15',
  time_range: { start_seconds: 0, end_seconds: 24 },
  anchor_media_time_seconds: 0,
  valid_at_media_time_seconds: 0,
  bbox_policy: 'detector',
  track_lifecycle_status: 'active',
  stale_after_ms: 0,
  detected_class: 'person',
  classification: 'person',
  identity_status: 'YOLO_TRACK',
  visibility_proof: true,
  bbox_percent: { left: 10, top: 10, width: 40, height: 70 },
  render_policy: {},
}

const legacyLabels = {
  track_15: {
    trackId: 'track_15',
    characterName: 'Willie',
    actorName: 'Billy Bob Thornton',
    status: 'accepted' as const,
    source: 'human' as const,
    confidence: 1,
    updatedAt: '2026-07-03T00:00:00.000Z',
  },
}

const events = [
  {
    action: 'accept',
    status: 'accepted',
    track_id: 'track_15',
    box_key: 'track_15@100',
    time_seconds: 1,
    character_name: 'Marcus',
    actor_name: 'Tony Cox',
    confidence: 1,
    created_at: '2026-07-03T00:00:01.000Z',
  },
  {
    action: 'reject_box',
    status: 'rejected_box',
    track_id: 'track_15',
    box_key: 'track_15@179',
    time_seconds: 1.79,
    created_at: '2026-07-03T00:00:02.000Z',
  },
  {
    action: 'accept',
    status: 'accepted',
    track_id: 'track_15',
    box_key: 'track_15@454',
    time_seconds: 4.54,
    character_name: 'Willie',
    actor_name: 'Billy Bob Thornton',
    confidence: 1,
    created_at: '2026-07-03T00:00:03.000Z',
  },
]

assert.equal(
  yoloLabelForOverlay(overlay, events, legacyLabels, {}, {}, 0.5)?.characterName ?? null,
  null,
  'future accepted labels must not leak backward before the first sequence event',
)

assert.equal(
  yoloLabelForOverlay(overlay, events, legacyLabels, {}, {}, 1.2)?.characterName,
  'Marcus',
  'accepted labels should hold after their event until a stop',
)

assert.equal(
  yoloLabelForOverlay(overlay, events, legacyLabels, {}, {}, 2.02)?.characterName ?? null,
  null,
  'UNASSIGN_STOP should hold the same detector track unassigned until reassignment',
)

assert.equal(
  yoloLabelForOverlay(overlay, events, legacyLabels, {}, {}, 5)?.characterName,
  'Willie',
  'explicit reassignment should start a new assigned sequence segment',
)

assert.equal(
  yoloLabelForOverlay(overlay, [], legacyLabels, {}, {}, 0.5)?.characterName,
  'Willie',
  'legacy track labels remain available only when no event ledger exists',
)

console.log('watchYoloSequenceProjection smoke passed')
