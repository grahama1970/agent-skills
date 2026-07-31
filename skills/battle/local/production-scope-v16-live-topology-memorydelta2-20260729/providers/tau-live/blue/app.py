"""RelayForge V16 blue patch manifest.

This replacement file is intentionally self-contained and declarative. It does not
issue provider commands, choose network destinations, set headers, reference
filesystem locations, or rely on private implementation details. The Battle
selection authority evaluates the proposed controls from the public catalog.
"""

import json

SELECTION_AUTHORITY = "BATTLE"
PROVIDER_COMMAND_EXECUTION = False
TARGET_ID = "battle-v16-relayforge-a"

MEMORY_CHAIN_QUALIFICATION_SHA256 = "72d1f41dd20ba4ad7777dce434615fa88277c5818f5bdbe78684dab3e95be5f2"
POST_MEMORY_STRATEGY_SHA256 = "e0dac6dc4c3159be8c7cdcefc2b534dfe421065dea0f8489bb42f44de64e4095"

BLUE_PATCH = {
    "artifact_type": "blue_patch",
    "target_id": TARGET_ID,
    "selection_authority": SELECTION_AUTHORITY,
    "provider_command_execution": PROVIDER_COMMAND_EXECUTION,
    "strategy_genome": {
        "selected_methods": [
            "cache-principal-partition",
            "capability-audience-policy",
        ],
        "rejected_methods": [
            "broad-quarantine",
            "legacy-convert-disable",
            "provider-selected-destinations",
            "implementation-guessing",
        ],
        "parameters": {
            "control_scope": "measured_trust_boundary",
            "preserve_functionality": True,
            "memory_chain_qualification_sha256": MEMORY_CHAIN_QUALIFICATION_SHA256,
            "post_memory_strategy_sha256": POST_MEMORY_STRATEGY_SHA256,
            "action_proposals": [
                {
                    "action_id": "blue-v16-cache-principal-partition-001",
                    "rank": 1,
                    "operation": "cache-principal-partition",
                    "evidence_refs": [
                        "OBS-20",
                        "OBS-21",
                        "public-action-catalog",
                        "memory-chain",
                        "post-memory-strategy",
                    ],
                    "expected_observation": "Observed report references are resolved only within the requesting principal cache partition, preserving tenant-owned report retrieval while preventing cross-principal cache reuse of an observed recent reference.",
                    "parameters": {
                        "enabled": True,
                    },
                },
                {
                    "action_id": "blue-v16-capability-audience-policy-002",
                    "rank": 2,
                    "operation": "capability-audience-policy",
                    "evidence_refs": [
                        "setup-import",
                        "OBS-20",
                        "public-action-catalog",
                        "memory-chain",
                        "post-memory-strategy",
                    ],
                    "expected_observation": "Preview and report-profile capability use remains available only for the intended principal audience, preserving the valid public workflows and safe report profile while containing capability replay outside the evidenced trust boundary.",
                    "parameters": {
                        "enabled": True,
                    },
                },
            ],
        },
        "mutation_origin": "durable_memory design input only; memory_chain_qualification_sha256=72d1f41dd20ba4ad7777dce434615fa88277c5818f5bdbe78684dab3e95be5f2; post_memory_strategy_sha256=e0dac6dc4c3159be8c7cdcefc2b534dfe421065dea0f8489bb42f44de64e4095; selected narrow boundary controls instead of global service shutdown.",
        "expected_observation": "The evidenced trust boundary is contained while the public functionality contract remains available: regular import, caller-owned job status, tenant-owned report retrieval, valid preview, safe report profile, and required legacy conversion continue to operate.",
    },
}


def get_blue_patch():
    """Return the deterministic public blue patch manifest."""
    return json.loads(json.dumps(BLUE_PATCH, sort_keys=True))


def application(environ, start_response):
    """Minimal WSGI-compatible responder for environments that import app.py."""
    body = json.dumps(get_blue_patch(), sort_keys=True).encode("utf-8")
    start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
    return [body]


if __name__ == "__main__":
    print(json.dumps(get_blue_patch(), sort_keys=True))
