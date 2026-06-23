# Clarify, Then Create Full Architecture And Code Solution

## Objective

Create one combined solution zip for the final PersonaPlex deliverable: a **live
voice session with Embry verified through a visual UI** showing every tool being
used in real time.

The UI is a SPARTA Chat-style interface (React via $ux-lab or standalone HTML/CSS
in `reviews/personaplex-deepgram/`) that shows:

| What | Where | How |
|------|-------|-----|
| Transcript received | Chat message panel | "User: Focus on the west gateway." |
| Intent route | Collapsible tool trace | "/memory intent → COMPLIANCE (0.94)" |
| Recall items | Tool trace expansion | "recall → 3 items (BM25 0.82, dense 0.91)" |
| Evidence case | Tool trace expansion | "evidence-case → can_answer=false, route=/clarify" |
| PersonaPlex response | Chat message panel | "Embry: I need one more grounded detail..." |
| Upsert receipt | Tool trace | "upsert → conversation:session:003 → 201" |
| Gate state | Status bar | "gate: OPEN | queue: 0 | turn: 3" |

Every step must show `real_*=true` — no deterministic fixtures in the final demo.

## Required Output

Return ONE downloadable solution zip named:
```
personaplex-e2e-live-voice-ui-combined-solution.zip
```

`MANIFEST.json.bundle_filename` must match.

The zip must include:
- `MANIFEST.json`, `ARCHITECTURE.md`, `prompt_improvements.md`
- An **end-to-end probe script** that runs all real P0-P10 services in sequence
  and produces a single receipt showing every step with `real_*` flags
- A **verification UI** (standalone HTML/CSS or React component) that reads the
  probe receipt and renders the conversation + tool trace
- Tests that prove the UI renders real tool data
- Exact commands to run the probe and view the UI

## Key Context

- Memory daemon: `http://127.0.0.1:8601` (P6 P7 proven LIVE)
- Deepgram: `wss://api.deepgram.com/v1/listen` with `DEEPGRAM_API_KEY` env var
- GPU inference: `personaplex_golden_state_server.py` with `LMGen.step(...)`
- Audio fixture: PersonaPlex `assets/test/input_assistant.wav` (16kHz mono linear16)
- Existing probes: `personaplex_p3_p5_combined_probe.py` with `run_combined_probe()`
- Existing UI: `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
- All 44 PersonaPlex tests pass (2 GPU tests skip gracefully)

## Constraints

- Keep existing architecture; extend from current adapter seam.
- Receipts must honestly record `real_*` flags.
- The UI must be viewable by opening a local HTML file or served via `python -m http.server`.
- No inline vectors in memory payloads.
- Deterministic fallback when live services unavailable (but the goal is all `real_*=true`).

## Non-Goals

- Production deployment or scaling.
- Browser microphone capture (use fixture audio for the probe).
- Replacing existing P0-P10 architecture.
