# Clarify, Then Create Full Architecture And Code Solution

## Objective

Create the next combined `$create-architecture` solution zip that wires the existing
P3-P5 deterministic adapters to **real services**. The P3-P5 slice proved deterministic
fallback behavior (stale fencing, output gate, receipt shapes). This slice makes
the adapters actually reach real endpoints, with honest fail-closed receipts if
a service is unavailable.

Three real-service targets, one combined zip:

1. **P6: real `$memory /upsert` transport** — wire the configurable memory adapter
   (`personaplex_p3_p5_live_services.py`) to the actual memory daemon at
   `http://127.0.0.1:8601` with the discovered `UpsertRequest` contract.
2. **P7: real `create-evidence-case` transport** — wire the configurable adapter
   to the actual memory daemon's `POST /create-evidence-case` endpoint at
   `http://127.0.0.1:8601` with the discovered `CreateEvidenceCaseRequest` contract.
3. **P8: live Deepgram WebSocket proof** — wire the configurable WebSocket/Deepgram
   adapter to a live Deepgram endpoint using `DEEPGRAM_API_KEY` from `~/.zshrc`,
   with explicit deterministic fallback when the key or GPU is absent.

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return one downloadable solution zip, not prose and not a review:

```text
personaplex-p6-p7-p8-real-services-combined-solution.zip
```

`MANIFEST.json` must include:

```json
{
  "project": "personaplex",
  "slice_id": "p6-p7-p8-real-services-combined",
  "bundle_filename": "personaplex-p6-p7-p8-real-services-combined-solution.zip"
}
```

Do not return PASS/NEEDS_CHANGES/BLOCKED. Do not review the current code. Create the missing files.

## Required Output

The zip must include:

- `MANIFEST.json` with `bundle_filename` exactly matching the zip name;
- `ARCHITECTURE.md` for this slice covering P6+P7+P8 wiring;
- `prompt_improvements.md` for the next project-agent turn;
- finished repo-relative files under `skills/personaplex/...`;
- updated sanity script(s) and/or new focused sanity scripts per real-service target;
- unit/integration tests per target;
- fixture data for deterministic fallback when live services are unavailable;
- exact commands to run and expected exit codes;
- rollback notes (what to undo if wiring breaks P3-P5 deterministic).

## Constraints

- Project agent is not allowed to invent greenfield architecture locally.
- Keep P0/P1/P2/P3-P5 architecture; extend the configurable adapters.
- The memory daemon URL is `http://127.0.0.1:8601` — discovered by endpoint audit.
- `POST /upsert` contract: `{"collection": "...", "documents": [{"_key": "...", ...}], "skip_embedding": false}`.
- `POST /create-evidence-case` contract:
  `{"question": "...", "context_framework": "SPARTA", "enable_llm": false, "include_cae_tree": false, "fail_on_degraded_evidence": false}`.
- Deepgram API key is in `~/.zshrc` as `DEEPGRAM_API_KEY`; the script should source it.
- Do not claim real service proof unless the script actually achieves a 2xx response
  or observed WebSocket `speech_final=true` event.
- Provide deterministic fallback tests only if live services are unavailable, and label them honestly.
- Receipt must record `real_memory_upsert: true|false`, `real_create_evidence_case: true|false`,
  `real_deepgram: true|false`, `real_gpu_personaplex: true|false`.
- No inline vectors in Arango-shaped memory payloads.
- Audio stored by path/hash metadata, not inline blobs.
- The zip must not overwrite existing P3-P5 adapter modules — extend them.

## Non-Goals

- Do not invent a replacement architecture for P0/P1/P2/P3-P5.
- Do not claim GPU PersonaPlex owner-loop proof (deferred).
- Do not implement conversation compaction (deferred to P9).
- Do not store inline vectors in Arango-shaped records.
- Do not make `personaplex_turns` canonical.
- Do not rely on historical tool/route fields for current-turn authorization.

## HANDOFF.md

# Handoff Report: Personaplex P6-P7-P8 Real Services Combined Slice

