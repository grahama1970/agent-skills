# Battle Next MVP Competition Packet - Production Deployment Gap - 2026-07-29

## Immutable Goal

Deliver production-scope Battle frontend and backend behavior with deterministic
local receipts, beyond the prior local MVP proof.

## Source Boundary

- Repository: `/home/graham/workspace/experiments/agent-skills-main-clean`
- Branch: `main`
- Current pushed source commit under proof: `b6e839ec0f5243cc3360bb2b324e8de7473214aa`
- Do not use old Battle feature branches, `/tmp` source trees, or
  `/home/graham/workspace/experiments/agent-skills` as authoritative source.

## Current Proven State

Recent deterministic local receipts now prove these bounded slices:

1. Packaged frontend/backend transport smoke:
   - Receipt:
     `skills/battle/local/packaged-deployment-smoke-current-main-20260729-next5/packaged-deployment-smoke.json`
   - Status: `PASS`
   - mocked: `false`
   - live: `packaged_local_http_sse_websocket_adapter_plus_vite_preview`
   - PR8: `33 total / 0 failed`
   - `$test-interactions`: `38 total / 38 passed / 0 failed / 0 warned`
   - visual findings: `0`
   - screenshot:
     `skills/battle/local/packaged-deployment-smoke-current-main-20260729-next5/frontend-pr8/01-live-sse-adapter.png`

2. Backend WebSocket transport:
   - Receipt:
     `skills/battle/local/packaged-deployment-smoke-current-main-20260729-next5/backend/live-transport-server-proof.json`
   - Status: `PASS`
   - mocked: `false`
   - live: `local_http_sse_websocket_adapter`
   - WebSocket event count: `36`
   - `websocket_snapshot_first`: `true`
   - `websocket_matches_sse_payloads`: `true`

3. Bounded live Memory ablation:
   - Receipt:
     `skills/battle/local/adaptive-memory-ablation-v15-20260729-next5/memory-ablation-result.json`
   - Status: `PASS`
   - Required/completed live trials: `12/12`
   - All trials crossed Tau, Docker, and Judge: `true`
   - Red memory classification: `INCONCLUSIVE`
   - Blue memory classification: `INCONCLUSIVE`

4. Existing V16 topology proof:
   - Receipt:
     `skills/battle/local/production-scope-v16-live-topology-zipadapter-20260729/live-topology-qualification.json`
   - Status: `PASS`
   - mocked: `false`
   - live: `true`
   - closed blocker: `live-topology-not-qualified`
   - remaining blockers: `[]`
   - production readiness proven: `false`

5. Ticket state:
   - `skills/ticket/run.sh doctor --repo grahama1970/agent-skills`: `status=ok`, missing labels `0`
   - `gh issue list --state open --label battle`: `[]`
   - `gh issue list --state open --label route:frontend_code`: `[]`
   - Battle-related backend-route open issue filter: `[]`

## Current Missing Scope

Do not re-open solved gaps. WebSocket transport is now implemented and proven
locally. Current remaining gap is a production-like deployment/readiness
contract.

The current packaged smoke may claim:

- A Git-archived local Battle package can launch the existing backend live
  HTTP/SSE adapter.
- The packaged backend advertises and proves the paired local WebSocket endpoint.
- A Git-archived local Battle package can build and preview the spectator
  frontend.
- The packaged frontend consumed the packaged adapter through PR8.
- `$test-interactions` exercised the packaged frontend/backend WebSocket route
  with zero failures and warnings.

The current packaged smoke must not claim:

- production infrastructure is deployed;
- production WebSocket TLS, auth, fanout, compression, or reconnect behavior;
- unbounded swarm execution works;
- Battle or RelayForge is production ready;
- six-trial qualification, factorial effects, or cross-target generalization.

## Local Code Inventory

Existing commands:

- `./run.sh serve-live-transport`
- `./run.sh prove-live-transport-server`
- `./run.sh prove-packaged-deployment-smoke`
- `./run.sh v16-live-topology-qualify`
- `./run.sh adaptive-memory-ablation plan|validate|preflight|run|aggregate`

Existing assets:

- `skills/battle/spectator/package.json` builds and previews the React/Pixi
  spectator via Vite.
- `skills/battle/src/battle_skill/live_transport_server.py` serves HTTP
  snapshot, SSE, and WebSocket from a normalized fixture.
- `skills/battle/src/battle_skill/packaged_deployment_smoke.py` archives
  `skills/battle` and `skills/common`, installs package deps, starts the
  backend adapter plus Vite preview, runs PR8, runs `$test-interactions`, and
  captures screenshots.
- `skills/battle/arena/relayforge-v16/compose.yaml` proves a RelayForge target
  topology, not the Battle spectator/backend deployment.
- `skills/battle/docker/Dockerfile` is a QEMU twin image, not the Battle
  frontend/backend deployment.

## Competition Question

Choose the next MVP-level implementation slice that advances the immutable goal
with the smallest deterministic proof surface and without claiming production
readiness from local-only evidence.

Compare at least these candidates:

1. Containerized deployment smoke:
   - Add a Battle-owned local container or compose proof that builds the
     spectator static assets, starts the backend live transport, serves the
     frontend and backend from declared container entrypoints, proves health,
     WebSocket, PR8, `$test-interactions`, and screenshot.

2. Production readiness contract without deployment:
   - Add a strict `battle.production_readiness.v1` checklist/validator that
     fails closed until TLS/auth/fanout/reconnect/observability/deploy authority
     receipts exist, then wire current local receipts into it as partial
     evidence.

3. Unbounded swarm qualification gate:
   - Add an explicit fail-closed unbounded-swarm preflight/guard that refuses to
     claim unbounded swarm execution unless external budget/authority and worker
     limits are provided, then proves bounded fallback behavior.

4. Do nothing locally and require human deployment authority:
   - State the exact missing authority or external target needed before any
     production deployment proof can be created.

## Required Answer Format

Return:

1. Recommended next MVP and why.
2. Exact files likely touched.
3. Exact receipt schema/artifact to add.
4. Deterministic proof commands.
5. What the MVP may claim.
6. What the MVP must not claim.
7. Stop condition if the MVP requires human authority, credentials, paid
   services, or a production infrastructure decision.

Do not expand the goal. Do not claim production readiness without production
infrastructure proof.
