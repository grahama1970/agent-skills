export type NormalizedBbox = [number, number, number, number]

export const WATCH_KEYFRAME_COLLECTION = 'watch_keyframe_annotations' as const
export const WATCH_TRACK_OBSERVATION_COLLECTION = 'watch_track_observations' as const
export const UNASSIGNED_CHARACTER = 'Unassigned'
export const EXACT_TIME_EPSILON_SECONDS = 1 / 120

export type PersistStatus = 'clean' | 'pending' | 'failed'
export type RuntimeOverlayPolicy = 'exact_keyframe' | 'runtime_interpolated' | 'runtime_held'

export interface SessionRow {
  rowIndex: number
  movieTitle: string
  segmentStartSeconds: number
  segmentEndSeconds: number
  fps?: number
}

export interface MemoryRecordRef {
  collection: typeof WATCH_KEYFRAME_COLLECTION | typeof WATCH_TRACK_OBSERVATION_COLLECTION
  key?: string
  id?: string
  rev?: string
  rowIndex: number
}

export interface Keyframe {
  type: 'keyframe'
  localId: string
  characterId: string
  characterName: string
  actorName?: string
  timeSeconds: number
  timeKey: string
  bbox: NormalizedBbox
  memoryRef?: MemoryRecordRef
  duplicateMemoryRefs?: MemoryRecordRef[]
  source: 'memory' | 'local'
  status: PersistStatus
  createdAtTick: number
  updatedAtTick: number
}

export interface OffscreenMarker {
  type: 'offscreen'
  localId: string
  characterId: string
  characterName: string
  actorName?: string
  timeSeconds: number
  timeKey: string
  memoryRef?: MemoryRecordRef
  source: 'memory' | 'local'
  status: PersistStatus
  createdAtTick: number
  updatedAtTick: number
}

export interface AnnotationTrack {
  characterId: string
  characterName: string
  actorName?: string
  keyframesById: Record<string, Keyframe>
  offscreenById: Record<string, OffscreenMarker>
}

export interface ActiveSelection {
  characterId: string | null
  characterName: string
  actorName?: string
  selectedOverlayId?: string | null
  selectedKeyframeId?: string | null
  selectedMarkerId?: string | null
  explicit: boolean
  source: 'none' | 'user-dropdown' | 'user-overlay' | 'session-recovery'
}

export interface PendingPersistenceOp {
  opId: string
  localId: string
  kind: 'upsert_keyframe' | 'delete_keyframe' | 'mark_offscreen' | 'clear_segment'
  row: SessionRow
  keyframe?: Keyframe
  marker?: OffscreenMarker
  memoryRefs?: MemoryRecordRef[]
  status: 'pending' | 'failed'
  createdAtTick: number
  updatedAtTick: number
}

export interface DeleteTombstone {
  localId: string
  characterId: string
  timeKey: string
  bboxHash: string
  memoryRefs: MemoryRecordRef[]
  keyframe: Keyframe
  status: 'pending' | 'succeeded' | 'failed'
  deletedAtTick: number
}

export interface AnnotationSessionState {
  row: SessionRow
  tracksByCharacterId: Record<string, AnnotationTrack>
  trackOrder: string[]
  activeSelection: ActiveSelection
  playbackTimeSeconds: number
  pendingOpsByLocalId: Record<string, PendingPersistenceOp>
  deleteTombstonesByLocalId: Record<string, DeleteTombstone>
  revision: number
  lastError?: string | null
}

export type WatchMemoryRecord = Record<string, unknown>

export type AnnotationSessionAction =
  | { type: 'hydrateFromMemory'; row: SessionRow; records: WatchMemoryRecord[] }
  | { type: 'selectCharacter'; characterName: string; actorName?: string; characterId?: string }
  | { type: 'setPlaybackTime'; seconds: number }
  | { type: 'commitDraw'; bbox: NormalizedBbox }
  | { type: 'selectOverlay'; overlayId: string | null }
  | { type: 'moveSelectedBox'; bbox: NormalizedBbox }
  | { type: 'resizeSelectedBox'; bbox: NormalizedBbox }
  | { type: 'deleteSelectedExactKeyframe' }
  | { type: 'markSelectedCharacterOffscreen' }
  | { type: 'clearSegment' }
  | { type: 'persistSucceeded'; localId: string; memoryRef?: MemoryRecordRef }
  | { type: 'persistFailed'; localId: string; error: string }