**Timestamp:** 2026-06-23T17:23:38Z
**Status:** Synthesized `$create-architecture` handoff after P3-P5 deterministic fallback checkpoint.
**Rendered progress page:** `reviews/personaplex-deepgram/compliance-memory-decision-tree.html` served at `http://127.0.0.1:8771/reviews/personaplex-deepgram/compliance-memory-decision-tree.html`

## What Exists Now

P0/P1/P2/P3-P5 are deterministic/local proof slices already ported into `skills/personaplex`.

P3-P5 added combined deterministic fallback for WebSocket, memory upsert, and evidence-case routing. The adapters exist (`personaplex_p3_p5_live_services.py`) but are configured to use `MEMORY_URL=""` and `EVIDENCE_CASE_URL=""` with deterministic file-backed fallback.

## Concrete P3-P5 Proof

- **Solution zip:** `personaplex-p3-p5-live-websocket-memory-evidence-combined-solution.zip`
- **SHA-256:** `46f9caa2153bfdbe5ea01ced76bb56b02c6afc567f6859e3f61bbef88df05fce`
- **Focused tests:** `Ran 6 tests, OK`
- **Combined PersonaPlex tests:** `Ran 26 tests, OK`
- **Final receipt:** `/tmp/personaplex-p3-p5-combined-sanity/p3-p5-final-receipt.json`

Receipt anchors:
- `ok=true`, `turn_count=2`, `active_turn_id=2`
- `stale_rejection_count=1`, `queue_depth_at_release=0`
- `live_websocket=false`, `real_deepgram=false`, `real_gpu_personaplex=false`
- `real_memory_upsert=false`, `real_create_evidence_case=false`
- `memory_url_not_configured` and `evidence_case_url_not_configured`

## Endpoint Discovery (Completed for This Bundle)

Found by auditing the memory project at `/home/graham/workspace/experiments/memory`:

| Service | URL | Method | Request Schema |
|---------|-----|--------|----------------|
| Memory upsert | `http://127.0.0.1:8601/upsert` | POST | `{"collection": str, "documents": [{_key, ...}], "skip_embedding": bool}` |
| Evidence case | `http://127.0.0.1:8601/create-evidence-case` | POST | `{"question": str, "context_framework": str?, "enable_llm": bool, "include_cae_tree": bool, "fail_on_degraded_evidence": bool}` |
| Deepgram WebSocket | `wss://api.deepgram.com/v1/listen` | WS | API key from `DEEPGRAM_API_KEY` env var |

## Current Defects / Missing Rows

1. Memory upsert adapter exists but `MEMORY_URL` is empty — no real 2xx upsert proven.
2. Evidence-case adapter exists but `EVIDENCE_CASE_URL` is empty — no real response proven.
3. Deepgram WebSocket adapter uses `deterministic_transcript_fixture` — no real `speech_final=true` from Deepgram's servers.
4. GPU PersonaPlex inference not proven (deferred).
5. Conversation compaction not implemented (deferred to P9).

## Files Likely In Scope

- `skills/personaplex/scripts/personaplex_p3_p5_live_services.py` — adapter needs real URL wiring
- `skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py` — probe needs to accept real endpoints
- `skills/personaplex/scripts/personaplex_deepgram_live.py` — may need env-var or config-key wiring
- `skills/personaplex/scripts/personaplex_golden_state_server.py` — may need config pass-through
- `skills/personaplex/sanity_p3_p5_live_websocket_memory_evidence_combined.sh` — update with real-service variants
- `skills/personaplex/tests/test_p3_p5_live_websocket_memory_evidence_combined.py` — update with live-service tests
- New dedicated sanity scripts per service target

## Must Not Disturb

- Do not replace the project agent's P0/P1/P2/P3-P5 architecture with a new local design.
- Do not claim real service proof from deterministic fixture receipts.
- Do not store inline vectors in Arango-shaped records.
- Do not make `personaplex_turns` canonical.
- Do not use generic zip names or omit `MANIFEST.json.bundle_filename`.

