# Handoff Report: ask

**Timestamp**: 2026-07-20T17:14:36Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python skill runtime with shell entrypoint, pytest tests, Tau DAG integration, and browser automation via sibling `$surf` and `$browser-oracle` skills.
- **Core Purpose**: `ask` is the executable `/ask` runtime for memory-backed questions, oracle calls, deep/parallel/CAE reviews, persona and roundtable workflows, image generation, health checks, legacy ask DAGs, and strict Tau DAG execution.
- **Primary Entrypoint**: `skills/ask/run.sh`.
- **Important Contract**: Browser/model/reviewer output is evidence, not closure proof. Local deterministic checks or receipts must back any readiness claim.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - `./run.sh ask "<question>" --json` for memory-backed answers.
  - Oracle, persona, roundtable, argue, deep review, parallel review, CAE gap review, image generation, doctor/status/config, and OS health modes.
  - `./run.sh tau-dag "<request>" ...` as the preferred front door for multi-agent/model workflows, emitting strict `tau.dag_contract.v1` before execution.
  - Opt-in live sanity scripts for WebClaude, WebKimi, Tau DAG e2e/stress, and persona delegate flows.
  - WebGPT/ChatGPT browser flows are documented as removed from `/ask` direct oracle routing; use `$surf webgpt.submit` or a project-level WebGPT workflow directly.
- **Implemented Reality**:
  - Recent work added Tau roundtable compilation and live browser-backed adapter execution for `webclaude`, `webkimi`, `webgemini`, and `webgpt` through Tau command specs.
  - `webgpt` roundtable routing uses browser-oracle project override `webgpt=tau`; generic `webgpt` binding was not used.
  - `skills/surf/scripts/claude-submit.py` now provides `surf claude.submit`, with explicit tab validation and latest-Claude-response sentinel extraction.
  - `skills/ask/scripts/tau_roundtable_sanity_eval.py` now provides default compile/binding checks and opt-in live roundtable checks.
- **Drift/Misalignments**:
  - `SKILL.md` still says WebGPT/ChatGPT routing is deprecated in `/ask`; Tau roundtable now supports `webgpt` as a browser handler via `$surf`, not as an `/ask` oracle backend. Keep this distinction clear in docs and future edits.
  - No `CONTEXT.md` or `0N_TASKS.md` exists in `skills/ask`; this handoff is the current local context bridge.
  - README still presents older browser-oracle examples alongside the newer Tau DAG and browser-handler work. Future doc cleanup should clarify the difference between `/ask` browser review modes and Tau roundtable web handlers.

## 3. What is Working Well

- Focused unit coverage for Tau DAG and roundtable eval paths passed:
  - `uv run --group dev pytest -q tests/test_tau_dag.py tests/test_tau_roundtable_sanity_eval.py tests/test_webclaude_sanity_eval.py tests/test_webkimi_sanity_eval.py`
  - Result: `19 passed`.
- Deterministic/non-mocked Tau sanity checks passed:
  - `/tmp/ask-tau-dag-e2e-sanity-20260720T1257.json`: `status=PASS`, `ok=true`, `mocked=false`, `live=true`, `provider_live=false`.
  - `/tmp/ask-tau-dag-stress-sanity-20260720T1257.json`: `status=PASS`, `ok=true`, `mocked=false`, `live=true`, `provider_live=false`.
- Roundtable default eval passed:
  - `/tmp/ask-roundtable-sanity-eval-default-20260720T1236.json`: `status=PASS`, `ok=true`, `mocked=false`, `live=true`, `provider_live=false`.
  - It verifies browser-oracle bindings and concurrent/sequential Tau DAG compilation; live browser submits are `NOT_RUN` by design unless `--allow-live` is used.
- Live all-four sequential roundtable has one passing receipt:
  - `/tmp/ask-roundtable-live-four-sequential-20260720T123359.json`: `status=PASS`, `ok=true`, `mocked=false`, `live=true`, `provider_live=true`.
  - Handler receipts show `PASS` for `handler-webclaude`, `handler-webkimi`, `handler-webgemini`, `handler-webgpt`, and `join`.
- Live two-handler Kimi/Gemini smoke passed:
  - `/tmp/ask-roundtable-live-two-smoke-20260720T122338.json`: `status=PASS`, `ok=true`, `mocked=false`, `live=true`, `provider_live=true`.
- Current relevant implementation commit is pushed:
  - `e714317294375715d5d2feabaa3e2d8e1d5e099c` on `origin/battle-adaptive-lineage-goal`.

## 4. What is Currently Broken

- **Failed Tests**:
  - No focused pytest failures in the latest Ask roundtable/test slice.
  - `python3 scripts/check_mock_evidence_claims.py` could not run from repo root because `/home/graham/workspace/experiments/agent-skills/scripts/check_mock_evidence_claims.py` does not exist. This is missing-checker, not a passing proof.
