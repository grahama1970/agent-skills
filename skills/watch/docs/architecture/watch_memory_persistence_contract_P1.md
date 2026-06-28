# Watch Memory/Qdrant/Arango Contract P1

## Collections

### Qdrant

Recommended collections:

- `watch_reference_embeddings`
- `watch_track_crop_embeddings`
- `watch_row_text_embeddings`
- `watch_segment_embeddings`

Point ids should be deterministic where possible:

```text
sha256:<schema>|<asset_id>|<entity_id>|<artifact_ref>|<embedding_model>|<version>
```

### Arango

Recommended document collections:

- `watch_assets`
- `watch_entities`
- `watch_reference_candidates`
- `watch_approved_references`
- `watch_tracks`
- `watch_track_observations`
- `watch_trace_observations`
- `watch_row_text_receipts`
- `watch_memory_write_receipts`
- `watch_recall_receipts`
- `watch_evidence_cases`

Recommended edge collections:

- `watch_asset_has_segment`
- `watch_asset_has_track`
- `watch_track_has_observation`
- `watch_observation_has_crop`
- `watch_observation_mentions_entity`
- `watch_entity_has_reference`
- `watch_doc_has_qdrant_point`
- `watch_case_has_observation`
- `watch_case_has_source_ref`

## Arango vector prohibition

Arango payloads must not contain:

- `vector`
- `embedding`
- `embeddings`
- `dense_vector`
- list-valued fields containing numeric vector arrays

Arango may contain:

- `qdrant_collection`
- `qdrant_point_id`
- `qdrant_point_ids`
- `embedding_model`
- source refs and artifact refs

## Write idempotence

Every memory write must be keyed by:

- `asset_id`
- `run_id`
- `trace_observation_id`
- `artifact_ref`
- `embedding_model`
- `schema_version`

Re-running the writer with the same inputs must upsert the same Qdrant point ids and Arango keys, not create duplicate graph facts.

## Recall contract

Recall is a memory operation, not UI scraping. A recall receipt must include:

- user query,
- intent classification,
- extracted entities,
- Arango query summary,
- Qdrant query summary,
- joined trace observations,
- source refs,
- answer mode: `answer`, `clarify`, or `deflect`,
- whether an evidence case was created.

If identity support is not proven, recall may return candidate/inconclusive trace observations but must answer with that status explicitly.