## Next Build Step (After This Zip)

Port the real-service wiring, run focused tests per target, update the HTML progress gaps table (mark P6/P7/P8 rows according to real-vs-fallback), then start the next WebGPT round for compaction or GPU proof if remaining.

## GOAL.md

# Goal: PersonaPlex P6-P7-P8 Real Services Combined Slice

## Rendered Progress Report

Repo path: `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
Served URL: `http://127.0.0.1:8771/reviews/personaplex-deepgram/compliance-memory-decision-tree.html`

## Objective

Extend the P3-P5 deterministic adapters to reach actual live services. Each adapter
already has a configurable URL/endpoint and deterministic file-backed fallback.
This slice wires the URLs, adds acceptance tests that try the real endpoint and
record whether it succeeded or fell back to deterministic mode, and updates the
receipt `real_*` flags honestly.

## Non-Goals

- No new conversation compaction logic (P9).
- No GPU PersonaPlex owner-loop proof (separate round).
- No browser-level microphone/WebRTC integration.

## Service Endpoints (Discovered)

1. **Memory upsert:** `POST http://127.0.0.1:8601/upsert`
   Body: `{"collection": "conversation_history", "documents": [{"_key": "...", "turn_id": 1, "transcript": "..."}], "skip_embedding": false}`
2. **Evidence case:** `POST http://127.0.0.1:8601/create-evidence-case`
   Body: `{"question": "Focus on the west gateway.", "context_framework": "SPARTA", "enable_llm": false, "include_cae_tree": false, "fail_on_degraded_evidence": false}`
3. **Deepgram WebSocket:** `wss://api.deepgram.com/v1/listen` with `DEEPGRAM_API_KEY` env var

## Acceptance Gates

### P6: Real Memory Upsert Gate

- Probe script sets `MEMORY_URL=http://127.0.0.1:8601` and sends a real `POST /upsert`.
- If daemon responds 2xx: receipt `real_memory_upsert=true`, response status/body excerpt recorded.
- If daemon is unreachable: receipt `real_memory_upsert=false`, reason documented, deterministic fallback used.
- No inline vectors in payload. `retrieval_text` present in documents.

### P7: Real Evidence-Case Gate

- Probe script sets `EVIDENCE_CASE_URL=http://127.0.0.1:8601` and sends a real `POST /create-evidence-case`.
- If daemon responds 2xx: receipt `real_create_evidence_case=true`, response excerpt recorded.
- If daemon is unreachable: receipt `real_create_evidence_case=false`, fallback to `/memory /clarify`.
- No substantive compliance claim released without evidence-case or clarify packet.

### P8: Live Deepgram WebSocket Gate

- Probe script sources `DEEPGRAM_API_KEY` from `~/.zshrc` and opens a live Deepgram WebSocket.
- If Deepgram is reachable: receipt `real_deepgram=true`, at least one `speech_final=true` event observed.
- If key is missing or endpoint unreachable: receipt `real_deepgram=false`, `deepgram_mode=deterministic_transcript_fixture`.
- GPU PersonaPlex is NOT required for this gate (separate).

## Required Files In The Zip

WebGPT should choose exact files, but expected file classes include:

- `ARCHITECTURE.md` for P6-P7-P8 wiring
- `MANIFEST.json` with `bundle_filename`
- `prompt_improvements.md`
- Updated `personaplex_p3_p5_live_services.py` with real URL configuration
- New or updated sanity scripts:
  - `sanity_p6_real_memory_upsert.sh`
  - `sanity_p7_real_evidence_case.sh`
  - `sanity_p8_live_deepgram.sh` (or combined)
- Updated `test_p3_p5_live_websocket_memory_evidence_combined.py` or new per-target test files
- Updated combined probe module if needed
- Fixture data for deterministic fallback

## Required Proof Commands

The zip must include exact commands to run. They should be runnable from repo root after porting, and should produce JSON receipts under `/tmp/personaplex-p6-p7-p8-sanity/`.

