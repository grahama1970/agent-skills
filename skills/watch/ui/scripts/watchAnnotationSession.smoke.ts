import assert from 'node:assert/strict'

import {
  type NormalizedBbox,
  type SessionRow,
  type WatchMemoryRecord,
  annotationSessionActions as actions,
  annotationSessionReducer,
  characterIdFor,
  createInitialAnnotationSession,
  exactOverlayId,
  selectActiveCharacter,
  selectDeleteTarget,
  selectExactKeyframeAtTime,
  selectPersistenceQueue,
  selectVisibleOverlays,
} from '../src/watchAnnotationSession'

const row: SessionRow = {
  rowIndex: 9,
  movieTitle: 'Watch fixture',
  segmentStartSeconds: 216,
  segmentEndSeconds: 240,
  fps: 24,
}

const row10: SessionRow = {
  rowIndex: 10,
  movieTitle: 'Watch row 10 fixture',
  segmentStartSeconds: 240,
  segmentEndSeconds: 264,
  fps: 24,
}

const boxA: NormalizedBbox = [0.1, 0.1, 0.3, 0.4]
const boxB: NormalizedBbox = [0.5, 0.1, 0.7, 0.4]
const boxC: NormalizedBbox = [0.1, 0.5, 0.3, 0.8]

function memKeyframe(
  key: string,
  characterName: string,
  timeSeconds: number,
  bbox: NormalizedBbox,
  sourceRow = row,
): WatchMemoryRecord {
  return {
    _id: `watch_keyframe_annotations/${key}`,
    _key: key,
    collection: 'watch_keyframe_annotations',
    rowIndex: sourceRow.rowIndex,
    movieTitle: sourceRow.movieTitle,
    characterName,
    characterId: characterIdFor(characterName),
    timeSeconds,
    bbox,
  }
}

function memOffscreen(key: string, characterName: string, timeSeconds: number, sourceRow = row): WatchMemoryRecord {
  return {
    _id: `watch_keyframe_annotations/${key}`,
    _key: key,
    collection: 'watch_keyframe_annotations',
    annotation: {
      id: key,
      row_index: sourceRow.rowIndex,
      character_name: characterName,
      character_id: characterIdFor(characterName),
      keyframe_time_seconds: timeSeconds,
      visibility_state: 'offscreen',
      bbox: null,
      track_control: {
        action: 'stop_character_scan',
        reason: 'character_offscreen',
        applies_after_seconds: timeSeconds,
      },
    },
  }
}

function countKeyframes(state: ReturnType<typeof createInitialAnnotationSession>): number {
  return Object.values(state.tracksByCharacterId)
    .reduce((sum, track) => sum + Object.keys(track.keyframesById).length, 0)
}

function countOffscreenMarkers(state: ReturnType<typeof createInitialAnnotationSession>): number {
  return Object.values(state.tracksByCharacterId)
    .reduce((sum, track) => sum + Object.keys(track.offscreenById).length, 0)
}

{
  let state = createInitialAnnotationSession(row)
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row, [
    memKeyframe('willie-216', 'Willie', 216, boxA),
  ]))
  state = annotationSessionReducer(state, actions.selectCharacter('The Kid'))
  state = annotationSessionReducer(state, actions.setPlaybackTime(216 + 1 / 24))
  state = annotationSessionReducer(state, actions.setPlaybackTime(216 + 2 / 24))
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row, [
    memKeyframe('willie-216', 'Willie', 216, boxA),
    memKeyframe('willie-216-next', 'Willie', 216 + 2 / 24, boxB),
  ]))

  assert.equal(selectActiveCharacter(state)?.characterName, 'The Kid')
  assert.equal(state.activeSelection.source, 'user-dropdown')
}

{
  let state = createInitialAnnotationSession(row)
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row, [
    memKeyframe('willie-216', 'Willie', 216, boxA),
    memKeyframe('kid-216', 'The Kid', 216, boxB),
  ]))
  state = annotationSessionReducer(state, actions.setPlaybackTime(216))

  const kid = selectExactKeyframeAtTime(state, characterIdFor('The Kid'), 216)
  assert.ok(kid)

  state = annotationSessionReducer(state, actions.selectOverlay(exactOverlayId(kid.localId)))
  assert.equal(selectDeleteTarget(state)?.characterName, 'The Kid')

  state = annotationSessionReducer(state, actions.deleteSelectedExactKeyframe())

  assert.equal(selectExactKeyframeAtTime(state, characterIdFor('The Kid'), 216), null)
  assert.ok(selectExactKeyframeAtTime(state, characterIdFor('Willie'), 216))
  assert.equal(countKeyframes(state), 1)
  assert.equal(selectPersistenceQueue(state)[0]?.kind, 'delete_keyframe')
}

{
  let state = createInitialAnnotationSession(row)
  state = annotationSessionReducer(state, actions.selectCharacter('The Kid'))
  state = annotationSessionReducer(state, actions.setPlaybackTime(216))
  state = annotationSessionReducer(state, actions.commitDraw(boxA))
  state = annotationSessionReducer(state, actions.setPlaybackTime(218))
  state = annotationSessionReducer(state, actions.commitDraw(boxC))
  assert.equal(countKeyframes(state), 2)

  state = annotationSessionReducer(state, actions.setPlaybackTime(217))
  state = annotationSessionReducer(state, actions.markSelectedCharacterOffscreen())
  assert.equal(countKeyframes(state), 2)
  assert.equal(selectVisibleOverlays(state, 216.5).filter((overlay) => overlay.characterName === 'The Kid').length, 1)
  assert.equal(selectVisibleOverlays(state, 217.5).filter((overlay) => overlay.characterName === 'The Kid').length, 0)
  assert.equal(selectVisibleOverlays(state, 218).filter((overlay) => overlay.characterName === 'The Kid')[0]?.policy, 'exact_keyframe')
}

