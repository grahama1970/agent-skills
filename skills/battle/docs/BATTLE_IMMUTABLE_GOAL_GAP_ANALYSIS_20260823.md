# Battle Immutable Goal Gap Analysis - 2026-08-23

## Status

Immutable Goal: NOT_MET

The goal is clear: Battle needs one working adaptive-lineage backend proof and a
PixiJS replay game that truthfully replays the same receipt set. PixiJS polish
is not the product; it is the receipt inspector.

## Evidence Read This Turn

- `skills/battle/CURRENT_STATUS.json`
  - `adaptive_lineage_effect` is partial/open.
  - `full_adaptive_improvement_proven` is unsupported.
  - production readiness is unsupported.
- `skills/battle/GOAL_ADAPTIVE_LINEAGE.md`
  - now clarifies that the July 2026 MET block is historical recovery evidence,
    not current closure.
- `skills/agentic-evals/run.sh run skills/battle/fixtures/agentic_eval.json`
  focused cases:
  - report: `/tmp/battle-immutable-gap-eval-20260823.json`
  - readiness: `READY`
  - cases: `7`
  - trials: `14`
  - outcomes: `PASS=7`, `FAIL=0`, `BLOCKED=0`, `NOT_TESTED=0`
  - mocked: `false`
  - live: `true`
- Pixi screenshots inspected:
  - `/tmp/battle-agentic-evals/pixi-gameplay-video/screenshots/loaded.png`
  - `/tmp/battle-agentic-evals/pixi-gameplay-video/screenshots/playing.png`
  - `/tmp/battle-agentic-evals/pixi-gameplay-video/screenshots/scrubbed.png`
  - `/tmp/battle-agentic-evals/receipt-pixi-replay/screenshots/after-spawn.png`
- Narrow local proof after the ticket split:
  - `cd skills/battle && pytest -q tests/test_agentic_eval_probe_exact_chain.py tests/test_adaptive_lineage_fixture.py`
  - result: `9 passed`
  - `cd skills/battle && python scripts/current_status.py check --path CURRENT_STATUS.json`
  - result: `PASS`
- Full UX contract check:
  - `cd skills/battle && ./run.sh validate-ux-contract local/battle-004-adaptive-lineage-v13/battle.normalized_ux_fixture.json`
  - result: `FAIL`
  - meaning: the committed adaptive-lineage replay fixture is usable by the
    current focused tests, but it does not satisfy the broader normalized UX
    contract guardrail.
- WebGPT Ask review:
  - Ask run: `one-shot-oneshot-3728fa94-webgpt`
  - receipt:
    `/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/one-shot-oneshot-3728fa94-webgpt/node-artifacts/handler-webgpt/node-receipt.json`
  - verdict:
    `/mnt/storage12tb/skills/ask/outputs/battle-gap-webgpt-20260823/one-shot-verdict.json`
  - result: `READY`, `answered=1`, `mocked=false`, `live=true`,
    `provider_live=true`.

## What Is Working

Backend proof guards exist and are not empty:

- `adaptive-lineage-live-exact-chain` passed `2/2` trials.
- `adaptive-lineage-same-run-backend-contracts` passed `2/2` trials.
- `memory-team-learning-contracts` passed `2/2` trials.
- Exact-chain qualification artifact:
  `/tmp/battle-agentic-evals/adaptive-lineage-live-exact-chain-artifacts/adaptive-lineage-qualification.json`
  has `status: PASS`, `live: true`, `mocked: false`, no fixture fallback, four
  slot hashes matched, and two exact replays matched.

Pixi replay is real enough to inspect:

- `receipt-backed-pixi-replay-browser-proof` passed `2/2` trials.
- `pixi-gameplay-video-acceptance` passed `2/2` trials.
- Gameplay proof:
  `/tmp/battle-agentic-evals/pixi-gameplay-video/pixi-gameplay-video-proof.json`
  has `status: PASS`, `mocked: false`, local HTTP browser execution, nonblank
  canvas dimensions, play/pause/scrub checks, no runtime errors, screenshots,
  and a video at
  `/tmp/battle-agentic-evals/pixi-gameplay-video/video/pixi-replay-gameplay.webm`.

This does not mean the replay fixture satisfies the full UX contract. The
current full contract validator fails the adaptive-lineage fixture.

Production readiness is fail-closed:

- `production-readiness-missing-receipts-fail-closed` passed `2/2` trials.
- `production-positive-readiness-contract` passed `2/2` trials, proving the
  validator can pass only when all required receipt classes are supplied.

## Backend Gaps

### B1. Current backend-generation closure is not durable in the repo

The focused eval writes the exact-chain proof under `/tmp`. That is useful
evidence, but it is not a durable repo-owned closure bundle. The immutable goal
requires a reproducible receipt path under `skills/battle/local/` plus
`CURRENT_STATUS.json` regenerated from durable receipts.

Ticket: `#1499` - Battle: regenerate durable adaptive-lineage qualification receipt.

### B2. The current backend has not proved causal adaptive generation

The qualification receipt says it proves recovered `battle-004` adaptive
Red/Blue lineage receipts rehash under the backend verifier. It explicitly does
not prove `a new live Tau/Docker campaign was rerun`.

