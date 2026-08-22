# Project Knowledge: live-evidence

**Last updated:** 2026-08-22 by agent
**Status:** Active development; all eight campaign tickets (#1428, #1449-#1455) and all six review-roadmap tickets (#1472-#1477) closed with receipts.

## Current Understanding

- IMMUTABLE GOAL v2 (human goal change, 2026-08-22): follow ANY consented meeting and surface three card families -- research cards (bounded external), memory-recall cards (Graph Memory prior knowledge), and code cards -- plus briefing packs and human-approved actions. The v1 coding-interview proof is achieved and stays binding as the regression floor; v2's completion standard is a frozen-build daily-use campaign (20+ real sessions, onset-to-card latency measured from speech start, zero policy violations).
- Live Evidence is a local-first meeting/interview copilot with one governing idea: every claim it surfaces is bound to evidence, and every capability claim it makes about itself is bound to a receipt. The 31-case agentic-eval suite is the gate; the immutable goal's primary live path (consented audio -> GPU RealtimeSTT -> transcript -> retrieval -> visible HUD cards) is PROVEN, not aspirational.
- The live loop: PipeWire audio -> Docker RealtimeSTT (CUDA, CPU fallback on OOM) -> stage-1 streaming readiness resolver (direct SciLLM; its canonical question authors the card) -> Memory/ripgrep retrieval -> stage-2 fast streaming answer (p50 0.9s / p95 2.2s to first content) published through a compare-and-swap revision fence.
- Session purposes are backend-enforced authority: meeting, rehearsal (practice-only), formal_assessment (all assistance fails closed), interviewer_assist, post_interview_review. A policy digest binds every card and journal record.
- Beyond cards, the meeting product now includes: briefing packs (pre-call talking points surfaced when the conversation opens a door, e.g. fixtures/briefing_straive.json), an evidence-triggered action lane (fact-check / remember / open artifact, human-approved with destination readbacks), clause-level provenance with mutation-invalidation, model-authored rubric coverage over a deterministic floor, read-only debugger proofs, review dossiers with click-to-seek media, a chatterbox rehearsal loop, and deterministic speaker turns.
- The pinned public G2i benchmark (g2i/python-api-challenge@25ceb5ad) ran its full seven-case campaign twice live and legitimately earned LIVE_EVIDENCE_G2I_PUBLIC_BENCHMARK_READY through a fail-closed gate with a claim-hygiene oracle on comparison wording.

## Hard-won operational lessons

- A success signal from the thing under test is worth nothing; independent readback decides. This is enforced structurally (structurally-blind memory writes + keyed readback; debugger proofs revalidated; solver receipts with response digests).
- UV_PROJECT_ENVIRONMENT must never leak into sibling-runner subprocesses: an inherited value lets another skill's `uv run` REBUILD the caller's venv as that project's environment (observed live: an eval venv became surf's, pydantic gone). subprocess_env.child_env strips it server-side; every eval-side surf/ask subprocess strips it too.
- httpx eagerly builds an SSL context and dies with FileNotFoundError in CA-less venvs; local plain-http boundaries (resolver, solver, salient facts) use urllib on purpose.
- Roundtable prompt scaffolding on single-handler ask calls cost ~21s per call and degraded answers (models argued with the scaffold); fixed upstream in skills/ask (#1472, workflow_mode "single").
- Generated sources must be excluded from clause->source mapping or every clause trivially self-cites the generator.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-08-19 | Stage-1 resolver stays direct SciLLM (documented exception); stage-2 gains a direct streaming fast path with $ask as escalation | Live conversational latency cannot absorb per-call orchestration; receipts (model, latency segments, response digest) preserve accountability |
| 2026-08-19 | Purposes are backend authority, not UI labels | A disabled capability must fail closed on manual routes too |
| 2026-08-20 | The stage-1 resolver is the single ambient authority; its vocabulary extends (questions, claims, facts, artifacts) instead of adding parallel detectors | Competing publication semantics were the failure mode to avoid (external review, 2026-08-20) |
| 2026-08-20 | Diarization deferred behind a deterministic speaker-turn contract | Anonymous stable turns + manual correction first; model diarization only when proven insufficient |
| 2026-08-21 | Briefing packs are deterministic stem-matching on the hot path | Zero latency, exact trigger-event binding; fuzzy model matching can layer on later without changing the contract |

## Open Questions

- [ ] Should briefing-pack matching gain a resolver-fuzzy second tier for paraphrased openings the stem floor misses (measured miss rate first)?
- [ ] When does the speaker-turn contract prove insufficient enough to justify a real diarizer behind the existing adapter seam?
- [ ] vscode_bridge remains truthfully BLOCKED_EXTERNAL; provision only when a debugger-centric workflow demands the visible editor.

## Key Files

| File | Purpose |
|------|---------|
| IMMUTABLE_GOAL.md | Live-coding interview proof target + per-purpose claim boundaries |
| SKILL.md | Operating contract, capability map, provider-boundary tiers with measured latencies |
| PROJECT_STATE.md | Receipt-backed state table (updated 2026-08-20) |
| fixtures/agentic_eval.json | The 31-case suite (live audio, resolver, solver, policy, debugger, review, rubric, rehearsal, provenance, actions, briefing, turns) |
| fixtures/briefing_straive.json | Shipped briefing-pack example (Straive call, 15 points) |
| benchmarks/g2i-public-python-v1/ | Pinned public benchmark pack + campaign receipts + release marker |
| src/live_evidence/coordinator.py | Transcript -> question -> retrieval -> card orchestration |
| src/live_evidence/{solver,fast_path}.py | Stage-2 streaming fast answers with receipts |
| src/live_evidence/{briefing,actions,provenance,rubric,rubric_author,review,rehearsal,debugger_lane,echo}.py | The capability lanes |
| ui/src/components/InsightsPanel.tsx | Openings, actions, provenance, rubric, review, rehearsal surfaces |

## Infrastructure State

- Suite: 31 cases; last full 30-case run READY with 60/60 trials (le-30-final); case 31 (briefing) runner-verified PASS 2/2.
- Known environment coupling: chatterbox on :8018 (rehearsal + voice evals), memory on :8601, SciLLM proxy on :4001 (key from the container, not the drifted shell export), surf-controlled Chrome for browser rungs. Each absence reports BLOCKED/unresolved, never a fake pass.
