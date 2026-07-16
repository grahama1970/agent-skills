# Handoff Report: Surf

**Timestamp**: 2026-07-16T15:44:26-04:00
**Active Agent**: Codex `/root`

## 1. Project Overview

- **Ecosystem**: Bash and Python skill wrappers around a vendored Node/TypeScript Chrome extension and native host.
- **Core Purpose**: Browser automation plus proof-bearing transport for ChatGPT, Gemini, Kimi, Perplexity, and Cursor Browser.
- **Repository**: `/home/graham/workspace/experiments/agent-skills`
- **Skill root**: `skills/surf`
- **Authoritative remote baseline inspected**: `origin/main` at `f36e42c18e6479c9fcb578168c55fbcee8030d59`
- **Shared checkout at handoff time**: branch `battle-ux8-live-contract` at `32dd59f0082e807e9a3d533897c5e81e44db7ca9`

## 2. Current State (Doc-Code Alignment)

### Documented Features

- Exact-tab WebGPT submission with URL/title preflight and completion sentinel.
- Background `--no-activate` operation with focus-invariance metadata.
- Browser Oracle project binding and guarded tab maintenance.
- Surf Doctor 30-minute maintenance timer and durable recovery receipts.
- Same-tab extraction, WebGPT downloads, screenshot capture, and multiple web-oracle transports.
- Vendored `surf-cli` extension/native-host runtime with content-identity provenance.

### Implemented Reality

- Clean `origin/main` contains fail-closed exact-tab recovery and vendor-provenance work.
- Clean `origin/main` Surf suite: `91 passed in 50.67s` from
  `python3 -m pytest skills/surf/tests -q` in `/tmp/surf-handoff-origin-main`.
- Clean vendor status reports 73 files with matching content identity:
  `c0a024254a7b9c98bca427148c03232e8e0e02964353a8055e80d560b17b9201`.
- The clean worktree has no built `dist` bundle, so `vendor-status.sh --json`
  reports `dist_fresh: false` and `dist_reason: missing dist bundle`. Build and
  reload are required before new live extension proof.
- A live exact-tab WebGPT assessment completed on tab `837358677` without
  activation or focus change. This proves the downstream review transport, not
  the proposed upstream implementation.

### Drift/Misalignments

- `PROJECT_KNOWLEDGE.md` was last updated 2026-05-30 and omits the July recovery,
  timer, receipt, exact-tab, extension-freshness, and upstream-feasibility work.
- `SKILL.md` still says stale-CDP recovery clears the ChatGPT composer and its
  local-storage draft source. Current `origin/main` native code instead fails
  closed on a non-empty composer. The documentation claim is unsafe and stale.
- `README.md` documents the core transport but does not capture the current
  upstream contribution decision or distinguish the dirty shared checkout from
  the clean `origin/main` baseline.
- `01_PROACTIVE_TAB_RECOVERY_TASKS.yaml` is an execution plan without recorded
  per-task completion status. Git history and tests, not the YAML alone, are the
  authoritative completion evidence.

## 3. What is Working Well

- Clean `origin/main` deterministic Surf suite passes: 91 tests.
- Vendor provenance is explicit: the tree is recorded as a downstream-modified
  vendor tree, not falsely presented as a clean upstream copy.
- Exact-tab routing is fail-closed in the merged baseline: requested tab identity
  is retained, fallback tab creation is forbidden for human-named targets, and
  drafts are not silently deleted.
- Guarded maintenance treats active or unknown generation/draft/download state
  as hazardous and uses the centralized receipt writer.
- The feasibility review produced a concrete upstream boundary rather than a
  wholesale vendor sync proposal.

## 4. What is Currently Broken

### Shared Checkout Test Failure

Running `python3 -m pytest skills/surf/tests -q` in the current shared checkout
produced `85 passed, 2 failed in 47.07s`:

1. `test_extension_fresh_reports_installed_host_path_mismatch`
2. `test_extension_fresh_accepts_running_host_from_current_checkout`

The checked-out branch has the tests but an older `extension-fresh.sh` that does
not detect installed native-host checkout mismatch or emit
`installed_host_path_mismatch`. This is branch drift; clean `origin/main` passes.

### Uncommitted Surf Work

Do not discard or overwrite these modified files:

- `scripts/lib/browser_oracle_resolve.sh`
- `scripts/webgpt-preflight.sh`
- `scripts/webgpt-submit.sh`
- `tests/test_webgpt_submit_attach_preflight.py`
- `uv.lock`
- `vendor/surf-cli/src/cdp/controller.ts`
- `vendor/surf-cli/test/unit/cdp/controller.test.ts`

There are also untracked Surf scripts, tests, fixtures, `.surf_artifacts`, and a
shell snapshot. Inventory them with `git status --short -- skills/surf` before
any cleanup or rebase.