export interface VisibleAnnotationOverlay {
  overlayId: string
  characterId: string
  characterName: string
  actorName?: string
  bbox: NormalizedBbox
  timeSeconds: number
  timeKey: string
  policy: RuntimeOverlayPolicy
  isActiveCharacter: boolean
  isExact: boolean
  isEditable: boolean
  isSelected: boolean
  sourceKeyframeIds: string[]
  status?: PersistStatus
}

export const annotationSessionActions = {
  hydrateFromMemory: (row: SessionRow, records: WatchMemoryRecord[]): AnnotationSessionAction => ({
    type: 'hydrateFromMemory',
    row,
    records,
  }),
  selectCharacter: (characterName: string, actorName?: string, characterId?: string): AnnotationSessionAction => ({
    type: 'selectCharacter',
    characterName,
    actorName,
    characterId,
  }),
  setPlaybackTime: (seconds: number): AnnotationSessionAction => ({ type: 'setPlaybackTime', seconds }),
  commitDraw: (bbox: NormalizedBbox): AnnotationSessionAction => ({ type: 'commitDraw', bbox }),
  selectOverlay: (overlayId: string | null): AnnotationSessionAction => ({ type: 'selectOverlay', overlayId }),
  moveSelectedBox: (bbox: NormalizedBbox): AnnotationSessionAction => ({ type: 'moveSelectedBox', bbox }),
  resizeSelectedBox: (bbox: NormalizedBbox): AnnotationSessionAction => ({ type: 'resizeSelectedBox', bbox }),
  deleteSelectedExactKeyframe: (): AnnotationSessionAction => ({ type: 'deleteSelectedExactKeyframe' }),
  markSelectedCharacterOffscreen: (): AnnotationSessionAction => ({ type: 'markSelectedCharacterOffscreen' }),
  clearSegment: (): AnnotationSessionAction => ({ type: 'clearSegment' }),
  persistSucceeded: (localId: string, memoryRef?: MemoryRecordRef): AnnotationSessionAction => ({
    type: 'persistSucceeded',
    localId,
    memoryRef,
  }),
  persistFailed: (localId: string, error: string): AnnotationSessionAction => ({
    type: 'persistFailed',
    localId,
    error,
  }),
}

export function createInitialAnnotationSession(row: SessionRow): AnnotationSessionState {
  return {
    row,
    tracksByCharacterId: {},
    trackOrder: [],
    activeSelection: {
      characterId: null,
      characterName: '',
      selectedOverlayId: null,
      selectedKeyframeId: null,
      selectedMarkerId: null,
      explicit: false,
      source: 'none',
    },
    playbackTimeSeconds: row.segmentStartSeconds,
    pendingOpsByLocalId: {},
    deleteTombstonesByLocalId: {},
    revision: 0,
    lastError: null,
  }
}

