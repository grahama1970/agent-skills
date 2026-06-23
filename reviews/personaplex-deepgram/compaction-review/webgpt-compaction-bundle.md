# Advisory WebGPT Review Bundle: PersonaPlex Conversation Compaction For Memory Recall

## Review Type

Advisory architecture/plan review. This is not a closure gate and must not be
treated as implementation proof.

## Reviewer Persona Requested

Act as an Orpheus/PersonaPlex voice-conversation systems reviewer who also
understands retrieval memory systems. Focus on how conversation compaction should
preserve live voice continuity while keeping `$memory /recall` effective across
BM25, dense semantic recall, and multi-hop graph traversal.

## Objective

Recommend a concrete conversation-history compaction contract for the
PersonaPlex + Deepgram + `$memory` routing flow.

The design must fit this lifecycle:

1. Assign persona/session before audio.
2. Deepgram produces transcript with `speech_final=true`.
3. Wrapper creates `session_id`, active `turn_id`, closes output gate, and
   cancels stale tasks.
4. Wrapper selects compact session history from `$memory` before `/memory /intent`.
5. `/memory /intent` returns action, confidence, recall profile, required
   artifacts, extracted entities, frameworks, keywords, query plan, tool calls,
   allowed tools, disallowed tools, and dependencies.
6. Wrapper validates the intent-recommended tools.
7. Wrapper calls `/memory /recall` for query-specific route context.
8. Route goes to `/memory /deflect`, `/memory /clarify`,
   `/create-evidence-case`, or `/memory /answer`.
9. Output is bounded to the active turn and released only when safe.
10. Wrapper writes turn receipt through `/memory /upsert`.
11. Wrapper compacts/upserts session summary when a budget threshold trips.
12. Next turn cancels stale work.

## Current Artifacts

These files exist locally in the project:

