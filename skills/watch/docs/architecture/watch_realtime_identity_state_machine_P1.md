# Watch Realtime Identity State Machine P1

## States

| State | Meaning | Allowed next states |
| --- | --- | --- |
| `ASSET_REGISTERED` | Asset exists in Watch registry. | `REFERENCE_DISCOVERY_PLANNED`, `SOURCE_REFERENCE_MANIFEST_REQUIRED`, `FAIL_CLOSED` |
| `REFERENCE_DISCOVERY_PLANNED` | Movie-domain candidate search or manifest loading is planned. | `REFERENCE_CANDIDATES_COLLECTED`, `FAIL_CLOSED` |
| `REFERENCE_CANDIDATES_COLLECTED` | Candidate sources exist, not approved identity evidence. | `REFERENCE_IMAGES_DOWNLOADED`, `REFERENCE_IMAGES_PENDING_APPROVAL`, `FAIL_CLOSED` |
| `REFERENCE_IMAGES_DOWNLOADED` | Local candidate artifacts exist. | `REFERENCE_IMAGES_PENDING_APPROVAL`, `FAIL_CLOSED` |
| `REFERENCE_IMAGES_PENDING_APPROVAL` | Human/source approval required. | `REFERENCE_EMBEDDINGS_READY`, `FAIL_CLOSED` |
| `REFERENCE_EMBEDDINGS_READY` | Approved references have deterministic Qdrant point ids. | `INGEST_READY` |
| `INGEST_READY` | Asset can be ingested/tracked with identity gate configured. | `TRACK_STREAM_ACTIVE` |
| `TRACK_STREAM_ACTIVE` | ML observations are streaming. | `TRACK_OBSERVATION_CAPTURED` |
| `TRACK_OBSERVATION_CAPTURED` | A bounded crop/frame observation exists. | `IDENTITY_CANDIDATE`, `IDENTITY_INCONCLUSIVE` |
| `IDENTITY_CANDIDATE` | Candidate identity label exists but is not supported. | `IDENTITY_SUPPORTED`, `IDENTITY_INCONCLUSIVE`, `IDENTITY_REFUTED`, `NEEDS_HUMAN_REVIEW` |
| `IDENTITY_SUPPORTED` | Approved references plus source evidence support identity. | `ROW_TEXT_MATERIALIZED`, `MEMORY_WRITE_PLANNED` |
| `IDENTITY_INCONCLUSIVE` | Evidence insufficient or ambiguous. | `ROW_TEXT_MATERIALIZED`, `MEMORY_WRITE_PLANNED`, `NEEDS_HUMAN_REVIEW` |
| `IDENTITY_REFUTED` | Evidence contradicts candidate identity. | `ROW_TEXT_MATERIALIZED`, `MEMORY_WRITE_PLANNED` |
| `ROW_TEXT_MATERIALIZED` | Required source channels have source refs and materialized text. | `MEMORY_WRITE_PLANNED` |
| `MEMORY_WRITE_PLANNED` | Persistence payload prepared, no live write claim yet. | `MEMORY_PERSISTED`, `FAIL_CLOSED` |
| `MEMORY_PERSISTED` | Qdrant/Arango/memory receipt exists. | `RECALL_VERIFIED` |
| `RECALL_VERIFIED` | Memory recall returns trace evidence by entity/time. | `CASE_ANCHOR_CREATED` |
| `CASE_ANCHOR_CREATED` | Bounded evidence case exists. | terminal |

## Fail-closed transitions

- Unknown asset class -> `FAIL_CLOSED`.
- Drone/ITAR/RTSP/YouTube without source manifest -> `SOURCE_REFERENCE_MANIFEST_REQUIRED` / `FAIL_CLOSED`.
- Movie with only Brave Search candidates -> tracking may continue, identity support disabled.
- Missing approved references -> `IDENTITY_INCONCLUSIVE`.
- Detector-only identity -> `IDENTITY_INCONCLUSIVE`.
- Missing row-text source refs -> `ROW_TEXT_MATERIALIZATION_BLOCKED` and no user-facing recall claim.
- Planned-only Qdrant/Arango writes -> no `MEMORY_PERSISTED`.
- Recall not proven -> no user-facing memory answer; answer must clarify/deflect.
