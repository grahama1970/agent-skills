# Battle Production Infrastructure MVP Competition Packet

## Objective

Find the next smallest honest MVP that unblocks Battle's remaining
production-infrastructure readiness gap without making a false production-ready
claim.

## Immutable Goal

Deliver production-scope Battle frontend and backend behavior with deterministic
local receipts, beyond the prior local MVP proof.

## Target Repo / Branch

- Repo: `/home/graham/workspace/experiments/agent-skills-main-clean`
- Branch: `main`
- Remote readback: `origin/main` =
  `b43a85e29fbf10f5f90953486aaf1b5a5de71292`
- Do not use old Battle branches, detached worktrees, or `/tmp` source trees.

## Source-Derived Current State

1. Implemented: local Battle HTTP/SSE/WebSocket backend adapter serves
   `battle.snapshot.v1` and ordered `battle.live_event.v1` for `battle-004`.
2. Implemented: source-built Vite spectator frontend renders the Battle live
   route against the local adapter.
3. Implemented: Docker container packaging runs the backend adapter and Vite
   preview together.
4. Implemented: production-shaped local WebSocket proof covers auth rejection,
   bad-token rejection, Last-Event-ID resume, future cursor fail-closed behavior,
   and two-client fanout.
5. Implemented: Docker-backed dynamic swarm proof covers 12 isolated no-network
   workers with max observed concurrency 12.
6. Implemented: fail-closed production-readiness contract accepts local
   container, WebSocket, and swarm receipts.
7. Intended/missing: production infrastructure deployment receipt is still
   missing.
8. Intended/missing: cloud/Kubernetes/DNS/cert/ingress/secret-management
   behavior is not proven.
9. Intended/missing: production TLS/certificate-backed WebSocket deployment and
   production-scale fanout capacity are not proven.
10. Intended/missing: mathematically infinite swarm execution and production
    cluster autoscaling are not proven.

## Deterministic Evidence Already Produced

- Containerized frontend/backend receipt:
  `skills/battle/local/containerized-deployment-smoke-20260729-next6/containerized-deployment-smoke.json`
  - `status`: `PASS`
  - `mocked`: `false`
  - `live`: `containerized_http_sse_websocket_adapter_plus_vite_preview`
  - PR8: `33 total / 0 failed`
  - `$test-interactions`: `38 passed / 0 failed / 0 warned`
  - visual findings: `0`
  - source commit: `ab622a7d47c138ce1769beb308c1644e9187ed91`

- Production-shaped WebSocket receipt:
  `skills/battle/local/production-websocket-transport-20260729-next1/production-websocket-transport-proof.json`
  - `status`: `PASS`
  - `mocked`: `false`
  - missing auth and bad token rejected with code `1008`
  - reconnect from `Last-Event-ID: 2` returned `34` events
  - future `Last-Event-ID` rejected with code `1008`
  - two client fanout streams identical

- Docker-backed dynamic swarm receipt:
  `skills/battle/local/unbounded-swarm-execution-20260729-next1/unbounded-swarm-execution-proof.json`
  - `status`: `PASS`
  - `mocked`: `false`
  - `worker_count`: `12`
  - `completed`: `12`
  - `failed`: `0`
  - `max_concurrent_observed`: `12`
  - `network_mode`: `none`

- Current readiness receipt:
  `skills/battle/local/production-readiness-contract-20260729-next5/production-readiness-contract.json`
  - `status`: `BLOCKED`
  - local frontend/backend: `PASS`
  - production WebSocket: `PASS`
  - unbounded swarm: `PASS`
  - only blocker:
    `production_infrastructure_missing_or_not_pass`

## Deployment Clue From Repo

`skills/battle/GOAL_ADAPTIVE_LINEAGE.md` says UX acceptance depends on
`/mnt/storage12tb/deployments/agent-skills/current` pointing at a release that
contains current code. Local inspection shows:

- `/mnt/storage12tb/deployments/agent-skills/current` exists.
- It points to `/mnt/storage12tb/deployments/agent-skills/releases/995ea0ad8`.
- That release's handoff says it came from the old
  `battle-adaptive-lineage-goal` branch, not current `main`.
- No release-cut script was found beyond repo-level `deploy.sh`, which only
  symlinks skills/hooks into agent directories and does not cut a release.

## Candidate Task

Propose the smallest production-infrastructure MVP that the project agent can
implement or prove next.

The answer must distinguish:

- a real production infrastructure receipt, if enough target/authority exists;
- a local deployment-alignment receipt, if only the `/mnt/storage12tb`
  release symlink can be proven;
- a true human blocker, if selecting or mutating the production target requires
  human authority.

## Expected Candidate Output

Use this exact structure:

```text
APPROACH:
CHANGES:
VERIFIED_FEATURE:
RISKS:
PROOF_COMMANDS:
BLOCKERS:
RECOMMENDED_NEXT_ACTION:
```

## Allowed Files / Boundaries

- Prefer existing Battle code and receipts.
- Do not propose editing `/tmp` source trees.
- Do not propose using old Battle branches.
- Do not propose direct `$scillm` use; Battle routes through Tau where relevant.
- Do not claim production readiness from model prose or mocked checks.
- Do not say local symlink proof proves cloud/Kubernetes/DNS/TLS/cert/ingress
  behavior.

## Judging Criteria

1. Honest claim boundary.
2. Deterministic proof path.
3. Minimal code or deployment mutation.
4. Compatibility with the current `battle.production_readiness_contract.v1`
   schema, or a precise schema change if the current schema would create a
   false claim.
5. Safe treatment of `/mnt/storage12tb/deployments/agent-skills/current`.

## Proof Boundary

Candidate output is advisory only. Local closure still requires code inspection,
deterministic receipts, screenshot or endpoint proof where relevant, focused
tests, committed artifacts, push to `origin/main`, and remote ref readback.
