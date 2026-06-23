# Clarify, Then Create Finished-File Update Bundle For PersonaPlex Decision Tree
## Objective

Update the PersonaPlex Compliance Memory Routing decision-tree artifacts so they reflect the current agreed architecture. If any material ambiguity remains, return only numbered clarifying questions. If no material ambiguity remains, create a complete finished-file solution bundle for download as a zip attachment, with manifest and checksums, and no review verdict.

## Constraints

- Do not return PASS, NEEDS_CHANGES, BLOCKED, or review framing.
- Do not ask the project agent to invent missing greenfield architecture.
- Finished files should update only the chart/doc artifacts, not implement the live wrapper.
- Prefer a downloadable zip attachment containing the full replacement files and manifest. If the browser cannot attach a zip, return complete file contents in fenced code blocks plus a manifest so the runtime can capture them into a local source bundle before any implementation.
- Treat the local chart as a greenfield sanity artifact: it can prove the approach is inspectable, not that the live project is implemented.
- Preserve fail-closed behavior for compliance/evidence routes.
- Use current agreed canonical persistence: conversation_history canonical, conversation_history_summaries immutable rolling summaries, personaplex_sessions mutable session head, optional personaplex_turns derived only, optional conversation_audio_artifacts for raw audio metadata.

## Current Known Problems In Existing Artifacts

- HTML/DAG still says /memory /upsert writes to proposed personaplex_turns as canonical.
- HTML/DAG does not include conversation_history as canonical immutable ledger.
- HTML/DAG does not include conversation_history_summaries as immutable rolling summaries.
- HTML/DAG does not include personaplex_sessions as mutable session head with generation/CAS semantics.
- HTML/DAG does not include conversation_audio_artifacts, artifact URI/hash/retention/deletion state, or optional Qdrant audio embedding pointer metadata.
- HTML/DAG does not make historical tool recommendations non-authoritative.
- Existing source model still needs to show WebGPT-created greenfield artifacts are only sanity-check proof, not implementation proof.
## Required Output

If no material ambiguity remains, return a finished-file zip bundle for these files:
1. reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json
2. reviews/personaplex-deepgram/compliance-memory-decision-tree.html
3. scratch.md
For each file, provide complete replacement content. Include a manifest with file paths, purpose, and checksums. Do not provide partial diffs.

Required response shape:

1. If there is material ambiguity, return only numbered clarifying questions.
2. If there is no material ambiguity and zip attachment is possible, return a short note naming the attached zip and include the manifest.
3. If there is no material ambiguity but zip attachment is not possible, return complete replacement file contents in fenced code blocks with exact paths, plus the manifest. This fallback is still treated as a source bundle candidate; the project agent must capture it locally and sanity-check it before touching production files.

## Current Source: DAG JSON

