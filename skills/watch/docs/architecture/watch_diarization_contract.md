# Watch Diarization And Speaker Attribution Contract

Status: `CONTRACT_DEFINED_NOT_IMPLEMENTED`

## Purpose

Watch needs an audio evidence lane for "who spoke when." This lane must
complement frames, captions/SRT, Whisper, scene rows, YOLO tracks, and the
immutable identity ledger. It must not replace any of them.

The selected provider contract is pyannote Community-1 through a future local
HTTP service. The service is not implemented by this artifact.

## Evidence Layers

```text
SRT/captions = subtitle, script, and cue evidence
Whisper      = acoustic text evidence
pyannote     = anonymous who-spoke-when evidence
YOLO/tracks  = visual person observations
human review = accepted identity decision
```

Pyannote diarization must never mutate transcript text, SRT text, YOLO identity
receipts, or accepted character identity.

## Artifact Contracts

The durable diarization receipt is defined by:

```text
skills/watch/docs/architecture/schemas/watch_diarization.schema.json
```

It records:

- `schema: watch.diarization.v1`
- `status`
- provider/model/library/device
- source audio path and source audio hash
- source-timeline analysis range
- regular speaker turns
- exclusive speaker turns
- structured failure codes

The derived transcript-speaker attribution artifact is defined by:

```text
skills/watch/docs/architecture/schemas/watch_speaker_attribution.schema.json
```

It records:

- transcript source
- diarization artifact pointer
- assigned, mixed, and unassigned segment counts
- per-segment anonymous speaker evidence
- explicit identity boundary fields

## Failure Codes

The stable failure vocabulary is:

```text
DIARIZATION_DISABLED
DIARIZATION_SERVICE_UNAVAILABLE
DIARIZATION_AUTH_REQUIRED
DIARIZATION_MODEL_LOAD_FAILED
DIARIZATION_TIMEOUT
DIARIZATION_AUDIO_INVALID
DIARIZATION_DURATION_EXCEEDED
DIARIZATION_NO_SPEECH
DIARIZATION_INFERENCE_FAILED
```

When diarization is attempted and unavailable, Watch must write a structured
receipt with `safe_default: continue_without_speaker_attribution`. A later
implementation may make `--require-diarization` fail the run after diagnostic
artifacts are written.

## Timeline Rule

Focused Watch runs must emit source-timeline diarization timestamps, not
clip-relative timestamps. If a focused clip starts at 168.0 seconds and pyannote
returns a local turn at 0.5 seconds, Watch must persist the turn start as
168.5 seconds.

## Identity Boundary

Anonymous speaker labels are not identity:

```text
SPEAKER_00 != Willie
SPEAKER_01 != Marcus
SPEAKER_02 != narrator
```

Those mappings require separate evidence and must remain candidates until the
existing Watch identity ledger accepts them. No pyannote cluster may auto-accept
or silently promote an actor, character, or real-world identity.

## Current Non-Implementation Boundary

This contract artifact does not add:

- a pyannote service
- CLI flags
- canonical audio refactoring
- transcript attribution code
- report rendering changes
- memory persistence changes
- UI speaker filters or chips
- live model proof

The next artifact should implement the persistent local pyannote service or the
model-free speaker-attribution algorithm, but not both in the same slice.
