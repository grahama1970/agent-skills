# Watch Realtime Identity Memory Loop P1

## Contract

Watch P1 turns realtime track observations into memory-addressable trace evidence without promoting unsupported identities. Movies are the current test case for the future AO/multi-stream system.

The contract is:

```text
reference hydration before ingest
+ YOLO/ByteTrack observation streaming
+ bounded 5 FPS verification sampling
+ approved-reference identity gate
+ row text/source-ref materialization
+ Qdrant/Jina embeddings
+ Arango metadata/pointers
+ memory recall proof
= grounded Watch trace memory
```

## Core data products

| Data product | Schema | Produced by | Proof level |
| --- | --- | --- | --- |
| Reference hydration plan | `watch.asset_reference_hydration_plan.v1` | asset registration/pre-ingest planner | dry-run / live |
| Reference manifest | `watch.reference_manifest.v1` | movie hydration or source manifest loader | dry-run / live |
| Realtime track event | `watch.realtime_track_event.v1` | YOLO + ByteTrack runtime | dry-run fixture / live ML |
| UI overlay event | `watch.ui_realtime_overlay_event.v1` | overlay adapter | dry-run / live |
| Identity verification result | `watch.identity_verification_result.v1` | verifier | dry-run / live |
| Trace observation | `watch.trace_observation.v1` | sampler/verifier | mocked / live persistence |
| Memory write receipt | `watch.memory_write_receipt.v1` | memory writer | mocked / live |
| Recall receipt | `watch.recall_receipt.v1` | memory recall adapter | live proof required |
| Evidence case | `watch.evidence_case.v1` | case builder | live proof required |

## Asset policies

Movie/cinema assets default to automatic domain candidate discovery before ingest. This may use Brave Search for cast/character source candidates, but those candidates are not scene truth and do not support identity by themselves.

Drone, ITAR, RTSP, YouTube, AO, and security-camera streams require source-provided manifests. The system must fail closed if the manifest is missing or incomplete. Public search is disabled by default for restricted stream classes.

## Runtime policy

- Run YOLO at the selected frame cadence for observation proposals.
- Run ByteTrack to maintain continuous `track_id` across frames.
- Emit track events as JSONL while the asset plays.
- Sample verification at a bounded 5 FPS target per stream.
- Extract crops/frame samples only for scheduled verification observations.
- Keep identity state separate from detector/tracker output.

## Identity policy

Identity remains `IDENTITY_INCONCLUSIVE` unless all required evidence is present:

1. approved reference image or source-provided reference package,
2. reference embedding in Qdrant with deterministic point id,
3. crop/frame embedding for the track observation,
4. row text or source-context ref for the time range,
5. no conflicting evidence,
6. memory persistence and later recall proof before user-facing memory claims.

## Memory policy

Arango stores metadata and Qdrant point ids. It must never store raw vector arrays. Qdrant stores embeddings. User-facing recall must run through the memory pipeline: intent classification, entity extraction, memory recall, evidence case creation only if needed, then answer/clarify/deflect.
