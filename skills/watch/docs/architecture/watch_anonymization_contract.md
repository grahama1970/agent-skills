# Watch Post-Detection Pixel Redaction Contract

Status: `BACKEND_CORE_IMPLEMENTED` — the compositor, CLI wiring, schemas, and
retained synthetic regression tests are implemented. UI target materialization,
a concrete local face detector, and the real-media immutable proof gate remain
separate follow-up work.

## Goal

Watch may alter pixels for explicitly selected YOLO/ByteTrack observations
without changing what the identity ledger says is true.

```text
source frame
  -> YOLO/ByteTrack observations
  -> accepted/suggested/manual anonymization-target policy
  -> face, upper-person, or full-track ROI
  -> gaussian, pixelated, or solid pixel redaction
  -> redacted JPEG/video frame + frame receipt
```

The feature is named anonymization for operator discoverability, but its durable
receipts deliberately claim **pixel redaction**, not successful anonymization or
de-identification. A face can be hidden while clothing, gait, voice, tattoos,
context, or metadata still identify the subject.

## Non-negotiable boundaries

1. Detector `track_id` remains an observation, not identity truth.
2. `accepted` targets are derived only from timed human events in a
   `watch.yolo_track_labels.v1` receipt. The receipt asset must match the
   requested asset, and each event must match its receipt's asset and row. The
   CLI does not trust a caller-created target
   manifest as accepted identity.
3. `suggested` targets may drive reversible frame-stream redaction. Permanent
   `--output-video` use requires the explicit `--allow-suggested-export` flag.
4. `manual-track` is an explicit operator choice and is never represented as
   accepted identity.
5. The compositor never writes `accept`, `identity_accepted`, or any
   `YoloReceiptStore` event. Each frame receipt fixes `identity_mutated=false`.
6. `reject`, `reset`, `reject_box`, and `reset_box` close the accepted target
   interval at their timestamp. A later accept opens a new decision.
7. A detector dropout may reuse the last ROI only for `--blur-hold-ms`. Once
   stale, that decision is retired; a reused `track_id` requires a new target
   decision.
8. Every target decision is bound to one `stream_id`, `asset_uid`, and
   `segment_id`. A wrong-scope or zero-target policy fails before the media
   source is opened; Watch must not create a plausible-looking unredacted export.
9. Stage-1 `watch.live_track_update.v1` events are unchanged. Redaction is a
   downstream rendering policy with its own receipts.
10. `--output-video` continues processing source frames after the observation
    event budget is exhausted. The event count may be bounded without silently
    truncating the pixel pass.
11. Redaction receipt files are created exclusively and never overwritten.
    Source media, authority receipts, target manifests, frame receipts, and
    output video must resolve to distinct paths.
12. This backend uses OpenCV `VideoWriter`; its `--output-video` artifact is
    video-only and does not preserve source audio. A release exporter must remux
    or explicitly strip-and-receipt audio rather than imply full-container parity.

## Target authorities

| `--blur-source` | Required input | Authority meaning | Permanent export default |
|---|---|---|---|
| `accepted` | `--blur-label-receipt` | Timed human acceptance projected until stop/reset/reassignment | Allowed |
| `suggested` | `--blur-target-manifest` | Tentative Memory/Qdrant or detector suggestion | Refused unless explicitly opted in |
| `manual-track` | Repeatable `--blur-track` | Explicit operator-selected observation | Allowed |

A `watch.anonymization_targets.v1` manifest is the typed handoff for tentative
or downstream-generated target decisions. It contains decision IDs, authority
source, stream, asset, segment, validity interval, track ID, optional
class/name/confidence, and an evidence reference. The manifest is not itself an
identity ledger.

## CLI examples

Accepted Willie export from the human ledger:

```bash
python skills/watch/scripts/live_ultralytics_tracking.py \
  --source /path/to/input.mp4 \
  --stdout-jsonl \
  --output-video /path/to/willie-redacted.mp4 \
  --blur-source accepted \
  --blur-character Willie \
  --blur-label-receipt /path/to/watch-yolo-labels.json \
  --blur-mode upper-person \
  --blur-style gaussian \
  --blur-strength 31 \
  --blur-hold-ms 750
```

Manual track export without an identity claim:

```bash
python skills/watch/scripts/live_ultralytics_tracking.py \
  --source /path/to/input.mp4 \
  --output-video /path/to/track-7-redacted.mp4 \
  --blur-source manual-track \
  --blur-track track_7 \
  --blur-mode person
```

Tentative live frame stream:

```bash
python skills/watch/scripts/live_ultralytics_tracking.py \
  --source /path/to/input.mp4 \
  --stdout-frame-jsonl \
  --blur-source suggested \
  --blur-character Willie \
  --blur-target-manifest /path/to/suggested-targets.json \
  --blur-mode face
```

