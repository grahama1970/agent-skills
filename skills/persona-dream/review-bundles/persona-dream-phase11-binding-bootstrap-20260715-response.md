The official fal Standard I2V contract requires start_image_url, supports multi_prompt, end_image_url, custom elements, generate_audio, duration and CFG controls, and requires input URLs to be publicly accessible. The patch binds those fields without invoking fal’s submit, status, or result APIs.
Fal
+1

Download the Phase 11 current-revision binding bootstrap patch

Base commit:
9ce346f4e508382350f49f42563b998f1aa8efe7

Byte count:
71323

SHA-256:
96970ecd3d84254ec16c686bfa3a755fe66b92d43d6cdfdfec627623ee2ebec1

git apply --check:
0

git diff --check:
0

Focused tests:
28 passed

Provider generation attempts:
0
Apply and test
Bash
set -euo pipefail

test "$(git rev-parse HEAD)" = \
  "9ce346f4e508382350f49f42563b998f1aa8efe7"

git apply --check \
  /path/to/persona-dream-phase11-current-revision-binding-bootstrap.patch

git apply \
  /path/to/persona-dream-phase11-current-revision-binding-bootstrap.patch

git diff --check
bash -n skills/persona-dream/run.sh

python3 -m py_compile \
  skills/persona-dream/scripts/bootstrap_phase11_payload_binding.py \
  skills/persona-dream/scripts/phase11_payload_binding.py \
  skills/persona-dream/scripts/capture_phase11_provider_source_snapshot.py \
  skills/persona-dream/scripts/phase11_canonical_common.py \
  skills/persona-dream/scripts/reconcile_phase11_upstream_validation.py

python3 -m json.tool \
  skills/persona-dream/contracts/phase11_payload_binding.v1.schema.json \
  >/dev/null

python3 -m pytest -q \
  skills/persona-dream/tests/test_phase11_adapter_and_approvals.py \
  skills/persona-dream/tests/test_phase11_payload_binding_bootstrap.py \
  skills/persona-dream/tests/test_phase11_canonical_live_request.py \
  skills/persona-dream/tests/test_phase11_technical_evidence.py

Expected:

28 passed
Bootstrap the active-revision binding
Bash
set -euo pipefail

cd skills/persona-dream

export RUN_ROOT="$PWD/reports/pipeline-complete"
export REVISION_ID="rev_idea_f3f9c48d5cc2"
export PUBLICATION_COMMIT="9ce346f4e508382350f49f42563b998f1aa8efe7"

./run.sh bootstrap-phase11-payload-binding \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --publication-commit "$PUBLICATION_COMMIT" \
  --json |
  tee /tmp/persona-dream-phase11-binding-bootstrap.json
Bash
jq -e '
  .status == "PASS_PHASE11_PAYLOAD_BINDING_BOOTSTRAP"
  and .gate_status == "BLOCKED_PROVIDER_GATE"
  and .binding_status == "BLOCKED_PUBLIC_MEDIA_PROBE_REQUIRED"
  and .role_counts == {
    "continuity_only": 6,
    "element_packs": 2,
    "global_end_anchor": 1,
    "global_start_anchor": 1
  }
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .paid_call_authorized == false
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' /tmp/persona-dream-phase11-binding-bootstrap.json

Validate the binding itself:

Bash
export BINDING="$RUN_ROOT/.persona-dream/revisions/$REVISION_ID/phase_11_submit_return/preflight/phase11_payload_binding.json"

jq -e \
  --arg revision "$REVISION_ID" \
  --arg commit "$PUBLICATION_COMMIT" '
  .schema == "persona_dream.phase11_payload_binding.v1"
  and .revision_id == $revision
  and .publication.commit == $commit
  and .publication.state == "UNPROBED_COMMIT_PINNED_URLS"
  and .publication.provider_accessible_urls_proven == false
  and .model == "fal-ai/kling-video/v3/standard/image-to-video"
  and .mode == "standard"
  and .input.generate_audio == false
  and .input.duration == "10"
  and (.input.multi_prompt | length) == 4
  and [.input.multi_prompt[].duration] == ["2", "3", "2", "3"]
  and (
    [.input.multi_prompt[].prompt | test("\\bPro\\b"; "i")]
    | any
    | not
  )
  and (
    .input.multi_prompt[2].prompt
    | test("If we paddle now|Dialogue cue:|quietly says"; "i")
    | not
  )
  and (.input.elements | length) == 2
  and .media_roles.role_counts == {
    "continuity_only": 6,
    "element_packs": 2,
    "global_end_anchor": 1,
    "global_start_anchor": 1
  }
  and .actual_provider_call_attempts == 0
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' "$BINDING"
Capture current official provider evidence
Bash
./run.sh capture-phase11-provider-source-snapshot \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --json |
  tee /tmp/persona-dream-phase11-provider-source.json
