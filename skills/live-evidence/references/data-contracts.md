# Data Contracts

All external and cross-layer payloads are Pydantic models.

## `live_evidence.transcript_event.v1`

A single interim, stabilized, or final speaker turn. Text is bounded, speaker
and source use closed vocabularies, and timestamps must be timezone-aware.

## `live_evidence.evidence_source.v1`

One source candidate from Memory, indexed code, ripgrep, Brave, or Dogpile. It
carries lane, excerpt, score, freshness, and a source locator. A source without
an excerpt or locator cannot become the primary proof line.

## `live_evidence.evidence_card.v1`

The human-facing unit. It carries:

- a compact talking point;
- a proof line derived from selected sources;
- a visible qualification;
- confidence and freshness;
- source references and retrieval lanes.

An insufficient card explicitly says no source-bound support was found.

## `live_evidence.app_snapshot.v1`

The UI state sent over REST and SSE. The React client does not infer hidden
backend state from prose.
