# Battle Handoff - main branch only

Timestamp: 2026-07-29T15:33Z

Branch rule: work only in `/home/graham/workspace/experiments/agent-skills-main-clean`
on branch `main`. Do not continue old Battle feature branches, detached
worktrees, `/tmp` source trees, or `/home/graham/workspace/experiments/agent-skills`
as authoritative Battle source.

Frontend proof commit already on `origin/main`:

```text
fbebe321e4a28b5b17ca204d27a386d4fa147d04 battle: prove live frontend backend route
```

Remote readback before this handoff update:

```bash
git ls-remote origin refs/heads/main
# fbebe321e4a28b5b17ca204d27a386d4fa147d04 refs/heads/main
```

## Current Slice

Objective: deliver and prove a local Battle frontend plus backend path without
using stale feature branches or reviewer output as closure proof.

Implemented/proven local slice:

1. Backend: local HTTP SSE adapter serves `battle.snapshot.v1` and
   `battle.live_event.v1` for `battle-004`.
2. Frontend: source-built Vite Battle spectator renders `#battle/live` against
   that adapter.
3. Pixi/live route: `#battle/live?engine=pixi&battle=battle-004&liveBase=...`
   shows the live adapter state, EventSource transport, `MOCKED: NO`, and
   `seq 36/36`.
4. Interaction surface: `$test-interactions` exercises the live route through
   QID/action/title interactions.
5. Backend live MVP: Battle creates Arena public/private artifacts, invokes
   Tau Red/Blue through the Tau handoff bridge, receives Tau subagent receipts,
   materializes Red/Blue executable artifacts, and Judge replays the pair in
   Docker.
6. Prekill survival lineage: a parent Red pressure receipt causes a
   parent-authored pre-terminal child spawn; the child materializes and gets a
   real post-terminal Judge receipt.
7. V16 durable Memory chain: Battle writes and exactly recalls one team-scoped
   measured RelayForge record through the production Memory API, then a live
   Tau/SciLLM provider cites and uses it to change a Blue strategy artifact.
8. V16 live topology: one immutable nine-service RelayForge topology runs a
   live bounded Red/Blue campaign; provider artifacts are converted into typed
   Battle-selected public actions and bound to private Judge measurements.
9. Ticket state: no open GitHub issue has label `battle`; `#1040` reads back
   closed/completed.

Intended/missing product scope:

1. Production deployment is not proven.
2. WebSocket transport is not implemented/proven.
3. Unbounded swarm execution is not proven.
4. Blue kill/promotion and memory-improved Judge outcome are not proven by this
   slice.
5. Global `skills/project-state/run.sh report --json` reports the wider
   Embry/agent-skills environment, not a Battle-specific readiness verdict.
6. Six-trial qualification, factorial effects, and cross-target generalization
   are not proven.

Immutable Goal: NOT_MET

## 2026-07-29 Current-Main Update

Source commit under the newest deployment proof:

```text
69d65110f503170fc2a8e39b345a61398a110f41
```

New bounded receipts on `main`:

1. Packaged frontend/backend smoke with WebSocket:
   `skills/battle/local/packaged-deployment-smoke-current-main-20260729-next5/packaged-deployment-smoke.json`
   - `status`: `PASS`
   - `mocked`: `false`
   - `live`: `packaged_local_http_sse_websocket_adapter_plus_vite_preview`
   - PR8: `33 total / 0 failed`
   - `$test-interactions`: `38 passed / 0 failed / 0 warned`
   - visual findings: `0`
   - backend WebSocket proof: `websocket_event_count=36`,
     `websocket_snapshot_first=true`, `websocket_matches_sse_payloads=true`

2. Bounded live Memory ablation:
   `skills/battle/local/adaptive-memory-ablation-v15-20260729-next5/memory-ablation-result.json`
   - `status`: `PASS`
   - live trials: `12/12`
   - all trials crossed Tau, Docker, and Judge: `true`
   - Red memory classification: `INCONCLUSIVE`
   - Blue memory classification: `INCONCLUSIVE`

