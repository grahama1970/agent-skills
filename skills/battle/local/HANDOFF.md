# Battle Handoff — main branch, source-build MVP proof

Timestamp: 2026-07-28
Branch rule: work only on `agent-skills@main`. Do not resume the old
`battle-adaptive-lineage-goal` branch.

## Current GitHub ticket state

Command run:

```bash
gh issue list --repo grahama1970/agent-skills --state open --limit 200 \
  --json number,title,labels,assignees,updatedAt,url \
  | jq '[.[] | select((.title|test("(?i)battle")) or ([.labels[].name] | any(test("(?i)battle"))))]'
```

Result on 2026-07-28: `[]`.

## Main branch receipts

- `773eae2bd873c035892b06b7ced14d6f841f3057`:
  source-built Battle spectator proof, pushed to `refs/heads/main`.
- `324f805b69286f2adc8ea9904233fad56374563a`:
  recovered WebGPT roundtable lane recorded on `main`.
- `848443435...`:
  roundtable synthesis and executable slice manifest recorded on `main`.
- `166cb20f320085b715e00c171ec89dfe171eb085`:
  issue #1040 branch-triage proof recorded on `main`.

Remote check:

```text
773eae2bd873c035892b06b7ced14d6f841f3057	refs/heads/main
```

## Source-build MVP proof

Command:

```bash
cd skills/battle
BATTLE_SPECTATOR_PROOF_ID=20260728T-source-build ./run.sh prove-spectator-source-build
```

Receipt:

- `skills/battle/local/spectator-source-build-20260728T-source-build/proof.json`
- `skills/battle/local/spectator-source-build-20260728T-source-build/captures/results.json`
- `skills/battle/local/spectator-source-build-20260728T-source-build/captures/battle-receipt-controls/0012_pane-controls_screenshot.png`

Result:

```json
{
  "mocked": false,
  "live": true,
  "interaction_counts": {
    "total": 12,
    "passed": 12,
    "failed": 0,
    "warned": 0,
    "skipped": 0
  }
}
```

What this proves:

- `skills/battle/spectator` has a standalone Vite source entrypoint.
- `npm run build` produces a served `dist` artifact from source.
- The source-built `http://127.0.0.1:3015/#battle` route exposes and executes the
  targeted Battle controls required by `$test-interactions`.
- The final screenshot visibly renders the Battle header, roster search,
  receipt-backed timeline, zoom controls, and pane toggles after interaction.

What this does not prove:

- Production hosting.
- Long-running live backend campaigns.
- Provider reliability.

Additional check:

```bash
cd skills/battle/spectator
npm run typecheck
```

Result: `tsc --noEmit -p tsconfig.json` exited `0`.

## Roundtable status

Artifacts:

- `skills/battle/local/roundtable-full-battle-arena-20260728/roundtable-synthesis.md`
- `skills/battle/local/roundtable-full-battle-arena-20260728/executable-slice-manifest.json`
- WebGPT recovery receipt:
  `/mnt/storage12tb/skills/ask/outputs/battle-arena-roundtable-20260728/ask-tau-recovery-round-for-the-missing-w-b812ba02719d/node-artifacts/handler-webgpt/node-receipt.json`

The roundtable is advisory. It does not replace local source-build, typecheck,
browser screenshot, backend endpoint, or live campaign receipts.

## Remaining non-ticket caveats

- The project-state snapshot at
  `skills/battle/local/project-state/battle-project-state-20260728T000000Z.json`
  is an Embry OS-wide snapshot, not a Battle ticket ledger.
- The source-build proof is the first frontend MVP proof. A fully working Battle
  Arena frontend/back end still needs broader live backend campaign proof if the
  human asks for product-level readiness rather than ticket closure.
- Any future UI claim must include `$test-interactions` output and inspected
  screenshot evidence.

