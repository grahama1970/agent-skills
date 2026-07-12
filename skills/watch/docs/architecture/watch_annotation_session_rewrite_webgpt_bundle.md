# Watch Annotation Session Rewrite Review Bundle

Generated: 2026-07-02

## Request

Use WebGPT as an architecture/code reviewer to propose a **clean replacement** for the Watch annotation-session state and persistence layer.

Do **not** patch the existing `WatchReportView.tsx` implementation. The current component has become unreliable because toolbar selection, persisted segment metadata, fetched memory records, interpolation, overlay rendering, and delete behavior are coupled in one React component.

Produce another version of the annotation code to compare against the current implementation: a normalized session model, reducer/actions/selectors, persistence adapter, and React integration sketch.

## Primary Objective

Design and provide TypeScript code for a reliable Watch annotation session that lets a human annotate multiple characters across frames within one movie segment, with keyframes persisted to existing Watch memory collections.

The core user job:

> In a segment such as `03:36-04:00`, the human selects a character, draws or adjusts boxes for that character on specific frames, steps forward/backward, switches to another character, annotates that character too, deletes the currently selected box when needed, and expects all previously recorded keyframes to remain stable.

## Non-Negotiable Boundaries

1. Use the existing canonical collection: `watch_keyframe_annotations`.
2. Do not introduce a new `movie_annotation` collection.
3. Do not store raw embedding vectors in Arango.
4. Do not persist interpolated frame-by-frame boxes as canonical keyframes.
5. Runtime interpolation is derived from human keyframes and offscreen/track-stop markers.
6. Same-track propagation belongs in `watch_track_observations`, not `watch_keyframe_annotations`.
7. A selected toolbar character must not change merely because playback advances, memory rehydrates, or another overlay exists at the current frame.
8. A human keyframe can exist even if no YoloAnalytics detector observation is linked.

## Existing Persistence Surface

Frontend file currently involved:

```text
/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/watch/WatchReportView.tsx
```

Existing server endpoints:

```text
POST /api/projects/watch/annotations
POST /api/projects/watch/annotations/track-control
GET  /api/projects/watch/annotations/summary
GET  /api/projects/watch/annotations/rows/:rowIndex
POST /api/projects/watch/annotations/clear-segment
POST /api/projects/watch/annotations/delete-keyframe
```

Existing schema:

```text
/home/graham/workspace/experiments/agent-skills/skills/watch/docs/architecture/schemas/watch_keyframe_annotation.schema.json
```

Existing runtime interpolation helper:

```text
/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/watch/watchAnnotationTracking.ts
```

## Source-Derived Step Model

1. Open a video segment row.
   - Status: implemented.
   - Problem: row open also initializes toolbar character from row/entity/stored state.

2. Fetch active annotations for that row from memory.
   - Status: implemented via `GET /api/projects/watch/annotations/rows/:rowIndex`.
   - Problem: fetched records are merged into the same local object that stores toolbar character.

3. Human selects active character in toolbar.
   - Status: implemented.
   - Problem: selection is persisted as `stored.characterName`, so it is confused with annotation data.

4. Human draws an exact keyframe box at current segment time.
   - Status: implemented.
   - Required behavior: append or replace a keyframe for the selected character/track at that exact time.

5. Human steps forward/backward in frames.
   - Status: implemented.
   - Required behavior: playback time changes only; selected character must remain unchanged.
   - Current reported failure: selected character switches back to Willie when moving frames.

6. UI renders all relevant boxes at current time.
   - Status: implemented.
   - Required behavior: active character boxes should be clearly active; other characters may remain visible but should not steal selection.
   - Current reported failure: annotation frame appears muted/grey and ambiguous.

7. Human selects or clicks another character intentionally.
   - Status: partially implemented.
   - Required behavior: only explicit user selection changes active character.

8. Human deletes current exact box.
   - Status: partially implemented.
   - Required behavior: Delete/Backspace removes exactly the selected exact keyframe at current time; other characters and previous keyframes remain.
   - Current reported failure history: deleting one annotation sometimes increased keyframes or removed the wrong thing.

9. Human marks character absent/offscreen.
   - Status: implemented as track-control/offscreen marker, but UI semantics were confusing.
   - Required behavior: offscreen marker ends interpolation/scan for that character sequence; it must not delete prior keyframes.

10. Persist to memory.
    - Status: implemented through app endpoints.
    - Required behavior: memory is authoritative; localStorage is only a session/cache layer and must not resurrect deleted records.

## Current Code Smells / Failure Sources

Relevant excerpts from `WatchReportView.tsx`:

1. Toolbar selection is written into the same local draft object as annotation data:

```tsx
// lines 3200-3218
function updateClipModalCharacter(name: string): void {
  setClipModalCharacterName(name)
  const actor = actorForCharacter(name)
  const nextActorName = actor || ''
  setClipModalActorName(nextActorName)
  if (!expandedClipRow || !reportWithDiff) return
  const key = annotationDraftStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
  const stored = readAnnotationDraft(key) || {}
  writeAnnotationDraft(key, {
    characterName: name || 'Unassigned',
    actorName: nextActorName,
    capturedFrameDataUrl: stored.capturedFrameDataUrl ?? null,
    capturedFrameSeconds: stored.capturedFrameSeconds ?? null,
    draftBbox: stored.draftBbox ?? null,
    savedBoxes: Array.isArray(stored.savedBoxes) ? stored.savedBoxes : [],
    adjustmentEvents: Array.isArray(stored.adjustmentEvents) ? stored.adjustmentEvents : [],
    saveStatus: stored.saveStatus ?? '',
  })
  setClipModalAnnotationRevision((currentRevision) => currentRevision + 1)
}
```

2. Row initialization and memory fetch can also choose the character:

```tsx
// lines 3264-3278
const storedCharacter = stored?.characterName && (stored.characterName !== 'Unassigned' || storedHasAnnotationWork) ? stored.characterName : ''
const rowCharacter = expandedClip?.entities.find((entity) => actorForCharacter(entity)) || candidate?.name || expandedClip?.entities[0] || ''
const currentCharacter = clipModalCharacterName.trim()
const nextCharacterName = currentCharacter || storedCharacter || rowCharacter || memorySummary?.character_names[0] || 'Unassigned'
const nextActorName = clipModalActorName.trim() || stored?.actorName || actorForCharacter(nextCharacterName) || candidate?.actor || memorySummary?.actor_names[0] || ''
setClipModalCharacterName(nextCharacterName)
setClipModalActorName(nextActorName)
```

3. Memory rehydrate stores preferred character back into the same draft:

```tsx
// lines 3295-3328
const current = readAnnotationDraft(key) || {}
const currentBoxes = Array.isArray(current.savedBoxes) ? current.savedBoxes : []
const preferredCharacterName = clipModalCharacterName.trim() || current.characterName || rowCharacter || memoryBoxes[0]?.characterName || 'Unassigned'
const preferredActorName = clipModalActorName.trim() || current.actorName || actorForCharacter(preferredCharacterName) || candidate?.actor || memoryBoxes[0]?.actorName || ''
const mergedBoxes = mergeFetchedMemoryAnnotationBoxes(currentBoxes, memoryBoxes)
writeAnnotationDraft(key, {
  characterName: preferredCharacterName,
  actorName: preferredActorName,
  savedBoxes: mergedBoxes,
  ...
})
```

4. Active overlay styling is derived from `clipModalActiveCharacter`, which itself falls back to stored draft character:

```tsx
// lines 3451-3455
const clipModalStoredDraft = expandedClipRow
  ? readAnnotationDraft(annotationDraftStorageKey(reportWithDiff.watch_report.title, expandedClipRow))
  : null
const clipModalActiveCharacter = clipModalCharacterName || clipModalStoredDraft?.characterName || 'Unassigned'
```

5. Interpolated overlays are mixed into the same render list as exact keyframes:

```tsx
// lines 3522-3526
const annotationModalOverlays = exactAnnotationModalOverlays
const eventModalOverlays = activeTab !== 'annotation' && !clipModalAnnotationOverlaysCleared && expandedClip && overlayPayload && annotationModalOverlays.length === 0 && interpolationModalOverlays.length === 0
  ? overlaysForClip(expandedClip, overlayPayload)
  : []
const modalOverlays = [...annotationModalOverlays, ...interpolationModalOverlays, ...eventModalOverlays]
```

6. Delete behavior switches between deletion and offscreen-marker creation depending on runtime interpolation state:

```tsx
// lines 2530-2551
const activeRuntimeBox = clipModalInterpolatedBoxes.find((box) => sameAnnotationCharacter(box.characterName, activeCharacter))
const currentRuntimeBox = selectedRuntimeBox
  || (selectedBoxId ? null : activeRuntimeBox)
  || (selectedBoxId ? null : interpolatedKeyframeBox(boxes, clipModalPlaybackSeconds, activeCharacter))

if (currentRuntimeBox && currentRuntimeBox.runtimePolicy !== 'exact_keyframe') {
  markClipModalCharacterOffscreen(currentRuntimeBox)
  setClipModalSelectedOverlayId(null)
  return
}
```

## Failed Local Repair History / What Remains Unfixed

Treat this section as the reason for requesting a clean replacement architecture instead of another patch to the current component.

The human repeatedly disproved local fixes with live Watch UI screenshots at:

```text
http://localhost:3002/watch#watch?clipRow=5
http://localhost:3002/watch#watch?clipRow=9
```

Reported failures:

1. Delete button sometimes did not remove the visible annotation box for the current frame.
2. Backspace did not reliably delete the current selected exact keyframe, especially when a form control such as the character select had focus.
3. Clear did not reliably clear all keyframes in the entire video segment.
4. Deleting a keyframe sometimes removed too much state: when rewinding, previously recorded keyframes were gone even though they should have remained.
5. Deleting one visible annotation when two characters were on the same screen sometimes increased the keyframe count instead of decreasing it.
6. With two characters annotated in the same segment, stepping to the next frame was difficult because selection and overlays interfered with each other.
7. The selected annotation character did not persist across frame stepping. Example: the human selected `The Kid`, advanced frames, and the toolbar switched back to `Willie`.
8. Some frames showed a muted/grey annotation overlay state at `03:36-04:00`, making it unclear whether the visible box was active, inactive, exact, interpolated, stale, or deleted.
9. The `Offscreen` button/behavior was confusing and too tightly coupled to Delete. It was later removed from the toolbar, but the underlying state distinction is still needed in the model.
10. Local stale or deleted receipt records could be rehydrated from localStorage/session state, causing deleted records or wrong character preferences to reappear.

Temporary patch attempts that are not sufficient as a final design:

1. Exact-time matching was tightened so Delete prefers an exact keyframe at the current time.
2. Duplicate/cluster deletion was attempted so nearby duplicate records could be removed together.
3. LocalStorage cleanup was attempted to avoid merging deleted memory records back into the local draft.
4. Backspace handling was expanded to fire from `SELECT` controls.
5. Interpolation suppression after Delete was attempted to keep deleted boxes from being immediately redrawn as runtime overlays.
6. Controlled browser checks were run, but they did not prove the real multi-character workflow:

```text
/tmp/codex-ui-verification/pi-mono/watch-row9-current-recheck/20260701T213105Z-live-stale.json
/tmp/codex-ui-verification/pi-mono/watch-row9-current-recheck/20260701T213205Z-live-backspace.json
/tmp/codex-ui-verification/pi-mono/watch-row9-current-recheck/20260701T213325Z-controlled-two-character.json
```

Caveat: the controlled two-character check used an augmented row API because the live row only exposed one character in that specific check. The human then immediately produced screenshots showing the selected-character switching and ambiguous/muted overlay problems, so the current implementation remains untrustworthy.

Please treat the existing component as a cautionary example. Produce a replacement annotation-session island with clear invariants, not another patch against the current state shape.

## Required Replacement Design

Please propose a clean alternative with these artifacts:

1. `watchAnnotationSession.ts`
   - Types for `AnnotationSessionState`, `AnnotationTrack`, `Keyframe`, `OffscreenMarker`, `ActiveSelection`, `DraftBox`, `MemoryRecordRef`.
   - Pure reducer actions:
     - `hydrateFromMemory(row, records)`
     - `selectCharacter(characterId/name, actor?)`
     - `setPlaybackTime(seconds)`
     - `beginDraw(point)`
     - `commitDraw(bbox)`
     - `selectOverlay(overlayId)`
     - `moveSelectedBox(bbox)`
     - `resizeSelectedBox(bbox)`
     - `deleteSelectedExactKeyframe()`
     - `markSelectedCharacterOffscreen()`
     - `clearSegment()`
     - `persistSucceeded(localId, memoryRef)`
     - `persistFailed(localId, error)`
   - Pure selectors:
     - `selectVisibleOverlays(state, timeSeconds)`
     - `selectActiveCharacter(state)`
     - `selectExactKeyframeAtTime(state, characterId, timeSeconds)`
     - `selectDeleteTarget(state)`
     - `selectPersistenceQueue(state)`

2. Persistence adapter
   - Talks to existing endpoints above.
   - Treats memory API records as authoritative for persisted keyframes.
   - Uses localStorage/sessionStorage only for UI draft/session recovery.
   - Does not write active toolbar selection into canonical annotation records.

3. Overlay rendering contract
   - Exact human keyframes and runtime interpolated/held overlays must be visually distinguishable.
   - Active character selection must be explicit and stable.
   - Inactive character boxes can be visible but must not be mistaken for selected/editable boxes.

4. Delete semantics
   - Delete/Backspace removes selected exact keyframe only.
   - If no exact keyframe is selected but the active character has a runtime held/interpolated box, the UI should expose a separate command/intent for `mark offscreen`; do not hide that behind Delete.
   - Deleting one character must not increase keyframe count and must not delete other characters' boxes.

5. Multi-character invariant
   - Multiple characters can have visible boxes at the same time/frame.
   - A character switch only happens from explicit dropdown change or explicit overlay selection.
   - Stepping frames does not mutate active character.

6. Migration/integration sketch
   - Show how `WatchReportView.tsx` should delegate annotation behavior to the new reducer/session module.
   - Do not rewrite the full 5k-line component; provide a replaceable island and integration seam.

7. Tests
   - Pure reducer tests for:
     - selected character remains stable across playback steps
     - two characters at same time; deleting active selected one leaves the other
     - offscreen stop ends interpolation without deleting prior keyframes
     - stale local cached records are replaced by memory hydrate
     - Backspace/Delete does not promote/interpolate/add keyframes

## Expected Output Format

Return:

1. Architecture summary.
2. State model.
3. Reducer/action TypeScript code.
4. Selector TypeScript code.
5. Persistence adapter TypeScript code.
6. React integration sketch.
7. Test cases.
8. Any unresolved assumptions.

Do not provide generic advice. Provide concrete code that can be compared against the current implementation.