This is not a contradiction: recovered exact-chain proof can be a valid
regression guard. It is not enough to claim the current backend can generate
adaptive lineage today.

The missing backend proof is causal, not merely statistical:

- parent generation exists;
- parent result is evaluated;
- feedback causes a non-noop child change;
- child execution result exists;
- scorekeeper/Judge-backed selection records the lineage decision;
- same-run integrity prevents stitched receipts from different runs.

Covered by `#1499`. Do not split this into a separate fresh-provider ticket.

### B3. Current status still has unsupported adaptive-improvement language

`CURRENT_STATUS.json` still says `adaptive_lineage_effect` is partial/open and
`full_adaptive_improvement_proven` is unsupported. That is correct today, but
the project needs one current-status regeneration after durable receipts are
created so agents stop reading stale contradictions.

Covered by `#1499` unless the fix becomes larger than receipt regeneration.

### B4. Production, QEMU, overnight, and arbitrary-target readiness are not
proved

The focused eval report explicitly leaves unverified:

- external staging authority bundle;
- production WebSocket TLS/auth/fanout against a real public endpoint;
- a real 1000-round overnight campaign;
- QEMU boot execution;
- arbitrary target exploitability outside `battle-004`.

These are Battle product gaps. They are not blockers for the local
`battle-004` adaptive-lineage + Pixi replay immutable goal unless the human
amends the goal to require production or arbitrary-target readiness.

Fresh current backend execution is different from these stretch gaps. Current
backend execution is required for the immutable goal; production/QEMU/overnight
scale and arbitrary-target coverage are not.

## Frontend / UX Gaps

### U1. Pixi replay is not tied to a fresh durable backend receipt bundle

The Pixi browser proofs passed against served fixtures, but the immutable goal
needs the replay to consume the same durable backend receipt bundle from B1.
The next UX proof must name the source backend receipt path and hash, then show
that the visible Pixi route loaded that exact source.

Needed ticket: bind Pixi replay proof to the fresh durable adaptive-lineage
receipt from `#1499`.

### U2. The replay route does not yet show the full causal adaptive story

The current browser proof demonstrates rendering and controls. It does not prove
that the visible replay tells the adaptive-lineage story a human needs to
inspect:

- source run and bundle identity;
- current round;
- parent/child relationship;
- evaluation and feedback;
- material child change;
- selection/outcome;
- position or terminal state.

Ticket: `#1500` for source binding, then `#1501` for usable replay acceptance.

The local full-contract failure belongs in this ticket chain. It is evidence
that the Pixi replay is not yet a complete, contract-backed replay game even
though focused browser/gameplay proofs pass.

### U3. `pause_after_round` visibly fails closed in the current Pixi proof

The inspected screenshots show:

```text
PAUSE AFTER ROUND  FAIL CLOSED
MISSING BACKEND
No pause_after_round backend receipts are present in this fixture.
```

That is honest, but it is not a finished UX for a working replay game. Either
the backend must emit the pause-after-round receipt for this fixture, or the UX
must move this non-applicable proof card out of the first viewport for the
adaptive-lineage replay route.

Covered by `#1501`. This is not just a visual polish issue: the route must
distinguish `MISSING_BACKEND` from `NOT_APPLICABLE`, and must fail closed when a
required backend receipt is absent.

### U4. Objective replay acceptance is still unverified

The eval report says Pixi gameplay proof does not prove full visual design
acceptance. I inspected screenshots and confirmed the game is nonblank and
functional, but it still needs an acceptance pass for scannability, first
viewport priority, readable lineage details, and whether the fail-closed banner
dominates the product experience.

Covered by `#1501`. This should be objective replay acceptance, not an open-ended
"visual design" ticket.

### U5. The replay proof does not prove production route availability

The Pixi proof uses local HTTP static bundle execution. It does not prove a
production/staging URL serves the same replay. That is not required for a local
working version, but it remains a product deployment gap.

## Recommended Ticket Set

Final watchdog ticket set:

1. `#1499` - backend closure. Regenerate a durable adaptive-lineage
   qualification bundle, prove causal current backend generation, add negative
   integrity cases, and regenerate `CURRENT_STATUS.json`.
2. `#1500` - cross-layer binding. Bind Pixi replay proof to the durable backend
   receipt path/hash from `#1499`.
3. `#1501` - replay UX acceptance. Make the adaptive-lineage Pixi route an
   inspectable replay of source identity, parent/child causality, feedback,
   material child change, selection, controls, and fail-closed missing/wrong
   source behavior.

Superseded/parked:

- `#1502` - over-broad visual acceptance duplicate. Fold into `#1501`.
- `#1503` - over-split fresh-provider backend ticket. Fold into `#1499`.

## Stop Condition

Do not call Battle complete until a fresh report can say:

- backend durable receipt exists under `skills/battle/local/...`;
- the durable receipt proves current backend causal adaptation, not only
  recovered receipt rehashing;
- `CURRENT_STATUS.json` points at that receipt and no longer carries stale
  contradictory closure language;
- Pixi replay proof names the same backend receipt hash;
- visual screenshot/video proof has been inspected and shows the causal
  adaptive-lineage story; and
- `#1499`, `#1500`, and `#1501` are closed with deterministic proof.
