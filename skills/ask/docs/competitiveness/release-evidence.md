# /ask Control Plane Evidence

Created: 2026-05-30

This is not a release-ready claim. It records concrete evidence from the current
control-plane improvement slice.

## Local Gates

Command:

```bash
PYTHONPATH=skills/ask/src uv run --project skills/ask --group dev python -m pytest -q \
  skills/ask/tests/test_ask_cli_protocols.py \
  skills/ask/tests/test_run_state_protocol.py \
  skills/ask/tests/test_cursor_browser_aliases.py \
  skills/ask/tests/test_webgpt_explicit_orchestration.py \
  skills/ask/tests/test_ask_oracle_protocols.py \
  skills/ask/tests/test_oracle_contracts.py \
  skills/ask/tests/test_config_doctor.py \
  skills/ask/tests/test_web_review_bundle_validation.py
```

Observed result:

```text
159 passed in 33.64s
```

## Live Doctor

Command:

```bash
./skills/ask/run.sh doctor --live --json
```

Observed lane state summary after the lane-health patch:

```text
cursor-browser=needs_attention :: cursor-browser-bridge is not running; /tmp/cursor-browser-bridge-port is missing
scillm=needs_attention :: exit=1 stderr=Could not determine current text model from proxy config
webgpt=available :: static prerequisites present; live readiness not asserted
```

## Real Fail-Closed Route Proof

Command:

```bash
./skills/ask/run.sh ask oc-kimi "artifact manifest lane gate smoke" \
  --ask-id scillm-manifest-gate-smoke \
  --run-output-root /tmp/ask-lane-gate \
  --overwrite \
  --json
```

Observed result:

```text
selected_oracle_lane_unavailable
/tmp/ask-lane-gate/scillm-manifest-gate-smoke/artifact_manifest.json
ask.artifact_manifest.v1
needs_attention
scillm
selected_oracle_lane_unavailable
```

Manifest path:

```text
/tmp/ask-lane-gate/scillm-manifest-gate-smoke/artifact_manifest.json
```

The manifest contains:

- `schema_version: ask.artifact_manifest.v1`
- `state: needs_attention`
- `route_decision.selected_backend: scillm`
- `needs_attention.reason: selected_oracle_lane_unavailable`

## WebGPT Review

Run id:

```text
ask-control-plane-value-review-r2
```

Artifact directory:

```text
/tmp/ask-control-plane-webgpt/ask-control-plane-value-review-r2
```

Reviewer verdict:

```text
NEEDS_CHANGES
```

Key reviewer demand:

```text
Make route_decision.unavailable_lane_reasons real by wiring doctor/lane-health state into routing; fail closed when a selected browser/scillm lane is unavailable or degraded.
```

Implemented response in this slice:

- selected unavailable `cursor-browser` exits before oracle transport
- selected unavailable `scillm` exits before oracle transport
- every run status now references `artifact_manifest.json`
- manifest records route decision and needs-attention evidence

## Remaining Blockers

- Cursor Browser bridge must be started before `cursor-browser` live review can
  be claimed.
- WebGPT is live and artifact-backed, but WebGPT review is not local closure
  proof by itself.

## Scillm Lane Debugger Follow-Up

Runtime-state question:

```text
Why does ./skills/scillm/run.sh warm-check --json fail with "Could not determine current text model from proxy config"?
```

Debugger proof artifact:

```text
/tmp/scillm-warm-check-debugger-proof.json
```

Observed breakpoint state:

```text
Breakpoint: skills/scillm/scripts/warm_check.py:158
source: model_id = get_current_text_model()
locals: args=Namespace(model=None, json=True), model_id=None
watch: PROXY_CONFIG.exists() == True

Breakpoint: skills/scillm/scripts/warm_check.py:33
source: if "model_name: text" in line and "text-" not in line:
locals: in_text_block=False, line='general_settings:'
```

The live config contains:

```text
57:   - model_name: chutes-deepseek
59:       model: deepseek-ai/DeepSeek-V3.2-TEE
```

Patch response:

- `skills/scillm/scripts/warm_check.py` now accepts current `chutes-deepseek`
  and legacy `text` default text profiles.
- `skills/scillm/tests/test_warm_check.py` covers both config shapes.

Regression command:

```bash
python3 -m unittest skills.scillm.tests.test_warm_check -v
```

Observed result:

```text
Ran 2 tests in 0.001s
OK
```

Live warm-check command:

```bash
./skills/scillm/run.sh warm-check --json
```

Observed result:

```json
{
  "model": "deepseek-ai/DeepSeek-V3.2-TEE",
  "current_hot": false,
  "recommendation": null,
  "variants": [],
  "switch_needed": false
}
```

Live `/ask` scillm lane command:

```bash
./skills/ask/run.sh ask oc-kimi "Return exactly: ask scillm lane smoke" \
  --ask-id scillm-lane-smoke-after-warmcheck-fix \
  --run-output-root /tmp/ask-lane-gate \
  --overwrite \
  --json
```

Observed result fields:

```text
answer: ask scillm lane smoke
oracle.backend: scillm
oracle.model: opencode-go/kimi-k2.6
oracle.model_served: opencode-go/kimi-k2.6
oracle.adapter_response.schema_version: ask.oracle_adapter_response.v1
oracle.adapter_response.status: ok
artifact_manifest.schema_version: ask.artifact_manifest.v1
artifact_manifest.state: answered
artifact_manifest.result_summary.oracle_backend: scillm
artifact_manifest.result_summary.oracle_model_served: opencode-go/kimi-k2.6
```

Affected suite rerun:

```bash
PYTHONPATH=skills/ask/src uv run --project skills/ask --group dev python -m pytest -q \
  skills/ask/tests/test_ask_cli_protocols.py \
  skills/ask/tests/test_run_state_protocol.py \
  skills/ask/tests/test_ask_oracle_protocols.py \
  skills/ask/tests/test_oracle_contracts.py \
  skills/ask/tests/test_config_doctor.py \
  skills/ask/tests/test_web_review_bundle_validation.py
```

Observed result:

```text
156 passed in 36.52s
```