A permanent suggestion-driven export adds `--allow-suggested-export`; the frame
receipts still say `identity_mutated=false` and `deidentification_claimed=false`.

## ROI behavior

| Requested mode | Person observation | Non-person observation |
|---|---|---|
| `face` | Use an injected local face detector and expand a face whose center remains inside the target person box by 1.6×; on missing model, exception, out-of-target result, invalid box, or miss, redact an expanded upper 45% of the person box | Redact the full expanded track box |
| `upper-person` | Redact an expanded upper 45% of the person box | Redact the full expanded track box |
| `person` | Redact the full expanded track box | Redact the full expanded track box |

The backend core intentionally has no network model download. A concrete face
localizer must be vendored or configured with a checksum and provenance receipt.
Until then, `face` mode fails safer by applying the upper-person fallback.

## Frame receipt

Every processed frame in an enabled session is appended to a JSONL file as
`watch.anonymization_frame_receipt.v1`. The receipt records:

- stream, asset, segment, source frame index, and media timestamp, all bound
  to the selected target scope;
- policy source, name filter, mode, style, strength, hold window, and target
  evidence SHA-256;
- every applied ROI, decision ID, track ID, authority source, fallback, and
  whether the last ROI was held across a detector gap;
- explicit non-applications such as a stale/retired track decision;
- raw in-memory input/output frame SHA-256 values;
- `identity_mutated=false` and `deidentification_claimed=false`.

This is compositor evidence. For redaction-enabled video output, Watch writes
the compositor frame rather than detector decorations added after its raw-frame
hash. A release proof must still hash and decode the encoded JPEG/video artifact,
verify frame/timeline coverage, and inspect negative controls.

## Failure behavior

Watch fails before opening the source when:

- anonymization options are present without `--blur-source`;
- accepted mode lacks a timed human label receipt;
- suggested mode lacks a typed target manifest;
- manual mode lacks at least one explicit track;
- a source/character policy selects no target decisions;
- suggestion-driven permanent export lacks explicit opt-in;
- the hold window cannot bridge both the requested and effective detector
  interval for permanent output;
- the target evidence belongs to another stream, asset, or segment;
- an accepted receipt or event is bound to a different asset/row, contains an
  unknown action, or has malformed timed values;
- target decisions overlap ambiguously or repeat a decision ID;
- an output path collides with source/evidence/receipt input;
- the receipt path already exists; or
- the output video writer cannot open.

At runtime, invalid boxes and expired tracks are retained as typed
non-applications rather than being silently ignored.

## Retained regression command

```bash
PYTHONPATH=skills/watch pytest -q \
  skills/watch/tests/test_watch_live_ultralytics_tracking.py \
  skills/watch/tests/test_watch_anonymizer.py
```

The focused suite covers accepted/suggested/manual authority separation,
stream/asset/segment binding, receipt-integrity rejection, non-target
preservation, face expansion, out-of-target face rejection, fail-safe localizer
fallback, stop/reset
boundaries, bounded hold, reused track IDs, ambiguous decision rejection, pixel
detail reduction, exclusive receipts, output-path collision rejection, receipt
schemas, redacted JPEG encoding, complete output-video frame count, and
continuation after the event budget is exhausted.

## Release proof still required

Synthetic OpenCV/fake-YOLO tests are not a release claim. Promotion requires a
clean-worktree Watch proof at the exact commit using real media and the real
Ultralytics/ByteTrack path. It must prove target recall, decoded pixel changes,
outside-ROI negative controls, stop/reset/reuse behavior, source/output frame
and duration parity, receipt-to-artifact hashes, audio-stream preservation or
explicit stripping, and that no accepted identity receipt was added by the
redaction run.

## Research basis

- Ultralytics documents `persist=True` as carrying tracks from the previous
  frame into the next frame in a sequence; that continuity is useful but does
  not turn a track ID into identity authority.
- OpenCV `FaceDetectorYN` is a suitable local face-localizer attachment point,
  provided the model and inference provenance are pinned.
- NIST IR 8053 treats multimedia de-identification as multimodal: faces,
  bodies, gait, voice, text, and context can all identify a person.
- Person re-identification research shows face blur can leave body-based
  matching largely effective. Watch therefore uses the narrower and verifiable
  term pixel redaction in receipts.

Sources:

- https://docs.ultralytics.com/modes/track/
- https://docs.opencv.org/4.10.0/df/d20/classcv_1_1FaceDetectorYN.html
- https://doi.org/10.6028/NIST.IR.8053
- https://arxiv.org/abs/2010.06307