export function annotationSessionReducer(
  state: AnnotationSessionState,
  action: AnnotationSessionAction,
): AnnotationSessionState {
  switch (action.type) {
    case 'hydrateFromMemory': {
      let tracksByCharacterId: Record<string, AnnotationTrack> = {}
      let trackOrder: string[] = []

      for (const record of action.records) {
        const keyframe = parseMemoryKeyframe(action.row, record)
        if (!keyframe) continue
        if (isTombstoned(keyframe, state.deleteTombstonesByLocalId)) continue
        const put = putKeyframeIntoMaps(tracksByCharacterId, trackOrder, action.row, keyframe)
        tracksByCharacterId = put.tracksByCharacterId
        trackOrder = put.trackOrder
      }

      const replayed = replayPendingOps(action.row, tracksByCharacterId, trackOrder, state.pendingOpsByLocalId)
      return {
        ...state,
        row: action.row,
        tracksByCharacterId: replayed.tracksByCharacterId,
        trackOrder: replayed.trackOrder,
        activeSelection: state.activeSelection,
        playbackTimeSeconds: clampSecondsToRow(action.row, state.playbackTimeSeconds),
        revision: state.revision + 1,
        lastError: null,
      }
    }

    case 'selectCharacter': {
      const characterName = cleanCharacterName(action.characterName)
      const characterId = action.characterId || characterIdFor(characterName)
      const ensured = ensureTrack(state.tracksByCharacterId, state.trackOrder, {
        characterId,
        characterName,
        actorName: action.actorName || undefined,
      })
      return {
        ...state,
        tracksByCharacterId: ensured.tracksByCharacterId,
        trackOrder: ensured.trackOrder,
        activeSelection: {
          characterId,
          characterName,
          actorName: action.actorName || undefined,
          selectedOverlayId: null,
          selectedKeyframeId: null,
          selectedMarkerId: null,
          explicit: true,
          source: 'user-dropdown',
        },
        revision: state.revision + 1,
        lastError: null,
      }
    }

    case 'setPlaybackTime':
      return {
        ...state,
        playbackTimeSeconds: clampSecondsToRow(state.row, action.seconds),
        activeSelection: state.activeSelection,
        revision: state.revision + 1,
      }

    case 'commitDraw': {
      const active = selectActiveCharacter(state)
      if (!active) return fail(state, 'Choose a character before drawing.')
      if (!isValidBbox(action.bbox)) return fail(state, 'Invalid bounding box.')
      const tick = state.revision + 1
      const timeSeconds = clampSecondsToRow(state.row, state.playbackTimeSeconds)
      const timeKey = timeKeyFor(state.row, timeSeconds)
      const existing = selectExactKeyframeAtTime(state, active.characterId, timeSeconds)
      const localId = existing?.localId || makeLocalId('kf', state.row, active.characterId, timeKey, tick)
      const keyframe: Keyframe = {
        type: 'keyframe',
        localId,
        characterId: active.characterId,
        characterName: active.characterName,
        actorName: active.actorName,
        timeSeconds,
        timeKey,
        bbox: action.bbox,
        memoryRef: existing?.memoryRef,
        duplicateMemoryRefs: existing?.duplicateMemoryRefs,
        source: existing?.source === 'memory' ? 'memory' : 'local',
        status: 'pending',
        createdAtTick: existing?.createdAtTick ?? tick,
        updatedAtTick: tick,
      }
      const put = putKeyframeIntoMaps(state.tracksByCharacterId, state.trackOrder, state.row, keyframe)
      return {
        ...state,
        tracksByCharacterId: put.tracksByCharacterId,
        trackOrder: put.trackOrder,
        activeSelection: {
          ...state.activeSelection,
          selectedOverlayId: exactOverlayId(localId),
          selectedKeyframeId: localId,
          selectedMarkerId: null,
        },
        pendingOpsByLocalId: {
          ...state.pendingOpsByLocalId,
          [localId]: makeUpsertOp(state.row, keyframe, tick),
        },
        deleteTombstonesByLocalId: omitKey(state.deleteTombstonesByLocalId, localId),
        revision: tick,
        lastError: null,
      }
    }

    case 'selectOverlay': {
      if (!action.overlayId) {
        return {
          ...state,
          activeSelection: {
            ...state.activeSelection,
            selectedOverlayId: null,
            selectedKeyframeId: null,
            selectedMarkerId: null,
          },
          revision: state.revision + 1,
        }
      }
      const parsed = parseOverlayId(action.overlayId)
      if (parsed.kind !== 'exact') return fail(state, 'Runtime overlays are not editable keyframes.')
      const found = findKeyframeById(state, parsed.localId)
      if (!found) return fail(state, 'Selected keyframe no longer exists.')
      return {
        ...state,
        activeSelection: {
          characterId: found.keyframe.characterId,
          characterName: found.keyframe.characterName,
          actorName: found.keyframe.actorName,
          selectedOverlayId: action.overlayId,
          selectedKeyframeId: found.keyframe.localId,
          selectedMarkerId: null,
          explicit: true,
          source: 'user-overlay',
        },
        revision: state.revision + 1,
        lastError: null,
      }
    }

    case 'moveSelectedBox':
    case 'resizeSelectedBox':
      return updateSelectedExactKeyframeBbox(state, action.bbox)

    case 'deleteSelectedExactKeyframe': {
      const target = selectDeleteTarget(state)
      if (!target) {
        return { ...state, revision: state.revision + 1, lastError: null }
      }
      const tick = state.revision + 1
      const refs = memoryRefsForKeyframe(target)
      const removed = removeKeyframeFromMaps(state.tracksByCharacterId, state.trackOrder, target.localId)
      const pendingOpsByLocalId = omitKey(state.pendingOpsByLocalId, target.localId)
      const deleteTombstonesByLocalId = { ...state.deleteTombstonesByLocalId }
      if (refs.length > 0) {
        pendingOpsByLocalId[target.localId] = makeDeleteOp(state.row, target, refs, tick)
        deleteTombstonesByLocalId[target.localId] = {
          localId: target.localId,
          characterId: target.characterId,
          timeKey: target.timeKey,
          bboxHash: bboxHash(target.bbox),
          memoryRefs: refs,
          keyframe: target,
          status: 'pending',
          deletedAtTick: tick,
        }
      }
      return {
        ...state,
        tracksByCharacterId: removed.tracksByCharacterId,
        trackOrder: removed.trackOrder,
        activeSelection: {
          ...state.activeSelection,
          selectedOverlayId: null,
          selectedKeyframeId: null,
          selectedMarkerId: null,
        },
        pendingOpsByLocalId,
        deleteTombstonesByLocalId,
        revision: tick,
        lastError: null,
      }
    }

    case 'markSelectedCharacterOffscreen': {
      const active = selectActiveCharacter(state)
      if (!active) return fail(state, 'Choose a character before marking offscreen.')
      const tick = state.revision + 1
      const timeSeconds = clampSecondsToRow(state.row, state.playbackTimeSeconds)
      const timeKey = timeKeyFor(state.row, timeSeconds)
      const marker: OffscreenMarker = {
        type: 'offscreen',
        localId: makeLocalId('offscreen', state.row, active.characterId, timeKey, tick),
        characterId: active.characterId,
        characterName: active.characterName,
        actorName: active.actorName,
        timeSeconds,
        timeKey,
        source: 'local',
        status: 'pending',
        createdAtTick: tick,
        updatedAtTick: tick,
      }
      const put = putMarkerIntoMaps(state.tracksByCharacterId, state.trackOrder, marker)
      return {
        ...state,
        tracksByCharacterId: put.tracksByCharacterId,
        trackOrder: put.trackOrder,
        activeSelection: {
          ...state.activeSelection,
          selectedOverlayId: null,
          selectedKeyframeId: null,
          selectedMarkerId: marker.localId,
        },
        pendingOpsByLocalId: {
          ...state.pendingOpsByLocalId,
          [marker.localId]: makeOffscreenOp(state.row, marker, tick),
        },
        revision: tick,
        lastError: null,
      }
    }

    case 'clearSegment': {
      const tick = state.revision + 1
      const localId = makeLocalId('clear', state.row, 'segment', `row:${state.row.rowIndex}`, tick)
      return {
        ...state,
        tracksByCharacterId: {},
        trackOrder: [],
        pendingOpsByLocalId: {
          [localId]: {
            opId: `op:${localId}`,
            localId,
            kind: 'clear_segment',
            row: state.row,
            status: 'pending',
            createdAtTick: tick,
            updatedAtTick: tick,
          },
        },
        deleteTombstonesByLocalId: {},
        activeSelection: { ...state.activeSelection, selectedOverlayId: null, selectedKeyframeId: null },
        revision: tick,
        lastError: null,
      }
    }

    case 'persistSucceeded': {
      const op = state.pendingOpsByLocalId[action.localId]
      if (!op) return state
      const next = { ...state, pendingOpsByLocalId: omitKey(state.pendingOpsByLocalId, action.localId), revision: state.revision + 1 }
      if (op.kind === 'upsert_keyframe') {
        return updateKeyframeById(next, action.localId, (keyframe) => ({
          ...keyframe,
          memoryRef: action.memoryRef || keyframe.memoryRef,
          status: 'clean',
          source: 'memory',
        }))
      }
      return next
    }

    case 'persistFailed': {
      const op = state.pendingOpsByLocalId[action.localId]
      if (!op) return { ...state, revision: state.revision + 1, lastError: action.error }
      return {
        ...state,
        pendingOpsByLocalId: {
          ...state.pendingOpsByLocalId,
          [action.localId]: {
            ...op,
            status: 'failed',
            updatedAtTick: state.revision + 1,
          },
        },
        revision: state.revision + 1,
        lastError: action.error,
      }
    }
  }
}