The uncommitted CDP controller change blindly detaches and reattaches when Chrome
reports another debugger. Treat it as untrusted: it may detach an external
debugger and does not prove the conflicting session is extension-owned. The
required invariant is bounded same-tab recovery only for stale extension-owned
state; external conflicts must fail closed.

### Repository Safety

The shared worktree has unrelated unmerged Persona Dream paths (`UU`/`DU`) and
large unrelated staged/untracked changes. Do not run broad add, clean, reset,
checkout, rebase, or commit commands in it. Use an isolated worktree from
`origin/main` for Surf implementation.

### Upstream Gap

No upstream Draft PR exists. The proposed controlled-tab behavior has not been
implemented or tested against Nico's current `main`; feasibility is established,
but implementation acceptance is pending.

## 5. Next Steps

1. Create an isolated worktree from current `origin/main`; do not implement on
   `battle-ux8-live-contract` and do not transplant its dirty Surf files blindly.
2. Preserve the current dirty Surf diff as a patch or named worktree artifact.
   Review each change against the clean baseline, especially debugger ownership.
3. Correct `SKILL.md` so stale-CDP recovery never claims automatic draft or
   local-storage deletion. Update `PROJECT_KNOWLEDGE.md` with the July state.
4. Re-run the clean Surf suite, vendor status, extension build/freshness check,
   and mock-evidence checker if the checker exists on the chosen baseline.
5. Reconstruct one upstream Draft PR on Nico's current `main` with title:
   `Draft: add a fail-closed controlled-tab execution contract for ChatGPT`.
6. Keep that PR to the controlled ChatGPT vertical slice: exact target identity,
   focus policy, tab ownership, non-destructive guards, one same-target recovery,
   submission/completion states, and structured JSON execution evidence.
7. Exclude agent-skills wrappers, Browser Oracle, Surf Doctor, Kimi, GPU handling,
   filesystem receipts, download workflows, and provider-wide plugin architecture.
8. Before calling the Draft ready, run upstream deterministic tests and a clean
   built-extension live matrix: background exact-tab success, draft-preservation
   failure, and same-tab CDP recovery or fail-closed conflict.

## 6. Project Context for Success

### Key Files

- `SKILL.md`: operator contract; currently contains the stale draft-clearing claim.
- `README.md`: human/operator guide.
- `PROJECT_KNOWLEDGE.md`: stale project history requiring refresh.
- `run.sh`: skill command router.
- `scripts/webgpt-submit.sh`: exact-tab submission and proof metadata.
- `scripts/webgpt-preflight.sh`: target identity and focus preflight.
- `scripts/tab-maintenance.sh`: guarded maintenance coordinator.
- `scripts/extension-fresh.sh`: installed-host and build freshness gate.
- `scripts/tab_recovery_receipt.py`: centralized fail-closed receipt writer.
- `vendor/surf-cli/native/chatgpt-client.cjs`: provider DOM transport.
- `vendor/surf-cli/src/cdp/controller.ts`: CDP attachment ownership boundary.
- `vendor/surf-cli/VENDOR.lock.json`: vendor content identity.

### Upstream Feasibility Evidence

- Nico checkout: `/tmp/nicobailon-surf-cli-feasibility`
- Nico commit assessed: `64dba493019a25d5aa4b9d228431b309ba362c6f`
- Historical downstream base: `3acf60f98f3a2a8679774ec6f3ecc88433b0e2fb`
- Old feature branch was measured as 67 commits behind and 5 ahead of current
  upstream. Raw vendor-tree transplantation was rejected.
- WebGPT bundle: `/tmp/surf-upstream-pr-feasibility-assess.md`
- Response: `/tmp/surf-upstream-pr-feasibility-assess-assess-response.md`
- Sentinel metadata:
  `/tmp/surf-upstream-pr-feasibility-assess-assess-response.meta.json`
- Reviewer routing proof: requested and controlled tab `837358677`, mismatch
  false, tab not created, not activated, focus unchanged, sentinel present.

### Recent Surf Changes on `origin/main`

- `f139d27dbc1011fbc870952698dd06268148b769` - keep vendor provenance self-consistent.
- `cc4b11f60f2d23fa21ed6ad7fb982a0a53b4198d` - merge exact-tab recovery work.
- `703236190c4a9a678a5cf304933e2413331bcbd3` - preserve recovery evidence without leaks.
- `09f7cdf9b842e4f7f6b719e73c87b741c8c86506` - reconcile extension freshness and vendor provenance.
- `8a05babd27893840bcab0cd58303a196b7003f04` - align submit with native query contract.

### Evidence Classification

- `mocked: no`, `live: yes` for the completed downstream WebGPT review transport.
- `mocked: no`, `live: no` for the clean deterministic 91-test run.
- The proposed upstream controlled-tab feature remains unimplemented and has no
  upstream live acceptance evidence.