- `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
- `reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json`
- `scratch.md`
- `.codex/ui-verification/latest.json`

The current DAG validated with:

```json
{
  "ok": true,
  "node_count": 19,
  "layer_count": 14,
  "warnings": []
}
```

The latest visual verification marker exists locally, but the browser reviewer
cannot inspect local screenshot paths. Treat the chart content included in this
bundle as the review target; do not rely on filesystem access.

## Relevant `$memory` Contract

Important constraints from `skills/memory/SKILL.md`:

- `/intent` is the deterministic route and QuerySpec product.
- `/intent` does not perform recall internally.
- Callers should call `/intent` first, then pass `recall_profile` explicitly to
  `/recall` when retrieval is required.
- `/intent` must expose recommended skills/tools through `query_plan`,
  `tool_calls`, `allowed_tools`, `disallowed_tools`, dependencies, and required
  artifacts. The wrapper should not invent a separate tool-selection policy.
- `/intent` must expose extracted entities, valid entities, unresolved terms,
  frameworks, keywords, and tag families so compaction can preserve the anchors
  recall needs.
- `/recall` returns `{found, should_scan, confidence, items, meta, errors}`.
- Results are in `items`, not `results`.
- Recall combines BM25 lexical matching, dense semantic recall through Qdrant,
  and graph traversal.
- Persona recall must be question-shaped, not keyword piles.
- Persona recall should inspect `_key`, `persona_id`, `retrieval_text`,
  `scores.bm25`, `scores.dense`, `scores.graph`, `tom_state_type`, `tom_tags`,
  `emotion`, `stance`, relationship edges, and salience fields.
- Do not write inline vectors into Arango documents.
- `/store` writes a single document to any collection and auto-upserts by `_key`.
- `/upsert` is the batch write endpoint and follows the same canonical document
  rules.
- A collection such as `conversation_history` is trivial to add through
  `/memory /upsert`; the compaction design should include it directly instead of
  treating persistence as a later add-on.
- Memory is a durable registry of observations, not a live scanner.

## Known Execution Risk

The current live wrapper still has a separate execution bug:

- Current `personaplex_golden_state_server.py` uses one shared
  `injection_tokens` queue and one shared `OutputGate`.
- New Deepgram turns spawn another grounding task without cancelling older
  grounding tasks.
- Prior live proof showed `queue_depth=268` when gate opened.

This review is about compaction design, not fixing that task leak directly.
However, compaction must be compatible with a future turn-aware state machine.

## Proposed Storage Surfaces

The project currently proposes:

### Collection: `conversation_history`

This should be the canonical append/update collection for turn-level
conversation records. The project can alias or specialize it later, but the MVP
should use a plainly named collection because `$memory /upsert` can write any
collection.

Deterministic key:

```text
conversation:{session_id}:{turn_id}
```

Candidate fields:

- `_key`
- `kind: "conversation_turn"`
- `session_id`
- `turn_id`
- `persona_id`
- `created_at`
- `transcript`
- `normalized_query`
- `assistant_response_excerpt`
- `user_audio_artifact_key`
- `assistant_audio_artifact_key`
- `user_audio_uri`
- `assistant_audio_uri`
- `audio_sha256`
- `audio_codec`
- `audio_sample_rate_hz`
- `audio_duration_ms`
- `audio_retention_class`
- `audio_embedding_state`
- `audio_qdrant_collection`
- `audio_qdrant_point_id`
- `intent_action`
- `intent_confidence`
- `intent_classifier_source`
- `recall_profile`
- `recall_profile_source`
- `required_artifacts`
- `extracted_entities`
- `valid_entities`
- `unresolved_terms`
- `frameworks`
- `keywords`
- `tom_tags`
- `emotion`
- `stance`
- `sparta_tags`
- `query_plan`
- `tool_calls`
- `allowed_tools`
- `disallowed_tools`
- `depends_on`
- `route_endpoint`
- `source_refs`
- `recall_item_keys`
- `evidence_case_key`
- `response_packet_hash`
- `gate_closed_at`
- `gate_opened_at`
- `queue_depth_at_release`
- `stale_turn_dropped_count`
- `safety_outcome`
- `tags`

### Optional Specialized Collection: `personaplex_turns`

If we want a voice-specific projection, it should duplicate or derive from
`conversation_history`, not replace it.

Deterministic key:

```text
personaplex:{session_id}:{turn_id}
```

Candidate fields:

- `_key`
- `kind: "personaplex_turn"`
- `session_id`
- `turn_id`
- `persona_id`
- `created_at`
- `transcript`
- `normalized_query`
- `intent_classifier_source`
- `intent_action`
- `intent_confidence`
- `recall_profile`
- `recall_profile_source`
- `required_artifacts`
- `extracted_entities`
- `valid_entities`
- `unresolved_terms`
- `frameworks`
- `keywords`
- `tom_tags`
- `emotion`
- `stance`
- `sparta_tags`
- `query_plan`
- `tool_calls`
- `allowed_tools`
- `disallowed_tools`
- `depends_on`
- `route_endpoint`
- `source_refs`
- `recall_item_keys`
- `evidence_case_key`
- `response_packet_hash`
- `final_response_excerpt`
- `user_audio_artifact_key`
- `assistant_audio_artifact_key`
- `user_audio_uri`
- `assistant_audio_uri`
- `audio_sha256`
- `audio_codec`
- `audio_sample_rate_hz`
- `audio_duration_ms`
- `audio_retention_class`
- `audio_embedding_state`
- `audio_qdrant_collection`
- `audio_qdrant_point_id`
- `gate_closed_at`
- `gate_opened_at`
- `queue_depth_at_release`
- `stale_turn_dropped_count`
- `safety_outcome`
- `tags`

### Collection: `personaplex_sessions`

Deterministic key:

```text
personaplex_session:{session_id}
```

Candidate fields:

- `_key`
- `kind: "personaplex_session_summary"`
- `session_id`
- `persona_id`
- `updated_at`
- `summary_text`
- `conversation_history_keys`
- `active_entities`
- `active_valid_entities`
- `unresolved_terms`
- `active_controls`
- `active_frameworks`
- `active_personas`
- `open_questions`
- `recent_turn_keys`
- `salient_turn_keys`
- `thread_tags`
- `tom_tags`
- `emotion`
- `stance`
- `relationship_edges`
- `evidence_case_keys`
- `last_compacted_turn_id`
- `compaction_policy_version`
- `source_turn_range`
- `tags`

### Optional Rolling Summary Collection: `conversation_history_summaries`

If a single mutable session record becomes too lossy, use rolling summaries with
deterministic range keys:

```text
conversation_summary:{session_id}:{start_turn_id}:{end_turn_id}
```

These records should preserve entity/control/framework/tag anchors and link back
to the exact `conversation_history` turn keys they summarize.

## Audio Artifact And Embedding Contract

PersonaPlex should preserve per-turn sound files, but they should not be stored
as blob fields inside Arango documents. The turn record should store stable
artifact references and hashes, while the audio bytes live in an artifact store
or filesystem path managed by the wrapper.

Recommended MVP behavior:

1. Store user audio and assistant audio as immutable artifacts per turn.
2. Write artifact metadata into `conversation_history` via `/memory /upsert`.
3. Use Deepgram transcript, normalized query, final response excerpts, entities,
   tags, and route metadata as the default BM25 and dense-text recall surface.
4. If the memory stack supports an audio/multimodal Qdrant lane, create audio
   embeddings in Qdrant and store only pointer metadata on the turn document:
   `audio_qdrant_collection`, `audio_qdrant_point_id`,
   `audio_embedding_model`, `audio_embedding_version`, and
   `audio_embedding_state`.
5. Do not write raw audio vectors or audio blobs into ArangoDB.

Open design question for review: should the project add a dedicated
`conversation_audio_artifacts` collection keyed by
`conversation_audio:{session_id}:{turn_id}:{role}`, or are audio artifact fields
on `conversation_history` enough for the MVP?

Audio recall should be treated as supplemental. `$memory /recall` should answer
normal conversation questions from text transcript and structured route fields
first. Audio-vector recall is valuable for voice-continuity queries such as
prosody, interruption timing, emotional tone, pacing, and reproducing the sound
of a previous turn, but it should not replace transcript/evidence grounding for
compliance answers.

## Question For WebGPT

Given the memory system above, what is the optimal conversation compaction
contract for PersonaPlex?

Please answer with a concrete design, not a generic summary. Include:

1. What fields should be stored per turn so BM25 recall works well?
2. What fields should be stored per turn/session so dense semantic recall works well?
3. What fields/edges/tags should be stored so multi-hop graph traversal works?
4. What should be selected before `/memory /intent` versus after `/intent`?
5. What should never be compacted away?
6. What should be summarized, and at what threshold?
7. How should compliance/security/evidence-case turns differ from persona/social turns?
8. How should compaction preserve Orpheus/PersonaPlex voice continuity without
   letting conversational vibe override grounding?
9. Should session summaries be one mutable record, rolling window records, or
   both?
10. Should `conversation_history` be the canonical collection, with
    `personaplex_turns` as an optional voice-specific projection, or should the
    project only use a specialized collection?
11. How should `/memory /intent` recommended skills/tools and extracted entities
    be stored so future turns can recall and reuse them without reclassifying
    stale context?
12. How should raw audio artifacts and optional audio embeddings be stored so
    they are available to future `$memory /recall` without polluting Arango with
    blobs or inline vectors?
13. What deterministic acceptance tests should the project add before coding
    this compaction slice?

## Expected Output Shape

Return:

- Verdict: `ADVISORY_READY`, `NEEDS_CHANGES`, or `BLOCKED`.
- A recommended schema for `personaplex_turns`.
- A recommended schema for `conversation_history`.
- A recommended schema for `personaplex_sessions`.
- Whether rolling `conversation_history_summaries` are required.
- Whether a `conversation_audio_artifacts` collection is needed.
- A recommended audio artifact and optional Qdrant audio embedding contract.
- A route-time selection algorithm.
- A compaction trigger policy.
- A list of test fixtures and expected recall behavior.
- Any risks that would make the current proposal unsafe for `$memory` recall.

## Local Acceptance Gate After Review

The project agent will not claim implementation success from this review alone.
After reconciling the advice, local proof must include at minimum:

- schema validation for proposed turn/session records,
- deterministic `/memory /upsert` dry-run or live proof against test records,
- `/memory /recall` checks showing BM25, dense, and graph-relevant fields survive,
- multi-turn probe showing compaction does not break active route selection,
- evidence that compliance turns route to clarify/evidence/fallback safely.