export function selectActiveCharacter(state: AnnotationSessionState) {
  if (!state.activeSelection.characterId) return null
  return {
    characterId: state.activeSelection.characterId,
    characterName: state.activeSelection.characterName,
    actorName: state.activeSelection.actorName,
  }
}

export function selectExactKeyframeAtTime(
  state: AnnotationSessionState,
  characterId: string,
  timeSeconds: number,
): Keyframe | null {
  const track = state.tracksByCharacterId[characterId]
  if (!track) return null
  return Object.values(track.keyframesById)
    .filter((keyframe) => sameTime(state.row, keyframe.timeSeconds, timeSeconds))
    .sort((a, b) => b.updatedAtTick - a.updatedAtTick)[0] || null
}

export function selectDeleteTarget(state: AnnotationSessionState): Keyframe | null {
  const active = selectActiveCharacter(state)
  if (!active) return null
  const selectedId = state.activeSelection.selectedKeyframeId
  if (selectedId) {
    const found = findKeyframeById(state, selectedId)
    if (
      found
      && found.keyframe.characterId === active.characterId
      && sameTime(state.row, found.keyframe.timeSeconds, state.playbackTimeSeconds)
    ) {
      return found.keyframe
    }
  }
  return selectExactKeyframeAtTime(state, active.characterId, state.playbackTimeSeconds)
}

