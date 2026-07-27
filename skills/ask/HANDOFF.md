# Handoff Report: Ask Browser Roundtable And Competition

**Timestamp**: 2026-07-27T19:30:00Z
**Active Agent**: Codex
**Directory**: `skills/ask`
**Status**: live competition proof is current; live roundtable proof exists from the same repair slice but was not rerun after the final two small patches.

## 1. Project Overview

- **Ecosystem**: Python CLI/runtime with Tau DAG adapters, Surf browser transport, browser-oracle bindings, and pytest/eval scripts.
- **Core purpose**: `$ask` is the project-agent front door for single handler calls, concurrent roundtables, isolated competitions, creator-reviewer loops, and mixed web/API Tau DAGs.
- **Current goal**: make browser/API roundtable and competition workflows usable by project agents without manual tab rebinding, silent provider failures, or fake proof.

## 2. Current State

`$ask` now documents and routes browser roundtables and competitions through a fresh browser lifecycle by default:

- `--browser-tab-lifecycle auto` creates one Ask-owned Chrome window.
- One fresh provider tab is created per browser handler.
- Run-scoped browser-oracle projects are bound automatically.
- Tau launches browser handler workers concurrently.
- Surf commands still queue on the shared Surf lock at `/tmp/surf.sock`, so browser I/O can serialize even while Tau nodes are concurrent.
- Ask writes `browser-tab-lifecycle.json`, per-node receipts, join receipts, and browser/provider recovery packets.

Recent pushed commits relevant to this slice:

- `816c3bdce41e6c9cf64eff35caa5ae8d39d36c5d` - `Fix Kimi provider setup recovery in Ask`
- `58b7bf8dadd9fcf1f7082e205fa094ba5ca4cb0f` - `Treat stale browser cooldown probes as degraded`

Remote `origin/main` had advanced to `ea6188669a802c702469540c92812a8de41c92d5` when this handoff was prepared, so push this handoff only after integrating current `origin/main`.

## 3. What Is Working Well

### Current live competition proof

- **Run dir**: `/tmp/agent-skills-ask-browser-main-clean.IZmHzF/.ask_artifacts/tau-dag-runs/ask-tau-objective-live-ask-competition-e-12d57a6d0467`
- **Summary**: `/tmp/ask-live-all-four-competition-after-fixes-summary.json`
- **Validation**: `/tmp/ask-live-all-four-competition-after-fixes-validation.json`
- **Workflow**: `compete`
- **Handlers**: `webgpt`, `webclaude`, `webkimi`, `webgemini`
- **Browser lifecycle**: fresh Ask-created window `837363020`
- **Tabs**: `webgpt=837363021`, `webclaude=837363022`, `webkimi=837363026`, `webgemini=837363029`
- **Result**: validator status `PASS`; `mocked:false`; `live:true`; `max_observed_concurrency:4`; `failed_checks:[]`
- **Scorecard**: `status:PASS`; `winner_handler:webkimi`; `winner_node_id:handler-webkimi`
- **Lane evidence**: all four lane receipts were `PASS`, `mocked:false`, `live:true`, `failure_code:null`, and included `PING_RESULT: 4`

Validation command:

```bash
skills/ask/scripts/validate_live_browser_workflow.py \
  /tmp/agent-skills-ask-browser-main-clean.IZmHzF/.ask_artifacts/tau-dag-runs/ask-tau-objective-live-ask-competition-e-12d57a6d0467 \
  --workflow-mode compete \
  --handler webgpt --handler webclaude --handler webkimi --handler webgemini \
  --min-concurrency 4 \
  --require-cleanup \
  --json
```

### Live roundtable proof from this repair slice

- **Run dir**: `/mnt/storage12tb/skills/ask/outputs/ask-tau-objective-live-ask-roundtable-en-3f8204e160cf`
- **Summary**: `/tmp/ask-live-all-four-roundtable-summary.json`
- **Validation**: `/tmp/ask-live-all-four-roundtable-validation.json`
- **Workflow**: `roundtable`
- **Handlers**: `webgpt`, `webclaude`, `webkimi`, `webgemini`
- **Browser lifecycle**: fresh Ask-created window `837362939`
- **Tabs**: `webgpt=837362940`, `webclaude=837362944`, `webkimi=837362945`, `webgemini=837362948`
- **Result**: validator status `PASS`; `mocked:false`; `live:true`; `max_observed_concurrency:4`; `failed_checks:[]`
- **Lane evidence**: all four lane receipts were `PASS`, `mocked:false`, `live:true`, `failure_code:null`, and included `PING_RESULT: 4`

Validation command:

```bash
skills/ask/scripts/validate_live_browser_workflow.py \
  /mnt/storage12tb/skills/ask/outputs/ask-tau-objective-live-ask-roundtable-en-3f8204e160cf \
  --workflow-mode roundtable \
  --handler webgpt --handler webclaude --handler webkimi --handler webgemini \
  --min-concurrency 4 \
  --require-cleanup \
  --json
```

### Provider availability probe behavior

