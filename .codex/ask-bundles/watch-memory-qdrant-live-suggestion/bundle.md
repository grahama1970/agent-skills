# WebGPT Code Gate: Watch live Memory/Qdrant suggestion smoke

## Objective
Add the next repeatable proof slice for the immutable `$watch` goal: prove a Watch YOLO/interpolated Marcus crop can be sent as `image_data_url` to the live `$memory`/Qdrant crop-recall path and returns a tentative Marcus suggestion with confidence, without mutating accepted YOLO label receipts.

## Immutable goal context
`$watch` must use YOLOAnalytics person boxes as source regions, identify each box by querying `$memory`/Qdrant multimodal crop recall against human-labeled character crops, surface tentative labels with confidence, persist accepted/rejected labels, stop propagation on identity conflicts, and prove the row 9 Marcus/Willie flow end-to-end in browser and backend.

## Current completed slice
Pushed to `agent-skills@main`: `e071ee43ae0114beab8fa88133ba551101a91ed3` (`watch: prove yolo label receipt replay`).

That slice added a deterministic receipt replay smoke proving:
- accept Marcus on `track_15`
- `reject_box` / stop at 1.79s
- projection becomes unassigned after stop
- explicit Willie reassignment later starts a new identity segment
- local Memory sync failure remains visible and retryable

Browser-oracle/CDP row-10 artifact from that slice:
`/tmp/codex-ui-verification/agent-skills/watch-yolo-label-receipt-replay-row10/20260715T173445Z.png`

## Current live probe before this gate
Memory daemon health was live:
`curl http://127.0.0.1:8601/health` returned `{"status":"ok","ok":true,...}`.

A one-off live probe using crop:
`skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260704T172759115162Z_yolo_track_2_only/crops/sample_15_12.515_marcus_detector_9_track_2_interpolated.png`
returned:
- status 200
- schema `memory.watch_identity_crop_recall.v1`
- found true
- top suggestion `Marcus? 0.94`
- confidence `0.944098`
- hit count 9
- proof scope from Memory: live image embedding, Qdrant crop similarity query, Arango Watch keyframe hydration

Full live probe artifact:
`.codex/ask-bundles/watch-memory-qdrant-live-suggestion/live-memory-probe.json`

## Relevant Memory contract
Read from `skills/memory/SKILL.md` and Memory source:
- Use daemon HTTP, not direct Qdrant or direct Arango from Watch UI.
- Use `X-Caller-Skill: watch`.
- Image crop recall endpoint: `POST http://127.0.0.1:8601/watch/identity/recall-crop`.
- Endpoint filters Qdrant to `review_state=human_approved` and `label_type=positive`, hydrates `watch_keyframe_annotations`, and returns `display_label` such as `Marcus? 0.94`.
- Qdrant remains vector store; Arango remains canonical metadata/hydration source.

## Relevant Watch code
- `skills/watch/ui/server/index.ts` exposes `/api/projects/watch/identity-suggestions`, proxying to Memory `/watch/identity/recall-crop` with `X-Caller-Skill: watch`.
- `skills/watch/ui/components/WatchReportView.tsx` calls `/api/projects/watch/identity-suggestions` from `requestClipModalMemorySuggestion()` and renders tentative labels through `clipModalMemorySuggestions`.

## Required implementation
Add a repeatable live smoke test script:
`skills/watch/ui/scripts/watchMemorySuggestionLive.smoke.ts`

Add package script:
`"test:memory-suggestion-live": "tsx scripts/watchMemorySuggestionLive.smoke.ts"`

The smoke should:
1. Read the existing Marcus detector/interpolated crop file above.
2. Convert it to `image_data_url`.
3. Start the existing Watch API server from `skills/watch/ui/server/index.ts` or call Memory directly only if using the Watch proxy is too brittle. Prefer the Watch proxy because the immutable goal includes Watch calling Memory.
4. Call `/api/projects/watch/identity-suggestions` with:
   - asset uid `bad_santa_unrated_2003_brrip_xvidhd_720p_npw`
   - row_index `9`
   - track_id `track_2`
   - `image_data_url`
5. Assert response schema `watch.identity_suggestions.v1`.
6. Assert status `ok`.
7. Assert suggestion exists, is tentative, character `Marcus`, confidence >= `0.82`, display label includes `Marcus?` if present.
8. Assert Memory response includes live proof scope or equivalent fields showing Memory/Qdrant path was exercised.
9. Assert the smoke does not write or mutate the persisted YOLO label receipt for row 9. It should snapshot the row-9 receipt file before/after if present.
10. Fail closed if Memory is unavailable; do not mock Memory.

## Blocker command
`npm --prefix skills/watch/ui run test:memory-suggestion-live`

It currently fails because the script does not exist.

## Allowed paths
- `skills/watch/ui/package.json`
- `skills/watch/ui/scripts/watchMemorySuggestionLive.smoke.ts`
- `.codex/ask-bundles/watch-memory-qdrant-live-suggestion/**`

## Forbidden paths
- `skills/ask/**`
- `skills/persona-dream/**`
- `skills/watch/docs/architecture/generated/watch_yolo_track_labels/**`

## Output contract
Return a minimal patch/diff only. Do not propose architecture. Do not modify generated label receipts. Do not add mocked tests as the completion proof.
