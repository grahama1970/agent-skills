# Battle Next MVP Competition Packet - 2026-07-29

## Immutable Goal

Deliver production-scope Battle frontend and backend behavior with deterministic local receipts, beyond the prior local MVP proof.

## Current Source Boundary

- Repo: `/home/graham/workspace/experiments/agent-skills-main-clean`
- Branch: `main`
- Latest pushed Battle slice: `dcec408887efc0c6c6dacfc45f799c73d13590e4`
- Do not use old Battle feature branches, `/tmp` checkouts, or `/home/graham/workspace/experiments/agent-skills` as source.

## Current Proven State

Local receipts now prove:

1. Battle writes and exactly recalls one team-scoped measured RelayForge record through the production Memory API.
2. A live Tau/SciLLM provider cites and uses that Memory record to change a Blue strategy artifact.
3. One immutable nine-service RelayForge topology runs a live bounded Red/Blue campaign.
4. Live Tau/SciLLM provider artifacts are converted into typed Battle-selected public actions and bound to private Judge measurements.
5. A paired fresh-state live Judge delta shows Memory-aligned Blue control impact against a Red-only control.
6. The Battle spectator renders the live local HTTP SSE adapter with EventSource transport, `mocked=false`, and `seq 36/36`.
7. `$test-interactions` exercises 38 live QID interactions with 0 failures and 0 warnings.

Key receipts:

- `skills/battle/local/production-scope-v16-evidence-20260729.json`
- `skills/battle/local/production-scope-v16-live-topology-memorydelta2-20260729/live-topology-qualification.json`
- `skills/battle/local/production-scope-v16-live-topology-memorydelta2-20260729/memory-delta/memory-judge-delta.json`
- `skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-memorydelta/summary.json`
- `skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/captures-live-route-memorydelta/results.json`

## Remaining Not Proven

The current ledger intentionally remains `PARTIAL_PASS` and names:

1. Production deployment.
2. WebSocket transport.
3. Unbounded swarm execution.
4. Battle or RelayForge production readiness.
5. Six-trial qualification.
6. Factorial effects.
7. Cross-target generalization.

## Source-Derived Existing Guidance

`skills/battle/local/roundtable-full-battle-arena-20260728/executable-slice-manifest.json` listed these later slices:

1. `transport-reconnect-replay-safety`: deterministic injected transport fault harness, adapter replay diff, `$test-interactions` where visual state changes.
2. `packaged-deployment-smoke`: package a clean-checkout frontend/backend smoke, declared launch command, backend health, fresh bounded campaign, `$test-interactions`, browser screenshot.

Current code inventory shows:

- Implemented executable transport command: `./run.sh serve-live-transport` for HTTP snapshot plus SSE.
- Implemented proof command: `./run.sh prove-live-transport-server`.
- No WebSocket command or implementation was found by `rg "websocket|WebSocket|ws://|wss://" skills/battle -g '!local/**'`.
- Existing contracts explicitly list WebSocket and production deployment as `must not claim`.

## Competition Question

Choose the next MVP-level implementation slice to advance the immutable goal with the smallest deterministic proof surface.

Compare at least these candidates:

1. **WebSocket MVP**: add a local WebSocket mirror of the current live transport and prove frontend consumption.
2. **Transport Safety MVP**: add deterministic SSE/client fault injection for reconnect, duplicates, ordering, malformed events, and stale cursors, then prove UI behavior.
3. **Packaged Deployment Smoke MVP**: prove a clean local package/launch path for the existing frontend plus backend adapter, including backend health, fresh bounded campaign, `$test-interactions`, and screenshot.

## Required Answer Format

Return:

1. Recommended next MVP and why.
2. Exact implementation files likely touched.
3. Exact receipt schema or artifact to add.
4. Deterministic proof commands.
5. What the MVP may claim.
6. What it must not claim.
7. Clear stop condition if the MVP needs human authority, external credentials, or production infrastructure.

Do not expand the goal. Do not claim production readiness without production infrastructure proof.