3. Containerized local frontend/backend deployment smoke:
   `skills/battle/local/containerized-deployment-smoke-20260729-next3/containerized-deployment-smoke.json`
   - `status`: `PASS`
   - `mocked`: `false`
   - `live`: `containerized_http_sse_websocket_adapter_plus_vite_preview`
   - Docker image id:
     `sha256:596dc25fe5cbab67c94cab6a70f8dad570755b8aabcddd1a4e3a5bc83dbceba2`
   - PR8: `33 total / 0 failed`
   - `$test-interactions`: `38 passed / 0 failed / 0 warned`
   - visual findings: `0`
   - screenshot:
     `skills/battle/local/containerized-deployment-smoke-20260729-next3/frontend-pr8/01-live-sse-adapter.png`

4. Ask competition attempt for next MVP:
   `/mnt/storage12tb/skills/ask/outputs/battle-next-mvp-production-deployment-20260729/battle-next-mvp-production-deployment-execute-20260729`
   - `webgemini`: `PASS`
   - `webclaude`: `NEEDS_ATTENTION`, `surf_browser_connection_unavailable`
   - `webkimi`: `NEEDS_ATTENTION`, `surf_browser_connection_unavailable`
   - `webgrok`: `NEEDS_ATTENTION`, `missing_sentinel`
   - Tau progress verdict: `SURF_BROWSER_CONNECTION_UNAVAILABLE`
   - WebGPT was availability-probed by the runtime, but `/ask` no longer accepts
     WebGPT as a compete handler; use the project WebGPT/Surf workflow for a
     separate WebGPT lane.

The containerized proof may claim only local Docker container packaging and
mapped local frontend/backend execution. It still must not claim production
infrastructure, TLS/auth/fanout/reconnect behavior, cloud/Kubernetes/DNS/secret
management, unbounded swarm execution, Battle/RelayForge production readiness,
six-trial qualification, factorial effects, or cross-target generalization.

## Proof Receipts

Combined evidence receipt:

```text
skills/battle/local/full-working-battle-evidence-20260729.json
```

Production-scope partial receipt:

```text
skills/battle/local/production-scope-battle-evidence-20260729.json
```

Current V16 production-scope partial receipt:

```text
skills/battle/local/production-scope-v16-evidence-20260729.json
```

Evidence bundle:

```text
skills/battle/local/working-frontend-backend-20260729/evidence-bundle.json
```

Result summary:

```json
{
  "schema": "battle.working_frontend_backend_evidence.v1",
  "status": "PASS",
  "mocked": false,
  "live": "local_http_sse_adapter_plus_vite_preview",
  "branch": "main"
}
```

Integrated frontend/backend proof:

```bash
cd skills/battle/spectator
BATTLE_HOST=http://127.0.0.1:3016 \
BATTLE_LIVE_TRANSPORT_BASE=http://127.0.0.1:18766 \
BATTLE_LIVE_TRANSPORT_PROOF_DIR=/home/graham/workspace/experiments/agent-skills-main-clean/skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-ui-fallback \
npm run prove:pr8-live-transport
```

Receipt:

```text
skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-ui-fallback/summary.json
```

Readback:

```json
{
  "mocked": false,
  "live": "local_http_sse_adapter",
  "checks_total": 33,
  "failed": []
}
```

Screenshot inspected:

```text
skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-ui-fallback/01-live-sse-adapter.png
```

Visible state observed: live adapter banner, `LIVE: LOCAL HTTP SSE`,
`MOCKED: NO`, `TRANSPORT: EVENTSOURCE`, `seq 36/36`, and the claim boundary.

`$test-interactions` proof:

```bash
skills/test-interactions/run.sh run \
  --manifest skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/live-route-unique-hash-manifest.json \
  --output-dir skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/captures-live-route-unique-hash \
  --max-retries 1
```

Receipt:

```text
skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/captures-live-route-unique-hash/results.json
```

Readback:

