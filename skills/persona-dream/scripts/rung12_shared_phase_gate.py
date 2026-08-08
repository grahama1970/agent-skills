#!/usr/bin/env python3
"""rung12_shared_phase_gate - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_json_with_hash(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def linked(artifact, artifact_hash, reviewer):
    return {
        "reviewer_schema_ok": reviewer.get("schema") == "persona_dream.panel_reviewer_receipt.v1",
        "panel_id_ok": reviewer.get("panel_id") == artifact.get("panel_id"),
        "artifact_revision_ok": reviewer.get("artifact_revision") == artifact.get("artifact_revision"),
        "artifact_hash_ok": reviewer.get("artifact_receipt_sha256") == artifact_hash,
        "reviewer_identity_ok": reviewer.get("reviewer") == "panel-reviewer",
        "reviewer_readonly_ok": reviewer.get("reviewer_readonly") is True,
    }


def image_valid(artifact):
    image = artifact.get("image_artifact") or {}
    path = image.get("path")
    return (
        bool(path)
        and Path(path).is_file()
        and image.get("sha256") == file_hash(path)
        and str(image.get("media_type", "")).startswith("image/")
    )


def decide(case_id, artifact_path, reviewer_path):
    artifact, artifact_hash = load_json_with_hash(artifact_path)
    reviewer, reviewer_hash = load_json_with_hash(reviewer_path)
    linkage = linked(artifact, artifact_hash, reviewer)
    linkage_ok = all(linkage.values())
    has_image = bool(artifact.get("image_artifact"))
    image_ok = image_valid(artifact)
    reviewer_verdict = reviewer.get("reviewer_verdict")
    reviewer_blockers = reviewer.get("unresolved_blockers") or []
    no_live_paid = artifact.get("live_call_performed") is False and artifact.get("paid_call_performed") is False

    blockers = []
    if not linkage_ok:
        blockers.append({"code": "receipt_linkage_mismatch", "severity": "blocking"})
    if not has_image:
        blockers.append({"code": "missing_image_artifact", "severity": "blocking"})
    elif not image_ok:
        blockers.append({"code": "image_artifact_invalid", "severity": "blocking"})
    if reviewer_verdict != "PASS":
        blockers.extend(reviewer_blockers or [{"code": "reviewer_not_pass", "severity": "blocking"}])
    elif reviewer_blockers:
        blockers.append({"code": "reviewer_has_blockers", "severity": "blocking"})
    if not no_live_paid:
        blockers.append({"code": "live_or_paid_call_present", "severity": "blocking"})

    verdict = "PASS" if not blockers else "INSUFFICIENT_EVIDENCE"
    return {
        "case_id": case_id,
        "artifact_receipt_path": artifact_path,
        "artifact_receipt_sha256": artifact_hash,
        "reviewer_receipt_path": reviewer_path,
        "reviewer_receipt_sha256": reviewer_hash,
        "panel_id": artifact.get("panel_id"),
        "artifact_revision": artifact.get("artifact_revision"),
        "linkage": linkage,
        "linkage_ok": linkage_ok,
        "has_image_artifact": has_image,
        "image_artifact_valid": image_ok,
        "reviewer_verdict": reviewer_verdict,
        "verdict": verdict,
        "advance_allowed": verdict == "PASS",
        "unresolved_blockers": blockers,
        "live_call_performed": artifact.get("live_call_performed"),
        "paid_call_performed": artifact.get("paid_call_performed"),
    }


def decide_story_executor(executor_path):
    executor, executor_hash = load_json_with_hash(executor_path)
    blockers = []
    if executor.get("schema") not in {
        "persona_dream.rung20_story_executor_receipt.v1",
        "persona_dream.rung21_story_executor_receipt.v1",
    }:
        blockers.append({"code": "executor_schema_mismatch", "severity": "blocking"})
    if executor.get("phase") != "story":
        blockers.append({"code": "executor_phase_mismatch", "severity": "blocking"})
    if executor.get("executor_readonly") is not True:
        blockers.append({"code": "executor_not_readonly", "severity": "blocking"})
    if executor.get("unresolved_blockers"):
        blockers.append({"code": "executor_has_blockers", "severity": "blocking"})
    if executor.get("active_artifact_mutation_performed") is not False:
        blockers.append({"code": "active_artifact_mutation_present", "severity": "blocking"})
    if executor.get("provider_call_performed") is not False:
        blockers.append({"code": "provider_call_present", "severity": "blocking"})
    if executor.get("live_call_performed") is not False:
        blockers.append({"code": "live_call_present", "severity": "blocking"})
    if executor.get("paid_call_performed") is not False:
        blockers.append({"code": "paid_call_present", "severity": "blocking"})
    if (
        executor.get("schema") == "persona_dream.rung21_story_executor_receipt.v1"
        and executor.get("workspace_manifest_unchanged") is not True
    ):
        blockers.append({"code": "workspace_manifest_changed", "severity": "blocking"})
    if (
        executor.get("schema") == "persona_dream.rung21_story_executor_receipt.v1"
        and executor.get("execution_isolated") is not True
        and executor.get("repo_manifest_unchanged_outside_allowed_output") is not True
    ):
        blockers.append({"code": "out_of_scope_repo_change_or_no_isolation", "severity": "blocking"})
    output_contract = executor.get("output_contract") or {}
    if output_contract.get("phase") != "story" or output_contract.get("status") != "READY_FOR_SHARED_GATE":
        blockers.append({"code": "executor_output_contract_invalid", "severity": "blocking"})

    verdict = "PASS" if not blockers else "INSUFFICIENT_EVIDENCE"
    return {
        "case_id": "story_executor_pass",
        "executor_receipt_path": executor_path,
        "executor_receipt_sha256": executor_hash,
        "executor_schema": executor.get("schema"),
        "phase": executor.get("phase"),
        "executor_readonly": executor.get("executor_readonly"),
        "workspace_manifest_unchanged": executor.get("workspace_manifest_unchanged"),
        "execution_isolated": executor.get("execution_isolated"),
        "isolated_source_hashes_match": executor.get("isolated_source_hashes_match"),
        "repo_manifest_unchanged_outside_allowed_output": executor.get(
            "repo_manifest_unchanged_outside_allowed_output"
        ),
        "output_contract": output_contract,
        "verdict": verdict,
        "advance_allowed": verdict == "PASS",
        "unresolved_blockers": blockers,
        "active_artifact_mutation_performed": executor.get("active_artifact_mutation_performed"),
        "provider_call_performed": executor.get("provider_call_performed"),
        "live_call_performed": executor.get("live_call_performed"),
        "paid_call_performed": executor.get("paid_call_performed"),
    }


def decide_voice_executor(executor_path):
    executor, executor_hash = load_json_with_hash(executor_path)
    blockers = []
    if executor.get("schema") != "persona_dream.rung23_voice_executor_receipt.v1":
        blockers.append({"code": "executor_schema_mismatch", "severity": "blocking"})
    if executor.get("phase") != "voice":
        blockers.append({"code": "executor_phase_mismatch", "severity": "blocking"})
    if executor.get("executor_readonly") is not True:
        blockers.append({"code": "executor_not_readonly", "severity": "blocking"})
    if executor.get("unresolved_blockers"):
        blockers.append({"code": "executor_has_blockers", "severity": "blocking"})
    if executor.get("active_artifact_mutation_performed") is not False:
        blockers.append({"code": "active_artifact_mutation_present", "severity": "blocking"})
    if executor.get("provider_call_performed") is not False:
        blockers.append({"code": "provider_call_present", "severity": "blocking"})
    if executor.get("live_call_performed") is not False:
        blockers.append({"code": "live_call_present", "severity": "blocking"})
    if executor.get("paid_call_performed") is not False:
        blockers.append({"code": "paid_call_present", "severity": "blocking"})
    output_contract = executor.get("output_contract") or {}
    if output_contract.get("phase") != "voice" or output_contract.get("status") != "READY_FOR_SHARED_GATE":
        blockers.append({"code": "executor_output_contract_invalid", "severity": "blocking"})
    voice_plan = executor.get("voice_handoff_plan") or {}
    voice_plan_path = voice_plan.get("path")
    if (
        not voice_plan_path
        or not Path(voice_plan_path).is_file()
        or voice_plan.get("sha256") != file_hash(voice_plan_path)
        or voice_plan.get("schema") != "persona_dream.voice_handoff_plan.v1"
        or not isinstance(voice_plan.get("line_count"), int)
        or voice_plan.get("line_count") < 1
        or not isinstance(voice_plan.get("speaker_count"), int)
        or voice_plan.get("speaker_count") < 1
    ):
        blockers.append({"code": "voice_handoff_plan_invalid", "severity": "blocking"})

    verdict = "PASS" if not blockers else "INSUFFICIENT_EVIDENCE"
    return {
        "case_id": "voice_executor_pass",
        "executor_receipt_path": executor_path,
        "executor_receipt_sha256": executor_hash,
        "executor_schema": executor.get("schema"),
        "phase": executor.get("phase"),
        "executor_readonly": executor.get("executor_readonly"),
        "voice_handoff_plan": voice_plan,
        "output_contract": output_contract,
        "verdict": verdict,
        "advance_allowed": verdict == "PASS",
        "unresolved_blockers": blockers,
        "active_artifact_mutation_performed": executor.get("active_artifact_mutation_performed"),
        "provider_call_performed": executor.get("provider_call_performed"),
        "live_call_performed": executor.get("live_call_performed"),
        "paid_call_performed": executor.get("paid_call_performed"),
    }


parser = argparse.ArgumentParser()
parser.add_argument("--receipt", default=".codex/persona-dream/sanity/rung12_shared_phase_gate_latest.json")
parser.add_argument(
    "--case",
    choices=["both", "missing_image_fail_closed", "valid_image_pass", "story_executor_pass", "voice_executor_pass"],
    default="both",
)
parser.add_argument("--story-executor-receipt", default="")
parser.add_argument("--voice-executor-receipt", default="")
args = parser.parse_args()

cases = [
    {
        "case_id": "missing_image_fail_closed",
        "artifact": "skills/persona-dream/fixtures/rung9_panel_artifact_missing_image.json",
        "reviewer": "skills/persona-dream/fixtures/rung10_panel_reviewer_receipt_missing_image.json",
        "expected_verdict": "INSUFFICIENT_EVIDENCE",
        "expected_advance_allowed": False,
    },
    {
        "case_id": "valid_image_pass",
        "artifact": "skills/persona-dream/fixtures/rung11_panel_artifact_valid_image.json",
        "reviewer": "skills/persona-dream/fixtures/rung11_panel_reviewer_receipt_pass.json",
        "expected_verdict": "PASS",
        "expected_advance_allowed": True,
    },
]
if args.case != "both":
    cases = [case for case in cases if case["case_id"] == args.case]

results = []
if args.case == "story_executor_pass":
    if not args.story_executor_receipt:
        results.append(
            {
                "case_id": "story_executor_pass",
                "verdict": "INSUFFICIENT_EVIDENCE",
                "advance_allowed": False,
                "unresolved_blockers": [{"code": "missing_story_executor_receipt", "severity": "blocking"}],
                "case_ok": False,
            }
        )
    else:
        result = decide_story_executor(args.story_executor_receipt)
        result["expected_verdict"] = "PASS"
        result["expected_advance_allowed"] = True
        result["case_ok"] = (
            result["verdict"] == "PASS"
            and result["advance_allowed"] is True
            and result["executor_readonly"] is True
            and result["active_artifact_mutation_performed"] is False
            and result["provider_call_performed"] is False
            and result["live_call_performed"] is False
            and result["paid_call_performed"] is False
        )
        results.append(result)
elif args.case == "voice_executor_pass":
    if not args.voice_executor_receipt:
        results.append(
            {
                "case_id": "voice_executor_pass",
                "verdict": "INSUFFICIENT_EVIDENCE",
                "advance_allowed": False,
                "unresolved_blockers": [{"code": "missing_voice_executor_receipt", "severity": "blocking"}],
                "case_ok": False,
            }
        )
    else:
        result = decide_voice_executor(args.voice_executor_receipt)
        result["expected_verdict"] = "PASS"
        result["expected_advance_allowed"] = True
        result["case_ok"] = (
            result["verdict"] == "PASS"
            and result["advance_allowed"] is True
            and result["executor_readonly"] is True
            and result["active_artifact_mutation_performed"] is False
            and result["provider_call_performed"] is False
            and result["live_call_performed"] is False
            and result["paid_call_performed"] is False
        )
        results.append(result)
else:
    for case in cases:
        result = decide(case["case_id"], case["artifact"], case["reviewer"])
        result["expected_verdict"] = case["expected_verdict"]
        result["expected_advance_allowed"] = case["expected_advance_allowed"]
        result["case_ok"] = (
            result["verdict"] == case["expected_verdict"]
            and result["advance_allowed"] is case["expected_advance_allowed"]
            and result["linkage_ok"] is True
            and result["live_call_performed"] is False
            and result["paid_call_performed"] is False
        )
        results.append(result)

negative_checks = {
    "shared_logic_rejects_panel_id_mismatch": decide(
        "negative_panel_id",
        "skills/persona-dream/fixtures/rung9_panel_artifact_missing_image.json",
        "skills/persona-dream/fixtures/rung11_panel_reviewer_receipt_pass.json",
    )["linkage_ok"]
    is False,
    "shared_logic_rejects_artifact_hash_mismatch": decide(
        "negative_hash",
        "skills/persona-dream/fixtures/rung11_panel_artifact_valid_image.json",
        "skills/persona-dream/fixtures/rung10_panel_reviewer_receipt_missing_image.json",
    )["linkage"]["artifact_hash_ok"]
    is False,
}

receipt = {
    "schema": "persona_dream.rung12_shared_phase_gate.v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "producer": "skills/persona-dream/scripts/rung12_shared_phase_gate.py",
    "cases": results,
    "negative_checks": negative_checks,
}
receipt["ok"] = all(case["case_ok"] for case in results) and all(negative_checks.values())

atomic_write(Path(args.receipt), receipt)
print(json.dumps({"rung": 12, "cases": len(results), "receipt": args.receipt, "ok": receipt["ok"]}))
raise SystemExit(0 if receipt["ok"] else 1)
