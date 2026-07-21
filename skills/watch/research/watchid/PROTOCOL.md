# WatchID Protocol

## Purpose

WatchID is the research track for Watch's stop-aware identity ledger. It turns
the current immutable engineering proof into a falsifiable research protocol
without expanding the claim beyond the evidence.

The current committed proof establishes a narrow systems invariant: detector
track ids are observations, Memory/Qdrant returns tentative suggestions, human
accept/stop/reassign decisions persist, identity does not cross a stop, and
the accepted state hydrates after reload. It does not establish broad identity
recognition, production accuracy, or naturalistic long-horizon tracking.

## Current Evidence Boundary

Accepted engineering evidence:

- Proof manifest:
  `skills/watch/proofs/immutable-goal/091baa9b5d2ddaafffbbbde5b6af9379cc270264/manifest.json`
- Manifest status: `PASS`
- Proof scope: `mocked=false`, `live=true`
- Live canary: row 9 Memory/Qdrant tentative Marcus suggestion.
- Deterministic lifecycle canary: row 10 proof-only asset with
  `accept(Marcus) -> reject_box(stop) -> accept(Willie)`.
- Row 10 receipt event sequences: `1, 2, 3`.
- Row 10 final accepted top-level label: Willie.
- Row 10 stop interval projection: null between the stop and reassignment.

Research limitations that remain open:

- General identity recognition is not established.
- Broad handoff, occlusion, and detector-track reuse coverage is not
  established.
- Multi-video and multi-domain generalization are not established.
- Public benchmark performance is not established.
- The live proof depends on local service/media state and is not yet a public
  reproduction package.

## Research Claim Under Test

At a fixed human workload budget, stop-aware, human-governed identity memory
reduces identity boundary leakage compared with detector-track propagation and
memory-assisted auto-propagation that lacks explicit stop barriers.

The first paper-scale claim must stay narrower than "general video
understanding." The research claim is about identity state governance over
detector observations.

## Primary Hypothesis

When detector tracks switch, merge, split, or become semantically stale, an
explicit stop barrier prevents the previous accepted identity from leaking into
the interval before a later explicit reassignment.

Formally, for a stop at `t_s` and the next explicit acceptance at `t_a`, the
projected identity must be null for every evaluated instant:

```text
projection(track_id, t) = null for all t where t_s <= t < t_a
```

No detector track id, held overlay, interpolation, Memory suggestion, recall
score, or top-level legacy label may override that barrier.

## Primary Endpoint

Identity Boundary Leakage Rate, abbreviated `IBLR`:

```text
IBLR = leaked_pre_stop_identity_frames / evaluated_frames_in_stop_interval
```

A leaked frame is any evaluated frame in `[t_s, t_a)` where the visible or API
projected identity equals the pre-stop identity.

The primary endpoint is the difference in `IBLR` between WatchID and each
baseline on held-out episodes. The expected value for deterministic replay of a
valid WatchID receipt is zero; naturalistic tracking experiments must still
measure it from the generated projections.

## Secondary Metrics

- Stop compliance: fraction of stop interventions that immediately project
  null identity.
- Reassignment latency: time from explicit accept to correct visible/API
  projected identity.
- Segment purity: fraction of evaluated frames inside accepted segments with
  the expected identity.
- Suggestion precision at coverage: correctness of tentative suggestions at
  confidence thresholds chosen on validation data only.
- Suggestion non-interference: suggestion-only queries that leave the accepted
  receipt event count unchanged.
- Human actions per correct identity-minute: annotation cost normalized by
  correctly projected identity duration.
- Restart replay equivalence: exact projection equality before and after UI
  reload or process restart.
- Memory sync durability: accepted human events remain locally durable when
  remote Memory sync fails, then store exactly once after retry.
- Negative memory contamination: rejected or stopped crops must not improve
  future suggestion confidence for the rejected identity unless explicitly
  accepted later.

## Benchmark Episode Unit

Each episode is one bounded video or synthetic-proof clip interval with a
single canonical asset id, detector observations, human interventions, expected
identity segments, and artifact hashes.

The minimal machine-readable shape is defined by:

```text
skills/watch/research/watchid/schemas/watchid_episode.v1.schema.json
```

An episode must include:

- `video_id` and stable source metadata.
- `asset_uid` scoped to the episode.
- `split`: `train`, `validation`, or `test`.
- `observations`: detector boxes or track observations.
- `interventions`: human accept, stop, reject, reset, or reassignment events.
- `expected_segments`: the identity projection expected over time.
- `artifacts`: repo-relative or dataset-relative hashes for source assets,
  detector logs, receipts, and screenshots where available.
- `limitations`: known reasons the episode should not be overclaimed.

