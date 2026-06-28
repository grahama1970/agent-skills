# Watch Identity Verifier Stack P1a

## Purpose

P1 defines the realtime identity memory loop. P1a pins down the default identity verifier stack so the system does not stop at "YOLO tracks people" or "Brave found cast photos".

The rule is:

```text
YOLO + ByteTrack propose person tracks.
Approved references + verifier lanes decide whether a track can become a named character.
Memory stores bounded trace evidence and recall receipts.
```

## Default Stack

| Layer | Default | Role | Boundary |
| --- | --- | --- | --- |
| Detector | Ultralytics YOLO person detection | Finds person/object observations in frames | Not named identity |
| Tracker | ByteTrack | Maintains temporal track continuity | Not identity |
| Face verifier | InsightFace / ArcFace-compatible embeddings | Strong identity signal when a usable face crop exists | May be absent in profile/occlusion |
| Body/costume verifier | OSNet/FastReID-style ReID embeddings | Supports identity continuity when face is weak, costume is stable, or angle changes | Weak alone; needs corroboration |
| Multimodal verifier | Jina CLIP/SigLIP/CLIP-style image/text embeddings | Compares approved references, frame crops, row text, and scene context | Similarity support, not authority |
| Storage | Qdrant + Arango | Qdrant stores vectors; Arango stores metadata/pointers | No raw vectors in Arango |

The detector/tracker stack is practical P1 infrastructure. The verifier stack is the identity gate.

## Reference Gate

Movies must hydrate references before ingest/tracking:

```text
Brave Image Search API / cast metadata -> candidate source refs
candidate images -> downloaded reference candidates
human/source approval -> approved references
approved references -> Qdrant/Jina embeddings
```

Canary/provisional threshold:

- Minimum approved references per character: `3`.
- Target approved references per character: `6`.
- Include at least two visual modes when possible:
  - face/portrait
  - costume/body/frame still
- If fewer than 3 approved images exist, identity promotion is disabled.

Drone/ITAR/RTSP/YouTube streams do not default to public search. They require a source-provided reference manifest or fail closed.

Brave Image Search API results are discovery inputs only. A result can help fill
the candidate queue for Billy Bob Thornton / Willie, but it cannot satisfy the
reference gate until the image is downloaded, rights/source-reviewed, approved,
embedded, and attached to a recall receipt.

## Verification Cadence

P1a starts with:

```yaml
verification_cadence_fps: 5
min_interval_ms_per_track: 200
```

This is a verification sampling cadence, not a requirement to run every verifier on every decoded frame. ByteTrack continues to maintain the track between verification samples.

## Promotion Policy

`IDENTITY_SUPPORTED` requires all of:

1. A stable `track_id`.
2. An approved reference package for the candidate entity.
3. At least one visual verifier lane above threshold.
4. No refuting verifier lane.
5. Segment/frame/crop refs attached to the decision.
6. Row text/transcript/context refs materialized when used.
7. Qdrant point ids and Arango metadata/pointers planned or written according to the proof level.

Default identity state remains:

```text
IDENTITY_INCONCLUSIVE
```

## Threshold Contract

The first concrete threshold profile is intentionally conservative:

| Lane | Canary threshold | Notes |
| --- | --- | --- |
| Face | `cosine >= 0.42` against approved entity refs | Placeholder until calibrated on local canaries |
| Body/costume ReID | `cosine >= 0.35` against approved entity refs | Must not promote alone |
| Multimodal image/text | `cosine >= 0.30` with supporting row text/context | Support only |
| Repeated crop agreement | `>= 2` sampled crops in same track/time range | Prevent one-frame promotion |

These values are canary thresholds, not production biometrics. Calibration must write a threshold receipt before any live identity claim.

## Fail-Closed Rules

Identity remains `IDENTITY_INCONCLUSIVE` when:

- the only evidence is YOLO/ByteTrack,
- the only evidence is Brave Search or cast text,
- reference images are candidates but not approved,
- fewer than 3 approved images exist for the entity,
- the row text materialization receipt is blocked for required source refs,
- Qdrant/Arango writes are only planned and the user asks for persistent recall,
- visual verifier lanes disagree,
- the crop is too blurry, occluded, or too small.

## Memory Interaction

P1a does not answer from raw detector events. It writes or plans trace observations that the Watch memory pipeline can later recall:

```text
intent classification
entity extraction
memory recall
evidence case creation only when bounded case anchoring is required
answer / clarify / deflect
```

For a query such as `find all movie segments with Willie`, Watch should retrieve stored trace observations and recall receipts, not scrape the visible table.
