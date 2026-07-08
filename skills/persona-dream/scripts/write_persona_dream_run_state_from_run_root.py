#!/usr/bin/env python3
"""Project a Persona Dream run root into local run-state artifacts.

This adapter reads files from a real run root and writes a local deterministic
state bundle. It never calls Tau or providers and never treats missing evidence
as accepted progress.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_RUN_ROOT_STATE_ADAPTER"
BLOCKED_STATUS = "BLOCKED_RUN_ROOT_STATE_ADAPTER"
STATE_SCHEMA = "persona-dream.dream-run-state.v1"
MODE = "LOCAL_DETERMINISTIC"

PROGRESS_UNITS = [
    ("phase01_memory_residue", "01", "Memory residue", "residue_links.json"),
    ("phase02_story_contract", "02", "Story contract", "story_contract.json"),
    ("phase03_crew_contract", "03", "Crew contract", "crew_contract.json"),
    ("phase04_entity_environment", "04", "Entity environment", "entity_environment_contract.json"),
    ("phase05_contact_sheets", "05", "Contact sheets", "receipts/phase05_contact_sheet_gate.json"),
    ("phase06_script_contract", "06", "Script contract", "script_contract.json"),
    ("phase07_storyboard_packet", "07", "Storyboard packet", "storyboard_packet.json"),
    ("phase08_kling_scene_packet", "08", "Kling scene packet", "phase08_kling_scene_packet/kling_scene_packet.json"),
    ("reference_assets", "refs", "Reference assets", "reference_assets.v1.json"),
    ("prompt_contracts", "prompts", "Prompt contracts", "prompt_contracts/index.v1.json"),
    ("validator_receipts", "validators", "Validator receipts", "receipts/validator_index.v1.json"),
    ("reviewer_receipts", "reviewers", "Reviewer receipts", "receipts/reviewer_index.v1.json"),
    ("media_lock", "locks", "Media lock", "artifact_lock_index.v1.json"),
    ("accepted_evidence", "evidence", "Accepted evidence", "accepted_evidence_index.v1.json"),
    ("respawn_plan", "respawn", "Respawn plan", "respawn_plan.v1.json"),
    ("stale_write_fence", "fence", "Stale write fence", "receipts/stale_write_fence_receipt.v1.json"),
    ("dynamic_respawn_events", "events", "Dynamic respawn events", "dynamic_change_events.v1.json"),
    ("creator_reviewer_loop", "loop", "Creator/reviewer loop", "receipts/creator_reviewer_respawn_loop_receipt.v1.json"),
    ("run_state", "state", "Run state", "dream_run_state.v1.json"),
    ("provider_final_gate", "provider", "Provider final gate", "provider_final_gate_state.v1.json"),
]


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def artifact_ref(path: Path, root: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return {
        "path": rel(path, root),
        "sha256": sha256_file(path),
    }


def load_or_default(run_root: Path, rel_path: str, default: dict[str, Any]) -> dict[str, Any]:
    data = read_json(run_root / rel_path, default)
    if not data:
        data = dict(default)
    return data


def build_progress_sources(run_root: Path, blockers: list[str]) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    for unit_id, phase, label, rel_path in PROGRESS_UNITS:
        path = run_root / rel_path
        if path.exists():
            units.append(
                {
                    "unit_id": unit_id,
                    "phase": phase,
                    "label": label,
                    "status": "PASS_WITH_LIVE_BLOCKERS" if unit_id in {"phase08_kling_scene_packet", "provider_final_gate"} else "PASS",
                    "evidence_state": "CURRENT",
                    "receipt_path": rel_path,
                    "receipt_sha256": sha256_file(path),
                    "live_blockers": ["DRY_RUN_NOT_LIVE_SUBMITTABLE"] if unit_id in {"phase08_kling_scene_packet", "provider_final_gate"} else [],
                }
            )
        else:
            units.append(
                {
                    "unit_id": unit_id,
                    "phase": phase,
                    "label": label,
                    "status": "BLOCKED",
                    "evidence_state": "MISSING",
                    "receipt_path": None,
                    "receipt_sha256": None,
                    "live_blockers": [],
                }
            )
            if unit_id in {"media_lock", "accepted_evidence", "phase07_storyboard_packet"}:
                add_blocker(blockers, "BLOCKED_RUN_ROOT_REQUIRED_ARTIFACT_MISSING")
    return {
        "schema": "persona_dream.global_progress_sources.v1",
        "run_root": str(run_root),
        "provider_ready": False,
        "live_submit_ready": False,
        "manual_acceptance_claimed": False,
        "paid_call_authorized": False,
        "submitted": False,
        "units": units,
    }


def build_global_progress(progress_sources: dict[str, Any], source_path: Path) -> dict[str, Any]:
    units = progress_sources.get("units") if isinstance(progress_sources.get("units"), list) else []
    pass_count = sum(1 for unit in units if unit.get("status") in {"PASS", "PASS_WITH_LIVE_BLOCKERS"})
    blocked_count = sum(1 for unit in units if unit.get("status") == "BLOCKED")
    return {
        "schema": "persona_dream.global_progress.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "status": "PASS_GLOBAL_PROGRESS_ROLLUP" if blocked_count == 0 else "BLOCKED_GLOBAL_PROGRESS_ROLLUP",
        "derived": True,
        "owner_artifact": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "live_image_call_started": False,
        "live_kling_call_started": False,
        "manual_acceptance_claimed": False,
        "submitted": False,
        "unit_count": len(units),
        "expected_unit_count": len(PROGRESS_UNITS),
        "pass_count": pass_count,
        "blocked_count": blocked_count,
        "progress_percent": round((pass_count / len(PROGRESS_UNITS)) * 100, 2),
        "units": units,
        "blockers": ["BLOCKED_RUN_ROOT_REQUIRED_ARTIFACT_MISSING"] if blocked_count else [],
    }


def validate_accepted_evidence(run_root: Path, evidence_index: dict[str, Any], lock_index: dict[str, Any], blockers: list[str]) -> None:
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
        for field, blocker in [
            ("reviewer_receipt_path", "BLOCKED_REVIEWER_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT"),
            ("promotion_receipt_path", "BLOCKED_PROMOTION_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT"),
        ]:
            receipt_path = item.get(field)
            if not receipt_path or not (run_root / str(receipt_path)).exists():
                add_blocker(blockers, blocker)


def build_from_run_root(run_root: Path, output: Path, progress_source_out: Path | None = None) -> dict[str, Any]:
    run_root = run_root.resolve()
    output = output.resolve()
    blockers: list[str] = []
    if not run_root.exists():
        add_blocker(blockers, "BLOCKED_RUN_ROOT_MISSING")
    output.parent.mkdir(parents=True, exist_ok=True)
    docs_dir = output.parent / "run_state_documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    progress_source_path = (progress_source_out.resolve() if progress_source_out else output.parent / "global_progress_sources.v1.json")
    progress_sources = build_progress_sources(run_root, blockers)
    write_json(progress_source_path, progress_sources)
    global_progress = build_global_progress(progress_sources, progress_source_path)

    policy = load_or_default(
        run_root,
        "run_policy.v1.json",
        {
            "schema": "persona_dream.run_policy.v1",
            "provider_live": False,
            "paid_call_authorized": False,
            "provider_accessible_url_created": False,
            "submitted": False,
            "manual_acceptance_claimed": False,
        },
    )
    for flag, blocker in [
        ("provider_live", "BLOCKED_PROVIDER_LIVE_IN_RUN_STATE"),
        ("paid_call_authorized", "BLOCKED_PAID_CALL_AUTHORIZED_IN_RUN_STATE"),
        ("provider_accessible_url_created", "BLOCKED_PROVIDER_ACCESSIBLE_URL_CREATED_IN_RUN_STATE"),
        ("submitted", "BLOCKED_SUBMITTED_CLAIM_IN_RUN_STATE"),
        ("manual_acceptance_claimed", "BLOCKED_MANUAL_ACCEPTANCE_CLAIM_IN_RUN_STATE"),
    ]:
        if policy.get(flag) is True:
            add_blocker(blockers, blocker)

    revision = load_or_default(
        run_root,
        "dream_revision_manifest.v1.json",
        {
            "schema": "persona_dream.revision_state.v1",
            "run_id": run_root.name,
            "active_revision_id": "rev_0001",
            "last_change_event_seq": 0,
            "last_planned_event_seq": 0,
        },
    )
    if int(revision.get("last_change_event_seq", 0)) > int(revision.get("last_planned_event_seq", 0)):
        add_blocker(blockers, "BLOCKED_UNPLANNED_CHANGE_EVENTS")

    respawn_plan = load_or_default(run_root, "respawn_plan.v1.json", {"schema": "persona_dream.respawn_plan.v1", "revision_id": revision.get("active_revision_id"), "decisions": []})
    active_work_queue = load_or_default(run_root, "active_work_queue.v1.json", {"schema": "persona_dream.active_work_queue.v1", "revision_id": revision.get("active_revision_id"), "items": []})
    work_lease_index = load_or_default(run_root, "work_lease_index.v1.json", {"schema": "persona_dream.work_lease_index.v1", "revision_id": revision.get("active_revision_id"), "leases": []})
    lock_index = load_or_default(run_root, "artifact_lock_index.v1.json", {"schema": "persona_dream.artifact_lock_index.v1", "revision_id": revision.get("active_revision_id"), "artifacts": []})
    evidence_index = load_or_default(run_root, "accepted_evidence_index.v1.json", {"schema": "persona_dream.accepted_evidence_index.v1", "revision_id": revision.get("active_revision_id"), "accepted_artifacts": []})
    tau = load_or_default(run_root, "tau_contract_state.v1.json", {"schema": "persona_dream.tau_contract_state.v1", "contract_generated": False, "contract_claimed_executed": False, "live_tau_dag_execution_started": False, "command_loop_receipt_path": None})
    provider_gate = load_or_default(run_root, "provider_final_gate_state.v1.json", {"schema": "persona_dream.provider_final_gate_state.v1", "provider_ready": False, "live_submit_ready": False, "dry_run_treated_as_live_ready": False, "receipt_path": None})

    if tau.get("contract_claimed_executed") is True and not tau.get("command_loop_receipt_path"):
        add_blocker(blockers, "BLOCKED_TAU_CONTRACT_WITHOUT_EXECUTION_RECEIPT")
    if provider_gate.get("provider_ready") is True:
        add_blocker(blockers, "BLOCKED_PROVIDER_READY_CLAIM")
    if provider_gate.get("live_submit_ready") is True:
        add_blocker(blockers, "BLOCKED_LIVE_SUBMIT_READY_CLAIM")

    validate_accepted_evidence(run_root, evidence_index, lock_index, blockers)

    write_json(docs_dir / "policy.json", policy)
    revision["effective_policy_hash"] = sha256_file(docs_dir / "policy.json")
    write_json(docs_dir / "revision.json", revision)
    write_json(docs_dir / "respawn_plan.json", respawn_plan)
    write_json(docs_dir / "active_work_queue.json", active_work_queue)
    write_json(docs_dir / "work_lease_index.json", work_lease_index)
    write_json(docs_dir / "artifact_lock_index.json", lock_index)
    write_json(docs_dir / "accepted_evidence_index.json", evidence_index)
    write_json(docs_dir / "global_progress.json", global_progress)
    status_surface = {
        "schema": "persona_dream.status_surface.v1",
        "view_only": True,
        "authority": False,
        "claims_progress": True,
        "source_global_progress_sha256": sha256_file(docs_dir / "global_progress.json"),
    }
    write_json(docs_dir / "status_surface.json", status_surface)
    write_json(docs_dir / "tau.json", tau)
    write_json(docs_dir / "provider_final_gate.json", provider_gate)

    ref_names = [
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
    ]
    references = {}
    for name in ref_names:
        path = docs_dir / f"{name}.json"
        references[name] = {"document_id": name, "path": rel(path, output.parent), "sha256": sha256_file(path)}

    if "BLOCKED_UNPLANNED_CHANGE_EVENTS" in blockers and len(blockers) == 1:
        runtime_state = "LOCAL_RESPAWN_REQUIRED"
    elif blockers:
        runtime_state = "LOCAL_BLOCKED_RUN_STATE"
    else:
        runtime_state = "LOCAL_DRY_RUN_COMPLETE_NOT_PROVIDER_READY"

    state = {
        "schema_version": STATE_SCHEMA,
        "run_id": str(revision.get("run_id") or run_root.name),
        "state_id": f"{run_root.name}.run_state",
        "state_seq": int(revision.get("last_planned_event_seq", 0)),
        "mode": MODE,
        "active_revision_id_at_state": revision.get("active_revision_id"),
        "runtime_state": runtime_state,
        "effective_policy_hash": revision["effective_policy_hash"],
        "references": references,
        "artifact_decision_counts": {
            "CURRENT": 1,
            "REUSE_ALLOWED": 1,
            "REVALIDATE_REQUIRED": 0,
            "REGENERATE_REQUIRED": 0,
            "REVIEW_REQUIRED": 0,
            "BLOCKED_HUMAN_DECISION_REQUIRED": 0,
            "SUPERSEDED": 0,
        },
        "blockers": sorted(blockers),
        "non_claims": [
            "does_not_call_kling",
            "does_not_authorize_paid_calls",
            "does_not_create_provider_accessible_urls",
            "does_not_claim_manual_acceptance",
            "does_not_claim_provider_readiness",
            "does_not_claim_tau_execution",
        ],
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "manual_acceptance_claimed": False,
        "actual_provider_call_attempts": 0,
    }
    write_json(output, state)
    receipt = {
        "schema": "persona_dream.run_root_state_adapter_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "run_root": str(run_root),
        "dream_run_state_path": str(output),
        "global_progress_sources_path": str(progress_source_path),
        "runtime_state": runtime_state,
        "blockers": sorted(blockers),
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "manual_acceptance_claimed": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "mocked": False,
        "claims": {
            "proves": [
                "a run root was projected into local dream_run_state.v1 and global_progress_sources.v1 artifacts",
                "missing run-root evidence was represented as blockers rather than acceptance",
            ],
            "does_not_prove": [
                "manual acceptance",
                "provider readiness",
                "provider-accessible URLs",
                "paid-call authorization",
                "live Tau execution",
                "live Kling generation",
            ],
        },
    }
    write_json(output.parent / "run_root_state_adapter_receipt.v1.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--progress-source-out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = build_from_run_root(args.run_root, args.output, args.progress_source_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