```json
{
  "run_id": "test-interactions-20260729T142159889006Z",
  "total": 38,
  "passed": 38,
  "failed": 0,
  "warned": 0,
  "skipped": 0
}
```

Refreshed `$test-interactions` proof after V16 backend work:

```bash
skills/test-interactions/run.sh run \
  --manifest /home/graham/workspace/experiments/agent-skills-main-clean/skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/live-route-unique-hash-manifest.json \
  --output-dir /home/graham/workspace/experiments/agent-skills-main-clean/skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/captures-live-route-v16-refresh \
  --max-retries 1
```

Receipt:

```text
skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/captures-live-route-v16-refresh/results.json
```

Readback:

```json
{
  "run_id": "test-interactions-20260729T153115519021Z",
  "total": 38,
  "passed": 38,
  "failed": 0,
  "warned": 0,
  "skipped": 0
}
```

Refreshed PR8 live transport proof:

```bash
cd skills/battle/spectator
BATTLE_HOST=http://127.0.0.1:3016 \
BATTLE_LIVE_TRANSPORT_BASE=http://127.0.0.1:18766 \
BATTLE_LIVE_TRANSPORT_PROOF_DIR=/home/graham/workspace/experiments/agent-skills-main-clean/skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-v16 \
BATTLE_LIVE_TRANSPORT_TIMEOUT_MS=120000 \
npm run prove:pr8-live-transport
```

Readback:

```json
{
  "mocked": false,
  "live": "local_http_sse_adapter",
  "checks_total": 33,
  "failed": []
}
```

Screenshot inspected:

```text
skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-v16/01-live-sse-adapter.png
```

Visible state observed: live adapter banner, `LIVE: LOCAL HTTP SSE`,
`MOCKED: NO`, `TRANSPORT: EVENTSOURCE`, `SEQ 36/36`, and the claim boundary.

Live V16 durable Memory chain:

```bash
cd skills/battle
./run.sh v16-memory-chain-qualify \
  --deterministic-qualification local/production-scope-v16-deterministic-20260729 \
  --out local/production-scope-v16-memory-chain-postfilter-20260729
```

Receipt:

```text
skills/battle/local/production-scope-v16-memory-chain-postfilter-20260729/memory-chain-qualification.json
```

Readback:

```json
{
  "status": "PASS",
  "mocked": false,
  "live": true,
  "closed_blocker": "durable-memory-packets-unimplemented",
  "remaining_blockers": ["live-topology-not-qualified"]
}
```

Live V16 topology:

```bash
cd skills/battle
./run.sh v16-live-topology-qualify \
  --freeze local/production-scope-v16-freeze-20260729 \
  --deterministic-qualification local/production-scope-v16-deterministic-20260729 \
  --memory-chain local/production-scope-v16-memory-chain-postfilter-20260729 \
  --out local/production-scope-v16-live-topology-zipadapter-20260729
```

Receipt:

```text
skills/battle/local/production-scope-v16-live-topology-zipadapter-20260729/live-topology-qualification.json
```

Readback:

```json
{
  "status": "PASS",
  "mocked": false,
  "live": true,
  "closed_blocker": "live-topology-not-qualified",
  "remaining_blockers": [],
  "judge_verdict": "CONTESTED",
  "production_readiness_proven": false
}
```

Mechanical mock-claim check:

```bash
python3 scripts/check_mock_evidence_claims.py
# OK: checked 473 test file(s); no mock+proof claim violations
```

Live Tau/Docker/Judge backend MVP:

```bash
cd skills/battle
./run.sh arena-tau-public-only-proof battle-004 \
  --out local/full-battle-mvp-tau-docker-judge-20260729 \
  --query "OWASP file upload zip slip path traversal vulnerability" \
  --docker-image python:3.12-slim \
  --timeout-s 120 \
  --red-workers 1 \
  --blue-workers 1
```

Run receipt:

```text
skills/battle/local/full-battle-mvp-tau-docker-judge-20260729/run-receipt.json
```

Readback:

```json
{
  "schema": "battle.arena_tau_public_only_run_receipt.v1",
  "status": "PASS",
  "mocked": false,
  "live": "brave_search_docker_arena_oracle_tau_harness",
  "verdict": "BLUE_SUCCESS",
  "worker_counts": {
    "red_materialized": 1,
    "blue_materialized": 1,
    "judged_pairs": 1,
    "blue_success_pairs": 1
  }
}
```

Judge receipt:

```text
skills/battle/local/full-battle-mvp-tau-docker-judge-20260729/judge/judge-receipt.json
```

Judge readback:

```json
{
  "schema": "battle.arena_tau_public_only_judge_receipt.v1",
  "status": "PASS",
  "verdict": "BLUE_SUCCESS",
  "judged_pair_count": 1,
  "insufficient_evidence_count": 0
}
```

Tau manifest:

```text
skills/battle/local/full-battle-mvp-tau-docker-judge-20260729/tau-live/manifest.json
```

Tau readback:

```json
{
  "schema": "tau.battle_live_handoff_proof.v1",
  "status": "PASS",
  "mocked": false,
  "live": true,
  "materialized_counts": {
    "red": 1,
    "blue": 1
  }
}
```

Prekill survival / child-lineage proof:

```bash
cd skills/battle
./run.sh arena-prekill-survival-proof battle-004 \
  --out local/production-scope-prekill-survival-20260729 \
  --query "OWASP file upload zip slip path traversal vulnerability" \
  --docker-image python:3.12-slim \
  --timeout-s 180 \
  --red-workers 2 \
  --blue-workers 2
```

Run receipt:

```text
skills/battle/local/production-scope-prekill-survival-20260729/run-receipt.json
```

Readback:

```json
{
  "status": "PASS",
  "verdict": "BLUE_SUCCESS",
  "worker_counts": {
    "red_materialized": 2,
    "blue_materialized": 2,
    "judged_pairs": 4,
    "blue_success_pairs": 4,
    "red_child_spawn_requested": true
  },
  "lineage_request": {
    "mode": "prekill_survival_parent_decision",
    "requested": true,
    "status": "PASS"
  }
}
```

Lineage receipt:

```text
skills/battle/local/production-scope-prekill-survival-20260729/lineage-receipts.json
```

Lineage readback:

```json
{
  "schema": "battle.lineage_receipts_bundle.v1",
  "status": "PASS",
  "lineage_mode": "prekill_survival_parent_decision",
  "spawn_count": 1,
  "errors": []
}
```

Judge receipt:

```text
skills/battle/local/production-scope-prekill-survival-20260729/judge/judge-receipt.json
```

Judge readback:

```json
{
  "schema": "battle.arena_tau_public_only_judge_receipt.v1",
  "status": "PASS",
  "verdict": "BLUE_SUCCESS",
  "judged_pair_count": 4,
  "red_artifact_count": 2,
  "blue_artifact_count": 2,
  "blue_success_count": 4,
  "insufficient_evidence_count": 0
}
```

## Ticket Readback

Commands:

```bash
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh doctor --repo grahama1970/agent-skills
gh issue list --repo grahama1970/agent-skills --state open --label battle --limit 100 --json number,title,state,labels,updatedAt,url
skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh show 1040 --repo grahama1970/agent-skills
```

Readback:

```json
{"ok":true,"action":"doctor","status":"ok","missing_label_count":"0"}
```

Open `battle` label result:

```json
[]
```

Issue `#1040`: `CLOSED`, `stateReason: COMPLETED`.

## Next Product Scope

The frontend/backend local MVP and the child-lineage Tau/Docker/Judge rung now
have deterministic local receipts. WebSocket transport, bounded live Memory
ablation, and a local Docker containerized frontend/backend deployment smoke now
also have deterministic local receipts. The remaining production-shaped scope is:
external production infrastructure authority and proof, production
TLS/auth/fanout/reconnect behavior, unbounded swarm execution, and any broader
Battle/RelayForge production-readiness claim.