{
  let state = createInitialAnnotationSession(row)
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row, [
    memKeyframe('stale-willie', 'Willie', 216, boxA),
  ]))
  assert.equal(countKeyframes(state), 1)
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row, []))
  assert.equal(countKeyframes(state), 0)
  assert.equal(selectVisibleOverlays(state, 216).length, 0)
}

{
  let state = createInitialAnnotationSession(row)
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row, [
    memKeyframe('kid-216', 'The Kid', 216, boxA),
    memKeyframe('kid-218', 'The Kid', 218, boxC),
  ]))
  state = annotationSessionReducer(state, actions.selectCharacter('The Kid'))
  state = annotationSessionReducer(state, actions.setPlaybackTime(217))

  const runtime = selectVisibleOverlays(state, 217).filter((overlay) => overlay.characterName === 'The Kid')
  assert.equal(runtime.length, 1)
  assert.equal(runtime[0].policy, 'runtime_interpolated')
  assert.equal(runtime[0].isEditable, false)

  const beforeCount = countKeyframes(state)
  state = annotationSessionReducer(state, actions.selectOverlay(runtime[0].overlayId))
  state = annotationSessionReducer(state, actions.deleteSelectedExactKeyframe())
  assert.equal(countKeyframes(state), beforeCount)
  assert.equal(selectPersistenceQueue(state).length, 0)
}

{
  const persistedRecords = [
    memKeyframe('row10-track15-marcus-start', 'Marcus', 240, boxA, row10),
    memOffscreen('row10-track15-unassign-stop', 'Marcus', 241.792, row10),
    memKeyframe('row10-track15-willie-start', 'Willie', 244.542, boxC, row10),
  ]
  let state = createInitialAnnotationSession(row10)
  state = annotationSessionReducer(state, actions.hydrateFromMemory(row10, persistedRecords))

  assert.equal(countKeyframes(state), 2)
  assert.equal(countOffscreenMarkers(state), 1)
  assert.equal(selectVisibleOverlays(state, 240.5).filter((overlay) => overlay.characterName === 'Marcus').length, 1)
  assert.equal(selectVisibleOverlays(state, 241.792).filter((overlay) => overlay.characterName === 'Marcus').length, 0)
  assert.equal(selectVisibleOverlays(state, 242).filter((overlay) => overlay.characterName === 'Marcus').length, 0)
  assert.equal(selectVisibleOverlays(state, 244).filter((overlay) => overlay.characterName === 'Marcus').length, 0)
  assert.equal(selectVisibleOverlays(state, 244.542).filter((overlay) => overlay.characterName === 'Willie')[0]?.policy, 'exact_keyframe')
  assert.equal(selectVisibleOverlays(state, 245).filter((overlay) => overlay.characterName === 'Willie')[0]?.policy, 'runtime_held')

  state = annotationSessionReducer(state, actions.hydrateFromMemory(row10, persistedRecords))
  assert.equal(countKeyframes(state), 2)
  assert.equal(countOffscreenMarkers(state), 1)
  assert.equal(selectVisibleOverlays(state, 242).filter((overlay) => overlay.characterName === 'Marcus').length, 0)
  assert.equal(selectVisibleOverlays(state, 245).filter((overlay) => overlay.characterName === 'Willie')[0]?.policy, 'runtime_held')
}

{
  let state = createInitialAnnotationSession(row10)
  state = annotationSessionReducer(state, actions.selectCharacter('Marcus'))
  state = annotationSessionReducer(state, actions.setPlaybackTime(240))
  state = annotationSessionReducer(state, actions.commitDraw(boxA))
  state = annotationSessionReducer(state, actions.setPlaybackTime(241.792))
  state = annotationSessionReducer(state, actions.markSelectedCharacterOffscreen())

  assert.equal(selectPersistenceQueue(state).filter((op) => op.kind === 'mark_offscreen').length, 1)
  const markerId = selectPersistenceQueue(state).find((op) => op.kind === 'mark_offscreen')?.localId
  assert.ok(markerId)
  state = annotationSessionReducer(state, actions.persistSucceeded(markerId, {
    collection: 'watch_keyframe_annotations',
    id: 'watch_keyframe_annotations/row10-track15-unassign-stop',
    key: 'row10-track15-unassign-stop',
    rowIndex: row10.rowIndex,
  }))
  assert.equal(selectPersistenceQueue(state).filter((op) => op.kind === 'mark_offscreen').length, 0)
  assert.equal(state.tracksByCharacterId[characterIdFor('Marcus')]?.offscreenById[markerId]?.status, 'clean')
  assert.equal(state.tracksByCharacterId[characterIdFor('Marcus')]?.offscreenById[markerId]?.source, 'memory')
}

console.log('watchAnnotationSession smoke passed')
