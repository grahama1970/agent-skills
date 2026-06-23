# PersonaPlex Compliance Memory Routing Decision Tree

Artifact source:

- DAG JSON: `reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json`
- HTML review chart: `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
- Validator: `skills/phart-dag-chart/run.sh validate reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json --json`
- Renderer: `skills/phart-dag-chart/run.sh chart reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json`
- Source model status: greenfield chart/doc sanity artifact only. These files describe the agreed architecture and do not prove live wrapper behavior.

## Primary Question

Does every realistic multi-turn compliance conversation pass through persona assignment, history selection, current-turn memory intent/tool authorization, recall, clarify/deflect/evidence gates, bounded output gating, and canonical memory persistence before PersonaPlex is allowed to continue?

## Source-Derived Step Model

1. Establish artifact boundary.
   - Status: chart/doc artifact only.
   - Required interpretation: this model is inspectable architecture evidence, not live PersonaPlex, Deepgram, memory, evidence-case, or browser proof.

2. Assign the persona/session before audio.
   - Required state: `session_id`, `persona_id`, voice/golden-state context, stable persona context.
   - Historical recommendations from older turns may be loaded for audit/context only; they are not authority for the new turn.

3. Deepgram finalizes a user audio turn.
   - Required input: transcript with `speech_final=true`.
   - Optional raw audio is retained only as artifact metadata later; do not store audio blobs in Arango.

4. Wrapper creates active turn state.
   - Required state: deterministic `turn_id`, active route state, closed output gate, stale task cancellation/fencing, cleared stale token queues.
   - Latest-turn-wins starts here.

5. Select compact conversation history from memory before intent.
   - Memory role: recall stored session summaries and bounded canonical turn records.
   - Wrapper role: own token budget, select what enters the prompt, and decide when compaction is needed.
   - Sources: `conversation_history_summaries` plus bounded `conversation_history` records.

6. Call `/memory /intent` for the current turn.
   - Output must include action, confidence, recall profile, required artifacts, `query_plan`, `tool_calls`, `allowed_tools`, `disallowed_tools`, and dependencies.
   - Current `/memory /intent` must run for every `speech_final` turn.
   - Only the current turn's intent result can authorize tool execution.

7. Validate the intent-recommended skills/tools.
   - Wrapper must treat `/intent` as the tool recommendation source.
   - If `allowed_tools` excludes a tool, the wrapper must not call it.
   - Invalid or unsafe plans must fail closed into clarify, deflect, or fixed fallback; they must not fall through to free PersonaPlex generation.

8. Call `/memory /recall` for query-specific route context after transcript and intent.
   - `/intent` does not run recall internally.
   - Persona recall uses persona collections/tags such as `collections=["persona_memory"]`.
   - Compliance recall/evidence uses the profile and artifacts selected by `/intent`.
   - For routes that do not need retrieval, the recall packet may be empty/no-op but must remain explicit in receipts.

9. If `DEFLECT`, call `/memory /deflect`.
   - Output must be a bounded response packet, not free PersonaPlex generation.
   - Deflect bypasses evidence-case and answer generation.

10. If `CLARIFY`, call `/memory /clarify`.
    - Output asks one targeted follow-up.
    - Clarify stops evidence work unless a future user answer starts a new turn.

11. If compliance/security/control, call `/create-evidence-case`.
    - This is the strict route for compliance-style questions.
    - Answer generation cannot occur before evidence-case produces a coherent source packet.

12. If persona/current-fact blend, use the lighter memory/research `/answer` path.
    - This path may use only current intent-authorized research/tools plus recalled memory context.
    - This remains separate from compliance evidence-case routing.

13. If the evidence case is ambiguous, underspecified, inconclusive, or weakly bridged, route to `/memory /clarify`.
    - This is the recoverable evidence-gap path.
    - It is not the hard-failure path and should not become a generic fallback.

14. If evidence or tool failure cannot be clarified safely, fail closed with a fixed fallback.
    - Free PersonaPlex factual generation remains blocked.
    - Failure details must still be captured in the canonical turn receipt.

15. If the evidence case is coherent, call `/memory /answer` from the evidence source packet.
    - PersonaPlex may phrase the final response only from that packet and recorded recall refs.

16. Force a bounded response packet for the active turn only.
    - Exactly one selected route packet may inject tokens.
    - Stale turns, historical packets, and packets without active `turn_id` authority must be discarded/fenced.

17. Release output only after the active packet is consumed or fixed fallback is ready.
    - Gate must not open with stale tokens or nonzero unsafe queue depth.
    - Prior unsafe proof detail to guard against: gate release occurred with `queue_depth=268`.

18. Store the completed turn through `/memory /upsert` into canonical `conversation_history`.
    - Canonical collection: `conversation_history`.
    - Deterministic key: `conversation:{session_id}:{turn_id}`.
    - Store transcript, route action, selected tools, allowed/disallowed tools, recall/evidence source refs, response packet hash, gate timings, safety outcome, `retrieval_text`, artifact refs, and hashes.

19. Optionally store raw audio metadata through `/memory /upsert`.
    - Optional collection: `conversation_audio_artifacts`.
    - Required fields when retained: `source_conversation_key`, `artifact_uri`, `sha256`, codec, duration, retention class, deletion state.
    - Optional Qdrant metadata: audio point ID, embedding policy/version, and deletion propagation state.

20. Optionally store `personaplex_turns` only as a derived projection.
    - `personaplex_turns` is not canonical.
    - It may exist later only as a voice/debug projection with `source_conversation_key` pointing to `conversation_history`.
    - It must not become a second authority.

21. Compact conversation history when budget threshold trips.
    - Immutable rolling summaries: `conversation_history_summaries`.
    - Summary key: `conversation_summary:{session_id}:{start_turn_id}:{end_turn_id}:{policy_version}`.
    - Summary records must list source canonical turn keys.
    - The wrapper owns compaction timing and token budget; memory stores and recalls compact state.

22. Update the mutable session head.
    - Mutable session head: `personaplex_sessions`.
    - Session-head key: `personaplex_session:{session_id}`.
    - Required semantics: generation/CAS update, latest turn pointer, active persona, summary heads, policy versions, deletion cursors.

23. Next `speech_final` starts a new active turn.
    - Current `/memory /intent` runs again.
    - Stale tasks cannot open the gate or authorize tools.
    - Historical `query_plan`, `tool_calls`, `allowed_tools`, and `disallowed_tools` remain audit/context only.

## Canonical Persistence Contract

| Store | Authority | Key / linking rule | Notes |
| --- | --- | --- | --- |
| `conversation_history` | Canonical immutable turn ledger | `conversation:{session_id}:{turn_id}` | Stores the full turn receipt and route/gate evidence. |
| `conversation_history_summaries` | Immutable rolling summaries | `conversation_summary:{session_id}:{start_turn_id}:{end_turn_id}:{policy_version}` | Records source canonical turn keys. |
| `personaplex_sessions` | Mutable session head | `personaplex_session:{session_id}` with generation/CAS | Stores latest turn, summary heads, persona, policy versions, deletion cursors. |
| `conversation_audio_artifacts` | Optional raw audio metadata | `source_conversation_key` points to `conversation_history` | Stores URI/hash/codec/duration/retention/deletion state and optional Qdrant pointer metadata. |
| `personaplex_turns` | Optional derived voice/debug projection only | `source_conversation_key` points to `conversation_history` | Must not be canonical and must not become a second authority. |

## Operational Notes

- Persona assignment belongs before Deepgram turn handling.
- Session-history recall belongs before `/memory /intent`, but only for compact prior context selected by the wrapper.
- Query-specific `/memory /recall` belongs after transcript and `/memory /intent`, because the query does not exist before the user speaks.
- `/memory /intent` is where recommended skills/tools should come from: `query_plan`, `tool_calls`, `allowed_tools`, `disallowed_tools`, `required_artifacts`, `recall_profile`, and dependencies.
- Historical tool recommendations are non-authoritative. They may be used for audit or context, but only the current active intent response can authorize tool execution.
- `/memory /upsert` is the write surface for canonical turn receipts, audio artifact metadata, rolling summaries, derived projections, and session-head updates.
- `/store` may be acceptable for one document, but `/upsert` is the better default for turn/session batches.
- Conversation audio should be stored as immutable artifacts, not Arango blobs.
- Qdrant audio embeddings are optional supplemental voice-continuity recall. They require point IDs, embedding policy/version, and deletion propagation records in memory.
- Evidence ambiguity should normally become `/memory /clarify`; only unclarifiable tool/evidence failure should use fixed fallback.

## MVP Patch Focus

Status: implementation is not complete. This chart is a source model for review and implementation planning, not proof that the wrapper behaves this way.

1. Add explicit session and per-turn runtime state.
   - Track `session_id`, `persona_id`, `turn_id`, active route, gate state, compact history, and active response packet.
   - New `speech_final` becomes latest-turn-wins: cancel stale grounding, clear stale tokens, close gate.

2. Add memory-backed history selection.
   - Recall compact session summaries before `/intent`.
   - Use canonical `conversation_history` for bounded recent turn records.
   - Wrapper owns token budget and prompt assembly.

3. Drive tool routing from `/memory /intent`.
   - Read `query_plan`, `tool_calls`, `allowed_tools`, `disallowed_tools`, `depends_on`, and `required_artifacts`.
   - Do not call tools that intent disallows.

4. Add explicit `/memory /recall` after intent.
   - Use persona collections/tags for persona questions.
   - Use compliance/source collections and profiles for compliance questions.

5. Close output gate earlier.
   - Gate closes on incoming user audio or at latest on active turn setup.
   - PersonaPlex must not emit free factual speech before route/grounding.

6. Replace shared global injection queue with active-turn packet handling.
   - Only the active `turn_id` can enqueue tokens or open the gate.
   - Gate must not open with nonzero unsafe queue depth.

7. Implement compliance route selection.
   - `DEFLECT` -> `/memory /deflect`.
   - `CLARIFY` -> `/memory /clarify`.
   - compliance/security/control -> `/create-evidence-case`.
   - persona/current-fact blend -> existing lighter memory/research answer path.

8. Add fail-closed compliance behavior.
   - Ambiguous evidence/entity/scope relationship -> `/memory /clarify`.
   - Unclarifiable evidence/tool failure -> fixed fallback.
   - No unconstrained PersonaPlex generation on evidence failure.

9. Persist turn, audio metadata, and compact session state.
   - `/memory /upsert` canonical turn receipt into `conversation_history`.
   - Store `retrieval_text` as question-shaped prose for BM25/dense text recall.
   - Store raw sound files as artifact URIs/hashes, with optional `conversation_audio_artifacts` records.
   - Store Qdrant audio point IDs only when an audio embedding lane and deletion workflow exist.
   - `/memory /upsert` immutable rolling summaries into `conversation_history_summaries`.
   - `/memory /upsert` mutable session head into `personaplex_sessions` using generation/CAS semantics.
   - Treat `personaplex_turns` only as an optional derived projection with `source_conversation_key`.

10. Preserve active-turn authority boundaries.
    - Historical `query_plan`, `tool_calls`, `allowed_tools`, and `disallowed_tools` are audit/context only.
    - Current `/memory /intent` must run for every `speech_final` turn.
    - Only the current active intent response can authorize tool execution.

11. Tighten the live probe.
    - Probe must fail if output opens with stale tokens or nonzero unsafe queue depth.
    - Probe must include persona/current-fact, compliance clarify/deflect, compliance evidence-case, persistence, and two-turn latest-turn-wins cases.

## Verification Stop Condition For Live Implementation Later

The chart/doc bundle alone cannot satisfy these. They are listed as the stop condition for later live implementation work.

- DAG validates.
- HTML chart has fresh CDP screenshot proof.
- Live receipt proves `speech_final=true`.
- Required route stages succeed or fail closed.
- `/memory /intent` emits expected tools and dependencies.
- `/memory /recall` is called where retrieval is required.
- `/memory /upsert` writes canonical `conversation_history` turn records with deterministic keys.
- Optional `personaplex_turns` writes, if present, are derived only and link to `source_conversation_key`.
- `conversation_history_summaries` are immutable and list source turn keys.
- `personaplex_sessions` updates use generation/CAS semantics.
- Audio artifact metadata, if retained, includes URI/hash/retention/deletion state and optional Qdrant pointer/deletion propagation metadata.
- No stale turn opens the gate.
- Gate opens only for active bounded response packet readiness.

## MVP Acceptance Tests

- Persona/current-fact turn reaches `/memory /answer` and releases only after active packet readiness.
- Compliance ambiguity reaches `/memory /clarify` and does not call answer generation.
- Unsupported or unsafe request reaches `/memory /deflect` or fixed fallback without evidence leakage.
- Compliance/security/control turn calls `/create-evidence-case` before answer generation.
- Intent response produces expected `tool_calls`, `allowed_tools`, `disallowed_tools`, `recall_profile`, and branch dependencies.
- Each completed turn writes a canonical `conversation_history` receipt and updates compact session state only after output completion.
- Optional `personaplex_turns` receipt, if written, is a derived projection only and contains `source_conversation_key`.
- Two-turn interruption proves stale task results cannot enqueue tokens or open output.
- Historical tool recommendations are never accepted as authorization for a new turn.


## Prompt Improvements For Next Turn

`prompt_improvements`: this section is required in every finished create-architecture bundle. The project agent must read it before the next WebGPT round or implementation turn and must use it to make the next creation, clarification, sanity, or implementation request more specific.

### Missing context WebGPT needed but did not receive

- The previous source bundle included only HTML text excerpts, not the full current HTML file. This was acceptable only because the request explicitly allowed a greenfield sanity artifact. For future non-greenfield updates, include the full current file contents.
- The current DAG source in the earlier prompt was truncated. Future prompts should either include complete current source files or explicitly authorize generation from the stated route contract.
- Local file paths, command output, and screenshots are not browser-visible unless pasted into the prompt. Include local evidence summaries directly when they matter.

### Ambiguous wording to avoid in the next project-agent prompt

- Do not mix create-architecture instructions with review-mode language. Avoid words such as PASS, NEEDS_CHANGES, verdict, audit, code review, and gate until there is an implementation artifact to evaluate.
- Do not ask for a general review when the missing item is exact. State the precise missing contract item, expected file paths, and acceptable bundle shape.
- Do not ask the project agent or WebGPT to invent missing greenfield architecture when the canonical persistence and routing constraints are already known.
- Do not describe the greenfield chart as implementation proof. Keep the claim bounded to inspectable chart/doc sanity evidence.

### Exact facts, files, and evidence the next prompt should include

- Include the downloaded zip checksum and isolated sanity report before asking WebGPT for another creation round.
- Include the exact missing contract item instead of asking for a broad or verdict-oriented review.
- Include the current create-architecture contract excerpt that requires a `prompt_improvements` section.
- Include the target file list and state whether a complete replacement zip or a minimal update zip is preferred.
- Include all relevant current checksums, especially the previous zip SHA-256 and any extracted file SHA-256 values that should be preserved or intentionally changed.
- Include local validation output for the DAG, HTML screenshot/CDP proof if available, and exact search terms that failed or succeeded.

### Instructions that should be removed from the next prompt

- Remove any instruction to return PASS, NEEDS_CHANGES, BLOCKED, INSUFFICIENT_EVIDENCE, or a verdict-first object for create-architecture work.
- Remove review-gate framing unless the request is actually evaluating an implementation artifact with raw evidence.
- Remove open-ended requests for critique when the expected output is a finished zip bundle.
- Remove contradictory requirements that ask for both numbered clarifying questions and a verdict object.

### Revised prompt skeleton for another WebGPT round

```text
# Create Replacement/Update Bundle: <artifact name>

Objective:
Create a finished-file zip bundle that updates <specific files> to satisfy <specific contract item>. This is a create-architecture task, not a review.

Current local evidence:
- Previous zip: <filename>
- Previous zip SHA-256: <sha256>
- Extracted manifest: <paste manifest or relevant entries>
- Isolated sanity output: <paste command output and screenshots/receipt summaries if applicable>
- Exact missing contract item: <quote requirement>

Required output:
If material ambiguity remains, return only numbered clarifying questions.
If no material ambiguity remains, return a zip bundle containing:
1. <path>
2. <path>
3. MANIFEST.json
Include a short response manifest with paths and SHA-256 hashes.

Constraints:
- Do not return a verdict or review framing.
- Do not claim live implementation proof.
- Preserve canonical persistence: conversation_history, conversation_history_summaries, personaplex_sessions, optional derived personaplex_turns, optional conversation_audio_artifacts.
- Include ## Prompt Improvements For Next Turn with missing context, ambiguous wording, exact next evidence, instructions to remove, and a revised prompt skeleton.
```
