#!/usr/bin/env python3
"""phase_status - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any


SCHEMA = "plan_iterate.phase_status.v1"
ALLOWED_STATES = {
    "planned",
    "implementing",
    "local_validation_failed",
    "ready_for_review",
    "external_review_blocked",
    "external_review_passed",
    "accepted",
    "superseded",
    "abandoned",
}
ALLOWED_REVIEW_STATUSES = {
    "pending",
    "passed",
    "conditional_pass",
    "needs_changes",
    "blocked",
    "not_required",
}
ALLOWED_ADJUDICATOR_KINDS = {
    "webgpt",
    "scillm",
    "human",
    "deterministic_verifier",
}
ALLOWED_REVIEW_AGREEMENTS = {
    "pending",
    "agree",
    "partial",
    "disagree",
    "insufficient",
}


def default_status(phase_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "phase_id": phase_id,
        "status": "planned",
        "implementation_summary": "",
        "acceptance_contract": [],
        "changed_files": [],
        "validation_commands": [],
        "evidence_artifacts": [],
        "progress_context_artifacts": [],
        "skill_context_artifacts": [],
        "review_artifacts": [],
        "known_caveats": [],
        "claims": [],
        "blockers": [],
        "memory_context": {
            "collection": "plan_iterate_phase_context",
            "keys": [],
        },
        "reviewer_policy": {
            "required": True,
            "comparison_required": False,
            "closure_rule": "deterministic_validation_and_external_review",
        },
        "review_results": [],
        "review_comparison": {
            "agreement": "pending",
            "closure_allowed": False,
            "reason": "",
        },
        "review_status": "pending",
    }


def load_status(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def save_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(status, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_list(status: dict[str, Any], key: str, errors: list[str]) -> list[Any]:
    value = status.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} must be a list")
        return []
    return value


def _artifact_set(status: dict[str, Any]) -> set[str]:
    artifacts = status.get("evidence_artifacts", [])
    if not isinstance(artifacts, list):
        return set()
    names: set[str] = set()
    for artifact in artifacts:
        if isinstance(artifact, str):
            names.add(artifact)
        elif isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
            names.add(artifact["path"])
    return names


def _path_set(status: dict[str, Any], key: str) -> set[str]:
    values = status.get(key, [])
    if not isinstance(values, list):
        return set()
    names: set[str] = set()
    for value in values:
        if isinstance(value, str):
            names.add(value)
        elif isinstance(value, dict) and isinstance(value.get("path"), str):
            names.add(value["path"])
    return names


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_phase_subject_sha256(status: dict[str, Any]) -> str:
    validation_commands = []
    for command in status.get("validation_commands", []):
        if isinstance(command, dict):
            normalized = dict(command)
            normalized.pop("phase_subject_sha256", None)
            validation_commands.append(normalized)
        else:
            validation_commands.append(command)
    subject = {
        "acceptance_contract": status.get("acceptance_contract", []),
        "changed_files": status.get("changed_files", []),
        "claims": status.get("claims", []),
        "evidence_artifacts": status.get("evidence_artifacts", []),
        "progress_context_artifacts": status.get("progress_context_artifacts", []),
        "skill_context_artifacts": status.get("skill_context_artifacts", []),
        "validation_commands": validation_commands,
        "known_caveats": status.get("known_caveats", []),
        "blockers": status.get("blockers", []),
        "reviewer_policy": status.get("reviewer_policy", {}),
        "memory_context": status.get("memory_context", {}),
    }
    encoded = json.dumps(subject, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_progress_context_sha256(status: dict[str, Any], phase_dir: Path | None = None) -> str | None:
    artifacts = status.get("progress_context_artifacts", [])
    memory_context = status.get("memory_context", {})
    has_memory_refs = isinstance(memory_context, dict) and bool(memory_context.get("keys"))
    if not isinstance(artifacts, list) or (not artifacts and not has_memory_refs):
        return None

    normalized_artifacts: list[dict[str, Any]] = []
    for artifact in artifacts:
        path_value = _artifact_path_value(artifact)
        if not isinstance(path_value, str):
            normalized_artifacts.append({"path": artifact, "sha256": None})
            continue
        artifact_hash = None
        if isinstance(artifact, dict) and isinstance(artifact.get("sha256"), str):
            artifact_hash = artifact["sha256"]
        elif phase_dir is not None:
            candidate = phase_dir / path_value
            if candidate.exists() and candidate.is_file():
                artifact_hash = _sha256_file(candidate)
        normalized_artifacts.append({"path": path_value, "sha256": artifact_hash})

    subject = {
        "progress_context_artifacts": normalized_artifacts,
        "memory_context": memory_context if isinstance(memory_context, dict) else {},
    }
    encoded = json.dumps(subject, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_skill_context_sha256(status: dict[str, Any], phase_dir: Path | None = None) -> str | None:
    artifacts = status.get("skill_context_artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        return None

    normalized_artifacts: list[dict[str, Any]] = []
    for artifact in artifacts:
        path_value = _artifact_path_value(artifact)
        if not isinstance(path_value, str):
            normalized_artifacts.append({"path": artifact, "sha256": None})
            continue
        artifact_hash = None
        if isinstance(artifact, dict) and isinstance(artifact.get("sha256"), str):
            artifact_hash = artifact["sha256"]
        elif phase_dir is not None:
            candidate = phase_dir / path_value
            if candidate.exists() and candidate.is_file():
                artifact_hash = _sha256_file(candidate)
        normalized_artifacts.append({"path": path_value, "sha256": artifact_hash})

    encoded = json.dumps(
        {"skill_context_artifacts": normalized_artifacts},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_path_value(artifact: Any) -> str | None:
    if isinstance(artifact, str):
        return artifact
    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
        return artifact["path"]
    return None


def _artifact_hash_value(status: dict[str, Any], artifact_path: str) -> str | None:
    for artifact in status.get("evidence_artifacts", []):
        if isinstance(artifact, dict) and artifact.get("path") == artifact_path and isinstance(artifact.get("sha256"), str):
            return artifact["sha256"]
    return None


def _check_relative_artifact_hash(
    phase_dir: Path | None,
    artifact_path: str,
    expected_hash: str,
    errors: list[str],
    label: str,
) -> None:
    if phase_dir is None:
        return
    candidate = phase_dir / artifact_path
    if candidate.exists() and _sha256_file(candidate) != expected_hash:
        errors.append(f"{label} does not match current artifact bytes")


def _validate_phase_relative_path(path_value: str, label: str, errors: list[str]) -> bool:
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{label} must be phase-relative and must not contain '..'")
        return False
    return True


def _default_repo_root(phase_dir: Path | None) -> Path | None:
    if phase_dir is None:
        return None
    if phase_dir.parent.name == ".plan-iterate":
        return phase_dir.parent.parent
    return phase_dir.parent


def _validate_invocation_receipt(phase_dir: Path | None, result: dict[str, Any], index: int, errors: list[str]) -> None:
    if phase_dir is None:
        return
    invocation = result.get("invocation")
    if not isinstance(invocation, dict) or not _is_nonempty_string(invocation.get("receipt_artifact")):
        return
    receipt_path = phase_dir / str(invocation["receipt_artifact"])
    if not receipt_path.exists():
        return
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append(f"review_results[{index}].invocation.receipt_artifact must be JSON")
        return
    if not isinstance(receipt, dict):
        errors.append(f"review_results[{index}].invocation.receipt_artifact must contain a JSON object")
        return
    if receipt.get("status") not in {"completed", "success", "ok"}:
        errors.append(f"review_results[{index}].invocation.receipt_artifact status must indicate completion")
    if receipt.get("failure"):
        errors.append(f"review_results[{index}].invocation.receipt_artifact must not contain failure")
    expected_bindings = {
        "request_sha256": result.get("review_request_sha256"),
        "response_sha256": result.get("artifact_sha256"),
        "review_bundle_sha256": result.get("review_bundle_sha256"),
        "phase_subject_sha256": result.get("phase_subject_sha256"),
        "reviewer_id": result.get("reviewer_id"),
        "adjudicator_kind": result.get("adjudicator_kind"),
    }
    if _is_nonempty_string(result.get("progress_context_sha256")):
        expected_bindings["progress_context_sha256"] = result.get("progress_context_sha256")
    if _is_nonempty_string(result.get("skill_context_sha256")):
        expected_bindings["skill_context_sha256"] = result.get("skill_context_sha256")
    for key, expected_value in expected_bindings.items():
        if not _is_nonempty_string(expected_value) or receipt.get(key) != expected_value:
            errors.append(f"review_results[{index}].invocation.receipt_artifact {key} must match review_results[{index}]")
    adjudicator_kind = result.get("adjudicator_kind")
    if adjudicator_kind == "webgpt":
        if receipt.get("raw_contains_sentinel") is not True:
            errors.append(f"review_results[{index}].webgpt receipt must include raw_contains_sentinel=true")
        if receipt.get("clean_contains_sentinel") is not False:
            errors.append(f"review_results[{index}].webgpt receipt must include clean_contains_sentinel=false")
        if not _is_nonempty_string(receipt.get("sentinel")):
            errors.append(f"review_results[{index}].webgpt receipt must include sentinel")
        if not _is_nonempty_string(receipt.get("controlled_tab_id")):
            errors.append(f"review_results[{index}].webgpt receipt must include controlled_tab_id")
        if receipt.get("controlled_tab_id_mismatch") is True:
            errors.append(f"review_results[{index}].webgpt receipt must not have controlled_tab_id_mismatch=true")
        if receipt.get("no_activate") is True and receipt.get("activated") is True:
            errors.append(f"review_results[{index}].webgpt no_activate receipt must have activated=false")
    elif not any(key in receipt for key in ["request_sha256", "response_sha256", "output", "run_id", "id"]):
        errors.append(f"review_results[{index}].invocation.receipt_artifact lacks replay identifier or output field")


def validate_status(status: dict[str, Any], phase_dir: Path | None = None, repo_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    source_root = repo_root or _default_repo_root(phase_dir)

    if status.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if not _is_nonempty_string(status.get("phase_id")):
        errors.append("phase_id must be a non-empty string")

    state = status.get("status")
    if state not in ALLOWED_STATES:
        errors.append(f"status must be one of {sorted(ALLOWED_STATES)}")

    review_status = status.get("review_status")
    if review_status not in ALLOWED_REVIEW_STATUSES:
        errors.append(f"review_status must be one of {sorted(ALLOWED_REVIEW_STATUSES)}")

    acceptance_contract = _require_list(status, "acceptance_contract", errors)
    changed_files = _require_list(status, "changed_files", errors)
    validation_commands = _require_list(status, "validation_commands", errors)
    evidence_artifacts = _require_list(status, "evidence_artifacts", errors)
    progress_context_artifacts = _require_list(status, "progress_context_artifacts", errors)
    skill_context_artifacts = _require_list(status, "skill_context_artifacts", errors)
    review_artifacts = _require_list(status, "review_artifacts", errors)
    known_caveats = _require_list(status, "known_caveats", errors)
    claims = _require_list(status, "claims", errors)
    blockers = _require_list(status, "blockers", errors)
    review_results = _require_list(status, "review_results", errors)

    artifact_names = _artifact_set(status)
    review_artifact_names = _path_set(status, "review_artifacts")

    reviewer_policy = status.get("reviewer_policy")
    if not isinstance(reviewer_policy, dict):
        errors.append("reviewer_policy must be an object")
        reviewer_policy = {}
    review_required = reviewer_policy.get("required", True)
    comparison_required = reviewer_policy.get("comparison_required", False)
    if not isinstance(review_required, bool):
        errors.append("reviewer_policy.required must be a boolean")
        review_required = True
    if not isinstance(comparison_required, bool):
        errors.append("reviewer_policy.comparison_required must be a boolean")
        comparison_required = False
    if not _is_nonempty_string(reviewer_policy.get("closure_rule")):
        errors.append("reviewer_policy.closure_rule must be non-empty")

    review_comparison = status.get("review_comparison")
    if not isinstance(review_comparison, dict):
        errors.append("review_comparison must be an object")
        review_comparison = {}
    agreement = review_comparison.get("agreement")
    if agreement not in ALLOWED_REVIEW_AGREEMENTS:
        errors.append(f"review_comparison.agreement must be one of {sorted(ALLOWED_REVIEW_AGREEMENTS)}")
    if not isinstance(review_comparison.get("closure_allowed"), bool):
        errors.append("review_comparison.closure_allowed must be a boolean")
    elif review_comparison.get("closure_allowed") is True and agreement != "agree":
        errors.append("review_comparison.closure_allowed=true requires agreement=agree")

    memory_context = status.get("memory_context", {})
    if not isinstance(memory_context, dict):
        errors.append("memory_context must be an object")
        memory_context = {}
    if memory_context:
        collection = memory_context.get("collection", "plan_iterate_phase_context")
        keys = memory_context.get("keys", [])
        if not _is_nonempty_string(collection):
            errors.append("memory_context.collection must be non-empty")
        if not isinstance(keys, list):
            errors.append("memory_context.keys must be a list")
        else:
            for index, key in enumerate(keys):
                if not _is_nonempty_string(key):
                    errors.append(f"memory_context.keys[{index}] must be non-empty")

    for index, command in enumerate(validation_commands):
        if not isinstance(command, dict):
            errors.append(f"validation_commands[{index}] must be an object")
            continue
        if not _is_nonempty_string(command.get("command")):
            errors.append(f"validation_commands[{index}].command must be non-empty")
        if "exit_code" not in command or not isinstance(command.get("exit_code"), int):
            errors.append(f"validation_commands[{index}].exit_code must be an integer")
        if state == "accepted":
            log = command.get("log")
            if not _is_nonempty_string(log):
                errors.append(f"validation_commands[{index}].log must be non-empty when status is accepted")
            elif log not in artifact_names:
                errors.append(f"validation_commands[{index}].log must be listed in evidence_artifacts when status is accepted")
            elif _artifact_hash_value(status, str(log)) is None:
                errors.append(f"validation_commands[{index}].log evidence_artifact must include sha256 when status is accepted")
            if not _is_nonempty_string(command.get("log_sha256")):
                errors.append(f"validation_commands[{index}].log_sha256 must be non-empty when status is accepted")
            elif phase_dir is not None and _is_nonempty_string(log):
                log_path = phase_dir / str(log)
                if log_path.exists() and _sha256_file(log_path) != command["log_sha256"]:
                    errors.append(f"validation_commands[{index}].log_sha256 does not match current log bytes")
            if not _is_nonempty_string(command.get("phase_subject_sha256")):
                errors.append(f"validation_commands[{index}].phase_subject_sha256 must be non-empty when status is accepted")
            elif command.get("phase_subject_sha256") != compute_phase_subject_sha256(status):
                errors.append(f"validation_commands[{index}].phase_subject_sha256 does not match current phase subject")

    for index, changed_file in enumerate(changed_files):
        path_value = changed_file["path"] if isinstance(changed_file, dict) else changed_file
        if not isinstance(path_value, str) or not path_value.strip():
            errors.append(f"changed_files[{index}] must be a path string or object with path")
        elif not _validate_phase_relative_path(path_value, f"changed_files[{index}]", errors):
            continue
        elif state in {"external_review_passed", "accepted"}:
            if not isinstance(changed_file, dict) or not _is_nonempty_string(changed_file.get("sha256")):
                errors.append(f"changed_files[{index}].sha256 must be non-empty for {state}")
            elif source_root is not None:
                source_path = source_root / path_value
                if source_path is None:
                    errors.append(f"changed_files[{index}] path missing for {state}: {path_value}")
                elif not source_path.exists():
                    errors.append(f"changed_files[{index}] path missing for {state}: {path_value}")
                elif _sha256_file(source_path) != changed_file["sha256"]:
                    errors.append(f"changed_files[{index}].sha256 does not match current file bytes")

    for index, item in enumerate(acceptance_contract):
        if not _is_nonempty_string(item):
            errors.append(f"acceptance_contract[{index}] must be a non-empty string")

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] must be an object with claim and evidence_artifacts")
            continue
        if not _is_nonempty_string(claim.get("claim")):
            errors.append(f"claims[{index}].claim must be non-empty")
        claim_artifacts = claim.get("evidence_artifacts")
        if not isinstance(claim_artifacts, list) or not claim_artifacts:
            errors.append(f"claims[{index}] must cite evidence_artifacts")
            continue
        for artifact in claim_artifacts:
            if not isinstance(artifact, str) or not artifact.strip():
                errors.append(f"claims[{index}].evidence_artifacts entries must be non-empty strings")
                continue
            if artifact not in artifact_names:
                errors.append(f"claims[{index}] cites artifact not listed in evidence_artifacts: {artifact}")
            elif artifact in review_artifact_names:
                errors.append(f"claims[{index}] cites review artifact as implementation evidence: {artifact}")

    for index, result in enumerate(review_results):
        if not isinstance(result, dict):
            errors.append(f"review_results[{index}] must be an object")
            continue
        if not _is_nonempty_string(result.get("reviewer_id")):
            errors.append(f"review_results[{index}].reviewer_id must be non-empty")
        if result.get("adjudicator_kind") not in ALLOWED_ADJUDICATOR_KINDS:
            errors.append(f"review_results[{index}].adjudicator_kind must be one of {sorted(ALLOWED_ADJUDICATOR_KINDS)}")
        if result.get("verdict") not in ALLOWED_REVIEW_STATUSES - {"pending", "not_required"}:
            errors.append(f"review_results[{index}].verdict must be a concrete review verdict")
        artifact = result.get("artifact")
        if not _is_nonempty_string(artifact):
            errors.append(f"review_results[{index}].artifact must be non-empty")
        elif artifact not in review_artifact_names:
            errors.append(f"review_results[{index}] cites artifact not listed in review_artifacts: {artifact}")
        if not _is_nonempty_string(result.get("artifact_sha256")):
            errors.append(f"review_results[{index}].artifact_sha256 must be non-empty")
        elif phase_dir is not None and _is_nonempty_string(artifact):
            _check_relative_artifact_hash(
                phase_dir,
                str(artifact),
                result["artifact_sha256"],
                errors,
                f"review_results[{index}].artifact_sha256",
            )
        if not _is_nonempty_string(result.get("recorded_at")):
            errors.append(f"review_results[{index}].recorded_at must be non-empty")
        if not _is_nonempty_string(result.get("review_request_sha256")):
            errors.append(f"review_results[{index}].review_request_sha256 must be non-empty")
        if not _is_nonempty_string(result.get("review_bundle_sha256")):
            errors.append(f"review_results[{index}].review_bundle_sha256 must be non-empty")
        if review_required and not _is_nonempty_string(result.get("skill_context_sha256")):
            errors.append(f"review_results[{index}].skill_context_sha256 must be non-empty")
        elif _is_nonempty_string(result.get("skill_context_sha256")):
            skill_context_sha256 = compute_skill_context_sha256(status, phase_dir)
            if skill_context_sha256 is not None and result.get("skill_context_sha256") != skill_context_sha256:
                errors.append(f"review_results[{index}].skill_context_sha256 does not match current skill context")
        if not _is_nonempty_string(result.get("phase_subject_sha256")):
            errors.append(f"review_results[{index}].phase_subject_sha256 must be non-empty")
        elif state in {"external_review_passed", "accepted"} and result.get("phase_subject_sha256") != compute_phase_subject_sha256(status):
            errors.append(f"review_results[{index}].phase_subject_sha256 does not match current phase subject")
        for key in ["review_request_artifact", "review_bundle_artifact"]:
            value = result.get(key)
            if not _is_nonempty_string(value):
                errors.append(f"review_results[{index}].{key} must be non-empty")
            elif value not in review_artifact_names:
                errors.append(f"review_results[{index}].{key} must be listed in review_artifacts")
            else:
                hash_key = "review_request_sha256" if key == "review_request_artifact" else "review_bundle_sha256"
                expected_hash = result.get(hash_key)
                if _is_nonempty_string(expected_hash):
                    _check_relative_artifact_hash(
                        phase_dir,
                        str(value),
                        str(expected_hash),
                        errors,
                        f"review_results[{index}].{hash_key}",
                    )
        invocation = result.get("invocation")
        if not isinstance(invocation, dict):
            errors.append(f"review_results[{index}].invocation must be an object")
        else:
            if not _is_nonempty_string(invocation.get("tool")):
                errors.append(f"review_results[{index}].invocation.tool must be non-empty")
            if not _is_nonempty_string(invocation.get("command_or_run_id")):
                errors.append(f"review_results[{index}].invocation.command_or_run_id must be non-empty")
            receipt_artifact = invocation.get("receipt_artifact")
            if not _is_nonempty_string(receipt_artifact):
                errors.append(f"review_results[{index}].invocation.receipt_artifact must be non-empty")
            elif receipt_artifact not in review_artifact_names:
                errors.append(f"review_results[{index}].invocation.receipt_artifact must be listed in review_artifacts")
            if not _is_nonempty_string(invocation.get("receipt_sha256")):
                errors.append(f"review_results[{index}].invocation.receipt_sha256 must be non-empty")
            elif _is_nonempty_string(receipt_artifact):
                _check_relative_artifact_hash(
                    phase_dir,
                    str(receipt_artifact),
                    str(invocation["receipt_sha256"]),
                    errors,
                    f"review_results[{index}].invocation.receipt_sha256",
                )
            _validate_invocation_receipt(phase_dir, result, index, errors)

    for index, blocker in enumerate(blockers):
        if not isinstance(blocker, dict):
            errors.append(f"blockers[{index}] must be an object")
            continue
        occurrences = blocker.get("occurrences", 1)
        if not isinstance(occurrences, int) or occurrences < 1:
            errors.append(f"blockers[{index}].occurrences must be a positive integer")
        if isinstance(occurrences, int) and occurrences >= 2 and blocker.get("escalated") is not True:
            errors.append(f"blockers[{index}] repeated twice without escalated=true")

    if phase_dir is not None:
        for index, artifact in enumerate(evidence_artifacts):
            path_value = _artifact_path_value(artifact)
            if not isinstance(path_value, str) or not path_value.strip():
                errors.append(f"evidence_artifacts[{index}] must be a path string or object with path")
                continue
            if not _validate_phase_relative_path(path_value, f"evidence_artifacts[{index}]", errors):
                continue
            artifact_path = Path(path_value)
            candidate = artifact_path if artifact_path.is_absolute() else phase_dir / artifact_path
            if not candidate.exists():
                errors.append(f"evidence artifact missing: {path_value}")
            if state == "accepted":
                if not isinstance(artifact, dict) or not _is_nonempty_string(artifact.get("sha256")):
                    errors.append(f"evidence_artifacts[{index}].sha256 must be non-empty when status is accepted")
                elif candidate.exists() and _sha256_file(candidate) != artifact["sha256"]:
                    errors.append(f"evidence_artifacts[{index}].sha256 does not match current artifact bytes")
        for index, artifact in enumerate(progress_context_artifacts):
            path_value = _artifact_path_value(artifact)
            if not isinstance(path_value, str) or not path_value.strip():
                errors.append(f"progress_context_artifacts[{index}] must be a path string or object with path")
                continue
            if not _validate_phase_relative_path(path_value, f"progress_context_artifacts[{index}]", errors):
                continue
            candidate = phase_dir / path_value
            if not candidate.exists():
                errors.append(f"progress context artifact missing: {path_value}")
            if isinstance(artifact, dict) and _is_nonempty_string(artifact.get("sha256")) and candidate.exists():
                if _sha256_file(candidate) != artifact["sha256"]:
                    errors.append(f"progress_context_artifacts[{index}].sha256 does not match current artifact bytes")
        for index, artifact in enumerate(skill_context_artifacts):
            path_value = _artifact_path_value(artifact)
            if not isinstance(path_value, str) or not path_value.strip():
                errors.append(f"skill_context_artifacts[{index}] must be a path string or object with path")
                continue
            if not _validate_phase_relative_path(path_value, f"skill_context_artifacts[{index}]", errors):
                continue
            candidate = phase_dir / path_value
            if not candidate.exists():
                errors.append(f"skill context artifact missing: {path_value}")
            if isinstance(artifact, dict) and _is_nonempty_string(artifact.get("sha256")) and candidate.exists():
                if _sha256_file(candidate) != artifact["sha256"]:
                    errors.append(f"skill_context_artifacts[{index}].sha256 does not match current artifact bytes")
        for index, artifact in enumerate(review_artifacts):
            path_value = _artifact_path_value(artifact)
            if not isinstance(path_value, str) or not path_value.strip():
                errors.append(f"review_artifacts[{index}] must be a path string or object with path")
                continue
            if not _validate_phase_relative_path(path_value, f"review_artifacts[{index}]", errors):
                continue
            artifact_path = Path(path_value)
            candidate = artifact_path if artifact_path.is_absolute() else phase_dir / artifact_path
            if not candidate.exists():
                errors.append(f"review artifact missing: {path_value}")

    if state in {"ready_for_review", "external_review_passed", "accepted"}:
        if not acceptance_contract:
            errors.append(f"{state} requires acceptance_contract")
        if not changed_files:
            errors.append(f"{state} requires changed_files")
        if not evidence_artifacts:
            errors.append(f"{state} requires evidence_artifacts")
        if review_required and not skill_context_artifacts:
            errors.append(f"{state} requires skill_context_artifacts when reviewer_policy.required=true")

    if state == "local_validation_failed":
        has_failure = any(isinstance(command, dict) and command.get("exit_code", 0) != 0 for command in validation_commands)
        if not has_failure:
            errors.append("local_validation_failed requires at least one non-zero validation exit_code")

    if state == "external_review_blocked" and review_status not in {"needs_changes", "blocked", "conditional_pass"}:
        errors.append("external_review_blocked requires review_status needs_changes, blocked, or conditional_pass")

    if state == "external_review_passed" and review_required and review_status != "passed":
        errors.append("external_review_passed requires review_status=passed")

    if review_status == "not_required" and review_required:
        errors.append("review_status not_required requires reviewer_policy.required=false")

    if state in {"external_review_passed", "accepted"} and review_required:
        if not review_results:
            errors.append(f"{state} requires at least one review_results entry")
        passing_reviews = [
            result
            for result in review_results
            if isinstance(result, dict) and result.get("verdict") == "passed"
        ]
        if not passing_reviews:
            errors.append(f"{state} requires at least one passing review result")

    if len(review_results) > 1:
        if not progress_context_artifacts and not (isinstance(memory_context, dict) and memory_context.get("keys")):
            errors.append("multiple review_results require progress_context_artifacts or memory_context.keys")
        progress_context_sha256 = compute_progress_context_sha256(status, phase_dir)
        for index, result in enumerate(review_results):
            if isinstance(result, dict) and index > 0:
                if not _is_nonempty_string(result.get("progress_context_sha256")):
                    errors.append(f"review_results[{index}].progress_context_sha256 must be non-empty for non-first reviews")
                elif progress_context_sha256 is not None and result.get("progress_context_sha256") != progress_context_sha256:
                    errors.append(f"review_results[{index}].progress_context_sha256 does not match current progress context")

    if state == "accepted":
        if review_status not in {"passed", "not_required"}:
            errors.append("accepted requires review_status passed or not_required")
        if review_required and review_comparison.get("closure_allowed") is not True:
            errors.append("accepted requires review_comparison.closure_allowed=true")
        blocking_reviews = [
            result
            for result in review_results
            if isinstance(result, dict) and result.get("verdict") in {"blocked", "needs_changes", "conditional_pass"}
        ]
        if blocking_reviews:
            errors.append("accepted requires no blocked, needs_changes, or conditional_pass review_results")
        failing = [command for command in validation_commands if isinstance(command, dict) and command.get("exit_code") != 0]
        if failing:
            errors.append("accepted requires all validation_commands exit_code values to be 0")
        if not validation_commands:
            errors.append("accepted requires at least one validation command")
        if not claims:
            errors.append("accepted requires at least one claim")
        contract_items = {item for item in acceptance_contract if isinstance(item, str)}
        covered_items: set[str] = set()
        for claim in claims:
            if isinstance(claim, dict) and isinstance(claim.get("acceptance_contract"), list):
                covered_items.update(item for item in claim["acceptance_contract"] if isinstance(item, str))
        missing_contract_items = sorted(contract_items - covered_items)
        if missing_contract_items:
            errors.append(f"accepted claims must cover acceptance_contract items: {missing_contract_items}")

    if state == "accepted" and review_status in {"needs_changes", "blocked"}:
        errors.append("review says blocked but phase is marked accepted")

    if state in {"external_review_passed", "accepted"} and comparison_required:
        reviewer_ids = {
            result.get("reviewer_id")
            for result in review_results
            if isinstance(result, dict) and _is_nonempty_string(result.get("reviewer_id"))
        }
        if len(reviewer_ids) < 2:
            errors.append(f"{state} requires distinct reviewer_id values when comparison_required=true")
        non_passing_reviews = [
            result
            for result in review_results
            if isinstance(result, dict) and result.get("verdict") != "passed"
        ]
        if non_passing_reviews:
            errors.append(f"{state} requires all review_results verdict values to be passed when comparison_required=true")
        if agreement != "agree":
            errors.append(f"{state} requires review_comparison.agreement=agree when comparison_required=true")
        passing_bundle_hashes = {
            result.get("review_bundle_sha256")
            for result in review_results
            if isinstance(result, dict) and result.get("verdict") == "passed"
        }
        if len(passing_bundle_hashes) != 1:
            errors.append(f"{state} requires all passing comparison reviews to reference the same review_bundle_sha256")

    if state == "external_review_passed":
        blocking_reviews = [
            result
            for result in review_results
            if isinstance(result, dict) and result.get("verdict") in {"blocked", "needs_changes", "conditional_pass"}
        ]
        if blocking_reviews:
            errors.append("external_review_passed requires no blocked, needs_changes, or conditional_pass review_results")

    if state == "accepted":
        for index, caveat in enumerate(known_caveats):
            if isinstance(caveat, dict):
                if not (caveat.get("accepted") is True or _is_nonempty_string(caveat.get("impact"))):
                    errors.append(f"known_caveats[{index}] must include accepted=true or impact when status is accepted")
            elif not _is_nonempty_string(caveat):
                errors.append(f"known_caveats[{index}] must be a non-empty string or object")

    return errors


def status_path(root: Path, phase_id: str) -> Path:
    return root / phase_id / "PHASE_STATUS.json"
