# Live Evidence — Project State

Updated: 2026-08-20. Every LIVE claim below has a receipt: the 25-case agentic
suite last ran READY 25/25 cases, 50/50 trials (report `le-25d`), and the G2I
campaign receipt is committed under `benchmarks/g2i-public-python-v1/`.

| Area | State | Evidence boundary |
|---|---|---|
| Live audio -> STT -> question -> card | LIVE_PROVEN | Pinned YouTube interview WAV through PipeWire null-sink into Docker RealtimeSTT (CUDA, CPU fallback on OOM), capture-fidelity gate, source-bound card. Suite case + standalone oracle. |
| Stage-1 readiness resolver | LIVE_PROVEN | Direct SciLLM streaming gate (~2.3-11s); canonical_question authors the card. Keyless runs degrade to the punctuation heuristic and are the documented flake mode. |
| Requirement ledger (#1454) | LIVE_PROVEN | Blocking clarifications hold Ask at zero; exactly-once solver per revision; revision-fenced amendments; every clarifying question amendable. G2I-02 2/2 with one accepted amendment. |
| Session purpose / capability policy (#1449) | LIVE_PROVEN | Backend-enforced on automatic and manual routes; digest bound to every card/journal record; G2I-03 zero violations. |
| Debugger proof lane (#1450) | LIVE_PROVEN | POST /api/debug/request -> real breakpoint capture via sibling skills/debugger, independent --expect-valid validation, CAS-fenced card. vscode_bridge truthfully BLOCKED_EXTERNAL. |
| Review dossier (#1451) | LIVE_PROVEN_UI | ReviewBundle v1 deterministic proof 13/13; surf-verified browser rung: claim click seeks real audio to the bound span; unverified assertions stay visibly unverified. |
| Rubric coverage (#1452) | LIVE_PROVEN_UI | Evidence-bound floor 18/18; UI chips + evidence-bound follow-up; journaled dismissal never counts as coverage. Model-lane coverage authorship over live transcripts is NOT yet wired. |
| Chatterbox rehearsal (#1453) | LIVE_PROVEN | Practice-only loop, hash-bound render receipts, injection-proof audio gate; real TTS interrupted by real human audio with echo redaction (word-boundary cuts + fuzzy vocab scrub). |
| G2i public benchmark (#1455) | READY | G2I-01..07 all 2/2 live; LIVE_EVIDENCE_G2I_PUBLIC_BENCHMARK_READY earned through the fail-closed gate; claim-hygiene enforced. |
| Ask solver lane (stage 2) | FIXTURE_IN_EVALS | Evals count invocations via an owned fixture runner; live `$ask tau-dag` path exists but its ~21s single-call roundtable-scaffolding overhead in skills/ask is unfixed. |
| Graph Memory recall | LIVE_PROVEN_BOUNDED | leetcode public-corpus ingest + keyed readback; unix:// MEMORY_SERVICE_URL falls back to the HTTP boundary. |
| Salient-fact capture / meetings | PARTIAL | Decision extraction + structurally-blind memory write proven; broader meeting workflows (fact-check lane, pitch-deck launch) not built. |
| Diarization / speaker identity | NOT_BUILT | Single-channel speaker labels only; chatterbox/memory diarization not integrated. |

All eight live-evidence tickets (#1428, #1449-#1455) are closed with receipts.
Open engineering debts: /ask single-call latency (owned by skills/ask), live
Ask on the solver path inside evals, model-lane rubric coverage authorship,
vscode_bridge provisioning, diarization.
