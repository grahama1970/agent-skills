Implementation order

Add a Phase 07 live preflight helper to phase07_storyboard_tau_node.py.

Make _ensure_storyboard_frame_artifacts(...) call that helper before any path can reach _generate_image(...).

Add a second call in _promote_reviewer_accepted_frames(...) before reviewer promotion can write accepted_frame.

Add local-only negative fixtures/tests proving provider generation and reviewer PASS are refused when the chain preflight is missing or stale.

Add one Tau gate that runs only the local enforcement checker with provider_live=false, mocked=false, and live_image_call_started=false.

This patch should not change live image generation behavior except to block it when preflight is absent or invalid.

1. Exact live-enforcement invariant

Before panel-creator may start any provider image call, all of this must be true:

run-specific spine chain manifest exists
spine chain validator receipt exists or is generated successfully
spine chain validator status == PASS_SPINE_CHAIN_CONTRACT_GATE
provider_live == true
mocked == false
live_image_call_started == false before call
targeted panel/frame generation scope is represented in the manifest
every targeted Phase 07 prompt contract has PASS_PROMPT_CONTRACT receipt
every targeted compiled prompt hash matches the manifest
every targeted compiled prompt is bound to the full raw-byte hash of its source panel contract
Phase 07 prompt contract binds to the Phase 06 script contract by path/SHA
creator is forbidden from writing accepted_frame
reviewer PASS preconditions are represented in the manifest policy

The important runtime invariant is:

_generate_image(...) must be unreachable unless PASS_LIVE_CREATOR_PREFLIGHT exists for the same run, same chain manifest, and same targeted panel/frame scope.

The current runtime choke point is clear: _run_creator(...) calls _ensure_storyboard_frame_artifacts(...), and that function is where _generate_image(...) is reached.

2. Exact inputs

Use a run-specific generated chain manifest.

Do not use the existing good fixture manifest as live enforcement input. The fixture proves validator behavior. The live preflight must validate the current run’s actual chain.

Recommended live manifest path:

{run_root}/spine_chain_manifest.v1.json

Also allow an explicit override from Tau context:

JSON
{
  "persona_dream_phase07_storyboard": {
    "spine_chain_manifest": "/absolute/path/to/spine_chain_manifest.v1.json"
  }
}

Resolution order:

1. context.persona_dream_phase07_storyboard.spine_chain_manifest
2. start_payload.context.persona_dream_spine_chain_manifest
3. env PERSONA_DREAM_SPINE_CHAIN_MANIFEST
4. {run_root}/spine_chain_manifest.v1.json

The live preflight should consume this one artifact:

spine_chain_manifest.v1.json

The per-panel prompt contracts and compiled prompt proofs are not separate runtime inputs. They are referenced by the manifest and verified through validate_persona_dream_spine_chain.py.

3. Exact patch location
A. Patch _run_creator(...)

_run_creator(...) currently calls _ensure_storyboard_frame_artifacts(...) near the start of creator execution.

Do not put the main gate only in _run_creator(...), because future code could call _ensure_storyboard_frame_artifacts(...) directly. Add a receipt reference in _run_creator(...), but enforce inside _ensure_storyboard_frame_artifacts(...).

Patch shape:

Python
Run
generation = _ensure_storyboard_frame_artifacts(
    packet,
    packet_path=packet_path,
    run_root=run_root,
    start_payload=start_payload,
)

stays as-is.

B. Patch _ensure_storyboard_frame_artifacts(...)

Add the hard preflight after model-policy resolution succeeds but before the panel loop and before _generate_image(...) can be reached.

Current function initializes generation receipt, resolves image/review model policies, mutates the packet, then later enters the frame loop and calls _generate_image(...).

Insert:

Python
Run
live_preflight = _run_phase07_live_preflight(
    role="panel-creator",
    run_root=run_root,
    packet=mutable_packet,
    packet_path=packet_path,
    start_payload=start_payload,
    require_provider_live=True,
    require_target_scope=True,
)

receipt["live_preflight_receipt"] = live_preflight["receipt_path"]
receipt["live_preflight_status"] = live_preflight["status"]

