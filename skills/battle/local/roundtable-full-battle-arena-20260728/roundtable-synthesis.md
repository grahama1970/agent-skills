# Battle Arena Roundtable Synthesis - 2026-07-28

## Scope

Requested action: proceed with #1040, then run `$ask roundtable` with webclaude,
webgpt, webgrok, webkimi, and webgemini for next steps toward a fully working
Battle Arena frontend and backend.

This synthesis is advisory. It does not close the Battle implementation goal.
Local deterministic checks, backend receipts, browser screenshots/CDP evidence,
and `$test-interactions` remain the implementation proof gates.

## Source Evidence

1. `#1040` branch triage was closed from deterministic Git proof.
   - Proof path: `skills/persona-dream/local/issue-1040-branch-triage-20260728/issue-1040-proof.md`
   - Remote proof commit: `166cb20f320085b715e00c171ec89dfe171eb085`
   - `git cherry main battle-adaptive-lineage-goal`: 245 entries; 50 patch-equivalent to main; 195 branch-only deliberately dropped as wrong-lane work.

2. `skills/battle/sanity.sh` returned exit 0 with final `Result: PASS`.
   - UX normalized JSON contract: PASS for parent-spawn and sparse fixtures.
   - UX handoff summary: PASS.
   - UX data contract index: PASS.
   - Informational backend eval: `13/14`; known ticketed failure `fixture_valid::battle-004-kill-shot-pixi-replay`.

3. `$test-interactions` passed against the actual Battle static build served from `skills/battle/spectator/dist`.
   - URL: `http://127.0.0.1:3015/#battle`
   - Result: `12 PASS / 0 FAIL / 0 WARN / 12 total`
   - Results: `skills/battle/local/test-interactions-20260728-roundtable-battle3015/captures/results.json`
   - Screenshot: `skills/battle/local/test-interactions-20260728-roundtable-battle3015/captures/battle-receipt-controls/0012_pane-controls_screenshot.png`

4. `http://127.0.0.1:3002` is not Battle in the current environment.
   - Listener cwd: `/home/graham/workspace/experiments/sparta/explorer`
   - The first interaction run on 3002 rendered SPARTA/Global Posture content, proving route ambiguity rather than Battle component failure.

## Ask Runs

1. `battle-arena-front-back-roundtable-r1-20260728`
   - Status: fail-closed before provider dispatch.
   - Reason: attachment contract blocked because webgemini, webgpt, and webkimi accept exactly one attachment per submit, while three attachments were requested.

2. `battle-arena-front-back-roundtable-r1b-20260728`
   - Status: DEGRADED.
   - `mocked: false`
   - `live: true`
   - Usable seats: webclaude PASS, webgrok PASS, webgemini PASS.
   - Missing seats: webgpt rate-limited; webkimi missing sentinel/composer path failed.
   - Join receipt: `/mnt/storage12tb/skills/ask/outputs/battle-arena-roundtable-20260728/battle-arena-front-back-roundtable-r1b-20260728/node-artifacts/join/node-receipt.json`

3. `battle-arena-front-back-roundtable-r1c-recovery-20260728`
   - Status: NEEDS_ATTENTION.
   - `mocked: false`
   - `live: true`
   - webgpt: provider-side rate limit, raw response chars 0.
   - webkimi: browser composer interaction failed, raw response chars 0.
   - Join receipt: `/mnt/storage12tb/skills/ask/outputs/battle-arena-roundtable-20260728/battle-arena-front-back-roundtable-r1c-recovery-20260728/node-artifacts/join/node-receipt.json`

## Seat Positions

1. webclaude: close provenance and transport gaps before features.
   - Rank 1: source to build to interaction pass on `agent-skills@main`.
   - Rank 2: retire or explicitly track `battle-004-kill-shot-pixi-replay`.
   - Rank 3: introduce live backend to adapter transport behind a replay determinism gate.
   - Key false-green risks: stale built artifact, orphaned waiver, tautological contract pass, happy-path-only receipt gating, screenshot drift.

2. webgrok: stabilize the host path, fix the known backend fixture, then prove fresh receipt flow.
   - Rank 1: host/route owner and launch script.
   - Rank 2: backend fixture fix.
   - Rank 3: live-receipt interaction proof.
   - Human blocker: canonical local port and launch ownership.

3. webgemini: emphasize deterministic engine/state synchronization.
   - Proposed fixed-seed backend runner with per-tick state hashes.
   - Proposed transport/state protocol and frontend state-hash mirror.
   - This is useful as a determinism guard, but it is less grounded in the current Battle receipt/Pixi split than the other seats.

4. webgpt: no usable content.
   - Recovery reason: browser provider rate limited.
   - Evidence path: `/mnt/storage12tb/skills/ask/outputs/battle-arena-roundtable-20260728/battle-arena-front-back-roundtable-r1c-recovery-20260728/node-artifacts/handler-webgpt/node-receipt.json`

5. webkimi: no usable content.
   - Recovery reason: controlled Kimi composer refused focus/typing.
   - Evidence path: `/mnt/storage12tb/skills/ask/outputs/battle-arena-roundtable-20260728/battle-arena-front-back-roundtable-r1c-recovery-20260728/node-artifacts/handler-webkimi/node-receipt.json`

## Implemented vs Intended/Missing Model

1. Implemented: `#1040` closure proof is on remote `main`.
2. Implemented: local Battle sanity path returns PASS, with one known informational backend eval gap.
3. Implemented: built static Battle UI passes `$test-interactions` on a dedicated local static server.
4. Intended but missing: a source-to-dist proof that a clean `agent-skills@main` build creates the artifact that passed interactions.
5. Intended but missing: canonical Battle launch route/port. Port 3002 currently belongs to SPARTA Explorer.
6. Intended but missing: backend eval `fixture_valid::battle-004-kill-shot-pixi-replay` either passes or has an explicit live ticket/expiry.
7. Intended but missing: live backend/SSE to normalized adapter to DOM/Pixi proof under fresh receipts.
8. Intended but missing: deterministic negative fixtures for missing/invalid receipts disabling Pixi effects while DOM mirrors remain accessible.

## Selected Next Slice Order

1. Build provenance and launch contract.
   - Reason: the current UI proof is attached to `skills/battle/spectator/dist`, not a freshly built artifact from source.
   - Default port stance: use a dedicated Battle port until the human assigns production route ownership; fail preflight if the selected port is held by a foreign cwd.

2. Kill-shot fixture eval retirement.
   - Reason: the known backend eval failure sits directly under the replay/effect lane needed for the next frontend/backend phase.

3. Live transport replay determinism.
   - Reason: after source/build and fixture correctness are proven, the next risk is fresh backend receipt transport into the normalized adapter and UI.

4. Backend renderer-vocabulary purity guard.
   - Reason: the backend/Pixi boundary is a central Battle invariant and should be executable, not only documented.

5. Fail-closed receipt and DOM mirror inventory.
   - Reason: missing receipt behavior and selectable Pixi-to-DOM parity are high-risk false-green areas for the frontend.