export function selectVisibleOverlays(state: AnnotationSessionState, timeSeconds = state.playbackTimeSeconds): VisibleAnnotationOverlay[] {
  const active = selectActiveCharacter(state)
  const overlays: VisibleAnnotationOverlay[] = []
  for (const characterId of state.trackOrder) {
    const track = state.tracksByCharacterId[characterId]
    if (!track) continue
    const exact = selectExactKeyframeAtTime(state, characterId, timeSeconds)
    const isActiveCharacter = active?.characterId === characterId
    if (exact) {
      const overlayId = exactOverlayId(exact.localId)
      const isSelected = state.activeSelection.selectedKeyframeId === exact.localId || state.activeSelection.selectedOverlayId === overlayId
      overlays.push({
        overlayId,
        characterId,
        characterName: exact.characterName,
        actorName: exact.actorName,
        bbox: exact.bbox,
        timeSeconds: exact.timeSeconds,
        timeKey: exact.timeKey,
        policy: 'exact_keyframe',
        isActiveCharacter,
        isExact: true,
        isEditable: isActiveCharacter,
        isSelected,
        sourceKeyframeIds: [exact.localId],
        status: exact.status,
      })
      continue
    }
    const runtime = runtimeOverlayForTrack(state.row, track, timeSeconds)
    if (!runtime) continue
    overlays.push({
      overlayId: runtimeOverlayId(characterId, runtime.policy, timeKeyFor(state.row, timeSeconds)),
      characterId,
      characterName: track.characterName,
      actorName: track.actorName,
      bbox: runtime.bbox,
      timeSeconds,
      timeKey: timeKeyFor(state.row, timeSeconds),
      policy: runtime.policy,
      isActiveCharacter,
      isExact: false,
      isEditable: false,
      isSelected: false,
      sourceKeyframeIds: runtime.sourceKeyframeIds,
    })
  }
  return overlays.sort((a, b) => Number(a.isActiveCharacter) - Number(b.isActiveCharacter))
}

export function selectPersistenceQueue(state: AnnotationSessionState): PendingPersistenceOp[] {
  return Object.values(state.pendingOpsByLocalId)
    .filter((op) => op.status === 'pending')
    .sort((a, b) => a.createdAtTick - b.createdAtTick)
}

export function exactOverlayId(localId: string): string {
  return `kf:${localId}`
}

export function characterIdFor(characterName: string): string {
  const slug = cleanCharacterName(characterName)
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `char:${slug || 'unassigned'}`
}

export function timeKeyFor(row: SessionRow, seconds: number): string {
  if (row.fps && row.fps > 0) {
    return `frame:${Math.round((seconds - row.segmentStartSeconds) * row.fps)}`
  }
  return `sec:${seconds.toFixed(3)}`
}

function cleanCharacterName(name: string): string {
  return name.trim() || UNASSIGNED_CHARACTER
}

function fail(state: AnnotationSessionState, message: string): AnnotationSessionState {
  return { ...state, revision: state.revision + 1, lastError: message }
}

function clampSecondsToRow(row: SessionRow, seconds: number): number {
  if (!Number.isFinite(seconds)) return row.segmentStartSeconds
  return Math.max(row.segmentStartSeconds, Math.min(row.segmentEndSeconds, seconds))
}

function sameTime(row: SessionRow, a: number, b: number): boolean {
  if (timeKeyFor(row, a) === timeKeyFor(row, b)) return true
  const epsilon = row.fps && row.fps > 0 ? Math.min(EXACT_TIME_EPSILON_SECONDS, 0.5 / row.fps) : EXACT_TIME_EPSILON_SECONDS
  return Math.abs(a - b) <= epsilon
}

function ensureTrack(
  tracksByCharacterId: Record<string, AnnotationTrack>,
  trackOrder: string[],
  character: { characterId: string; characterName: string; actorName?: string },
) {
  const existing = tracksByCharacterId[character.characterId]
  const track: AnnotationTrack = existing
    ? {
      ...existing,
      characterName: character.characterName || existing.characterName,
      actorName: character.actorName || existing.actorName,
      keyframesById: { ...existing.keyframesById },
      offscreenById: { ...existing.offscreenById },
    }
    : {
      characterId: character.characterId,
      characterName: character.characterName,
      actorName: character.actorName,
      keyframesById: {},
      offscreenById: {},
    }
  return {
    tracksByCharacterId: { ...tracksByCharacterId, [character.characterId]: track },
    trackOrder: existing ? trackOrder : [...trackOrder, character.characterId],
    track,
  }
}

