#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lane_worker_common import (
    build_tau_agent_handoff,
    claim_one,
    latest_by_issue,
    read_jsonl,
    run_registry_check,
    run_registry_decision,
    run_registry_latest_approval,
    update_issue,
    utc_now,
    write_tau_handoff_artifacts,
    write_json,
)

DEFAULT_QUEUE = Path("/mnt/storage12tb/media/agents/shared/monitor-sparta/repair_queue.jsonl")
DEFAULT_RUN_ROOT = Path("/mnt/storage12tb/skills/review-db/outputs/qra-auditor")
DEFAULT_MEMORY_ROOT = Path("/home/graham/workspace/experiments/memory")
ALLOWED_LANES = {"source_text_qra_coverage", "qra_coverage_per_control", "qra_generation", "qra_quality_repair"}
DEFAULT_CURRENT_RUN_FILE = Path("/tmp/qbert-current-apply-dir.txt")
DEFAULT_CREATE_QRAS_STATE = Path.home() / ".create_qras_manifest_state.json"
DEFAULT_SUPERVISOR_PAUSE_FILE = Path("/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/PAUSED")
QBERT_PROCESS_PATTERN = "qbert_qra_repair|create-qras|create_qras|generator.py|run_qbert.sh"


def find_qra_after_count(value: Any) -> int | None:
    """Extract the source_text_qra_coverage after-count from a scan artifact."""
    if not isinstance(value, Mapping):
        return None
    direct = value.get("control_qra_generation_required")
    if direct is not None:
        return int(direct)
    for key in ("summary", "source_text_qra_summary", "coverage_counts"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            found = find_qra_after_count(nested)
            if found is not None:
                return found
    source_check = value.get("source_check")
    if isinstance(source_check, Mapping):
        nested = source_check.get("source_text_qra_summary")
        if isinstance(nested, Mapping):
            found = find_qra_after_count(nested)
            if found is not None:
                return found
        direct_check = source_check.get("qra_missing_generation_required")
        if direct_check is not None:
            return int(direct_check)
    checks = value.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, Mapping) and check.get("dimension") == "qra_coverage_per_control":
                found = find_qra_after_count(check)
                if found is not None:
                    return found
    return None


def load_after_count_artifact(path: Path) -> tuple[int | None, dict[str, Any]]:
    payload = load_json(path)
    return find_qra_after_count(payload), payload


