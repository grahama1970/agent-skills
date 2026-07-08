#!/usr/bin/env python3
"""Check Persona Dream local run state consistency.

This checker is a local deterministic run-state guard. It does not execute Tau,
submit provider requests, create provider URLs, or infer manual acceptance from
progress/status surfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PERSONA_DREAM_RUN_STATE"
BLOCKED_STATUS = "BLOCKED_PERSONA_DREAM_RUN_STATE"
SCHEMA_VERSION = "persona-dream.dream-run-state.v1"
RECEIPT_SCHEMA_VERSION = "persona-dream.dream-run-state-check-receipt.v1"
MODE = "LOCAL_DETERMINISTIC"

ARTIFACT_DECISIONS = {
    "CURRENT",
    "REUSE_ALLOWED",
    "REVALIDATE_REQUIRED",
    "REGENERATE_REQUIRED",
    "REVIEW_REQUIRED",
    "BLOCKED_HUMAN_DECISION_REQUIRED",
    "SUPERSEDED",
}

FORBIDDEN_TRUE_FLAGS = {
    "provider_live": "BLOCKED_PROVIDER_LIVE_IN_RUN_STATE",
    "paid_call_authorized": "BLOCKED_PAID_CALL_AUTHORIZED_IN_RUN_STATE",
    "provider_accessible_url_created": "BLOCKED_PROVIDER_ACCESSIBLE_URL_CREATED_IN_RUN_STATE",
    "submitted": "BLOCKED_SUBMITTED_CLAIM_IN_RUN_STATE",
    "manual_acceptance_claimed": "BLOCKED_MANUAL_ACCEPTANCE_CLAIM_IN_RUN_STATE",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_sha256(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def fixture_documents(fixture: dict[str, Any]) -> dict[str, Any]:
    documents = fixture.get("documents")
    return documents if isinstance(documents, dict) else {}


def doc_hash(documents: dict[str, Any], doc_id: str) -> str | None:
    if doc_id not in documents:
        return None
    return canonical_sha256(documents[doc_id])


def declared_hash(documents: dict[str, Any], state: dict[str, Any], ref_name: str) -> str | None:
    refs = state.get("references")
    if not isinstance(refs, dict):
        return None
    ref = refs.get(ref_name)
    if not isinstance(ref, dict):
        return None
    sha = ref.get("sha256")
    if isinstance(sha, str) and sha.startswith("sha256:fixture:"):
        return doc_hash(documents, sha.split(":", 2)[2])
    return sha if isinstance(sha, str) else None


def load_doc(documents: dict[str, Any], state: dict[str, Any], ref_name: str) -> dict[str, Any]:
    refs = state.get("references")
    if not isinstance(refs, dict):
        return {}
    ref = refs.get(ref_name)
    if not isinstance(ref, dict):
        return {}
    doc_id = ref.get("document_id") or ref_name
    doc = documents.get(str(doc_id))
    return doc if isinstance(doc, dict) else {}


def validate_hash_ref(documents: dict[str, Any], state: dict[str, Any], ref_name: str, blockers: list[str]) -> None:
    refs = state.get("references")
    if not isinstance(refs, dict) or not isinstance(refs.get(ref_name), dict):
        add_blocker(blockers, "BLOCKED_RUN_STATE_REFERENCE_MISSING")
        return
    ref = refs[ref_name]
    doc_id = str(ref.get("document_id") or ref_name)
    actual = doc_hash(documents, doc_id)
    declared = declared_hash(documents, state, ref_name)
    if actual is None or declared is None:
        add_blocker(blockers, "BLOCKED_RUN_STATE_REFERENCE_MISSING")
    elif actual != declared:
        add_blocker(blockers, "BLOCKED_ARTIFACT_HASH_MISMATCH")


def validate_policy(state: dict[str, Any], policy: dict[str, Any], blockers: list[str]) -> None:
    for flag, blocker in FORBIDDEN_TRUE_FLAGS.items():
        if state.get(flag) is True or policy.get(flag) is True:
            add_blocker(blockers, blocker)
    if state.get("actual_provider_call_attempts", 0) != 0:
        add_blocker(blockers, "BLOCKED_PROVIDER_CALL_ATTEMPTS_IN_RUN_STATE")
    if policy.get("provider_live") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_IN_RUN_STATE")
    if policy.get("paid_call_authorized") is not False:
        add_blocker(blockers, "BLOCKED_PAID_CALL_AUTHORIZED_IN_RUN_STATE")


def validate_revision(state: dict[str, Any], revision: dict[str, Any], blockers: list[str]) -> None:
    active_revision_id = state.get("active_revision_id_at_state")
    if not active_revision_id or active_revision_id != revision.get("active_revision_id"):
        add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")
    if revision.get("effective_policy_hash") and revision.get("effective_policy_hash") != state.get("effective_policy_hash"):
        add_blocker(blockers, "BLOCKED_POLICY_HASH_MISMATCH")
    if int(revision.get("last_change_event_seq", 0)) > int(revision.get("last_planned_event_seq", 0)):
        add_blocker(blockers, "BLOCKED_UNPLANNED_CHANGE_EVENTS")


def validate_respawn(state: dict[str, Any], respawn: dict[str, Any], blockers: list[str]) -> None:
    active_revision_id = state.get("active_revision_id_at_state")
    if respawn.get("revision_id") != active_revision_id:
        add_blocker(blockers, "BLOCKED_RESPAWN_PLAN_REVISION_MISMATCH")
        add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")


def validate_work_queue(state: dict[str, Any], work_queue: dict[str, Any], respawn_sha: str | None, blockers: list[str]) -> None:
    active_revision_id = state.get("active_revision_id_at_state")
    if work_queue.get("revision_id") != active_revision_id:
        add_blocker(blockers, "BLOCKED_WORK_QUEUE_REVISION_MISMATCH")
        add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")
    if work_queue.get("respawn_plan_hash") != respawn_sha:
        add_blocker(blockers, "BLOCKED_WORK_QUEUE_RESPAWN_PLAN_HASH_MISMATCH")


def validate_work_leases(state: dict[str, Any], work_leases: dict[str, Any], blockers: list[str]) -> None:
    active_revision_id = state.get("active_revision_id_at_state")
    if work_leases.get("revision_id") != active_revision_id:
        add_blocker(blockers, "BLOCKED_WORK_LEASE_REVISION_MISMATCH")
        add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")


def validate_accepted_evidence(
    state: dict[str, Any],
    lock_index: dict[str, Any],
    evidence_index: dict[str, Any],
    blockers: list[str],
) -> None:
    active_revision_id = state.get("active_revision_id_at_state")
    locks = {
        str(item.get("artifact_id"))
        for item in lock_index.get("artifacts", [])
        if isinstance(item, dict) and item.get("artifact_id")
    }
    for item in evidence_index.get("accepted_artifacts", []):
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("artifact_id") or "")
        if artifact_id not in locks:
            add_blocker(blockers, "BLOCKED_ACCEPTED_EVIDENCE_LOCK_MISSING")
        if item.get("revision_id") != active_revision_id:
            add_blocker(blockers, "BLOCKED_SUPERSEDED_EVIDENCE_COUNTED")


def validate_global_progress(global_progress: dict[str, Any], blockers: list[str]) -> None:
    if global_progress.get("derived") is not True or global_progress.get("owner_artifact") is not False:
        add_blocker(blockers, "BLOCKED_GLOBAL_PROGRESS_OWNERSHIP_INVALID")
    if global_progress.get("provider_ready") is True or global_progress.get("live_submit_ready") is True:
        add_blocker(blockers, "BLOCKED_FALSE_PROVIDER_READY_CLAIM")
    if global_progress.get("manual_acceptance_claimed") is True:
        add_blocker(blockers, "BLOCKED_MANUAL_ACCEPTANCE_CLAIM_IN_RUN_STATE")
    if global_progress.get("submitted") is True:
        add_blocker(blockers, "BLOCKED_SUBMITTED_CLAIM_IN_RUN_STATE")


def validate_status_surface(state: dict[str, Any], documents: dict[str, Any], status_surface: dict[str, Any], blockers: list[str]) -> None:
    if status_surface.get("authority") is not False:
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_TREATED_AS_AUTHORITY")
    if status_surface.get("view_only") is not True:
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_TREATED_AS_AUTHORITY")
    source_sha = status_surface.get("source_global_progress_sha256")
    progress_sha = declared_hash(documents, state, "global_progress")
    if status_surface.get("claims_progress") is True and source_sha != progress_sha:
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_SOURCE_HASH_MISMATCH")


def validate_tau(tau: dict[str, Any], blockers: list[str]) -> None:
    if tau.get("contract_claimed_executed") is True and not tau.get("command_loop_receipt_path"):
        add_blocker(blockers, "BLOCKED_TAU_EXECUTION_CLAIM_WITHOUT_RECEIPT")
    if tau.get("live_tau_dag_execution_started") is True and not tau.get("command_loop_receipt_path"):
        add_blocker(blockers, "BLOCKED_TAU_EXECUTION_CLAIM_WITHOUT_RECEIPT")


def validate_provider_final_gate(provider_gate: dict[str, Any], blockers: list[str]) -> None:
    if provider_gate.get("provider_ready") is True and not provider_gate.get("receipt_path"):
        add_blocker(blockers, "BLOCKED_PROVIDER_FINAL_GATE_CLAIM_WITHOUT_RECEIPT")
    if provider_gate.get("live_submit_ready") is True or provider_gate.get("dry_run_treated_as_live_ready") is True:
        add_blocker(blockers, "BLOCKED_DRY_RUN_TREATED_AS_LIVE_READY")


def evaluate_fixture(fixture_path: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    documents = fixture_documents(fixture)
    state = fixture.get("dream_run_state") if isinstance(fixture.get("dream_run_state"), dict) else {}
    blockers: list[str] = []

    if state.get("schema_version") != SCHEMA_VERSION:
        add_blocker(blockers, "BLOCKED_DREAM_RUN_STATE_SCHEMA")
    if state.get("mode") != MODE:
        add_blocker(blockers, "BLOCKED_DREAM_RUN_STATE_MODE")

    for ref_name in [
        "revision",
        "policy",
        "respawn_plan",
        "active_work_queue",
        "work_lease_index",
        "artifact_lock_index",
        "accepted_evidence_index",
        "global_progress",
        "status_surface",
        "tau",
        "provider_final_gate",
    ]:
        validate_hash_ref(documents, state, ref_name, blockers)

    revision = load_doc(documents, state, "revision")
    policy = load_doc(documents, state, "policy")
    respawn = load_doc(documents, state, "respawn_plan")
    work_queue = load_doc(documents, state, "active_work_queue")
    work_leases = load_doc(documents, state, "work_lease_index")
    lock_index = load_doc(documents, state, "artifact_lock_index")
    evidence_index = load_doc(documents, state, "accepted_evidence_index")
    global_progress = load_doc(documents, state, "global_progress")
    status_surface = load_doc(documents, state, "status_surface")
    tau = load_doc(documents, state, "tau")
    provider_gate = load_doc(documents, state, "provider_final_gate")

    validate_policy(state, policy, blockers)
    validate_revision(state, revision, blockers)
    validate_respawn(state, respawn, blockers)
    validate_work_queue(state, work_queue, declared_hash(documents, state, "respawn_plan"), blockers)
    validate_work_leases(state, work_leases, blockers)
    validate_accepted_evidence(state, lock_index, evidence_index, blockers)
    validate_global_progress(global_progress, blockers)
    validate_status_surface(state, documents, status_surface, blockers)
    validate_tau(tau, blockers)
    validate_provider_final_gate(provider_gate, blockers)

    if "BLOCKED_UNPLANNED_CHANGE_EVENTS" in blockers and len(blockers) == 1:
        runtime_state = "LOCAL_RESPAWN_REQUIRED"
    elif blockers:
        runtime_state = "LOCAL_BLOCKED_RUN_STATE"
    else:
        runtime_state = str(state.get("runtime_state") or "LOCAL_RUN_STATE_CONSISTENT")

    decisions = set()
    counts = state.get("artifact_decision_counts")
    if isinstance(counts, dict):
        decisions.update(str(key) for key in counts if str(key) in ARTIFACT_DECISIONS)
    for decision in respawn.get("decisions", []):
        if isinstance(decision, dict) and decision.get("decision") in ARTIFACT_DECISIONS:
            decisions.add(str(decision["decision"]))

    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    errors: list[str] = []
    if expected.get("runtime_state") and runtime_state != expected["runtime_state"]:
        errors.append(f"runtime_state_mismatch:{runtime_state}:expected:{expected['runtime_state']}")
    expected_blockers = set(expected.get("blockers") or [])
    missing = sorted(expected_blockers - set(blockers))
    unexpected = sorted(set(blockers) - expected_blockers) if expected.get("exact_blockers") is True else []
    errors.extend(f"missing_blocker:{blocker}" for blocker in missing)
    errors.extend(f"unexpected_blocker:{blocker}" for blocker in unexpected)

    return {
        "fixture": fixture_path.parent.name,
        "runtime_state": runtime_state,
        "blockers": sorted(blockers),
        "artifact_decisions": sorted(decisions),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    fixture_paths = sorted(fixtures_root.glob("*/fixture.json"))
    results = [evaluate_fixture(path) for path in fixture_paths]
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    observed_blockers = sorted({blocker for result in results for blocker in result["blockers"]})
    observed_runtime_states = sorted({result["runtime_state"] for result in results})
    observed_artifact_decisions = sorted({decision for result in results for decision in result["artifact_decisions"]})
    valid_fixture_count = sum(1 for result in results if not result["blockers"])
    respawn_required_fixture_count = sum(1 for result in results if result["runtime_state"] == "LOCAL_RESPAWN_REQUIRED")
    blocked_fixture_count = sum(1 for result in results if result["blockers"] and result["runtime_state"] != "LOCAL_RESPAWN_REQUIRED")
    expected_blockers = {
        "BLOCKED_RESPAWN_PLAN_REVISION_MISMATCH",
        "BLOCKED_ACTIVE_REVISION_MISMATCH",
        "BLOCKED_WORK_QUEUE_RESPAWN_PLAN_HASH_MISMATCH",
        "BLOCKED_ACCEPTED_EVIDENCE_LOCK_MISSING",
        "BLOCKED_FALSE_PROVIDER_READY_CLAIM",
        "BLOCKED_TAU_EXECUTION_CLAIM_WITHOUT_RECEIPT",
        "BLOCKED_STATUS_SURFACE_SOURCE_HASH_MISMATCH",
        "BLOCKED_STATUS_SURFACE_TREATED_AS_AUTHORITY",
        "BLOCKED_UNPLANNED_CHANGE_EVENTS",
        "BLOCKED_SUPERSEDED_EVIDENCE_COUNTED",
        "BLOCKED_PROVIDER_FINAL_GATE_CLAIM_WITHOUT_RECEIPT",
        "BLOCKED_DRY_RUN_TREATED_AS_LIVE_READY",
    }
    if len(results) != 10:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:10")
    missing_expected_blockers = sorted(expected_blockers - set(observed_blockers))
    errors.extend(f"missing_expected_observed_blocker:{blocker}" for blocker in missing_expected_blockers)
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "mode": MODE,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "manual_acceptance_claimed": False,
        "actual_provider_call_attempts": 0,
        "fixture_count": len(results),
        "valid_fixture_count": valid_fixture_count,
        "blocked_fixture_count": blocked_fixture_count,
        "respawn_required_fixture_count": respawn_required_fixture_count,
        "observed_runtime_states": observed_runtime_states,
        "observed_artifact_decisions": observed_artifact_decisions,
        "observed_blockers": observed_blockers,
        "errors": errors,
        "results": results,
        "mocked": False,
        "claims": {
            "proves": [
                "dream_run_state fixture references were checked against recomputed local document hashes",
                "local run-state blockers were classified deterministically",
                "provider, paid-call, manual-acceptance, submission, and Tau execution claims stayed false unless backed by receipts",
            ],
            "does_not_prove": [
                "Kling provider schema compatibility",
                "provider-accessible URLs",
                "paid-call authorization",
                "manual acceptance",
                "live Tau DAG execution",
                "live Kling generation",
                "fixture behavior is production run-root proof",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
