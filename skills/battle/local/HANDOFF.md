# Battle Handoff - main branch only

Timestamp: 2026-07-29T14:35Z

Branch rule: work only in `/home/graham/workspace/experiments/agent-skills-main-clean`
on branch `main`. Do not continue old Battle feature branches, detached
worktrees, `/tmp` source trees, or `/home/graham/workspace/experiments/agent-skills`
as authoritative Battle source.

Current remote proof commit:

```text
fbebe321e4a28b5b17ca204d27a386d4fa147d04 battle: prove live frontend backend route
```

Remote readback:

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
5. Ticket state: no open GitHub issue has label `battle`; `#1040` reads back
   closed/completed.

Intended/missing product scope:

1. Production deployment is not proven.
2. WebSocket transport is not implemented/proven.
3. Live Tau/provider/Docker/Judge runtime directories are not proven by this
   slice.
4. Exploit success, Blue detection/kill/block, Judge exploit success, and
   memory promotion are not proven by this slice.
5. Global `skills/project-state/run.sh report --json` reports the wider
   Embry/agent-skills environment, not a Battle-specific readiness verdict.

Immutable Goal: NOT_MET

## Proof Receipts

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

Mechanical mock-claim check:

```bash
python3 scripts/check_mock_evidence_claims.py
# OK: checked 473 test file(s); no mock+proof claim violations
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

## Next Deterministic Action

If the human means the local frontend/backend MVP only, the strongest current
receipt is:

```text
skills/battle/local/working-frontend-backend-20260729/evidence-bundle.json
```

If the human means full production Battle, the next MVP should be a narrow
live-Tau/Docker/Judge rung that proves one real team handoff, one executable
artifact, and one Judge replay receipt. Do not use direct Battle-to-Scillm
routing; Tau owns subagent/model execution.
