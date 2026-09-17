# Current project state — 2026-09-17 (agent-skills integration)

**Release readiness: NOT_ESTABLISHED.** This is a runnable research prototype,
not a validated all-provider detector or a hiring decision system.

## Present implementation

Local FastAPI/SQLite service, consented browser editor, server-controlled deadlines,
ordered Unicode edit receipts, idempotent retries, independent export replay,
retention/deletion, Python feature extraction, safe-JSON model training, frozen
thresholds, split-leakage checks, and real-corpus numerical qualification gates.
Unsupported languages and missing or unqualified models abstain.
The optional two-model likelihood adapter requires local pinned safetensors and
Transformers. Its numerical kernel is tested; real model inference is unexecuted.

## Evidence boundaries

The retained reports under `evidence/` are the delivery-environment execution
record; `reports/qualification/` holds the agent-skills integration runs.
Core checks include a real loopback HTTP server, actual SQLite storage, independent
export reconstruction and actual deletion readback.

**Integration run (2026-09-17, agent-skills checkout):** the full browser
journey now EXECUTES and PASSES (3/3 trials, `reports/qualification/`).
Exposing it required three root-cause repairs, all retained in git:
CSP-safe Playwright waiting (the app's `script-src 'self'` correctly blocks
`wait_for_function` string eval), removal of a premature `revokeObjectURL`
that aborted export downloads, and snap-Chromium avoidance (snap's namespaced
/tmp produces empty download artifacts; non-snap Chrome is preferred).
`uv.lock` is resolved and committed; Ruff is clean under the project profile.

Native gates were executed for real against the current agent-skills checkout
(`AGENT_SKILLS_ROOT`): setup-project `plan` PASS; `audit` fails CLOSED exactly
as designed because the required client-contract chain (acceptance-contract
bundle, Battle receipts, create-report release report) has not been produced
by its owning workflows — no lookalike receipts are fabricated. agentic-evals
mechanisms profile is READY (27/27 live trials, mocked=false); release profile
is USABLE_WITH_GAPS with the efficacy case BLOCKED pending a real human study.
Fixtures were upgraded to the current runner contract (`claim_semantics`,
live-path case commands).

Still NOT_ESTABLISHED: real-human or any-provider detection efficacy, Docker
deployment, acceptance/battle/create-report artifacts, independent human
review, and accessibility qualification.

## Red-team fragility probe (R&D, 2026-09-17)

`src/ai_detection/humanize.py` + `ai-detection humanize` add the first Battle
red move: bounded, semantics-preserving style transforms (`ast_reformat`,
`strip_comments`, `collapse_blanks`, `strip_docstrings`) that never execute
input and re-validate output parses, plus a feature-fragility probe. Measured
frontier: pure-formatting attacks move only the fragile raw-token view (struct
view 0.0, normalized digest unchanged) — cheap but shallow; the content-level
`strip_docstrings` attack (SHIELD/stylometry-informed: docstring verbosity is an
AI tell) also moves the structural view (~0.17) and changes the normalized
digest — stronger but a detectable semantic edit. Blue takeaway: weight the
structural/normalized channel over raw tokens. Mechanism-only — feature movement
is detector fragility, NOT evasion, authorship, or efficacy; a verdict flip
requires a trained model under Battle/Judge replay.

## Next meaningful gates

Collect consented provenance-grounded human examples plus held-out generator
families; train, freeze and independently qualify the detector at an approved
false-positive limit; produce the acceptance-contract, Battle and create-report
artifacts through their owning skills to open the setup-project audit gate.
See NEXT_STEPS.md for the handoff. Neither this document nor fixture counts
replace the missing evidence.