if live_preflight["status"] != "PASS_LIVE_CREATOR_PREFLIGHT":
    blockers.extend(live_preflight["blockers"])
    receipt["status"] = "BLOCKED_LIVE_PREFLIGHT"
    receipt["blockers"] = blockers
    receipt["provider_calls"] = []
    receipt["live_image_call_started"] = False
    _write_json(run_root / "receipts" / "storyboard_frame_generation_receipt.json", receipt)
    return {
        "packet_updated": False,
        "provider_called": False,
        "blockers": blockers,
        "receipt": receipt,
    }

Also add a defensive guard to _generate_image(...) by requiring a passed preflight token:

Python
Run
_generate_image(..., live_preflight_status=live_preflight["status"])

and inside _generate_image(...):

Python
Run
if live_preflight_status != "PASS_LIVE_CREATOR_PREFLIGHT":
    return {
        "status": "FAIL",
        "error": "BLOCKED_PROVIDER_CALL_BEFORE_PREFLIGHT_PASS",
        "provider_call_started": False,
    }

This catches accidental future bypasses.

C. Patch _promote_reviewer_accepted_frames(...)

_run_reviewer(...) currently calls _promote_reviewer_accepted_frames(...) before calculating final review status.

_promote_reviewer_accepted_frames(...) later creates accepted_frame after identity review succeeds.

Add reviewer preflight at the top of _promote_reviewer_accepted_frames(...):

Python
Run
reviewer_preflight = _run_phase07_live_preflight(
    role="panel-reviewer",
    run_root=run_root,
    packet=packet,
    packet_path=packet_path,
    start_payload=start_payload,
    require_provider_live=False,
    require_target_scope=True,
    require_reviewer_pass_preconditions=True,
)

if reviewer_preflight["status"] != "PASS_LIVE_REVIEWER_PREFLIGHT":
    return {
        "packet_updated": False,
        "blockers": reviewer_preflight["blockers"],
        "live_preflight_receipt": reviewer_preflight["receipt_path"],
    }

Then in _run_reviewer(...), include that receipt path in storyboard_review_verdict.json.

4. Exact live preflight helper

Add one helper:

Python
Run
def _run_phase07_live_preflight(
    *,
    role: str,
    run_root: Path,
    packet: Mapping[str, Any],
    packet_path: Path,
    start_payload: Mapping[str, Any],
    require_provider_live: bool,
    require_target_scope: bool,
    require_reviewer_pass_preconditions: bool = False,
) -> dict[str, Any]:
    ...

Responsibilities:

resolve run-specific spine chain manifest
run validate_persona_dream_spine_chain.py --manifest ... --receipt-out ...
load chain validator receipt
verify PASS_SPINE_CHAIN_CONTRACT_GATE
verify provider_live/mocked/live_image_call_started flags
verify targeted panel/frame scope is represented in manifest
verify reviewer PASS preconditions when role == panel-reviewer
write phase07 live preflight receipt
return status/blockers/receipt_path

Do not duplicate the full chain validator in this helper. It should call the existing validator and add only live-runtime-specific checks:

is this the current run manifest?
does this manifest cover the target panel/frame scope?
is provider_live allowed for creator?
is reviewer PASS allowed for reviewer?
5. Exact receipt schema

Receipt path:

{run_root}/receipts/live_preflight/{role}_phase07_live_preflight_receipt.json

Schema:

persona_dream.phase07.live_creator_reviewer_preflight_receipt.v1

Pass statuses:

PASS_LIVE_CREATOR_PREFLIGHT
PASS_LIVE_REVIEWER_PREFLIGHT

Blocked terminal status:

BLOCKED_LIVE_PREFLIGHT

Receipt shape:

JSON
{
  "schema": "persona_dream.phase07.live_creator_reviewer_preflight_receipt.v1",
  "created_at": "2026-07-08T00:00:00Z",
  "role": "panel-creator",
  "status": "PASS_LIVE_CREATOR_PREFLIGHT",
  "verdict": "PASS",
  "run_root": "string",
  "storyboard_packet": "string",
  "storyboard_packet_sha256": "sha256:...",
  "spine_chain_manifest_path": "string",
  "spine_chain_manifest_sha256": "sha256:...",
  "spine_chain_validator": "skills/persona-dream/scripts/validate_persona_dream_spine_chain.py",
  "spine_chain_validator_receipt_path": "string",
  "spine_chain_validator_receipt_sha256": "sha256:...",
  "spine_chain_validator_status": "PASS_SPINE_CHAIN_CONTRACT_GATE",
  "provider_live": true,
  "mocked": false,
  "live_image_call_started": false,
  "provider_call_authorized": true,
  "target_scope": {
    "target_panel_ids": ["sb_004"],
    "target_frame_ids": ["sb_004.start_frame", "sb_004.end_frame"]
  },
  "target_scope_represented_in_manifest": true,
  "target_manifest_entries": [
    {
      "panel_id": "sb_004",
      "frame_id": "sb_004.start_frame",
      "contract_path": "phase07/prompt_contracts/sb_004.start_frame.attempt_001.json",
      "contract_sha256": "sha256:...",
      "validator_receipt_status": "PASS_PROMPT_CONTRACT",
      "compiled_prompt_path": "phase07/prompts/sb_004.start_frame.attempt_001.md",
      "compiled_prompt_sha256": "sha256:..."
    }
  ],
  "reviewer_pass_preconditions": {
    "required": false,
    "satisfied": null
  },
  "blockers": [],
  "claims": {
    "proves": [
      "run-specific spine chain manifest passed",
      "targeted panel/frame scope is represented in the chain manifest",
      "compiled prompt hashes for target scope are current",
      "provider image call is allowed only after this receipt"
    ],
    "does_not_prove": [
      "provider reference images were attached",
      "image generation succeeded",
      "visual identity review passed",
      "storyboard was accepted",
      "panel generation stayed under five minutes"
    ]
  }
}

Blocked example:

JSON
{
  "schema": "persona_dream.phase07.live_creator_reviewer_preflight_receipt.v1",
  "role": "panel-creator",
  "status": "BLOCKED_LIVE_PREFLIGHT",
  "verdict": "FAIL_CLOSED",
  "provider_live": false,
  "mocked": false,
  "live_image_call_started": false,
  "provider_call_authorized": false,
  "spine_chain_manifest_path": null,
  "spine_chain_validator_status": null,
  "target_scope_represented_in_manifest": false,
  "blockers": [
    {
      "status": "BLOCKED_CHAIN_MANIFEST_MISSING",
      "message": "No run-specific spine_chain_manifest.v1.json was found."
    }
  ],
  "claims": {
    "proves": [
      "provider image call was blocked before generation"
    ],
    "does_not_prove": [
      "prompt contracts are valid",
      "provider reference attachment",
      "image generation",
      "visual identity pass"
    ]
  }
}
6. Exact fail-closed statuses

Use these statuses for this live enforcement rung.

PASS_LIVE_CREATOR_PREFLIGHT
PASS_LIVE_REVIEWER_PREFLIGHT

BLOCKED_LIVE_PREFLIGHT
BLOCKED_CHAIN_MANIFEST_MISSING
BLOCKED_CHAIN_MANIFEST_VALIDATOR_FAILED
BLOCKED_CHAIN_MANIFEST_HASH_MISMATCH
BLOCKED_STALE_COMPILED_PROMPT_HASH
BLOCKED_COMPILED_PROMPT_HASH_MISMATCH
BLOCKED_COMPILED_PROMPT_CONTRACT_HASH_MISMATCH
BLOCKED_PROVIDER_CALL_BEFORE_PREFLIGHT_PASS
BLOCKED_PROVIDER_LIVE_DISABLED_FOR_LOCAL_GATE
BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT
BLOCKED_REVIEWER_PASS_WITH_INVALID_CONTRACT
BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST
BLOCKED_TARGET_PANEL_SCOPE_NOT_IN_MANIFEST
BLOCKED_TARGET_FRAME_SCOPE_NOT_IN_MANIFEST
BLOCKED_MOCKED_LIVE_PREFLIGHT
BLOCKED_LIVE_CALL_STARTED_IN_LOCAL_GATE

Requested mappings:

missing chain manifest
-> BLOCKED_CHAIN_MANIFEST_MISSING

stale compiled prompt hash
-> BLOCKED_STALE_COMPILED_PROMPT_HASH
   plus specific child blocker BLOCKED_COMPILED_PROMPT_HASH_MISMATCH

provider call attempted before preflight PASS
-> BLOCKED_PROVIDER_CALL_BEFORE_PREFLIGHT_PASS

reviewer PASS without validator receipt
-> BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT

targeted panel scope not represented in manifest
-> BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST
   or more specific BLOCKED_TARGET_PANEL_SCOPE_NOT_IN_MANIFEST / BLOCKED_TARGET_FRAME_SCOPE_NOT_IN_MANIFEST
7. Targeted panel/frame scope rule

The preflight must compare current generation scope against the manifest.

Source of target scope:

packet.generation_scope.target_panel_ids
packet.generation_scope.target_frame_ids

Fallback if only targeted_panel_ids exist:

panel_id + both start_frame/end_frame

Fail if:

target_panel_ids is empty
target_frame_ids is empty
any target panel/frame is missing from manifest.stages.phase07.panel_prompt_contracts[]
any target panel/frame has validator status other than PASS_PROMPT_CONTRACT
any target panel/frame lacks compiled_prompt proof
any target panel/frame compiled prompt hash is stale

For a repair run targeting only sb_004.start_frame, the manifest does not need to include all eight frames, but it must include the exact targeted frame. For a full four-panel run, it should include all eight.

This avoids requiring broad regeneration when only one failed frame is being repaired.

8. Provider-live behavior

For the live runtime:

panel-creator provider call allowed only if provider_live == true

For this local-only rung:

provider_live=false

Therefore, even if the chain manifest passes, a provider call must not start. In local tests, either use missing/stale manifest blockers or assert:

provider_call_authorized=false
live_image_call_started=false
provider_calls=[]

Do not mark this as mock. It is a real local preflight proof:

JSON
{
  "mocked": false,
  "provider_live": false,
  "live_image_call_started": false
}
9. Minimal deterministic fixtures/tests

Create one local checker:

skills/persona-dream/scripts/check_phase07_live_creator_reviewer_preflight.py

It should create temporary run roots and run the actual runtime entrypoints or helper functions with provider disabled.

Test 1: creator blocks missing manifest

Fixture:

skills/persona-dream/tests/fixtures/phase07_live_preflight/missing_manifest/

Expected:

panel-creator exits without calling _generate_image
provider_calls=[]
provider_called=false
live_image_call_started=false
receipt status=BLOCKED_LIVE_PREFLIGHT
blocker=BLOCKED_CHAIN_MANIFEST_MISSING
Test 2: creator blocks stale compiled prompt hash

Fixture:

skills/persona-dream/tests/fixtures/phase07_live_preflight/stale_compiled_prompt_hash/

Make manifest point to a compiled prompt hash that does not match the file.

Expected:

provider_calls=[]
provider_called=false
receipt status=BLOCKED_LIVE_PREFLIGHT
blocker=BLOCKED_STALE_COMPILED_PROMPT_HASH
child blocker=BLOCKED_COMPILED_PROMPT_HASH_MISMATCH
Test 3: creator blocks target scope missing from manifest

Fixture:

skills/persona-dream/tests/fixtures/phase07_live_preflight/target_scope_missing/

Packet says:

JSON
{
  "generation_scope": {
    "target_panel_ids": ["sb_004"],
    "target_frame_ids": ["sb_004.start_frame"]
  }
}

Manifest contains only sb_001.start_frame.

Expected:

provider_calls=[]
provider_called=false
receipt status=BLOCKED_LIVE_PREFLIGHT
blocker=BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST
Test 4: reviewer blocks PASS without validator receipt

Fixture:

skills/persona-dream/tests/fixtures/phase07_live_preflight/reviewer_pass_without_validator_receipt/

Packet contains a candidate frame that could otherwise be promoted, but manifest lacks the required PASS validator receipt.

Expected:

accepted_frame is not written
storyboard_review_verdict.status != PASS_PANEL_REVIEWED
blocker=BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT
Deterministic command
Bash
python skills/persona-dream/scripts/check_phase07_live_creator_reviewer_preflight.py \
  --fixtures-root skills/persona-dream/tests/fixtures/phase07_live_preflight \
  --receipt-out /tmp/persona-dream-phase07-live-preflight/receipt.json

Expected aggregate receipt:

JSON
{
  "schema": "persona_dream.phase07.live_creator_reviewer_preflight_checker_receipt.v1",
  "status": "PASS_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE",
  "provider_live": false,
  "mocked": false,
  "live_image_call_started": false,
  "provider_call_attempts": 0,
  "tests": {
    "missing_manifest": "PASS",
    "stale_compiled_prompt_hash": "PASS",
    "target_scope_missing": "PASS",
    "reviewer_pass_without_validator_receipt": "PASS"
  },
  "observed_blockers": [
    "BLOCKED_CHAIN_MANIFEST_MISSING",
    "BLOCKED_STALE_COMPILED_PROMPT_HASH",
    "BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST",
    "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT"
  ]
}
10. Tau gate

DAG file:

skills/persona-dream/local/phase07_live_creator_reviewer_preflight_tau_dag.json

Route:

review-checker
  -> phase07-live-creator-reviewer-preflight-checker
  -> human

Single local checker node is enough. Do not split into several Tau nodes yet.

DAG context:

JSON
{
  "provider_live": false,
  "mocked": false,
  "live_image_call_started": false,
  "checker": "skills/persona-dream/scripts/check_phase07_live_creator_reviewer_preflight.py",
  "fixtures_root": "skills/persona-dream/tests/fixtures/phase07_live_preflight",
  "required_observed_blockers": [
    "BLOCKED_CHAIN_MANIFEST_MISSING",
    "BLOCKED_STALE_COMPILED_PROMPT_HASH",
    "BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST",
    "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT"
  ]
}

Expected Tau receipt:

JSON
{
  "schema": "tau.dag_receipt.v1",
  "ok": true,
  "status": "PASS",
  "verdict": "PASS_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE",
  "live": true,
  "mocked": false,
  "provider_live": false,
  "live_image_call_started": false,
  "selected_agents": [
    "phase07-live-creator-reviewer-preflight-checker"
  ],
  "observed_route": [
    "review-checker",
    "phase07-live-creator-reviewer-preflight-checker",
    "human"
  ],
  "required_evidence": [
    "phase07_live_creator_reviewer_preflight_checker_receipt.json"
  ],
  "provider_call_attempts": 0,
  "observed_blockers": [
    "BLOCKED_CHAIN_MANIFEST_MISSING",
    "BLOCKED_STALE_COMPILED_PROMPT_HASH",
    "BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST",
    "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT"
  ]
}
11. Acceptance criteria

This patch is accepted only when all are true:

phase07_storyboard_tau_node.py writes live preflight receipts
panel-creator cannot reach _generate_image without PASS_LIVE_CREATOR_PREFLIGHT
local provider_live=false run starts zero image calls
missing manifest blocks generation
stale compiled prompt hash blocks generation
target frame missing from manifest blocks generation
reviewer promotion cannot write accepted_frame without validator/pass precondition
aggregate checker status == PASS_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE
Tau DAG status == PASS
mocked=false
provider_live=false
live_image_call_started=false
provider_call_attempts=0

Use these proof commands:

Bash
python skills/persona-dream/scripts/check_phase07_live_creator_reviewer_preflight.py \
  --fixtures-root skills/persona-dream/tests/fixtures/phase07_live_preflight \
  --receipt-out /tmp/persona-dream-phase07-live-preflight/receipt.json
Bash
jq -e '
  .status == "PASS_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE" and
  .provider_live == false and
  .mocked == false and
  .live_image_call_started == false and
  .provider_call_attempts == 0 and
  (.observed_blockers | index("BLOCKED_CHAIN_MANIFEST_MISSING")) and
  (.observed_blockers | index("BLOCKED_STALE_COMPILED_PROMPT_HASH")) and
  (.observed_blockers | index("BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST")) and
  (.observed_blockers | index("BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT"))
' /tmp/persona-dream-phase07-live-preflight/receipt.json

Then run the Tau DAG:

Bash
tau run \
  --dag skills/persona-dream/local/phase07_live_creator_reviewer_preflight_tau_dag.json

Expected:

PASS_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE
12. Explicit non-claims

This patch does not prove:

live provider image generation works
reference images are attached to the provider request
Embry/Kai visually pass identity review
final storyboard approval
sb004 common-case generation under five minutes
memory/story/script quality
UI consumes the new manifest fields
Kling/provider readiness

Accepted claim only:

The live Phase 07 creator/reviewer runtime refuses provider generation and reviewer PASS promotion unless the run-specific spine chain manifest and targeted prompt-contract/compiled-prompt proofs have passed deterministic local preflight.