The committed row 10 proof-only asset can seed the first episode because it
tests the state machine. It must be labeled as `synthetic_proof_asset` and must
not be counted as evidence for naturalistic identity recognition.

## Dataset Construction

Build the dataset in stages:

1. Seed with the committed row 10 proof-only lifecycle episode.
2. Add the row 9 live Memory/Qdrant suggestion canary as a suggestion-only
   episode with no accepted identity mutation.
3. Add public or consented naturalistic video episodes with pseudonymous
   identities.
4. Add hard negative episodes where the correct behavior is abstention or null
   identity.
5. Freeze the validation split before choosing thresholds.
6. Keep the test split identity-disjoint and video-disjoint from training and
   validation.

Required episode families:

- Occlusion and re-entry.
- Detector track id switch.
- Detector track id reuse for a different person.
- Multiple people in frame.
- Visually similar people.
- Stop followed by no reassignment.
- Stop followed by reassignment to a different identity.
- Incorrect high-confidence Memory suggestion.
- Open-set person absent from Memory.
- Remote Memory failure between local persistence and sync.

## Baselines

Minimum baselines:

1. Detector `track_id` treated as identity.
2. Detector track id with label propagation until the track disappears.
3. Detector tracking plus conventional re-identification embedding.
4. Memory suggestion rendered directly as identity without human accept.
5. WatchID without stop barriers.
6. WatchID without durable event history.
7. WatchID without Memory suggestions.
8. WatchID with rejected/stopped crops allowed as positive suggestion evidence.

The critical ablation is WatchID without stop barriers. If that ablation does
not leak more identities or require more human correction, the stop-aware
ledger is not carrying the claimed research value.

## Evaluation Procedure

For each frozen episode:

1. Load detector observations and source artifact hashes.
2. Replay interventions in timestamp order with idempotency keys.
3. Query tentative suggestions only through the Watch/Memory API path.
4. Export the accepted receipt and temporal projections at sampled times.
5. Compute `IBLR` and secondary metrics from projections, not from detector
   track ids.
6. Restart the Watch API or reload the UI and recompute projections.
7. Compare replay projections to pre-restart projections.
8. Record all commands, hashes, and raw predictions.

Thresholds and confidence cutoffs must be selected on validation data only.
The test split cannot be re-run for threshold search.

## Falsification Checks

A result fails the protocol when any of these occur:

- The pre-stop identity appears during `[t_s, t_a)`.
- A suggestion-only query appends or mutates an accepted identity event.
- A legacy top-level label overrides an event history with a stop.
- A failed Memory sync exists only in an HTTP response and not in durable local
  receipt state.
- A rejected or stopped crop becomes positive evidence without later human
  acceptance.
- The same episode projects different identities after restart/reload.
- The benchmark depends on private absolute paths or unhashable source assets.
- Any public result omits raw predictions or metric code.

## Reproducibility Requirements

Paper-ready WatchID results require:

- Public, generated, or consented media assets.
- Dataset manifest with SHA256 hashes.
- Pinned detector, embedding, and Memory service configurations.
- Containerized Memory/Qdrant dependencies or a documented equivalent.
- Raw detector observations, intervention logs, receipts, projections, and
  predictions.
- Metric implementation committed with tests.
- One command that regenerates metrics from the dataset manifest.
- Hardware and runtime metadata for live experiments.
- Clear separation between deterministic proof assets and naturalistic
  identity-recognition episodes.

The current immutable proof is sufficient for the engineering invariant. It is
not by itself sufficient for paper-ready generalization.

## Ethics And Governance

WatchID evaluations must:

- Prefer pseudonymous identities in datasets and reports.
- Avoid inferring protected attributes.
- Document consent, license, or public-domain status for media.
- Provide deletion/revocation semantics for identity memory.
- Preserve rejected and stopped evidence as governance state, not as hidden
  positive training labels.
- Treat all model suggestions as uncertain until accepted by a human or by a
  separately approved policy.
- Avoid autonomous enforcement, targeting, or engagement claims.

## First Accepted Benchmark Seed

The first seed episode is the committed row 10 proof-only lifecycle:

```text
asset_uid: watch_immutable_proof_asset
row_index: 10
track_id: track_15
events:
  1. accept Marcus at 1.00 seconds
  2. reject_box stop at 1.79 seconds
  3. accept Willie at 4.54 seconds
expected:
  [0.00, 1.00): null
  [1.00, 1.79): Marcus
  [1.79, 4.54): null
  [4.54, 8.00]: Willie
```

This seed is accepted only for state-machine and replay semantics. It is not
accepted as evidence that the visual model recognized Marcus or Willie in
natural footage.

## Next Research Artifact

The next legal artifact is one concrete seed episode JSON file conforming to
`watchid_episode.v1.schema.json`, derived from the row 10 committed receipt and
explicitly labeled `synthetic_proof_asset`.