## Project-Agent / WebGPT Division

WebGPT creates the entire wiring extension as files. The project agent will only:

- download and checksum the zip;
- run isolated sanity;
- port files mechanically (overlay on existing adapters);
- fix light integration bugs without changing architecture;
- run local proof commands per target;
- update HTML report, gap report, and handoff;
- start another WebGPT round if required rows remain MISSING.

## Rendered Goal Page / Progress Report

Served URL:

```text
http://127.0.0.1:8771/reviews/personaplex-deepgram/compliance-memory-decision-tree.html
```

The HTML now has a P3-P5 engagement log row and P6/P7/P8 gaps table items. WebGPT should consult the report to understand what changed in P3-P5 and what the remaining gaps look like.

## Current Local Evidence

### P3-P5 Final Receipt (deterministic baseline)

```json
{
  "ok": true,
  "turn_count": 2,
  "active_turn_id": 2,
  "sealed_turn_keys": ["conversation:p3p5-session:000002"],
  "stale_rejection_count": 1,
  "queue_depth_at_release": 0,
  "live_websocket": false,
  "real_deepgram": false,
  "real_gpu_personaplex": false,
  "real_memory_upsert": false,
  "real_create_evidence_case": false,
  "deepgram_mode": "deterministic_transcript_fixture",
  "memory_upsert_attempts": [{
    "attempted": false,
    "real_memory_upsert": false,
    "unavailable_reason": "memory_url_not_configured"
  }],
  "evidence_case_attempts": [{
    "attempted": false,
    "real_create_evidence_case": false,
    "selected_route": "/memory /clarify",
    "unavailable_reason": "evidence_case_url_not_configured"
  }]
}
```

### P3-P5 Gap Report (excerpt)

P6: Real memory upsert — partial adapter only. Adapter exists but memory_url is not configured.
P7: Real evidence-case — partial adapter only. Adapter exists but evidence_case_url is not configured.
P8: Live Deepgram WebSocket — missing. Uses deterministic transcript fixtures.

## Relevant Files And Snippets

### Current adapter configuration pattern (`personaplex_p3_p5_live_services.py`)

The adapter currently reads:
```python
MEMORY_URL = os.environ.get("MEMORY_URL", "")
EVIDENCE_CASE_URL = os.environ.get("EVIDENCE_CASE_URL", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
```

When these are empty, the adapter falls back to deterministic file-backed storage:
- UPSERT: writes JSON to `/tmp/personaplex-.../conversation_history/` instead of HTTP POST
- EVIDENCE: routes to `$memory /clarify` instead of calling evidence endpoint
- DEEPGRAM: uses fixture JSON transcript instead of WebSocket

The test pattern proves `real_memory_upsert=false`, `real_create_evidence_case=false`, `real_deepgram=false`
via deterministic receipts. The adapter needs URL wiring + tests that try real endpoints.

### Memory daemon is confirmed running:

```bash
curl -s http://127.0.0.1:8601/upsert -X POST \
  -H "Content-Type: application/json" \
  -d '{"collection": "probe_test", "documents": [{"_key": "probe:001", "text": "hello"}]}'
```

Should return a 2xx response when tested.

## Constraints

- Project agent is not allowed to invent greenfield architecture locally.
- Keep existing P0/P1/P2/P3-P5 architecture; extend adapters by URL configuration.
- Do not claim real service proof from deterministic fixture runs.
- Receipt must honestly reflect `real_*` flags for each attempt.
- No inline vectors in payloads sent to memory daemon.
- No substantive compliance claim without evidence-case or clarify.
- Zip must be downloadable as `personaplex-p6-p7-p8-real-services-combined-solution.zip`.
- `MANIFEST.json.bundle_filename` must match.

## Non-Goals

- GPU PersonaPlex inference proof.
- Conversation compaction (P9).
- Browser-level microphone/WebRTC integration.
- Replacing P0/P1/P2/P3-P5 architecture.