def status_current(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    current_run_file = Path(args.current_run_file)
    state_path = Path(args.state_file)
    run_dir_text = current_run_file.read_text(encoding="utf-8").strip() if current_run_file.exists() else ""
    run_dir = Path(run_dir_text) if run_dir_text else None
    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            state = load_json(state_path)
        except Exception as exc:  # noqa: BLE001
            state = {"state_read_error": f"{type(exc).__name__}: {exc}"}

    pgrep = subprocess.run(
        ["pgrep", "-af", QBERT_PROCESS_PATTERN],
        text=True,
        capture_output=True,
        check=False,
    )
    processes = [line for line in (pgrep.stdout or "").splitlines() if line.strip()]
    receipt_path = run_dir / "qbert_qra_repair_receipt.json" if run_dir else None
    exit_code_path = run_dir / "exit_code.txt" if run_dir else None
    stderr_path = run_dir / "qbert_qra_repair.stderr.txt" if run_dir else None
    receipt: dict[str, Any] | None = None
    if receipt_path and receipt_path.exists():
        try:
            receipt = load_json(receipt_path)
        except Exception as exc:  # noqa: BLE001
            receipt = {"receipt_read_error": f"{type(exc).__name__}: {exc}"}

    snapshot = {
        "schema": "qra_auditor.current_status.v1",
        "checked_at": utc_now(),
        "current_run_file": str(current_run_file),
        "run_dir": str(run_dir) if run_dir else None,
        "process_count": len(processes),
        "processes": processes,
        "state_file": str(state_path),
        "state_file_exists": state_path.exists(),
        "state": {
            key: state.get(key)
            for key in (
                "status",
                "phase",
                "total_jobs",
                "total_chunks",
                "chunk_num",
                "completed_jobs",
                "successful_jobs",
                "skipped_jobs",
                "failed_jobs",
                "stored_qras",
                "generated_qras",
                "progress_pct",
                "current_item",
                "last_message",
                "last_error",
                "scillm_stream_events",
                "scillm_stream_heartbeats",
            )
        },
        "skipped_items_count": len(state.get("skipped_items") or []) if isinstance(state.get("skipped_items"), list) else 0,
        "skipped_items_tail": (state.get("skipped_items") or [])[-5:] if isinstance(state.get("skipped_items"), list) else [],
        "receipt_path": str(receipt_path) if receipt_path else None,
        "receipt_exists": bool(receipt_path and receipt_path.exists()),
        "receipt_terminal_status": receipt.get("terminal_status") if isinstance(receipt, Mapping) else None,
        "receipt_ok": receipt.get("ok") if isinstance(receipt, Mapping) else None,
        "receipt_proof_ok": receipt.get("proof_ok") if isinstance(receipt, Mapping) else None,
        "exit_code_path": str(exit_code_path) if exit_code_path else None,
        "exit_code_exists": bool(exit_code_path and exit_code_path.exists()),
        "exit_code": exit_code_path.read_text(encoding="utf-8").strip() if exit_code_path and exit_code_path.exists() else None,
        "stderr_path": str(stderr_path) if stderr_path else None,
        "stderr_tail": stderr_path.read_text(encoding="utf-8")[-2000:] if stderr_path and stderr_path.exists() else None,
        "supervisor_pause_file": str(args.supervisor_pause_file),
        "supervisor_paused": Path(args.supervisor_pause_file).exists(),
        "mocked": False,
        "live": True,
    }
    if args.output:
        write_json(Path(args.output), snapshot)
    return 0, snapshot


def source_text_summary(issue: Mapping[str, Any]) -> dict[str, Any]:
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    summary = slice_.get("summary") if isinstance(slice_.get("summary"), Mapping) else {}
    if summary:
        return dict(summary)
    check = issue.get("source_check") if isinstance(issue.get("source_check"), Mapping) else {}
    nested = check.get("source_text_qra_summary") if isinstance(check.get("source_text_qra_summary"), Mapping) else {}
    return dict(nested)


def source_text_manifest_path(issue: Mapping[str, Any]) -> str | None:
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    value = slice_.get("source_text_qra_manifest")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def needs_source_fetch(summary: Mapping[str, Any]) -> bool:
    return int(summary.get("control_text_missing_or_stub") or 0) > 0 or int(summary.get("url_text_missing_or_stub") or 0) > 0


def issue_value(issue: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if issue.get(key) not in (None, ""):
        return issue.get(key)
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    if slice_.get(key) not in (None, ""):
        return slice_.get(key)
    return default


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def prompt_approval_category(issue: Mapping[str, Any]) -> tuple[str, str]:
    category = str(issue_value(issue, "category", "sparta_countermeasure"))
    framework = str(issue_value(issue, "framework", "SPARTA"))
    return category, framework


def framework_for_qra_category(category: Any, *, fallback: Any = None) -> str:
    text = str(category or "").strip()
    if text == "nvd_native":
        return "NVD"
    if text in {"att_ck_enterprise_native", "attandck_native", "attack_native"}:
        return "ATT_CK_Enterprise"
    if text == "d3fend_native":
        return "D3FEND"
    if text.startswith("sparta_"):
        return "SPARTA"
    return str(fallback or text or "")


def resolve_prompt_approval(issue: Mapping[str, Any], *, run_dir: Path, memory_root: Path) -> dict[str, Any]:
    lane = str(issue.get("lane") or "")
    category, framework = prompt_approval_category(issue)
    prompt_hash = issue_value(issue, "prompt_contract_hash")
    expected_hash = issue_value(issue, "expected_response_hash")
    validator_hash = issue_value(issue, "validator_hash")
    latest = None
    if not prompt_hash:
        latest = run_registry_latest_approval(
            memory_root=memory_root,
            output=run_dir / "prompt_approval_latest.json",
            category=category,
            framework=framework,
            lane=lane,
        )
        latest_doc = latest.get("latest") if isinstance(latest.get("latest"), Mapping) else {}
        prompt_hash = latest_doc.get("prompt_contract_hash")
        expected_hash = latest_doc.get("expected_response_hash")
        validator_hash = latest_doc.get("validator_hash")

    if not prompt_hash:
        return {
            "ok": False,
            "category": category,
            "framework": framework,
            "lane": lane,
            "latest_approval": latest,
            "terminal_status": "MISSING_PROMPT_APPROVAL_HASH",
            "reason": "qra_issue_has_no_prompt_contract_hash_and_registry_has_no_usable_latest_approval",
            "mocked": False,
            "live": True,
        }

    check = run_registry_check(
        memory_root=memory_root,
        output=run_dir / "prompt_approval_check.json",
        category=category,
        framework=framework,
        lane=lane,
        prompt_contract_hash=str(prompt_hash),
        expected_response_hash=str(expected_hash) if expected_hash else None,
        validator_hash=str(validator_hash) if validator_hash else None,
    )
    return {
        "ok": bool(check.get("ok")),
        "category": category,
        "framework": framework,
        "lane": lane,
        "prompt_contract_hash": prompt_hash,
        "expected_response_hash": expected_hash,
        "validator_hash": validator_hash,
        "latest_approval": latest,
        "check": check,
        "terminal_status": "APPROVED" if check.get("ok") else "BLOCKED_BY_APPROVAL_REGISTRY",
        "mocked": False,
        "live": True,
    }


def run_qra_repair_primitive(
    *,
    issue: Mapping[str, Any],
    run_dir: Path,
    memory_root: Path,
    apply: bool,
) -> dict[str, Any]:
    category, _framework = prompt_approval_category(issue)
    output = run_dir / "qbert_qra_repair_receipt.json"
    artifact_root = run_dir / "qbert_qra_repair"
    slice_ = issue.get("slice") if isinstance(issue.get("slice"), Mapping) else {}
    scope = str(issue_value(issue, "scope", slice_.get("scope") or "") or "").strip().lower()
    raw_limit = issue_value(issue, "limit", None)
    full_category = scope == "all" or raw_limit in (None, "", "all", "ALL", 0, "0")
    cmd = [
        sys.executable,
        str(memory_root / "scripts" / "validation" / "qbert_qra_repair.py"),
        "repair",
        "--category",
        category,
        "--artifact-root",
        str(artifact_root),
        "--output",
        str(output),
    ]
    if full_category:
        cmd.append("--all")
    else:
        cmd.extend(["--limit", str(int(raw_limit or 1))])
    if apply:
        cmd.append("--apply")
    proc = subprocess.run(cmd, cwd=str(memory_root), text=True, capture_output=True, check=False)
    result: dict[str, Any] = {
        "cmd": cmd,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "receipt_path": str(output),
        "artifact_root": str(artifact_root),
    }
    if output.exists():
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
            result.update(payload)
        except Exception as exc:  # noqa: BLE001
            result["parse_error"] = f"{type(exc).__name__}: {exc}"
    result["ok"] = bool(result.get("ok")) and proc.returncode == 0
    return result


def process_issue(issue: Mapping[str, Any], *, run_id: str, run_dir: Path, queue: Path, memory_root: Path, apply: bool = False) -> tuple[int, dict[str, Any]]:
    lane = str(issue.get("lane") or "")
    issue_id = str(issue.get("issue_id") or "")
    summary = source_text_summary(issue)
    manifest_path = source_text_manifest_path(issue)
    write_json(run_dir / "issue.json", issue)
    registry_receipt: dict[str, Any] | None = None

    if lane == "source_text_qra_coverage" and needs_source_fetch(summary):
        next_issue_id = f"monitor-sparta:source-fetch:{issue_id.split(':')[-1]}"
        next_action = {
            "type": "create_queue_issue",
            "owner_subagent": "research-auditor",
            "owner_display_name": "Ryan",
            "lane": "source_fetch",
            "issue_id": next_issue_id,
            "blocked_issue_id": issue_id,
            "success_signal": "source_fetch_ready",
            "scope": "missing_source_text_for_qra_coverage",
            "limit": None,
            "collection": issue.get("collection"),
            "manifest_path": manifest_path,
        }
        registry_receipt = run_registry_decision(
            memory_root=memory_root,
            output=run_dir / "registry_decision.json",
            decision_type="handoff",
            decision="needs_source_fetch",
            status="NEEDS_AGENT",
            issuer_subagent="qra-auditor",
            issuer_display_name="Qbert",
            subject_subagent="qra-auditor",
            subject_display_name="Qbert",
            needed_agent="research-auditor",
            needed_display_name="Ryan",
            lane=lane,
            collection=str(issue.get("collection") or ""),
            issue_id=issue_id,
            summary=(
                f"Qbert cannot prepare QRA repair while source text is missing "
                f"(control_text_missing_or_stub={summary.get('control_text_missing_or_stub')}, "
                f"url_text_missing_or_stub={summary.get('url_text_missing_or_stub')}; "
                f"manifest_path={manifest_path or 'missing'})."
            ),
            rationale="Qbert is QRA generation/quality scoped; Ryan owns source-fetch evidence before QRA repair.",
            decision_reason="source_text_missing_or_stub",
            next_action=next_action,
            run_id=run_id,
        )
        final_status = "OPERATOR_REQUIRED" if not registry_receipt.get("ok") else "BLOCKED_WAITING_ON_RESEARCH"
        tau_handoff = write_tau_handoff_artifacts(
            run_dir,
            filename_stem="qbert_needs_research",
            handoff=build_tau_agent_handoff(
                previous_subagent="qra-auditor",
                next_agent="research-auditor",
                reason="Ryan owns source-fetch evidence before Qbert can prepare QRA repair.",
                result_status="NEEDS_AGENT",
                result_summary=(
                    "Qbert cannot prepare QRA repair while source text is missing "
                    f"(control_text_missing_or_stub={summary.get('control_text_missing_or_stub')}, "
                    f"url_text_missing_or_stub={summary.get('url_text_missing_or_stub')})."
                ),
                context_summary="monitor-sparta queued a QRA source-text coverage issue that requires source evidence first.",
                rationale="QRA generation must not run against missing or stub source text.",
                stop_condition="Ryan writes source-fetch evidence or a blocked registry decision for this issue.",
                issue_id=issue_id,
                evidence=[str(run_dir / "issue.json"), str(run_dir / "registry_decision.json")],
                artifacts=[manifest_path] if manifest_path else [str(run_dir / "issue.json")],
                required_evidence=["source text evidence manifest", "memory registry decision row"],
            ),
        )
        queue_update = update_issue(
            queue,
            issue,
            status=final_status,
            run_id=run_id,
            event="qbert_blocked_needs_research",
            fields={
                "registry_decision_key": registry_receipt.get("decision_key"),
                "tau_handoff_path": tau_handoff.get("handoff_path"),
                "tau_validation_path": tau_handoff.get("validation_path"),
                "tau_handoff_ok": tau_handoff.get("ok"),
                "blocked_reason": "source_text_missing_or_stub",
                "next_owner_subagent": "research-auditor",
                "source_text_qra_manifest": manifest_path,
            },
        )
        receipt = {
            "schema": "qra_auditor.issue_worker.receipt.v1",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "queue_path": str(queue),
            "claimed_issue_id": issue_id,
            "lane": lane,
            "terminal_status": final_status,
            "tau_handoff": tau_handoff,
            "registry_decision": registry_receipt,
            "queue_update": queue_update,
            "summary": dict(summary),
            "source_text_qra_manifest": manifest_path,
            "mocked": False,
            "live": True,
            "forbidden_paths": {
                "repair_cycle_invoked": False,
                "health_fix_invoked": False,
                "database_mutation": False,
            },
        }
        write_json(run_dir / "receipt.json", receipt)
        return (0 if registry_receipt.get("ok") else 12), receipt

    if lane == "qra_coverage_per_control" and bool(issue.get("requires_prompt_reviewer")):
        prompt_approval = resolve_prompt_approval(issue, run_dir=run_dir, memory_root=memory_root)
        if prompt_approval.get("ok"):
            primitive = run_qra_repair_primitive(
                issue=issue,
                run_dir=run_dir,
                memory_root=memory_root,
                apply=apply,
            )
            latest_doc = {}
            latest = prompt_approval.get("latest_approval")
            if isinstance(latest, Mapping) and isinstance(latest.get("latest"), Mapping):
                latest_doc = dict(latest["latest"])
            if not latest_doc:
                check = prompt_approval.get("check") if isinstance(prompt_approval.get("check"), Mapping) else {}
                usable = check.get("usable") if isinstance(check.get("usable"), list) else []
                if usable and isinstance(usable[0], Mapping):
                    latest_doc = dict(usable[0])
            primitive_ok = bool(primitive.get("ok"))
            primitive_status = str(primitive.get("terminal_status") or "")
            partial_mutation_retryable = (
                primitive_status == "CREATE_QRAS_PARTIAL_MUTATION_REQUIRES_RECONCILIATION"
                and bool(primitive.get("mutation_applied"))
                and int(primitive.get("after_count") or 0) > 0
            )
            no_remaining_qra_gap = (
                primitive_status == "NO_APPROVED_CATEGORY_QRA_JOB"
                and not primitive.get("next_required_category")
                and int(primitive.get("before_count") or 0) == 0
            )
            next_required_category = primitive.get("next_required_category")
            next_required_framework = framework_for_qra_category(
                next_required_category,
                fallback=prompt_approval.get("framework"),
            )
            terminal_status = (
                "DONE"
                if (apply and primitive_ok and primitive_status == "DONE") or no_remaining_qra_gap
                else "READY_RETRY"
                if primitive_ok and primitive_status == "CANDIDATE_REJECTIONS_RECORDED"
                else "READY_RETRY"
                if partial_mutation_retryable
                else ("DRY_RUN_READY" if primitive_ok and primitive_status == "DRY_RUN_READY" else "BLOCKED_WAITING_ON_PROMPT_HEALTH")
                if primitive_status == "NO_APPROVED_CATEGORY_QRA_JOB" and next_required_category
                else ("DRY_RUN_READY" if primitive_ok and primitive_status == "DRY_RUN_READY" else "BLOCKED_QRA_PRIMITIVE")
            )
            decision = (
                "bounded_qra_canary_applied"
                if terminal_status == "DONE"
                and not no_remaining_qra_gap
                else "qra_gap_already_covered"
                if no_remaining_qra_gap
                else (
                    "qra_partial_mutation_retry_remaining"
                    if partial_mutation_retryable
                    else "qra_candidate_rejected_retry_next"
                    if terminal_status == "READY_RETRY"
                    else (
                    "bounded_qra_dry_run_ready"
                    if terminal_status == "DRY_RUN_READY"
                    else (
                        "needs_prompt_health_for_next_qra_category"
                        if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                        else "bounded_qra_primitive_blocked"
                    )
                    )
                )
            )
            decision_status = (
                "DONE"
                if terminal_status == "DONE"
                else (
                    "SKIPPED"
                    if terminal_status == "READY_RETRY"
                    else (
                    "NEEDS_REVIEW"
                    if terminal_status == "DRY_RUN_READY"
                    else ("NEEDS_AGENT" if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH" else "BLOCKED")
                    )
                )
            )
            next_action_type = (
                "create_queue_issue"
                if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                else "review_or_apply_bounded_qra_primitive"
            )
            next_action_owner = (
                "prompt-health-auditor"
                if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                else "qra-auditor"
            )
            next_action_display = "Petey" if next_action_owner == "prompt-health-auditor" else "Qbert"
            next_action_lane = "prompt_health" if next_action_owner == "prompt-health-auditor" else lane
            registry_receipt = run_registry_decision(
                memory_root=memory_root,
                output=run_dir / "registry_decision.json",
                decision_type="qra_generation_gate",
                decision=decision,
                status=decision_status,
                issuer_subagent="qra-auditor",
                issuer_display_name="Qbert",
                subject_subagent="qra-auditor",
                subject_display_name="Qbert",
                lane=lane,
                issue_id=issue_id,
                category=str(prompt_approval.get("category") or ""),
                framework=str(prompt_approval.get("framework") or ""),
                needed_agent="prompt-health-auditor" if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH" else None,
                needed_display_name="Petey" if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH" else None,
                summary=(
                    "Qbert found a usable Petey prompt-health approval and ran the bounded create-qras primitive. "
                    f"Primitive terminal_status={primitive_status}, changed_count={primitive.get('changed_count')}, "
                    f"next_required_category={next_required_category}."
                ),
                rationale="Prompt health was consumed from the memory registry; Qbert then used one memory/create-qras primitive and stopped after one issue.",
                decision_reason=(
                    "bounded_qra_canary_applied"
                    if terminal_status == "DONE" and not no_remaining_qra_gap
                    else "qra_gap_already_covered"
                    if no_remaining_qra_gap
                    else (
                    "bounded_qra_dry_run_requires_apply"
                        if terminal_status == "DRY_RUN_READY"
                        else (
                            "partial_qra_mutation_retry_remaining"
                            if partial_mutation_retryable
                            else "deterministic_qra_candidate_rejection_recorded"
                            if terminal_status == "READY_RETRY"
                            else (
                            "prompt_health_required_for_next_qra_category"
                            if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                            else "bounded_qra_primitive_failed_or_blocked"
                            )
                        )
                    )
                ),
                next_action={
                    "type": next_action_type,
                    "owner_subagent": next_action_owner,
                    "owner_display_name": next_action_display,
                    "lane": next_action_lane,
                    "issue_id": (
                        f"monitor-sparta:prompt-health:qra-category:{str(next_required_category).replace('_', '-')}"
                        if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                        else issue_id
                    ),
                    "blocked_issue_id": issue_id if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH" else None,
                    "category": next_required_category or prompt_approval.get("category"),
                    "framework": next_required_framework,
                    "prompt_contract_hash": prompt_approval.get("prompt_contract_hash"),
                    "expected_response_hash": prompt_approval.get("expected_response_hash"),
                    "validator_hash": prompt_approval.get("validator_hash"),
                    "primitive_receipt": primitive.get("receipt_path"),
                    "success_signal": "bounded_create_qras_receipt_with_before_after_qra_counts",
                },
                run_id=run_id,
                receipt_path=run_dir / "receipt.json",
                artifact_paths={
                    "issue": str(run_dir / "issue.json"),
                    "prompt_approval_latest": str(run_dir / "prompt_approval_latest.json") if (run_dir / "prompt_approval_latest.json").exists() else None,
                    "prompt_approval_check": str(run_dir / "prompt_approval_check.json"),
                    "approval_receipt": latest_doc.get("receipt_path"),
                    "approval_artifacts": latest_doc.get("artifact_paths"),
                    "qbert_qra_repair_receipt": primitive.get("receipt_path"),
                    "qbert_qra_repair_artifact_root": primitive.get("artifact_root"),
                },
            )
            tau_handoff = write_tau_handoff_artifacts(
                run_dir,
                filename_stem="qbert_qra_generation_gate",
                handoff=build_tau_agent_handoff(
                    previous_subagent="qra-auditor",
                    next_agent=next_action_owner,
                    reason=str(
                        "Petey must approve the next QRA category."
                        if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                        else "Qbert owns the next bounded QRA review/apply step."
                    ),
                    result_status=decision_status,
                    result_summary=(
                        "Qbert consumed Petey prompt-health approval and ran one bounded create-qras primitive. "
                        f"Primitive terminal_status={primitive_status}, changed_count={primitive.get('changed_count')}, "
                        f"next_required_category={next_required_category}."
                    ),
                    context_summary="monitor-sparta queued a reviewed QRA generation issue.",
                    rationale="Prompt health was checked from the memory registry before Qbert touched create-qras.",
                    stop_condition=(
                        "Petey writes the next matching prompt-health approval row."
                        if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                        else "Qbert review/apply decision is consumed by the supervisor or human operator."
                    ),
                    issue_id=issue_id,
                    evidence=[
                        str(run_dir / "issue.json"),
                        str(run_dir / "prompt_approval_check.json"),
                        str(run_dir / "registry_decision.json"),
                        str(primitive.get("receipt_path") or ""),
                    ],
                    artifacts=[
                        str(run_dir / "prompt_approval_latest.json") if (run_dir / "prompt_approval_latest.json").exists() else "",
                        str(primitive.get("artifact_root") or ""),
                    ],
                    required_evidence=[
                        "Petey prompt approval registry row",
                        "create-qras review receipt",
                        "create-qras dry-run/apply receipt",
                    ],
                ),
            )
            queue_update = update_issue(
                queue,
                issue,
                status=terminal_status,
                run_id=run_id,
                event="qbert_prompt_approval_consumed_qra_primitive",
                fields={
                    "registry_decision_key": registry_receipt.get("decision_key"),
                    "tau_handoff_path": tau_handoff.get("handoff_path"),
                    "tau_validation_path": tau_handoff.get("validation_path"),
                    "tau_handoff_ok": tau_handoff.get("ok"),
                    "blocked_reason": (
                        None
                        if terminal_status in {"DONE", "DRY_RUN_READY", "READY_RETRY"}
                        else (
                            "prompt_health_required_for_next_qra_category"
                            if terminal_status == "BLOCKED_WAITING_ON_PROMPT_HEALTH"
                            else "bounded_qra_primitive_failed_or_blocked"
                        )
                    ),
                    "prompt_health_approved": True,
                    "prompt_approval_key": latest_doc.get("_key"),
                    "category": prompt_approval.get("category"),
                    "framework": prompt_approval.get("framework"),
                    "prompt_contract_hash": prompt_approval.get("prompt_contract_hash"),
                    "expected_response_hash": prompt_approval.get("expected_response_hash"),
                    "validator_hash": prompt_approval.get("validator_hash"),
                    "next_owner_subagent": next_action_owner,
                    "next_required_category": next_required_category,
                    "next_required_framework": next_required_framework,
                    "qbert_qra_repair_receipt": primitive.get("receipt_path"),
                    "qbert_qra_repair_terminal_status": primitive_status,
                    "qbert_qra_repair_changed_count": primitive.get("changed_count"),
                    "mutation_applied": primitive.get("mutation_applied"),
                },
            )
            receipt = {
                "schema": "qra_auditor.issue_worker.receipt.v1",
                "run_id": run_id,
                "run_dir": str(run_dir),
                "queue_path": str(queue),
                "claimed_issue_id": issue_id,
                "lane": lane,
                "terminal_status": terminal_status,
                "tau_handoff": tau_handoff,
                "prompt_approval": prompt_approval,
                "qra_repair_primitive": primitive,
                "registry_decision": registry_receipt,
                "queue_update": queue_update,
                "mocked": False,
                "live": True,
                "forbidden_paths": {
                    "repair_cycle_invoked": False,
                    "health_fix_invoked": False,
                    "database_mutation": bool(primitive.get("mutation_applied")),
                },
            }
            write_json(run_dir / "receipt.json", receipt)
            if not registry_receipt.get("ok"):
                return 12, receipt
            return (0 if terminal_status in {"DONE", "DRY_RUN_READY", "READY_RETRY", "BLOCKED_WAITING_ON_PROMPT_HEALTH"} else 13), receipt

        next_issue_id = f"monitor-sparta:prompt-health:for-{issue_id.split(':')[-1]}"
        next_action = {
            "type": "create_queue_issue",
            "owner_subagent": "prompt-health-auditor",
            "owner_display_name": "Petey",
            "lane": "prompt_health",
            "issue_id": next_issue_id,
            "blocked_issue_id": issue_id,
            "success_signal": "prompt_health_approved",
            "scope": "qra_generation_prompt_contract",
            "limit": 1,
            "category": prompt_approval.get("category"),
            "framework": prompt_approval.get("framework"),
            "prompt_approval_terminal_status": prompt_approval.get("terminal_status"),
        }
        registry_receipt = run_registry_decision(
            memory_root=memory_root,
            output=run_dir / "registry_decision.json",
            decision_type="handoff",
            decision="needs_prompt_health",
            status="NEEDS_AGENT",
            issuer_subagent="qra-auditor",
            issuer_display_name="Qbert",
            subject_subagent="qra-auditor",
            subject_display_name="Qbert",
            needed_agent="prompt-health-auditor",
            needed_display_name="Petey",
            lane=lane,
            issue_id=issue_id,
            summary="Qbert cannot run QRA generation until Petey approves the prompt contract payload.",
            rationale="Prompt health must precede QRA generation for reviewed create-qras lanes.",
            decision_reason="prompt_health_required_before_qra_generation",
            next_action=next_action,
            run_id=run_id,
        )
        final_status = "OPERATOR_REQUIRED" if not registry_receipt.get("ok") else "BLOCKED_WAITING_ON_PROMPT_HEALTH"
        tau_handoff = write_tau_handoff_artifacts(
            run_dir,
            filename_stem="qbert_needs_petey",
            handoff=build_tau_agent_handoff(
                previous_subagent="qra-auditor",
                next_agent="prompt-health-auditor",
                reason="Petey must approve the exact prompt payload before Qbert runs create-qras.",
                result_status="NEEDS_AGENT",
                result_summary="Qbert cannot run QRA generation until Petey approves the prompt contract payload.",
                context_summary="monitor-sparta queued a QRA issue with requires_prompt_reviewer=true.",
                rationale="Prompt health must precede QRA generation for reviewed create-qras lanes.",
                stop_condition="Petey writes a matching prompt-health approval row or a blocked review receipt.",
                issue_id=issue_id,
                evidence=[str(run_dir / "issue.json"), str(run_dir / "prompt_approval_check.json"), str(run_dir / "registry_decision.json")],
                artifacts=[str(run_dir / "issue.json")],
                required_evidence=[
                    "review-prompt PASS receipt",
                    "prompt_contract_hash",
                    "expected_response_hash",
                    "validator_hash",
                    "subagent_approval_registry APPROVED row",
                ],
            ),
        )
        queue_update = update_issue(
            queue,
            issue,
            status=final_status,
            run_id=run_id,
            event="qbert_blocked_needs_petey",
            fields={
                "registry_decision_key": registry_receipt.get("decision_key"),
                "tau_handoff_path": tau_handoff.get("handoff_path"),
                "tau_validation_path": tau_handoff.get("validation_path"),
                "tau_handoff_ok": tau_handoff.get("ok"),
                "blocked_reason": "prompt_health_required",
                "next_owner_subagent": "prompt-health-auditor",
            },
        )
        receipt = {
            "schema": "qra_auditor.issue_worker.receipt.v1",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "queue_path": str(queue),
            "claimed_issue_id": issue_id,
            "lane": lane,
            "terminal_status": final_status,
            "tau_handoff": tau_handoff,
            "prompt_approval": prompt_approval,
            "registry_decision": registry_receipt,
            "queue_update": queue_update,
            "mocked": False,
            "live": True,
            "forbidden_paths": {
                "repair_cycle_invoked": False,
                "health_fix_invoked": False,
                "database_mutation": False,
            },
        }
        write_json(run_dir / "receipt.json", receipt)
        return (0 if registry_receipt.get("ok") else 12), receipt

    queue_update = update_issue(
        queue,
        issue,
        status="OPERATOR_REQUIRED",
        run_id=run_id,
        event="qbert_blocked_unsupported_lane_state",
        fields={"blocked_reason": "unsupported_qra_issue_state"},
    )
    receipt = {
        "schema": "qra_auditor.issue_worker.receipt.v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "queue_path": str(queue),
        "claimed_issue_id": issue_id,
        "lane": lane,
        "terminal_status": "OPERATOR_REQUIRED",
        "queue_update": queue_update,
        "mocked": False,
        "live": True,
    }
    write_json(run_dir / "receipt.json", receipt)
    return 10, receipt


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    run_id = args.run_id or f"qra-auditor-{int(__import__('time').time())}"
    run_dir = Path(args.run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    claim_statuses = {"READY", "READY_RETRY", "DRY_RUN_READY"} if args.apply else {"READY", "READY_RETRY"}
    issue = claim_one(
        Path(args.queue),
        owner="qra-auditor",
        run_id=run_id,
        allowed_lanes=ALLOWED_LANES,
        claim_statuses=claim_statuses,
        issue_id=args.issue_id,
    )
    if issue is None:
        receipt = {
            "schema": "qra_auditor.issue_worker.receipt.v1",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "queue_path": str(args.queue),
            "requested_issue_id": args.issue_id,
            "terminal_status": "NO_READY_ISSUE",
            "mocked": False,
            "live": True,
            "created_at": utc_now(),
        }
        write_json(run_dir / "receipt.json", receipt)
        return 3, receipt
    return process_issue(
        issue,
        run_id=run_id,
        run_dir=run_dir,
        queue=Path(args.queue),
        memory_root=Path(args.memory_root),
        apply=bool(args.apply),
    )


def reconcile_manual(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    run_id = args.run_id or f"qra-auditor-reconcile-{int(__import__('time').time())}"
    run_dir = Path(args.run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    queue = Path(args.queue)
    primitive_receipt_path = Path(args.primitive_receipt)
    after_count_path = Path(args.after_count_artifact)
    memory_root = Path(args.memory_root)

    errors: list[str] = []
    primitive: dict[str, Any] = {}
    after_scan: dict[str, Any] = {}
    independent_after_count: int | None = None

    if not primitive_receipt_path.exists():
        errors.append(f"primitive_receipt_missing:{primitive_receipt_path}")
    else:
        try:
            primitive = load_json(primitive_receipt_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"primitive_receipt_parse_failed:{type(exc).__name__}:{exc}")

    if not after_count_path.exists():
        errors.append(f"after_count_artifact_missing:{after_count_path}")
    else:
        try:
            independent_after_count, after_scan = load_after_count_artifact(after_count_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"after_count_artifact_parse_failed:{type(exc).__name__}:{exc}")

    if primitive:
        if primitive.get("schema") != "qbert_qra_repair.receipt.v1":
            errors.append(f"unexpected_primitive_schema:{primitive.get('schema')}")
        if primitive.get("terminal_status") != "DONE":
            errors.append(f"primitive_terminal_status_not_done:{primitive.get('terminal_status')}")
        if primitive.get("ok") is not True:
            errors.append(f"primitive_ok_not_true:{primitive.get('ok')}")
        if primitive.get("proof_ok") is not True:
            errors.append(f"primitive_proof_ok_not_true:{primitive.get('proof_ok')}")
        if primitive.get("mutation_applied") is not True:
            errors.append(f"primitive_mutation_applied_not_true:{primitive.get('mutation_applied')}")
        if int(primitive.get("changed_count") or 0) <= 0:
            errors.append(f"primitive_changed_count_not_positive:{primitive.get('changed_count')}")
        if primitive.get("forbidden_paths", {}).get("repair_cycle_invoked"):
            errors.append("primitive_invoked_repair_cycle")
        if primitive.get("forbidden_paths", {}).get("health_fix_invoked"):
            errors.append("primitive_invoked_health_fix")

    primitive_after_count = int(primitive.get("after_count")) if primitive.get("after_count") is not None else None
    if independent_after_count is None:
        errors.append("independent_after_count_missing")
    elif primitive_after_count is not None and independent_after_count != primitive_after_count:
        errors.append(f"after_count_mismatch:primitive={primitive_after_count}:independent={independent_after_count}")

    latest = latest_by_issue(read_jsonl(queue))
    issue = latest.get(str(args.issue_id))
    if not issue:
        errors.append(f"queue_issue_missing:{args.issue_id}")
        issue = {"issue_id": str(args.issue_id), "lane": "qra_coverage_per_control", "owner_subagent": "qra-auditor"}
    else:
        if str(issue.get("owner_subagent") or "") != "qra-auditor":
            errors.append(f"queue_issue_wrong_owner:{issue.get('owner_subagent')}")
        if str(issue.get("lane") or "") != "qra_coverage_per_control":
            errors.append(f"queue_issue_wrong_lane:{issue.get('lane')}")

    category = str(primitive.get("category") or issue_value(issue, "category", ""))
    framework = str(primitive.get("framework") or issue_value(issue, "framework", ""))
    if args.category and category and category != args.category:
        errors.append(f"category_mismatch:primitive={category}:expected={args.category}")
    if args.framework and framework and framework != args.framework:
        errors.append(f"framework_mismatch:primitive={framework}:expected={args.framework}")

    write_json(run_dir / "primitive_receipt_snapshot.json", primitive)
    write_json(run_dir / "independent_after_count_snapshot.json", after_scan)

    if errors:
        receipt = {
            "schema": "qra_auditor.manual_reconciliation.receipt.v1",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "queue_path": str(queue),
            "issue_id": str(args.issue_id),
            "terminal_status": "RECONCILE_REFUSED",
            "errors": errors,
            "primitive_receipt_path": str(primitive_receipt_path),
            "after_count_artifact_path": str(after_count_path),
            "primitive_after_count": primitive_after_count,
            "independent_after_count": independent_after_count,
            "mocked": False,
            "live": True,
        }
        write_json(run_dir / "receipt.json", receipt)
        return 20, receipt

    registry_receipt = run_registry_decision(
        memory_root=memory_root,
        output=run_dir / "registry_decision.json",
        decision_type="qra_generation_gate",
        decision="manual_full_category_qra_repair_reconciled",
        status="DONE",
        issuer_subagent="qra-auditor",
        issuer_display_name="Qbert",
        subject_subagent="qra-auditor",
        subject_display_name="Qbert",
        lane="qra_coverage_per_control",
        issue_id=str(args.issue_id),
        category=category,
        framework=framework,
        summary=(
            "Qbert reconciled a supervised full-category create-qras apply run "
            f"from primitive receipt {primitive_receipt_path}; changed_count={primitive.get('changed_count')}, "
            f"after_count={primitive_after_count}."
        ),
        rationale="The manual supervised run produced terminal Qbert proof and an independent after-count scan, so the queue issue can consume the evidence without rerunning the primitive.",
        decision_reason="manual_full_category_qra_repair_terminal_proof_consumed",
        next_action={
            "type": "continue_monitor_sparta_supervisor",
            "owner_subagent": "monitor-sparta-supervisor",
            "issue_id": str(args.issue_id),
            "success_signal": "queue_issue_done_with_qbert_receipt_and_independent_after_count",
        },
        run_id=run_id,
        receipt_path=run_dir / "receipt.json",
        artifact_paths={
            "primitive_receipt": str(primitive_receipt_path),
            "independent_after_count": str(after_count_path),
            "primitive_snapshot": str(run_dir / "primitive_receipt_snapshot.json"),
            "after_count_snapshot": str(run_dir / "independent_after_count_snapshot.json"),
        },
    )
    queue_update = update_issue(
        queue,
        issue,
        status="DONE",
        run_id=run_id,
        event="qbert_manual_full_category_reconciled",
        fields={
            "manual_reconciliation": True,
            "registry_decision_key": registry_receipt.get("decision_key"),
            "qbert_qra_repair_receipt": str(primitive_receipt_path),
            "independent_after_count_artifact": str(after_count_path),
            "qbert_qra_repair_terminal_status": primitive.get("terminal_status"),
            "qbert_qra_repair_changed_count": primitive.get("changed_count"),
            "qbert_qra_repair_after_count": primitive_after_count,
            "qbert_qra_repair_expected_after_count": primitive.get("expected_after_count"),
            "mutation_applied": primitive.get("mutation_applied"),
            "proof_ok": primitive.get("proof_ok"),
            "category": category,
            "framework": framework,
        },
    )
    receipt = {
        "schema": "qra_auditor.manual_reconciliation.receipt.v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "queue_path": str(queue),
        "issue_id": str(args.issue_id),
        "terminal_status": "DONE",
        "primitive_receipt_path": str(primitive_receipt_path),
        "after_count_artifact_path": str(after_count_path),
        "primitive_after_count": primitive_after_count,
        "independent_after_count": independent_after_count,
        "registry_decision": registry_receipt,
        "queue_update": queue_update,
        "mocked": False,
        "live": True,
        "forbidden_paths": {
            "repair_cycle_invoked": False,
            "health_fix_invoked": False,
        },
    }
    write_json(run_dir / "receipt.json", receipt)
    return (0 if registry_receipt.get("ok") else 21), receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--run-id")
    run_p.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    run_p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    run_p.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    run_p.add_argument("--issue-id", help="Claim this exact monitor-sparta queue issue only.")
    run_p.add_argument("--apply", action="store_true")
    reconcile_p = sub.add_parser("reconcile-manual")
    reconcile_p.add_argument("--run-id")
    reconcile_p.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    reconcile_p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    reconcile_p.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    reconcile_p.add_argument("--issue-id", required=True)
    reconcile_p.add_argument("--primitive-receipt", type=Path, required=True)
    reconcile_p.add_argument("--after-count-artifact", type=Path, required=True)
    reconcile_p.add_argument("--category")
    reconcile_p.add_argument("--framework")
    status_p = sub.add_parser("status-current")
    status_p.add_argument("--current-run-file", type=Path, default=DEFAULT_CURRENT_RUN_FILE)
    status_p.add_argument("--state-file", type=Path, default=DEFAULT_CREATE_QRAS_STATE)
    status_p.add_argument("--supervisor-pause-file", type=Path, default=DEFAULT_SUPERVISOR_PAUSE_FILE)
    status_p.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        rc, receipt = run(args)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return rc
    if args.cmd == "reconcile-manual":
        rc, receipt = reconcile_manual(args)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return rc
    if args.cmd == "status-current":
        rc, receipt = status_current(args)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return rc
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
