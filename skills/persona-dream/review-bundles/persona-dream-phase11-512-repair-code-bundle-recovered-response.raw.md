Download the Phase 11 provider-contract repair patch

Base commit:
8be2a262f2ab5e1de4a39d96964dccadb9dd7b51

Byte count:
64718

SHA-256:
3d8c523a1ca80bf8fac70c4118847f22ea8082bb875d920cebeb692bc42d903e

git apply --check:
0

git diff --check:
0

Focused tests:
33 passed

Provider calls during proof:
0

The official Standard I2V contract confirms the multi_prompt shot structure, element references, queue submit/status/result lifecycle, and required media fields. The patch treats the committed live HTTP 422 receipt—not the broader documentation guidance—as authority for the enforced 512-character per-shot limit.
Fal AI

Bash
set -euo pipefail

test "$(git rev-parse HEAD)" = \
  "8be2a262f2ab5e1de4a39d96964dccadb9dd7b51"

git apply --check \
  /path/to/persona-dream-phase11-provider-contract-repair.patch

git apply \
  /path/to/persona-dream-phase11-provider-contract-repair.patch

git diff --check
Bash
python3 -m py_compile \
  skills/persona-dream/scripts/phase11_payload_binding.py \
  skills/persona-dream/scripts/phase11_canonical_common.py \
  skills/persona-dream/scripts/phase11_execution_common.py \
  skills/persona-dream/scripts/phase11_fal_canary_adapter.py

python3 -m pytest -q \
  skills/persona-dream/tests/test_phase11_payload_binding_bootstrap.py \
  skills/persona-dream/tests/test_phase11_canonical_live_request.py \
  skills/persona-dream/tests/test_phase11_technical_evidence.py \
  skills/persona-dream/tests/test_phase11_adapter_and_approvals.py

Expected:

33 passed

Zero-call recompilation:

Bash
set -euo pipefail

export RUN_ROOT="$PWD/skills/persona-dream/reports/pipeline-complete"
export REVISION_ID="rev_idea_f3f9c48d5cc2"
export CANONICAL_ROOT="$RUN_ROOT/.persona-dream/revisions/$REVISION_ID/phase_11_submit_return/canonical"
export OLD_REQUEST_KEY="444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71"
export OLD_LEDGER="$RUN_ROOT/.persona-dream/revisions/$REVISION_ID/phase_11_submit_return/attempts/$OLD_REQUEST_KEY/attempt_ledger.v1.json"

old_ledger_sha256="$(sha256sum "$OLD_LEDGER" | awk '{print $1}')"

skills/persona-dream/run.sh \
  compile-phase11-canonical-live-request \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --json |
  tee /tmp/persona-dream-phase11-provider-contract-repair.json

test "$(sha256sum "$OLD_LEDGER" | awk '{print $1}')" = \
  "$old_ledger_sha256"
Bash
jq -e \
  --arg failed "sha256:$OLD_REQUEST_KEY" '
  .provider_request_body.generate_audio == false
  and (.provider_request_body.multi_prompt | length) == 4
  and (
    [.provider_request_body.multi_prompt[].prompt | length]
    | all(. <= 512)
  )
  and (
    [.provider_request_body.multi_prompt[].prompt]
    | all(
        contains("@Element1")
        and contains("@Element2")
        and contains("Kling v3 Standard I2V")
      )
  )
  and (
    .provider_request_body.multi_prompt[2].prompt
    | contains("No spoken dialogue")
      and contains("No lip movement")
      and contains("nonverbal hand signal")
      and (contains("If we paddle now") | not)
      and (contains("quietly says") | not)
  )
  and .request_body_sha256 != $failed
  and .actual_provider_call_attempts == 0
  and .provider_ready == false
  and .live_submit_ready == false
' "$CANONICAL_ROOT/phase11_live_request.v1.json"

Expected regenerated fixture lengths from the focused proof:

SB_001: 247
SB_002: 268
SB_003: 362
SB_004: 271

Create the new request-hash ledger through zero-call preflight:

Bash
set -euo pipefail

export FAL_KEY="${FAL_API_KEY:?FAL_API_KEY is not configured}"

skills/persona-dream/run.sh \
  phase11-fal-canary-preflight \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --poll-interval-seconds 5 \
  --max-polls 180 \
  --json |
  tee /tmp/persona-dream-phase11-corrected-preflight.json

request_sha256="$(
  jq -r '.request_body_sha256' \
    "$CANONICAL_ROOT/phase11_live_request.v1.json"
)"
request_key="${request_sha256#sha256:}"
new_ledger="$RUN_ROOT/.persona-dream/revisions/$REVISION_ID/phase_11_submit_return/attempts/$request_key/attempt_ledger.v1.json"
Bash
jq -e '
  .status == "PASS_PHASE11_ADAPTER_PREFLIGHT"
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' /tmp/persona-dream-phase11-corrected-preflight.json

jq -e \
  --arg request "$request_sha256" '
  .request_body_sha256 == $request
  and .state == "PREFLIGHT_READY"
  and .submit_intent_count == 0
  and .actual_provider_call_attempts == 0
  and .request_id == null
  and .ambiguous_submit == false
  and .automatic_resubmit_allowed == false
' "$new_ledger"

jq -e '
  .state == "FAILED"
  and .submit_intent_count == 1
  and .actual_provider_call_attempts == 1
  and .automatic_resubmit_allowed == false
  and .request_id
      == "019f6acb-853c-7552-bc73-ff8a6548afb1"
' "$OLD_LEDGER"

No provider submit, status, result, download, authorization writing, Watch invocation, or ledger reset is performed by these proof commands.

<<<WEBGPT_DONE:20260716T122838Z:df3a536b>>>