function putKeyframeIntoMaps(
  tracksByCharacterId: Record<string, AnnotationTrack>,
  trackOrder: string[],
  row: SessionRow,
  keyframe: Keyframe,
) {
  const ensured = ensureTrack(tracksByCharacterId, trackOrder, keyframe)
  const track = ensured.track
  const sameFrame = Object.values(track.keyframesById).find((existing) => existing.localId !== keyframe.localId && sameTime(row, existing.timeSeconds, keyframe.timeSeconds))
  if (sameFrame) delete track.keyframesById[sameFrame.localId]
  track.keyframesById[keyframe.localId] = keyframe
  return { tracksByCharacterId: ensured.tracksByCharacterId, trackOrder: ensured.trackOrder, keyframe }
}

function putMarkerIntoMaps(
  tracksByCharacterId: Record<string, AnnotationTrack>,
  trackOrder: string[],
  marker: OffscreenMarker,
) {
  const ensured = ensureTrack(tracksByCharacterId, trackOrder, marker)
  const track = ensured.track
  const sameFrame = Object.values(track.offscreenById).find((existing) => existing.localId !== marker.localId && existing.timeKey === marker.timeKey)
  if (sameFrame) delete track.offscreenById[sameFrame.localId]
  track.offscreenById[marker.localId] = marker
  return { tracksByCharacterId: ensured.tracksByCharacterId, trackOrder: ensured.trackOrder, marker }
}

function removeKeyframeFromMaps(
  tracksByCharacterId: Record<string, AnnotationTrack>,
  trackOrder: string[],
  localId: string,
) {
  const next = { ...tracksByCharacterId }
  for (const characterId of Object.keys(next)) {
    const track = next[characterId]
    if (!track.keyframesById[localId]) continue
    next[characterId] = { ...track, keyframesById: omitKey(track.keyframesById, localId) }
    return { tracksByCharacterId: next, trackOrder }
  }
  return { tracksByCharacterId, trackOrder }
}

function updateSelectedExactKeyframeBbox(state: AnnotationSessionState, bbox: NormalizedBbox): AnnotationSessionState {
  if (!isValidBbox(bbox)) return fail(state, 'Invalid bounding box.')
  const target = selectDeleteTarget(state)
  if (!target) return fail(state, 'No exact keyframe is selected at the current time.')
  const updated: Keyframe = { ...target, bbox, status: 'pending', updatedAtTick: state.revision + 1 }
  const put = putKeyframeIntoMaps(state.tracksByCharacterId, state.trackOrder, state.row, updated)
  return {
    ...state,
    tracksByCharacterId: put.tracksByCharacterId,
    trackOrder: put.trackOrder,
    pendingOpsByLocalId: { ...state.pendingOpsByLocalId, [updated.localId]: makeUpsertOp(state.row, updated, state.revision + 1) },
    revision: state.revision + 1,
    lastError: null,
  }
}

function updateKeyframeById(state: AnnotationSessionState, localId: string, update: (keyframe: Keyframe) => Keyframe): AnnotationSessionState {
  const found = findKeyframeById(state, localId)
  if (!found) return state
  return {
    ...state,
    tracksByCharacterId: {
      ...state.tracksByCharacterId,
      [found.track.characterId]: {
        ...found.track,
        keyframesById: {
          ...found.track.keyframesById,
          [localId]: update(found.keyframe),
        },
      },
    },
  }
}

function findKeyframeById(state: AnnotationSessionState, localId: string): { track: AnnotationTrack; keyframe: Keyframe } | null {
  for (const characterId of state.trackOrder) {
    const track = state.tracksByCharacterId[characterId]
    const keyframe = track?.keyframesById[localId]
    if (track && keyframe) return { track, keyframe }
  }
  return null
}