- **Probe artifact**: `/tmp/ask-provider-availability-after-degraded-probe-fix.json`
- **Command status**: exit `0`
- **Report status**: `AVAILABLE_PREFLIGHT`
- **Proof scope**: live read-only provider preflight, not prompt submission.
- **Observed state**: old/background provider tabs timed out on read and are now reported as `probe_degraded:true`, `probe_failed:false`, `failure_code:browser_provider_probe_timeout`, `provider_limited:false`.
- **Important distinction**: visible cooldown/capacity banners remain `NEEDS_ATTENTION`; stale/background read timeouts no longer block a fresh lifecycle run by themselves.

## 4. Deterministic Checks Run

Latest focused checks after the degraded-probe patch:

```bash
uv run --project skills/ask pytest -q \
  skills/ask/tests/test_browser_provider_availability.py \
  skills/ask/tests/test_browser_failure_recovery.py \
  skills/ask/tests/test_tau_dag.py \
  skills/ask/tests/test_tau_roundtable_sanity_eval.py \
  skills/ask/tests/test_validate_live_browser_workflow.py
```

Result: `125 passed in 9.22s`

```bash
uv run pytest -q \
  skills/surf/tests/test_webgpt_submit_attach_preflight.py \
  skills/surf/tests/test_kimi_submit.py
```

Result: `34 passed in 32.12s`

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result: `OK: checked 453 test file(s); no mock+proof claim violations`

Earlier focused checks for the Kimi/provider setup patch:

- `python3 -m py_compile skills/ask/scripts/tau_roundtable_worker.py` -> exit `0`
- `uv run --project skills/ask pytest -q skills/ask/tests/test_browser_failure_recovery.py` -> `25 passed`
- `uv run pytest -q skills/surf/tests/test_kimi_submit.py` -> `3 passed`

## 5. What Is Currently Broken Or Risky

1. **Roundtable was not rerun after the final two commits**. The stored roundtable proof is live and all-four, but strict same-commit release evidence should rerun the roundtable on the current `origin/main`.
2. **Surf lock serialization remains real**. Tau workers start concurrently, but browser submit/read operations queue on the shared Surf lock. The current fix is long lock timeout and waiting, not true independent browser control lanes.
3. **`compete` CLI rejected `--browser-lock-timeout`**. The command-line surface does not accept that option directly. Generated browser handler command specs still include long lock waits internally. Future cleanup should either accept the option at `compete` or document that it is Tau/browser-worker only.
4. **WebGPT focus drift was observed**. The current competition passed with `webgpt` metadata showing recovered focus change (`focus_stolen_despite_no_activate`). Treat that as degraded browser evidence, not proof that focus isolation is perfect.
5. **Provider availability probing old tabs can be slow**. Stale/background tab read timeouts are now degraded instead of blocking, but the probe may still spend time reading old tabs before fresh lifecycle creation.
6. **Generated live artifacts are not committed**. Ask artifacts under `.ask_artifacts/` and `/mnt/storage12tb/skills/ask/outputs/` are evidence paths only. Do not commit them.

## 6. Next Steps

1. Integrate this handoff onto current `origin/main`, commit only `skills/ask/HANDOFF.md`, push to `agent-skills@main`, and verify the remote ref.
2. If strict current-commit proof is required, rerun the all-four live roundtable on the current pushed commit and validate it with `validate_live_browser_workflow.py`.
3. Open or update a follow-up issue for Surf lock serialization if true simultaneous browser control is required rather than queued shared-lock behavior.
4. Clean up the `compete` CLI surface so unsupported lock-timeout flags fail less surprisingly or are accepted and propagated.
5. Keep provider cooldown and rate-limit states lane-local: mark the affected participant unavailable, preserve recovery metadata, and continue with available participants when the workflow allows it.

## 7. Project Context For Success

Key files:

- `skills/ask/SKILL.md`
- `skills/ask/scripts/tau_roundtable_worker.py`
- `skills/ask/scripts/probe_browser_provider_availability.py`
- `skills/ask/scripts/validate_live_browser_workflow.py`
- `skills/ask/tests/test_browser_provider_availability.py`
- `skills/ask/tests/test_browser_failure_recovery.py`
- `skills/ask/tests/test_tau_dag.py`
- `skills/ask/tests/test_tau_roundtable_sanity_eval.py`
- `skills/ask/tests/test_validate_live_browser_workflow.py`
- `skills/surf/scripts/kimi-submit.sh`
- `skills/surf/tests/test_kimi_submit.py`

Known proof standard:

- `mocked:false`
- `live:true`
- every requested browser handler has a terminal node receipt
- browser lifecycle file records fresh window/tabs and cleanup attempt
- roundtable join receipt or competition scorecard is present
- validator reports `failed_checks:[]`
- provider cooldown/capacity states are explicit and lane-local

Handoff runner note: `.pi/skills/handoff/run.sh` was not present/executable in this clean worktree, so this file was synthesized from repo state, pushed commit evidence, and saved Ask live proof artifacts.
