# Watch Realtime Overlay Event Contract P1

## Purpose

The existing Watch modal/player needs a live data contract. P1 does not redesign the UI; it specifies what the overlay may consume.

## Contract

Schema: `watch.ui_realtime_overlay_event.v1`

Each event represents an overlay render update derived from a track event and optional identity verification status.

Required fields:

- `schema`
- `run_id`
- `asset_id`
- `stream_id`
- `track_id`
- `event_index`
- `media_time_s`
- `frame_ref`
- `bbox`
- `coordinate_space`
- `identity_status`
- `display_label`
- `source_event_ref`
- `stale_after_ms`
- `proof_scope`

Allowed display behavior:

- `OBSERVATION_ONLY`: draw unlabeled person/object box or track id.
- `IDENTITY_CANDIDATE`: draw candidate label with explicit uncertainty marker.
- `IDENTITY_INCONCLUSIVE`: draw candidate/inconclusive label only if useful for debugging/review.
- `IDENTITY_SUPPORTED`: draw supported label only when verifier has approved reference + source evidence.
- `IDENTITY_REFUTED`: hide identity label or show refuted debug state.

The UI must not infer identity from detector label, actor metadata, Brave Search result text, or table row text visible in the DOM.