function runtimeOverlayForTrack(row: SessionRow, track: AnnotationTrack, timeSeconds: number): { bbox: NormalizedBbox; policy: 'runtime_interpolated' | 'runtime_held'; sourceKeyframeIds: string[] } | null {
  const keyframes = Object.values(track.keyframesById).sort((a, b) => a.timeSeconds - b.timeSeconds)
  const previous = [...keyframes].reverse().find((keyframe) => keyframe.timeSeconds < timeSeconds && !sameTime(row, keyframe.timeSeconds, timeSeconds))
  if (!previous) return null
  const next = keyframes.find((keyframe) => keyframe.timeSeconds > timeSeconds && !sameTime(row, keyframe.timeSeconds, timeSeconds))
  const stop = Object.values(track.offscreenById).sort((a, b) => a.timeSeconds - b.timeSeconds).find((marker) => marker.timeSeconds > previous.timeSeconds)
  if (stop && timeSeconds >= stop.timeSeconds) return null
  if (next && (!stop || next.timeSeconds < stop.timeSeconds)) {
    const ratio = (timeSeconds - previous.timeSeconds) / Math.max(next.timeSeconds - previous.timeSeconds, 0.000001)
    return { bbox: lerpBbox(previous.bbox, next.bbox, ratio), policy: 'runtime_interpolated', sourceKeyframeIds: [previous.localId, next.localId] }
  }
  return { bbox: previous.bbox, policy: 'runtime_held', sourceKeyframeIds: [previous.localId] }
}

function lerpBbox(a: NormalizedBbox, b: NormalizedBbox, ratio: number): NormalizedBbox {
  const r = Math.max(0, Math.min(1, ratio))
  return [
    a[0] + (b[0] - a[0]) * r,
    a[1] + (b[1] - a[1]) * r,
    a[2] + (b[2] - a[2]) * r,
    a[3] + (b[3] - a[3]) * r,
  ]
}

function runtimeOverlayId(characterId: string, policy: RuntimeOverlayPolicy, timeKey: string): string {
  return `rt:${encodeURIComponent(characterId)}:${policy}:${timeKey}`
}

function parseOverlayId(overlayId: string): { kind: 'exact'; localId: string } | { kind: 'runtime' } | { kind: 'unknown' } {
  if (overlayId.startsWith('kf:')) return { kind: 'exact', localId: overlayId.slice(3) }
  if (overlayId.startsWith('rt:')) return { kind: 'runtime' }
  return { kind: 'unknown' }
}

function makeLocalId(prefix: string, row: SessionRow, characterId: string, timeKey: string, tick: number): string {
  return `${prefix}:row-${row.rowIndex}:${characterId}:${timeKey}:r${tick}`
}

function makeUpsertOp(row: SessionRow, keyframe: Keyframe, tick: number): PendingPersistenceOp {
  return {
    opId: `op:upsert:${keyframe.localId}:r${tick}`,
    localId: keyframe.localId,
    kind: 'upsert_keyframe',
    row,
    keyframe,
    memoryRefs: memoryRefsForKeyframe(keyframe),
    status: 'pending',
    createdAtTick: tick,
    updatedAtTick: tick,
  }
}

function makeDeleteOp(row: SessionRow, keyframe: Keyframe, memoryRefs: MemoryRecordRef[], tick: number): PendingPersistenceOp {
  return {
    opId: `op:delete:${keyframe.localId}:r${tick}`,
    localId: keyframe.localId,
    kind: 'delete_keyframe',
    row,
    keyframe,
    memoryRefs,
    status: 'pending',
    createdAtTick: tick,
    updatedAtTick: tick,
  }
}

function makeOffscreenOp(row: SessionRow, marker: OffscreenMarker, tick: number): PendingPersistenceOp {
  return {
    opId: `op:offscreen:${marker.localId}:r${tick}`,
    localId: marker.localId,
    kind: 'mark_offscreen',
    row,
    marker,
    status: 'pending',
    createdAtTick: tick,
    updatedAtTick: tick,
  }
}

function replayPendingOps(
  row: SessionRow,
  initialTracks: Record<string, AnnotationTrack>,
  initialOrder: string[],
  pendingOpsByLocalId: Record<string, PendingPersistenceOp>,
) {
  let tracksByCharacterId = initialTracks
  let trackOrder = initialOrder
  for (const op of selectPendingOps(pendingOpsByLocalId)) {
    if (op.kind === 'clear_segment') {
      tracksByCharacterId = {}
      trackOrder = []
    } else if (op.kind === 'upsert_keyframe' && op.keyframe) {
      const put = putKeyframeIntoMaps(tracksByCharacterId, trackOrder, row, op.keyframe)
      tracksByCharacterId = put.tracksByCharacterId
      trackOrder = put.trackOrder
    } else if (op.kind === 'delete_keyframe' && op.keyframe) {
      const removed = removeKeyframeFromMaps(tracksByCharacterId, trackOrder, op.keyframe.localId)
      tracksByCharacterId = removed.tracksByCharacterId
      trackOrder = removed.trackOrder
    } else if (op.kind === 'mark_offscreen' && op.marker) {
      const put = putMarkerIntoMaps(tracksByCharacterId, trackOrder, op.marker)
      tracksByCharacterId = put.tracksByCharacterId
      trackOrder = put.trackOrder
    }
  }
  return { tracksByCharacterId, trackOrder }
}

