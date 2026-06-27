verdict: ACCEPT

The event-derived watch.ui_overlay_payload.v1 is the right bridge for the current rung: it converts validated watch.live_track_update.v1 JSONL events into browser/modal-renderable geometry, preserves source-event refs, labels the payload DRY_RUN_ONLY, and does not claim live YOLO/ByteTrack, identity, memory, Qdrant, or recall proof.

Do not promote it as a live tracking proof yet. The current artifact proves dry-run geometry plumbing only.

Required schema changes

Before wiring this into the browser/modal as a durable contract, add or tighten these fields:

Output schema file

Add an explicit watch_ui_overlay_payload.schema.json.

Validate the generated payload against it, not only with json.tool and inline asserts.

Coordinate / render basis

Add coordinate_space, for example:

source: "video_frame_pixels"

frame_width

frame_height

normalized_basis: "percent_of_source_frame"

This prevents browser CSS transforms from silently changing the meaning of the box.

Temporal anchoring

Add anchor_media_time_seconds or valid_at_media_time_seconds.

The current payload uses a median bbox across three events while the representative event is the boundary event. That is fine for a still/modal dry-run, but dangerous for real-time rendering unless the bbox policy is explicit.

BBox policy

Add bbox_policy: "median_source_events" or "latest_event" / "representative_event".

For live overlays, prefer latest/representative event boxes; for evidence thumbnails, median/aggregate is acceptable if labeled.

Track lifecycle / stale handling

Add fields such as:

track_lifecycle_status

last_seen_media_time_seconds

expires_after_ms or stale_after_ms

This is required for drones/AO/many-stream overlays where tracks disappear, split, merge, or go stale.

Identity boundary

Rename or wrap entity as identity_candidate.

Add identity_status: "PROVISIONAL" and visibility_proof: false.

Keep Brave/movie-domain data as prior/candidate metadata only. Segment visibility must come from tracker/VLM/event evidence, not actor-domain data.

Proof scope

Keep top-level status: "DRY_RUN_ONLY".

Add proof_scope: ["geometry_plumbing"].

Explicitly exclude live_ml, identity, memory_write, qdrant_write, and recall.

Next bounded implementation step

Wire this payload into the existing Watch UI as a dry-run overlay fixture adapter, not a live YOLO/ByteTrack rung yet.

The next PR should do only this:

Add the output JSON schema.

Add a small UI adapter that maps watch.ui_overlay_payload.v1 into the existing Watch modal/player overlay.

Render the overlay from the payload, not hard-coded boxes.

Preserve the existing Watch table content: frame, playable segment, scene marker, SRT, audio audit, and explicit gaps.

Render identity as provisional, for example Marcus? or candidate: Marcus, not as proven visibility.

Do not call memory, Qdrant, recall, or evidence-case creation from this dry-run UI path.

That gives you a clean acceptance rung: “the browser can consume event-derived overlay geometry.” After that, the next rung can regenerate the same payload shape from live YOLO/ByteTrack events.

Proof commands/artifacts required before claiming progress

Minimum dry-run geometry/UI proof:

Bash
python3 skills/watch/scripts/build_tracking_overlay_payload.py
python3 -m json.tool skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json >/tmp/watch_overlay_payload.validated.json

Add a real output-schema validation command, for example:

Bash
python3 skills/watch/scripts/validate_watch_overlay_payload.py \
  --schema skills/watch/docs/architecture/watch_ui_overlay_payload.schema.json \
  --payload skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json

Required artifacts:

skills/watch/docs/architecture/watch_ui_overlay_payload.schema.json

regenerated watch_ui_overlay_payload.bad_santa_marcus.json

regenerated inspection.md

UI test fixture using the generated payload

browser/modal screenshot or Playwright trace proving the overlay was rendered from payload fields

test output proving table content was not deleted or hidden

negative test proving no hard-coded box renders when the payload is absent or bbox is changed

Suggested UI proof command, adapted to the repo’s actual package script:

Bash
pnpm test -- WatchReportView.overlay
pnpm exec playwright test watch-overlay-payload.spec.ts

Progress claim wording should remain:

Dry-run event-derived overlay geometry is wired into the Watch browser/modal overlay.

It should not say:

Live tracking works, Marcus is identified, memory recall works, Qdrant was written, or the segment proves character visibility.

<<<WEBGPT_DONE:20260627T200421Z:0e045280>>>
