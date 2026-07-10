# Persona Dream / WebGPT Round 03

## Objective

Review the hardened Phase 10 Provider Contract dry-run rung after applying the
Round 02 `NEEDS_CHANGES` feedback.

This is still a local dry-run contract compiler. It must not claim live fal.ai
schema compatibility, provider media URL readiness, paid-call authorization,
provider submission, provider return, Watch observation, or memory persistence.

## Implemented Patch

Added:

- `skills/persona-dream/scripts/write_phase10_provider_contract.py`
- `skills/persona-dream/scripts/check_phase10_provider_contract.py`
- `skills/persona-dream/run.sh` commands:
  - `write-phase10-provider-contract`
  - `check-phase10-provider-contract`
- `skills/persona-dream/tests/fixtures/phase10-provider-contract/*/fixture.json`

## Phase 10 Contract Boundary

Phase 10 consumes:

- Phase 09 video provider packet
- provider registry refresh receipt

Phase 10 emits:

- `phase10_provider_contract.json`
- `phase10_provider_contract_receipt.json`

It records:

- selected provider and route
- fal model endpoint
- provider packet path/hash
- registry refresh path/hash/status
- exact dry-run provider request body
- canonical payload hash
- normalized request schema
- provider field mapping
- provider media publication plan
- cost contract
- entitlement contract
- async return contract
- manual acceptance contract
- dry-run blockers and future live-readiness blockers as separate arrays
- non-claims

It hard-codes dry-run boundary facts:

```json
{
  "proof_kind": "fixture_contract_test",
  "fixture_backed": true,
  "live_external_evidence": false,
  "mocked_provider_response": false,
  "actual_provider_call_attempts": 0,
  "provider_live": false,
  "paid_call_authorized": false,
  "provider_accessible_url_created": false,
  "submitted": false,
  "provider_ready": false,
  "live_submit_ready": false,
  "mocked": false
}
```

## Proof Commands Run

```bash
python3 -m py_compile \
  skills/persona-dream/scripts/write_phase10_provider_contract.py \
  skills/persona-dream/scripts/check_phase10_provider_contract.py

bash -n skills/persona-dream/run.sh

skills/persona-dream/run.sh check-video-provider-packet-routing \
  --fixtures-root skills/persona-dream/tests/fixtures/video-provider-packet-routing \
  --receipt-out <local-temp-receipt-redacted> \
  --json

skills/persona-dream/run.sh check-phase10-provider-contract \
  --fixtures-root skills/persona-dream/tests/fixtures/phase10-provider-contract \
  --receipt-out <local-temp-receipt-redacted> \
  --json
```

## Command Results

`py_compile`: exit 0

`bash -n run.sh`: exit 0

Phase 09 provider packet routing:

```json
{
  "status": "PASS_VIDEO_PROVIDER_PACKET_ROUTING",
  "fixture_count": 3,
  "actual_provider_call_attempts": 0,
  "provider_live": false,
  "paid_call_authorized": false,
  "provider_accessible_url_created": false,
  "submitted": false,
  "provider_ready": false,
  "live_submit_ready": false,
  "mocked": false
}
```

Phase 10 provider contract:

```json
{
  "status": "PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE",
  "fixture_count": 15,
  "no_network_side_effect_status": "PASS_PHASE10_NO_NETWORK_SIDE_EFFECTS",
  "actual_provider_call_attempts": 0,
  "provider_live": false,
  "paid_call_authorized": false,
  "provider_accessible_url_created": false,
  "submitted": false,
  "provider_ready": false,
  "live_submit_ready": false,
  "mocked": false,
  "proof_kind": "fixture_contract_test",
  "fixture_backed": true,
  "live_external_evidence": false,
  "mocked_provider_response": false
}
```

Observed Phase 10 dry-run blockers:

```text
BLOCKED_ACTUAL_PROVIDER_CALL_ATTEMPTS_IN_PHASE10_DRY_RUN
BLOCKED_EXTERNAL_TASK_ID_IN_PHASE10_DRY_RUN
BLOCKED_PAID_CALL_AUTHORIZED_IN_PHASE10_DRY_RUN
BLOCKED_PHASE10_ENDPOINT_MISMATCH
BLOCKED_PHASE10_MAPPING_SOURCE_MISSING
BLOCKED_PHASE10_PAYLOAD_HASH_MISMATCH
BLOCKED_PHASE10_PROVIDER_ID_MISMATCH
BLOCKED_PHASE10_REQUIRED_FIELD_UNMAPPED
BLOCKED_PHASE10_REQUIRED_SECTION_MISSING
BLOCKED_PHASE10_REVISION_MISMATCH
BLOCKED_POLLING_PLAN_NOT_ACCEPTED
BLOCKED_POLLING_TASK_ID_MAPPING_MISSING
BLOCKED_POLLING_TERMINAL_STATES_MISSING
BLOCKED_PROVIDER_ACCESSIBLE_URL_CREATED_IN_PHASE10_DRY_RUN
BLOCKED_PROVIDER_LIVE_IN_PHASE10_DRY_RUN
BLOCKED_PROVIDER_REGISTRY_REFRESH_NOT_PASS
BLOCKED_SUBMITTED_IN_PHASE10_DRY_RUN
BLOCKED_VIDEO_PROVIDER_PACKET_NOT_PASS
```

Observed future live-readiness blockers retained separately:

```text
BLOCKED_COST_ESTIMATE_UNVERIFIED
BLOCKED_LIVE_SUBMIT_DISABLED_IN_PHASE10_DRY_RUN
BLOCKED_MANUAL_ACCEPTANCE_MISSING
BLOCKED_PAID_CALL_AUTHORIZATION_MISSING
BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING
BLOCKED_PROVIDER_ENTITLEMENT_UNVERIFIED
BLOCKED_PROVIDER_URL_PROBES_MISSING
```

The no-network side-effect lane monkeypatches `socket.socket`,
`urllib.request.urlopen`, and provider/network subprocesses (`curl`, `wget`,
`fal`) while compiling the good fixture. It observed:

```json
{
  "status": "PASS_PHASE10_NO_NETWORK_SIDE_EFFECTS",
  "network_calls_observed": [],
  "actual_provider_call_attempts": 0
}
```

## Review Questions

1. Does this satisfy the Phase 10 Provider Contract dry-run rung, with the
   explicit caveat that proof is fixture-backed and not live external evidence?
2. Are there any additional dry-run blockers required before committing this
   Phase 10 patch?
3. Should the next architecture artifact be limited to:
   `Phase 08 Media Lock -> Phase 09 Provider Packet/Registry Refresh -> Phase 10 Provider Contract -> Future Phase 11 Live Submit Gate -> Watch`
   rather than the full Dream -> Watch -> Memory loop?

## Non-Claims To Preserve

This patch does not prove:

- current live fal provider schema compatibility
- provider-accessible media URLs
- URL probe success
- cost approval
- provider entitlement
- callback readiness
- manual acceptance
- paid-call authorization
- live provider readiness
- live video generation
- Watch observation
- memory persistence

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260710T141241Z:74530305>>>

Do not print anything after that marker.
