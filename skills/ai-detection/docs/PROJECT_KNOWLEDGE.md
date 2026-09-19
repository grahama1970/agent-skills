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

`probe_evasion(model, sources)` closes the detect→humanize→re-detect loop
against a trained detector's calibrated threshold (a "passing" solution scores
≥threshold before and <threshold after). On the synthetic corpus the current
transforms evade 0/24 samples (mean score movement ~+0.001): the structure-keyed
detector resists formatting/docstring humanization, corroborating the blue
takeaway. Mechanism-only — analyze() still abstains for synthetic training; this
is not evasion of a qualified detector or an efficacy number. Moving the
frontier needs a real-provenance corpus, semantic red transforms, and
Battle/Judge replay.

## Provenance labeling (R&D, 2026-09-17)

`src/ai_detection/provenance.py` + `ai-detection classify-provenance` implement
the three-class labeling policy from metadata only (no code content, no license
risk): `agent_authored` (bot author), `ai_assisted` (human author + agent
co-author/trailer), `human_proxy` (no signal). `EFFICACY_ELIGIBLE` is empty by
design — no gh-mined class may establish detection accuracy; the strong-label
tier must come from a published, license-cleared dataset. Live metadata survey
(cline/cline, 40 commits): 0 agent_authored / 4 ai_assisted / 36 human_proxy,
confirming agent-attributed code is sparse and weak in the wild. Pulling code
bodies for training remains gated behind explicit human license/consent
clearance.

## Battle invariant target (R&D, 2026-09-17)

ai-detection is now a first-class `$battle` invariant target, composed (not
reimplemented): `battle/detector_judge.py` is a Battle pluggable judge
(`battle.invariant_result.v1`) enforcing "AI-authored code stays flagged"
(score >= threshold); a below-threshold file is a Red win. `battle/authorization.json`
is the operator `security.target_authorization.v1` manifest for this local
self-target. Proven through Battle's own `battle_skill.invariant_judge.run_judge`
(not a local copy). Live scoreboard on the synthetic detector: Red humanizes
every AI sample with every transform -> Blue holds, 0 Red wins across all four
transforms (structure-keyed detector resists formatting/docstring humanization).
Mechanism-only: not qualified-detector evasion or efficacy. Next Red rung is
semantic transforms; the efficacy-grade Battle (Docker campaign, adaptive
lineage) awaits a real-provenance corpus that qualifies the detector.

## Jev shadow challenger (R&D, 2026-09-19)

`ai-detection jev-shadow SOURCE --output RECEIPT --allow-provider-upload` composes
the existing `$jev` skill as a pinned (`jev-1.13.0`), typed, shadow-only code-signal
classifier. Provider upload is denied without the explicit per-call flag. Every
attempt writes `ai_detection.jev_shadow.v1` with accepted/abstained/blocked/failed
outcome; the result cannot change detector disposition, Battle scoring, or release
status. This is an experiment, not an accuracy claim. Qualification requires an
approved corpus and measured accepted-decision error, abstention/fallback rate,
external wall-clock latency, and cost.

## Hugging Face dataset candidates (R&D, 2026-09-19)

Read-only `$ops-huggingface` checks pinned three repositories in
`research/huggingface_candidates.json`. `AICD-bench/AICD-Bench` is quarantined
because its pinned card exposes no license/provenance narrative. `HanxiGuo/CodeMirage`
is a candidate for noncommercial evaluation only at the pinned revision; its card
declares CC BY-NC-ND 4.0 and human/AI/paraphrased strata, so derivatives, training,
and redistribution require review. `LTPhong/CSC15011_Detecting_AI-Generated_Code`
is quarantined because no card/license was exposed. Discovery is not corpus
admission and none of these datasets establishes consented-assessment efficacy.

## Next meaningful gates

Collect consented provenance-grounded human examples plus held-out generator
families; train, freeze and independently qualify the detector at an approved
false-positive limit; produce the acceptance-contract, Battle and create-report
artifacts through their owning skills to open the setup-project audit gate.
See NEXT_STEPS.md for the handoff. Neither this document nor fixture counts
replace the missing evidence.