- **Known Issues**:
  - Opt-in live roundtable eval had a later failing all-four execution:
    - `/tmp/ask-roundtable-sanity-eval-live-20260720T1236.json`: `status=FAIL`, `ok=false`, `mocked=false`, `live=true`, `provider_live=true`.
    - Passing cases in that eval: browser-oracle bindings, concurrent compile, sequential compile, two-handler live smoke.
    - Failing case: `live-four-handler-sequential`.
    - Root receipt: `/tmp/ask-roundtable-sanity-eval-live-20260720T1236/live-four-handler-sequential/ask-tau-roundtable-webclaude-webkimi-web-0887c2099a83/node-artifacts/handler-webgpt/node-receipt.json`.
    - Failure: `webgpt.submit` timed out after 990 seconds waiting for the WebGPT sentinel.
  - Live concurrent all-four browser execution is not proven. Concurrent DAG compilation is covered, but live concurrent browser submits were avoided because browser focus/contention could invalidate the proof.
  - WebGPT transport can be slow or stall. Treat WebGPT roundtable proof as timing-sensitive and receipt-dependent.
- **Recent Regressions / Repair History**:
  - Tau initially rejected synthetic `start` nodes and non-routable handler agents; fixed by removing synthetic `start`, using `handler-*` as Tau-routable agent ids, and preserving actual handler names in context.
  - Tau join initially failed on an empty command argument from `--browser-oracle-project ""`; fixed and covered by tests.
  - Claude submit initially accepted a sentinel embedded in the submitted prompt rather than only the latest Claude response; fixed by latest-response extraction and explicit-tab validation.

## 5. Next Steps

1. Re-run the opt-in live roundtable eval when WebGPT is responsive:
   ```bash
   cd /home/graham/workspace/experiments/agent-skills/skills/ask
   uv run python scripts/tau_roundtable_sanity_eval.py --allow-live --output-root /tmp/ask-roundtable-sanity-eval-live-$(date +%Y%m%dT%H%M%S) --timeout-seconds 1800 --json
   ```
   Closure bar: all cases `PASS`, especially `live-four-handler-sequential`, with `provider_live=true` for all four handlers and `join`.
2. Decide whether WebGPT timeout handling should be a retry policy, a longer timeout, or an explicit degraded/blocked status in `tau_roundtable_sanity_eval.py`. Do not hide timeouts as success.
3. Update Ask docs to describe the current distinction:
   - `/ask` direct WebGPT oracle routing remains deprecated/fail-closed.
   - Tau roundtable can use `webgpt` as a `$surf` browser handler with `--handler-project webgpt=tau`.
4. Consider adding a smaller WebGPT-only live sanity check for Tau roundtable handler transport, separate from all-four runs, to isolate WebGPT availability from cross-handler orchestration.
5. If live concurrent all-four support is required, design a browser-focus-safe proof first. Do not infer concurrent live readiness from concurrent compile-only DAG checks.

## 6. Project Context for Success

- **Key Files**:
  - `skills/ask/run.sh`: main Ask CLI shell entrypoint.
  - `skills/ask/src/ask/tau_dag.py`: Tau DAG compile/execute logic and roundtable DAG generation.
  - `skills/ask/src/ask/tau_dag_cli.py`: Typer CLI for `tau-dag`.
  - `skills/ask/scripts/tau_roundtable_worker.py`: live Tau node worker for web handlers and join.
  - `skills/ask/scripts/tau_roundtable_sanity_eval.py`: default and opt-in live roundtable eval.
  - `skills/ask/tests/test_tau_dag.py`: Tau DAG and roundtable compile contract tests.
  - `skills/ask/tests/test_tau_roundtable_sanity_eval.py`: eval contract tests.
  - `skills/surf/scripts/claude-submit.py`: Surf Claude submit wrapper.
  - `skills/surf/run.sh`: Surf command router, including `claude.submit`.
- **Recent Relevant Commits**:
  - `e71431729 Add live ask roundtable browser adapters`.
  - `9306ceec6 Add ask roundtable Tau DAG compile path`.
  - `1b534a113 Add WebKimi sanity eval`.
  - `55ec0ee13 Add ask WebClaude sanity eval`.
  - `8931ee990 Teach ask tau-dag live scillm routing`.
- **Current Browser Bindings Used In Proofs**:
  - `webclaude`: tab `837359291`, URL `https://claude.ai/chat/3cdf38d5-2c6c-4727-b5b9-eb7fd95f5146`.
  - `webkimi`: tab `837359704`, URL `https://www.kimi.com/chat/19f7fb71-76e2-812e-8000-095c2eacb877?chat_enter_method=home`.
  - `webgemini`: tab `837359725`, URL `https://gemini.google.com/app`.
  - `webgpt`: project `tau`, tab `837359244`, URL `https://chatgpt.com/g/g-p-6a401806e7a08191a4ea6745a305f981-tau/c/6a5a1f08-edc8-83ea-8376-6dd6d7accd16`.
- **Git/Workspace Notes**:
  - Branch at handoff time: `battle-adaptive-lineage-goal`.
  - Relevant Ask/Surf roundtable work was committed and pushed at `e714317294375715d5d2feabaa3e2d8e1d5e099c`.
  - The broader repository still has many unrelated dirty files outside this task. Do not stage or revert unrelated changes.
  - This handoff file itself is new local project context and should be committed separately if accepted.