{
  "schema_version": "ask.dag.v1",
  "graph_id": "personaplex-compliance-memory-routing",
  "description": "Decision tree for PersonaPlex multi-turn routing across persona session assignment, Deepgram, memory intent/recall, clarify, deflect, answer, and create-evidence-case.",
  "max_concurrency": 1,
  "nodes": [
    {
      "id": "00_session_persona",
      "type": "skill.run",
      "depends_on": [],
      "display_type": "assign persona_id, load PersonaPlex golden state, preload stable persona context",
      "input": {
        "skill": "runtime.session",
        "args": [
          "assign persona_id, load PersonaPlex golden state, preload stable persona context"
        ]
      }
    },
    {
      "id": "01_audio_turn",
      "type": "skill.run",
      "depends_on": [
        "00_session_persona"
      ],
      "display_type": "Deepgram speech_final turn",
      "input": {
        "skill": "runtime.input",
        "args": [
          "Deepgram speech_final turn"
        ]
      }
    },
    {
      "id": "02_new_turn_gate",
      "type": "skill.run",
      "depends_on": [
        "01_audio_turn"
      ],
      "display_type": "latest-turn-wins: assign turn_id, close gate, clear stale injections",
      "input": {
        "skill": "runtime.state",
        "args": [
          "latest-turn-wins: assign turn_id, close gate, clear stale injections"
        ]
      }
    },
    {
      "id": "03_memory_intent",
      "type": "skill.run",
      "depends_on": [
        "02a_history_select"
      ],
      "display_type": "/memory /intent returns action, recall_profile, query_plan, tool_calls, allowed_tools",
      "input": {
        "skill": "memory.intent",
        "args": [
          "/memory /intent returns action, recall_profile, query_plan, tool_calls, allowed_tools"
        ]
      }
    },
    {
      "id": "02a_history_select",
      "type": "skill.run",
      "depends_on": [
        "02_new_turn_gate"
      ],
      "display_type": "select compact session history from memory before intent; wrapper owns token budget",
      "input": {
        "skill": "memory.recall",
        "args": [
          "select compact session history from memory before intent; wrapper owns token budget"
        ]
      }
    },
    {
      "id": "03a_tool_plan",
      "type": "skill.run",
      "depends_on": [
        "03_memory_intent"
      ],
      "display_type": "caller validates intent-recommended skills/tools and route plan",
      "input": {
        "skill": "runtime.plan",
        "args": [
          "caller validates intent-recommended skills/tools and route plan"
        ]
      }
    },
    {
      "id": "03b_memory_recall",
      "type": "skill.run",
      "depends_on": [
        "03a_tool_plan"
      ],
      "display_type": "/memory /recall fetches route-required persona, compliance, or source context after transcript exists",
      "input": {
        "skill": "memory.recall",
        "args": [
          "/memory /recall fetches route-required persona, compliance, or source context after transcript exists"
        ]
      }
    },
    {
      "id": "04_deflect_branch",
      "type": "skill.run",
      "depends_on": [
        "03b_memory_recall"
      ],
      "display_type": "if intent says DEFLECT or no-match: /memory /deflect",
      "input": {
        "skill": "memory.deflect",
        "args": [
          "if intent says DEFLECT or no-match: /memory /deflect"
        ]
      }
    },
    {
      "id": "05_clarify_branch",
      "type": "skill.run",
      "depends_on": [
        "03b_memory_recall"
      ],
      "display_type": "if intent says CLARIFY or ambiguous: /memory /clarify",
      "input": {
        "skill": "memory.clarify",
        "args": [
          "if intent says CLARIFY or ambiguous: /memory /clarify"
        ]
      }
    },
    {
      "id": "06_compliance_branch",
      "type": "skill.run",
      "depends_on": [
        "03b_memory_recall"
      ],
      "display_type": "if compliance/control/security: /create-evidence-case",
      "input": {
        "skill": "evidence.case",
        "args": [
          "if compliance/control/security: /create-evidence-case"
        ]
      }
    },
    {
      "id": "07_persona_branch",
      "type": "skill.run",
      "depends_on": [
        "03b_memory_recall"
      ],
      "display_type": "if persona/current-fact blend: memory + allowed research + /memory /answer",
      "input": {
        "skill": "memory.answer",
        "args": [
          "if persona/current-fact blend: memory + allowed research + /memory /answer"
        ]
      }
    },
    {
      "id": "08_evidence_gap_clarify",
      "type": "skill.run",
      "depends_on": [
        "06_compliance_branch"
      ],
      "display_type": "if evidence is ambiguous or underspecified: /memory /clarify",
      "input": {
        "skill": "memory.clarify",
        "args": [
          "if evidence is ambiguous or underspecified: /memory /clarify"
        ]
      }
    },
    {
      "id": "09_evidence_hard_fail",
      "type": "skill.run",
      "depends_on": [
        "06_compliance_branch"
      ],
      "display_type": "if evidence/tool failure cannot be clarified: fixed fallback, keep free generation blocked",
      "input": {
        "skill": "runtime.output",
        "args": [
          "if evidence/tool failure cannot be clarified: fixed fallback, keep free generation blocked"
        ]
      }
    },
    {
      "id": "10_evidence_answer",
      "type": "skill.run",
      "depends_on": [
        "06_compliance_branch"
      ],
      "display_type": "if evidence coherent: /memory /answer from evidence source packet",
      "input": {
        "skill": "memory.answer",
        "args": [
          "if evidence coherent: /memory /answer from evidence source packet"
        ]
      }
    },
    {
      "id": "11_force_response_packet",
      "type": "skill.run",
      "depends_on": [
        "04_deflect_branch",
        "05_clarify_branch",
        "07_persona_branch",
        "08_evidence_gap_clarify",
        "09_evidence_hard_fail",
        "10_evidence_answer"
      ],
      "display_type": "force bounded response packet for active turn only",
      "input": {
        "skill": "runtime.inject",
        "args": [
          "force bounded response packet for active turn only"
        ]
      }
    },
    {
      "id": "12_drain_then_release",
      "type": "skill.run",
      "depends_on": [
        "11_force_response_packet"
      ],
      "display_type": "release output only after active packet is consumed or fixed fallback is ready",
      "input": {
        "skill": "runtime.gate",
        "args": [
          "release output only after active packet is consumed or fixed fallback is ready"
        ]
      }
    },
    {
      "id": "13_memory_upsert_turn",
      "type": "skill.run",
      "depends_on": [
        "12_drain_then_release"
      ],
      "display_type": "/memory /upsert turn receipt to personaplex_turns with deterministic _key",
      "input": {
        "skill": "memory.upsert",
        "args": [
          "/memory /upsert turn receipt to personaplex_turns with deterministic _key"
        ]
      }
    },
    {
      "id": "14_next_turn_or_cancel",
      "type": "skill.run",
      "depends_on": [
        "13a_history_compact"
      ],
      "display_type": "next speech_final starts new turn; stale tasks cannot open gate",
      "input": {
        "skill": "runtime.loop",
        "args": [
          "next speech_final starts new turn; stale tasks cannot open gate"
        ]
      }

## Current Source: scratch.md
# PersonaPlex Compliance Memory Routing Decision Tree

Artifact source:

- DAG JSON: `reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json`
- HTML review chart: `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
- Validator: `skills/phart-dag-chart/run.sh validate reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json --json`
- Renderer: `skills/phart-dag-chart/run.sh chart reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json`
- Current source model: pending revalidation after adding history/upsert/compaction nodes.

## Source-Derived Step Model

1. Assign the persona/session before audio.
   - Status: partially implemented conceptually through PersonaPlex golden state.
   - Required state: `persona_id`, voice/golden-state context, stable persona context.

2. Deepgram finalizes a user audio turn.
   - Status: implemented for one synthesized Opus proof.
   - Deepgram supplies transcript and `speech_final=true`.

3. Wrapper creates active turn state.
   - Status: intended/missing.
   - Required state: `session_id`, `turn_id`, transcript, gate closed, stale tasks cancelled.

4. Select compact conversation history from memory.
   - Status: intended/missing.
   - Memory role: recall stored session summaries/turn records.
   - Wrapper role: own token budget, select what enters the prompt, and decide when compaction is needed.

5. Call `/memory /intent`.
   - Status: partially implemented for persona/current-fact blend.
   - Output must include action, confidence, recall profile, required artifacts, `query_plan`, `tool_calls`, `allowed_tools`, and dependencies.

6. Validate the intent-recommended skills/tools.
   - Status: intended/missing.
   - Wrapper must treat `/intent` as the tool recommendation source, not hard-code every branch locally.
   - If `allowed_tools` excludes a tool, the wrapper must not call it.

7. Call `/memory /recall` for query-specific route context.
   - Status: intended/missing in this wrapper.
   - `/intent` does not run recall internally.
   - Persona recall uses `collections=["persona_memory"]` plus persona tags.
   - Compliance recall/evidence uses the profile and artifacts selected by `/intent`.

8. If `DEFLECT`, call `/memory /deflect`.
   - Status: intended/missing.
   - Output must be a bounded response packet, not free PersonaPlex generation.

9. If `CLARIFY`, call `/memory /clarify`.
   - Status: intended/missing.
   - Output asks one targeted follow-up and stops the evidence path.

10. If compliance/security/control, call `/create-evidence-case`.
    - Status: intended/missing.
    - This is the strict route for compliance-style questions.

11. If persona/current-fact blend, use the lighter memory/research `/answer` path.
    - Status: partially implemented.
    - This remains separate from compliance evidence-case routing.

12. If the evidence case is ambiguous, underspecified, or the entity bridge is unclear, route to `/memory /clarify`.
    - Status: intended/missing.
    - This is the recoverable evidence-gap path.

13. If evidence or tool failure cannot be clarified safely, fail closed with a fixed fallback.
    - Status: intended/missing.
    - This is the hard-failure path, not the normal inconclusive-evidence path.

14. If the evidence case is coherent, call `/memory /answer` from the evidence source packet.
    - Status: intended/missing.
    - SciLLM/PersonaPlex may phrase the final response only from that packet.

15. Force a bounded response packet for the active turn only.
    - Status: intended/missing.
    - Stale turns must not inject or open the gate.

16. Release output only after the active packet is consumed or fixed fallback is ready.
    - Status: intended/missing.
    - Prior proof showed unsafe `queue_depth=268` at gate release.

17. Store the completed turn through `/memory /upsert`.
    - Status: intended/missing.
    - Canonical collection: `conversation_history`.
    - Deterministic key: `conversation:{session_id}:{turn_id}`.
    - Store transcript, route action, selected tools, recall/evidence source refs, response packet hash, gate timings, safety outcome, `retrieval_text`, and hashes.
    - `personaplex_turns` may exist later only as a derived voice/debug projection with `source_conversation_key`; it must not be a second authority.

18. Compact conversation history and upsert summary/session-head state when budget threshold trips.
    - Status: intended/missing.
    - Immutable rolling summaries: `conversation_history_summaries`.
    - Summary key: `conversation_summary:{session_id}:{start_turn_id}:{end_turn_id}:{policy_version}`.
    - Mutable session head: `personaplex_sessions`.
    - Session-head key: `personaplex_session:{session_id}`.
    - The wrapper owns compaction timing and token budget; memory stores and recalls the compact state.

19. Next `speech_final` starts a new active turn and cancels/replaces stale work.
    - Status: intended/missing.

Primary question this chart answers:

> Does every realistic multi-turn compliance conversation pass through persona assignment, history selection, memory intent/tool recommendation, recall, clarify/deflect/evidence gates, bounded output gating, and memory persistence before PersonaPlex is allowed to continue?

## Operational Notes

- Persona assignment belongs before Deepgram turn handling.
- Query-specific `/memory /recall` belongs after transcript and `/memory /intent`, because the query does not exist before the user speaks.
- Session-history recall belongs before `/memory /intent`, but only for compact prior context selected by the wrapper.
- `/memory /intent` is where recommended skills/tools should come from: `query_plan`, `tool_calls`, `allowed_tools`, `disallowed_tools`, `required_artifacts`, `recall_profile`.
- `/memory /upsert` is the write surface for turn receipts, audio artifact metadata, rolling summaries, and session-head updates. `/store` is acceptable for one document, but `/upsert` is the better default for turn/session batches.
- Conversation audio should be stored as immutable artifacts, not Arango blobs. Store user/assistant audio URI, hash, codec, duration, retention class, and deletion state in memory. Add `conversation_audio_artifacts` if raw audio is retained; use Qdrant audio embeddings only as supplemental voice-continuity recall, with point IDs and deletion propagation recorded in memory.
- Evidence ambiguity should normally become `/memory /clarify`; only unclarifiable tool/evidence failure should use fixed fallback.

## My Understanding Of Next Steps

Status: implementation is not complete. The chart is a review model, not proof that the wrapper behaves this way.

Patch sequence for working-code MVP:

1. Add explicit session and per-turn runtime state.
   - Track `session_id`, `persona_id`, `turn_id`, active route, gate state, compact history, and active response packet.
   - New `speech_final` becomes latest-turn-wins: cancel stale grounding, clear stale tokens, close gate.

2. Add memory-backed history selection.
   - Recall compact session summaries before `/intent`.
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

10. Preserve active-turn authority boundaries.
    - Historical `query_plan`, `tool_calls`, `allowed_tools`, and `disallowed_tools` are audit/context only.
    - Current `/memory /intent` must run for every `speech_final` turn.
    - Only the current active intent response can authorize tool execution.

11. Tighten the live probe.
    - Probe must fail if output opens with stale tokens or nonzero unsafe queue depth.
    - Probe must include persona/current-fact, compliance clarify/deflect, compliance evidence-case, persistence, and two-turn latest-turn-wins cases.

Verification stop condition:

- DAG validates.
- HTML chart has fresh CDP screenshot proof.
- Live receipt proves `speech_final=true`.
- Required route stages succeed or fail closed.
- `/memory /intent` emits expected tools and dependencies.
- `/memory /recall` is called where retrieval is required.
- `/memory /upsert` writes turn/session records with deterministic keys.
- No stale turn opens the gate.
- Gate opens only for active bounded response packet readiness.

## Current Source: HTML Text Excerpts
- PersonaPlex Compliance Memory Routing
- Decision tree for realistic multi-turn voice use: persona/session context is assigned before audio, compact history is selected before intent, memory recommends tools/routes and recalls evidence, and every turn is persisted before the next turn can replace stale work.
- Session Setup
- Assign `persona_id` and golden state before audio. Select compact memory-backed history before `/memory /intent`; wrapper owns the token budget.
- Intent Tools
- `/memory /intent` is the route and tool source: `query_plan`, `tool_calls`, `allowed_tools`, `disallowed_tools`, `depends_on`, and `required_artifacts`.
- Recall And Evidence
- Call `/memory /recall` after transcript and intent. Compliance/security/control questions then enter `/create-evidence-case`.
- Persistence
- After bounded output, write turn receipts to proposed `personaplex_turns` and compact session summaries to `personaplex_sessions` via `/memory /upsert`.
- MVP Patch Focus
- Per-turn `turn_id` state.
- Session history selection and compaction policy.
- Intent-selected tool plan validation.
- Close output before routing.
- Force bounded response packets.
- Persist turn receipts through `/memory /upsert`.
- Release only after active packet readiness.
- Compliance Rule
- Persona assignment happens before Deepgram turn handling.
- Compact history is selected before `/intent`.
- `/intent` recommends route, recall profile, tools, and dependencies.
- Query-specific `/recall` happens after transcript, intent, and tool-plan validation.
- `DEFLECT` and `CLARIFY` bypass evidence-case.
- Compliance/security/control turns require evidence-case.
- Recoverable evidence gaps route to `/memory /clarify`.
- Unclarifiable tool/evidence failures use fixed fallback.
- Proof Needed
- Persona turn receipt.
- Clarify or deflect compliance receipt.
- Evidence-case route receipt.
- Two-turn latest-turn-wins probe.
- Code Under Review
- Current Evidence
- Deepgram live probe produced `speech_final=true` for one synthesized Opus turn.
- Receipt: [local receipt path omitted for browser readability; known evidence summary: prior Deepgram live probe receipt existed and showed unsafe queue_depth=268 at gate release]
- Unsafe proof detail remains: gate release occurred with queue_depth=268.
- Existing WebGPT code review raw response reported `NEEDS_CHANGES` with blockers `PPX-LIVE-001` through `PPX-LIVE-010`.
- Source-Derived Route Contract
- 00 Assign `persona_id`, load the PersonaPlex golden state, and preload stable persona context before audio starts.
- 01-02 Deepgram finalizes the user turn and wrapper creates the active `turn_id`.
- 02a Wrapper selects compact session history from memory within its token budget.
- 03 `/memory /intent` returns action, confidence, recall profile, query plan, tool calls, and allowed tools.
- 03a-03b Wrapper validates recommended tools, then `/memory /recall` fetches route context after transcript exists.
- 04 `DEFLECT` must call `/memory /deflect` and emit only a bounded deflection packet.
- 05 `CLARIFY` must call `/memory /clarify`, ask one targeted follow-up, and stop evidence work.
- 06 Compliance, security, and control questions must call `/create-evidence-case` before answer generation.
- 08 Inconclusive because ambiguous, underspecified, or weakly bridged evidence routes to `/memory /clarify`.
- 09 Hard evidence or tool failure that cannot be clarified safely routes to fixed fallback.
- 10 Coherent evidence routes to `/memory /answer` with the evidence-case source packet.
- 11-12 Only the active turn can inject tokens or open the gate.
- 13-13a Turn receipt and compact session summary are written through `/memory /upsert`.
- 14 A newer turn cancels stale work and starts the loop again.
- Reviewer Questions
- Does the implementation enforce latest-turn-wins across all async memory, search, and evidence-case tasks?
- Does `/memory /intent` drive tool selection from `query_plan`, `tool_calls`, `allowed_tools`, and dependencies?
- Where is session history selected, compacted, and persisted, and is the token budget wrapper-owned?
- Are turn receipts stored by `/memory /upsert` with deterministic keys and enough route/gate evidence?
- Can PersonaPlex emit factual speech before `/memory /intent` and required grounding complete?
- Are `CLARIFY`, `DEFLECT`, evidence answer, and fixed fallback represented as bounded response packets?
- Does evidence-gap handling correctly choose `/memory /clarify` instead of a generic fallback?
- MVP Acceptance Tests
- Persona/current-fact turn reaches `/memory /answer` and releases only after packet readiness.
- Compliance ambiguity reaches `/memory /clarify` and does not call answer generation.
- Unsupported or unsafe request reaches `/memory /deflect` or fixed fallback without evidence leakage.
- Intent response produces expected `tool_calls`, `allowed_tools`, `recall_profile`, and branch dependencies.
- Each turn writes a `personaplex_turns` receipt and updates compact session state only after output completion.
- Two-turn interruption proves stale task results cannot enqueue tokens or open output.
