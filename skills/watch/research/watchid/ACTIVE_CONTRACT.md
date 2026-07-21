# WatchID Research Artifact Contract

MODE: EXECUTE_ARTIFACT

## Artifact

Create the first WatchID research protocol artifact and a minimal benchmark
episode schema.

## Input

- `skills/watch/SKILL.md`
- `skills/watch/README.md`
- `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- `skills/watch/proofs/immutable-goal/latest.json`
- `skills/watch/proofs/immutable-goal/091baa9b5d2ddaafffbbbde5b6af9379cc270264/manifest.json`
- `skills/watch/proofs/immutable-goal/091baa9b5d2ddaafffbbbde5b6af9379cc270264/api-row10-final-receipt.json`
- Human-provided WebGPT assessment that labels the current state
  `IMMUTABLE_GOAL_PROVEN`, `RESEARCH_GENERALIZATION_NOT_ESTABLISHED`, and
  `PAPER_DIRECTION_VALID`.

## Output Shape

- `PROTOCOL.md`: source-grounded research protocol for WatchID.
- `schemas/watchid_episode.v1.schema.json`: JSON Schema for one benchmark
  episode.
- `input_manifest.json`: local source list and proof boundaries.
- `inspection.md`: validation and grounding inspection.
- `status.md`: artifact status and next legal move.

## Must Include

- Immutable engineering proof boundary.
- Explicit statement that broad identity generalization is not established.
- Primary hypothesis and primary endpoint.
- Episode schema requirements for observations, interventions, expected
  identity segments, artifacts, and split metadata.
- Stop-aware identity metrics, baselines, ablations, falsification checks,
  reproducibility requirements, and ethics constraints.

## Must Not Include

- New engineering claims beyond the committed proof.
- New UI, service, Memory, Qdrant, detector, or receipt behavior.
- Private media paths as required reproduction inputs.
- Claims of production identity accuracy, full streaming runtime, RTSP, drone,
  or F36 implementation.

## Runtime/Tooling

- Markdown and JSON Schema files only.
- Validate JSON syntax with `jq`.
- Validate the schema with a Node JSON parse check.
- Inspect staged paths before commit.

## Inspection Method

- Parse all JSON artifacts.
- Confirm required protocol sections exist.
- Confirm no private absolute temporary or media-storage path is introduced in
  the research artifact.
- Confirm `git diff --name-only` is limited to
  `skills/watch/research/watchid/**`.

## Failure Conditions

- Malformed JSON.
- Missing proof boundary or missing non-generalization limitation.
- Broad product/research claims not supported by the current proof.
- Changes outside `skills/watch/research/watchid/**`.

## Allowed Writes

- `skills/watch/research/watchid/**`

## Forbidden Writes

- Watch UI, server, proof, docs outside the new research folder, Memory/Qdrant,
  and unrelated repository paths.

## Report Format

Report artifact paths, validation commands, commit SHA, pushed ref, status, and
next legal move.
