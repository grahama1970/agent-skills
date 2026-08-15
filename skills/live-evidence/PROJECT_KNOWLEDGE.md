# Project Knowledge: live-evidence

**Last updated:** 2026-08-15 10:06 by agent
**Status:** Active development

## Current Understanding

- Live Evidence is an always-on consented meeting/interview copilot: audio becomes stabilized speaker turns, interviewer questions trigger bounded Memory/code/ripgrep retrieval, code-related questions route to ask with evidence, and the UI should surface one to two scannable Ambient HUD cards plus a searchable Memory Vault.
- Recent deterministic evidence repaired the degraded indexed-code lane: GMO/current code projection for the YouTube live-coding eval reports generation cg_d59dfa910ea618dac9cf7128031a86f20a6f6a65d4b3a9bb, code_index ci_fc4040b33736adf135ae07713b40cab77d9ab419016f4c8f, 2 files, 3 symbols, 3 edges, and ingest-code ensure-current returned CURRENT with modification_ready=true and absence_claims_allowed=true.
- Current receipt-backed evidence proves local API/card wiring, current-source ripgrep and indexed-code freshness behavior, and browser-visible UI instrumentation. It does not yet prove the immutable goal's primary live path: consented PipeWire or microphone audio -> GPU RealtimeSTT -> transcript -> Memory/code/ask/research retrieval -> visible HUD/Vault cards during an actual meeting/interview.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-08-15 | Initialize project knowledge | Enable shared human/agent context |
| 2026-08-15 | Separate live HUD from historical Memory Vault | During calls the human needs one or two low-footprint source-bound cards; dense filtering/search belongs in the asynchronous post-call Vault, not a SaaS dashboard layout. |
| 2026-08-15 | Keep Brave/Dogpile manual and derived-query only | The complete transcript must stay local; external search should receive bounded derived questions only when local Memory/code evidence is insufficient or the human explicitly asks for research. |

## Open Questions

- [ ] What is the next smallest live proof that exercises real audio capture with GPU RealtimeSTT and produces at least one source-bound answer card from a technical interview segment?
- [ ] Which UI controls are still required for realtime use: lane filters, sort order, dismissal/copy affordances, transcript hotkey, insufficient-evidence state, and Vault search against current-session records?

## Key Files

| File | Purpose |
|------|---------|
| IMMUTABLE_GOAL.md | Defines the live-coding interview proof target and non-success cases |
| SKILL.md | Operating contract for consented audio, retrieval precedence, and proof boundaries |
| PROJECT_STATE.md | Prior packaged-state snapshot and evidence caveats |
| fixtures/agentic_eval.json | Deterministic regression suite for transcript/question/evidence behavior |
| src/live_evidence/retrieval/memory.py | Memory and indexed-code retrieval policy, including freshness/current-source checks |
| ui/src/App.tsx | Ambient HUD and Memory Vault browser surface |
| PROJECT_KNOWLEDGE.md | Shared Live Evidence knowledge projection |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
