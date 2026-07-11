# Phase 05 Autonomous Voice Selection Contract

Status: draft contract

Purpose: define how `persona-dream` may autonomously discover, test, and select
voice references without pretending that subjective voice curation is solved by
a single generated clip.

This contract applies to the `05 Voices` pane and the Tau creator/reviewer loop
that backs it.

## Operating Position

Voice work is allowed to be autonomous up to a receipt-backed default selection.
The final selected voice is still an artifact with provenance, quality evidence,
and reviewer rationale. It is not a hidden UI preference.

The autonomous lane may:

- search for candidate public/source audio when no existing approved voice
  reference exists;
- ingest and extract candidate clips;
- reject unusable clips deterministically;
- render Chatterbox demos from surviving candidates;
- rank candidates for a character;
- select a default candidate for autonomous dreaming.

The autonomous lane must not:

- silently clone a public person as the target identity;
- treat a YouTube/interview clip as final proof without extraction, audio
  quality, rights/provenance, and Chatterbox demo receipts;
- bypass the reviewer receipt;
- write `VOICE_READY` when Embry or Kai is missing a live non-mocked demo
  receipt and selected reference artifact.

## Required Loop

```text
voice-candidate-creator
  -> memory recall for existing persona_voice / persona_memory references
  -> Brave Search only if existing memory is insufficient
  -> ingest-youtube or local ingest for candidate media
  -> audio segmentation and technical rejection
  -> Chatterbox demo render
  -> voice_candidate_bundle.json

voice-candidate-reviewer
  -> verify source/provenance fields
  -> verify each accepted candidate has readable local audio
  -> verify each accepted candidate has a live non-mocked Chatterbox demo
  -> rank candidates per character
  -> select one default per required speaking character
  -> voice_selection_receipt.json
```

The creator/reviewer loop may repeat until:

- `voice_selection_receipt.status == "PASS_VOICE_SELECTION"`;
- max iterations are exhausted;
- a required character has no usable candidate and the reviewer writes
  `BLOCKED_VOICE_SELECTION`.

## Required Artifacts

The creator writes:

```text
voice_candidate_bundle.json
```

Schema:

```text
schemas/voice_candidate_bundle.schema.json
```

The reviewer writes:

```text
voice_selection_receipt.json
```

Schema:

```text
schemas/voice_selection_receipt.schema.json
```

The existing `voice_handoff_plan.json` may consume the selected voice references
only after `voice_selection_receipt.json` passes.

## Candidate Requirements

Each candidate must include:

- stable `candidate_id`;
- target `character_id`;
- `source_kind`: `memory`, `provided`, `youtube`, `local_file`, or `synthetic`;
- source URL or local source path;
- source provenance note;
- rights/use note;
- extracted audio path;
- duration seconds;
- transcript sample when available;
- speaker identity confidence;
- audio quality fields;
- Chatterbox demo text;
- Chatterbox demo WAV path;
- Chatterbox demo receipt path;
- tone, delivery stage, pace, pause strategy, and optional Chatterbox tags from
  `best-practices-chatterbox-agent`.

## Reviewer Requirements

The reviewer must reject a candidate when:

- the audio path is missing or unreadable;
- the Chatterbox demo receipt is missing;
- the receipt is mocked;
- the receipt is not live;
- the candidate has overlapping speakers;
- the speaker identity is ambiguous;
- the clip is dominated by music, crowd noise, effects, or compression;
- the rights/provenance note is absent;
- the candidate does not fit the character enough to use as the default.

The reviewer must select exactly one candidate per required speaking character
when status is `PASS_VOICE_SELECTION`.

## Phase 05 Gate Rule

Phase 05 passes when all required speaking characters have:

- a selected candidate in `voice_selection_receipt.json`;
- a readable reference WAV;
- a live non-mocked Chatterbox demo receipt;
- tone metadata using the canonical `best-practices-chatterbox-agent` tone
  vocabulary;
- a reviewer rationale.

If the project is preparing a Kling provider packet, local Chatterbox selection
is not enough for `voice_list` live submission. A provider voice id or explicit
provider-audio fallback must still be represented in the downstream provider
gate.

## UI Contract

The `05 Voices` pane should show:

- selected voice thumbnail/avatar for each speaking character;
- selected reference/demo playback;
- conversational `Tone` control;
- playback pause control;
- copyable payload/receipt reference;
- status derived from `voice_selection_receipt.json` or live audition receipts.

The UI may show alternate candidates, but alternates are secondary. The gate
uses the selected candidates and reviewer receipt.

## Fail-Closed Defaults

- If memory has accepted references, use them before web search.
- If no accepted memory reference exists, use Brave Search as raw source
  discovery evidence.
- If Brave Search or YouTube ingest fails, write `BLOCKED_VOICE_SOURCE_DISCOVERY`.
- If only one candidate survives, the reviewer may select it only if it passes
  all quality/provenance gates.
- If the system runs in experimental/non-commercial mode, record that in
  `rights_note`; do not remove source/provenance requirements.