function selectPendingOps(pendingOpsByLocalId: Record<string, PendingPersistenceOp>): PendingPersistenceOp[] {
  return Object.values(pendingOpsByLocalId)
    .filter((op) => op.status === 'pending')
    .sort((a, b) => a.createdAtTick - b.createdAtTick)
}

function parseMemoryKeyframe(row: SessionRow, record: WatchMemoryRecord): Keyframe | null {
  const collection = stringField(record, ['collection'])
  const id = stringField(record, ['_id', 'id'])
  if (collection && collection !== WATCH_KEYFRAME_COLLECTION) return null
  if (id && !id.startsWith(`${WATCH_KEYFRAME_COLLECTION}/`)) return null
  const characterName = cleanCharacterName(stringField(record, ['characterName', 'character_name', 'character']) || UNASSIGNED_CHARACTER)
  const characterId = stringField(record, ['characterId', 'character_id']) || characterIdFor(characterName)
  const timeSeconds = numberField(record, ['timeSeconds', 'time_seconds', 'keyframe_time_seconds', 'capturedFrameSeconds', 'captured_frame_seconds'])
  const bbox = bboxField(record)
  if (timeSeconds == null || !bbox) return null
  const ref: MemoryRecordRef = {
    collection: WATCH_KEYFRAME_COLLECTION,
    id: id || undefined,
    key: stringField(record, ['_key', 'key']) || undefined,
    rev: stringField(record, ['_rev', 'rev']) || undefined,
    rowIndex: numberField(record, ['rowIndex', 'row_index']) ?? row.rowIndex,
  }
  const timeKey = timeKeyFor(row, timeSeconds)
  return {
    type: 'keyframe',
    localId: ref.id ? `mem:${ref.id}` : `mem:${row.rowIndex}:${characterId}:${timeKey}`,
    characterId,
    characterName,
    actorName: stringField(record, ['actorName', 'actor_name']) || undefined,
    timeSeconds,
    timeKey,
    bbox,
    memoryRef: ref,
    duplicateMemoryRefs: [],
    source: 'memory',
    status: 'clean',
    createdAtTick: 0,
    updatedAtTick: 0,
  }
}

function stringField(record: WatchMemoryRecord, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function numberField(record: WatchMemoryRecord, keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return null
}

function bboxField(record: WatchMemoryRecord): NormalizedBbox | null {
  const value = record.bbox || record.box || record.boundingBox || record.bounding_box
  if (!Array.isArray(value) || value.length < 4) return null
  const bbox = value.slice(0, 4).map(Number) as NormalizedBbox
  return isValidBbox(bbox) ? bbox : null
}

function isValidBbox(bbox: NormalizedBbox): boolean {
  return bbox.length === 4 && bbox.every(Number.isFinite) && bbox[2] > bbox[0] && bbox[3] > bbox[1]
}

function bboxHash(bbox: NormalizedBbox): string {
  return bbox.map((value) => Math.round(value * 1000) / 1000).join('|')
}

function memoryRefsForKeyframe(keyframe: Keyframe): MemoryRecordRef[] {
  return [keyframe.memoryRef, ...(keyframe.duplicateMemoryRefs || [])].filter(Boolean) as MemoryRecordRef[]
}

function isTombstoned(keyframe: Keyframe, tombstones: Record<string, DeleteTombstone>): boolean {
  const refs = memoryRefsForKeyframe(keyframe)
  return Object.values(tombstones).some((tombstone) => {
    if (tombstone.status === 'failed') return false
    return tombstone.timeKey === keyframe.timeKey
      && tombstone.characterId === keyframe.characterId
      && (tombstone.bboxHash === bboxHash(keyframe.bbox) || refs.some((ref) => tombstone.memoryRefs.some((tRef) => memoryRefIdentity(ref) === memoryRefIdentity(tRef))))
  })
}

function memoryRefIdentity(ref: MemoryRecordRef): string {
  return `${ref.collection}:${ref.id || ref.key || ''}:row:${ref.rowIndex}`
}

function omitKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record }
  delete next[key]
  return next
}