Bash
jq -e '
  .status == "PASS_PROVIDER_SOURCE_SNAPSHOT"
  and .endpoint == "fal-ai/kling-video/v3/standard/image-to-video"
  and .mode == "standard"
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .paid_call_authorized == false
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' /tmp/persona-dream-phase11-provider-source.json

A missing or invalid binding now returns a JSON receipt such as:

JSON
{
  "schema": "persona_dream.phase11_provider_source_capture_receipt.v1",
  "status": "BLOCKED_PHASE11_PAYLOAD_BINDING_MISSING",
  "gate_status": "BLOCKED_PROVIDER_GATE",
  "actual_provider_call_attempts": 0,
  "provider_live": false,
  "paid_call_authorized": false,
  "submitted": false,
  "provider_ready": false,
  "live_submit_ready": false
}
Rebind upstream validation to the active revision
Bash
./run.sh reconcile-phase11-upstream-validation \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --json |
  tee /tmp/persona-dream-phase11-upstream-reconciliation.json
Bash
jq -e \
  --arg revision "$REVISION_ID" '
  .status == "PASS_PHASE11_UPSTREAM_VALIDATION_RECONCILED"
  and .revision_id == $revision
  and .validation_status == "BLOCKED_DOWNSTREAM_NOT_EXECUTED"
  and .first_blocker == "BLOCKED_PHASE11_PROVIDER_SUBMIT_NOT_EXECUTED"
  and .passed_step_count == 12
  and .step_count == 15
  and .actual_provider_call_attempts == 0
' /tmp/persona-dream-phase11-upstream-reconciliation.json
Probe the seven exact public assets
Bash
./run.sh capture-phase11-public-media-evidence \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --json |
  tee /tmp/persona-dream-phase11-public-media.json
Bash
jq -e '
  .status == "PASS_PROVIDER_MEDIA_TRANSITIONS_TECHNICAL"
  and .request_asset_count == 7
  and .publication_authorization_present == false
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .submitted == false
' /tmp/persona-dream-phase11-public-media.json
Compile, run the zero-call adapter preflight, and recompile
Bash
./run.sh compile-phase11-canonical-live-request \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --json |
  tee /tmp/persona-dream-phase11-before-adapter.json
Bash
export FAL_KEY="${FAL_API_KEY:?FAL_API_KEY is not configured}"

./run.sh phase11-fal-canary-preflight \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --poll-interval-seconds 5 \
  --max-polls 180 \
  --json |
  tee /tmp/persona-dream-phase11-adapter-preflight.json
Bash
jq -e '
  .status == "PASS_PHASE11_ADAPTER_PREFLIGHT"
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .paid_call_authorized == false
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' /tmp/persona-dream-phase11-adapter-preflight.json
Bash
./run.sh compile-phase11-canonical-live-request \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --json |
  tee /tmp/persona-dream-phase11-after-adapter.json
Independent validation and Memory persistence
Bash
./run.sh validate-phase11-canonical-live-request \
  --run-root "$RUN_ROOT" \
  --revision-id "$REVISION_ID" \
  --persist-memory \
  --memory-url http://127.0.0.1:8601 \
  --collection project_knowledge \
  --connect-timeout 5 \
  --read-timeout 60 \
  --json |
  tee /tmp/persona-dream-phase11-current-revision-validation.json
Bash
jq -e '
  .validator_status == "PASS_PHASE11_CANONICAL_BOUNDARY_VALIDATED"
  and .gate_status == "BLOCKED_AWAITING_HUMAN_APPROVAL"
  and .technical_blockers == []
  and (
    .missing_approval_types | sort
  ) == (
    [
      "publication_authorization",
      "visual_media_acceptance",
      "exact_request_acceptance",
      "cost_acceptance",
      "paid_call_authorization"
    ] | sort
  )
  and .memory.persisted == true
  and .memory.exact_reread_count == 1
  and .memory.semantic_sync_state == "synced"
  and .memory.recall.matching_identity_count >= 1
  and .memory.recall.dense_matching_count >= 1
  and .memory.recall.max_dense > 0
  and .actual_provider_call_attempts == 0
  and .provider_live == false
  and .paid_call_authorized == false
  and .submitted == false
  and .provider_ready == false
  and .live_submit_ready == false
' /tmp/persona-dream-phase11-current-revision-validation.json
