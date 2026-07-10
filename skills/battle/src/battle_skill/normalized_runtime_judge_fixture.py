"""Normalize runtime and Judge boundary receipts for UX consumption."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


NORMALIZED_RUNTIME_JUDGE_SCHEMA = "battle.normalized_runtime_judge_fixture.v1"
FIXTURE_KIND_PR4 = "pr4_runtime_judge"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.normalized_runtime_judge_fixture.v1.schema.json"
PATH_LEAK_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "/home/",
    "/tmp/",
    "/mnt/",
    "/workspace",
    "provider-workspace",
    "pr3c-provider-workspaces",
    "outputs/provider-worker-result.json",
    "inputs/tau-scillm-worker-work-order.json",
    "C:\\",
    "D:\\",
)
PRIVATE_MARKERS = (
    "arena/private/",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
)
MAY_CLAIM = [
    "docker_specimen_execution_attempted",
    "container_image_recorded",
    "container_network_policy_recorded",
    "timeout_recorded",
    "exit_code_recorded",
    "stdout_summary_recorded",
    "stderr_summary_recorded",
    "runtime_failed",
    "runnable_unproven",
    "target_contact_unproven",
    "judge_not_run",
]
MUST_NOT_CLAIM = [
    "exploit_success",
    "target_contact_is_exploit_success",
    "runnable_is_exploit_success",
    "blue_detection",
    "blue_bypass",
    "blue_kill",
    "blue_block",
    "judge_success",
    "packet_level_behavior",
    "memory_promotion",
]


def normalize_runtime_judge_fixture(
    *,
    proof_dir: Path,
    out_dir: Path,
    public_out_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write a normalized runtime/Judge fixture from a combiner-style proof directory."""

    root = _resolve_proof_root(proof_dir)
    run_receipt = _read_json(root / "run-receipt.json")
    scoreboard = _read_json(root / "scoreboard.json")
    specimen_receipts = [_read_json(path) for path in sorted((root / "specimens").glob("*/run-receipt.json"))]
    if not specimen_receipts:
        raise RuntimeError(f"no specimen run receipts found under {root / 'specimens'}")
    for receipt in specimen_receipts:
        _validate_source_run_receipt(receipt)
    fixture = _fixture(
        root=root,
        run_receipt=run_receipt,
        scoreboard=scoreboard,
        specimen_receipts=specimen_receipts,
        generated_at=generated_at,
    )
    report = validate_normalized_runtime_judge_fixture(fixture)
    source_index = _source_index(root=root, run_receipt=run_receipt, scoreboard=scoreboard, specimen_receipts=specimen_receipts)

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / "battle.normalized_runtime_judge_fixture.json"
    validation_path = out_dir / "validation.json"
    source_index_path = out_dir / "source-receipt-index.json"
    _write_json(fixture_path, fixture)
    _write_json(validation_path, report)
    _write_json(source_index_path, source_index)
    if public_out_dir is not None:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        public_fixture = public_out_dir / "battle.normalized_runtime_judge_fixture.json"
        shutil.copyfile(fixture_path, public_fixture)
        if _sha256_file(public_fixture) != _sha256_file(fixture_path):
            raise RuntimeError("public runtime/Judge fixture hash mismatch after copy")
    return fixture


def validate_normalized_runtime_judge_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_runtime_judge_fixture(_read_json(path))


def validate_normalized_runtime_judge_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(fixture, schema)
    errors: list[str] = []
    if fixture.get("schema") != NORMALIZED_RUNTIME_JUDGE_SCHEMA:
        errors.append("schema must be battle.normalized_runtime_judge_fixture.v1")
    if fixture.get("fixture_kind") != FIXTURE_KIND_PR4:
        errors.append("fixture_kind must be pr4_runtime_judge")
    for key, expected in {
        "status": "PASS",
        "mocked": False,
        "live": "local_docker_specimen_fixture",
        "proof_mode": "local_docker_specimen_fixture",
    }.items():
        if fixture.get(key) != expected:
            errors.append(f"{key} must be {expected!r}")
    runtime = fixture.get("runtime") if isinstance(fixture.get("runtime"), dict) else {}
    runs = runtime.get("specimen_runs") if isinstance(runtime.get("specimen_runs"), list) else []
    if not runs:
        errors.append("runtime.specimen_runs is required")
    statuses = {item.get("runtime_status") for item in runs if isinstance(item, dict)}
    if not statuses & {"RUNNABLE_UNPROVEN", "TARGET_CONTACT_UNPROVEN", "RUNTIME_FAILED", "COMPILE_FAILED"}:
        errors.append("at least one concrete runtime status is required")
    judge = fixture.get("judge") if isinstance(fixture.get("judge"), dict) else {}
    if judge.get("judge_status") != "NOT_RUN":
        errors.append("judge.judge_status must be NOT_RUN for this fixture")
    if judge.get("judge_verified_exploits") != 0:
        errors.append("judge.judge_verified_exploits must be 0")
    claims = fixture.get("claim_boundary") if isinstance(fixture.get("claim_boundary"), dict) else {}
    may_claim = set(claims.get("may_claim", []))
    must_not_claim = set(claims.get("must_not_claim", []))
    for item in MAY_CLAIM:
        if item not in may_claim:
            errors.append(f"claim_boundary.may_claim missing {item}")
    for item in MUST_NOT_CLAIM:
        if item not in must_not_claim:
            errors.append(f"claim_boundary.must_not_claim missing {item}")
    if {"exploit_success", "blue_block", "judge_success"} & may_claim:
        errors.append("claim_boundary.may_claim contains forbidden outcome claims")
    serialized = json.dumps(fixture, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            errors.append(f"normalized runtime/Judge fixture exposes forbidden marker: {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            errors.append("normalized runtime/Judge fixture exposes secret-like material")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.normalized_runtime_judge_fixture_validation.v1",
        "status": "PASS",
        "fixture_kind": fixture["fixture_kind"],
        "battle_id": fixture["battle_id"],
        "runtime_run_count": len(runs),
        "runtime_statuses": sorted(statuses),
        "target_contact_unproven_count": sum(1 for item in runs if item.get("target_contact", {}).get("observed") is True),
        "judge_status": judge.get("judge_status"),
        "judge_verified_exploits": judge.get("judge_verified_exploits"),
        "raw_paths_redacted": fixture.get("provenance", {}).get("raw_paths_redacted"),
    }


def _fixture(*, root: Path, run_receipt: dict[str, Any], scoreboard: dict[str, Any], specimen_receipts: list[dict[str, Any]], generated_at: str | None) -> dict[str, Any]:
    runs = [_normalized_run(root=root, receipt=receipt) for receipt in specimen_receipts]
    docker = _docker_summary(specimen_receipts[0])
    return {
        "schema": NORMALIZED_RUNTIME_JUDGE_SCHEMA,
        "fixture_kind": FIXTURE_KIND_PR4,
        "battle_id": str(run_receipt.get("battle_id") or scoreboard.get("battle_id") or "battle-004"),
        "run_id": "battle-004-pr4-runtime-judge",
        "generated_at": generated_at or _utc_stamp(),
        "status": "PASS",
        "mocked": False,
        "live": "local_docker_specimen_fixture",
        "proof_mode": "local_docker_specimen_fixture",
        "runtime": {
            "docker": docker,
            "specimen_runs": runs,
            "summary": {
                "generated_specimens": len(runs),
                "compile_failed": sum(1 for item in runs if item["runtime_status"] == "COMPILE_FAILED"),
                "runtime_failed": sum(1 for item in runs if item["runtime_status"] == "RUNTIME_FAILED"),
                "runnable_unproven": sum(1 for item in runs if item["runtime_status"] in {"RUNNABLE_UNPROVEN", "TARGET_CONTACT_UNPROVEN"}),
                "target_contact_unproven": sum(1 for item in runs if item["target_contact"]["observed"] is True),
                "best_specimen_id": scoreboard.get("best_specimen_id"),
            },
        },
        "judge": {
            "judge_status": "NOT_RUN",
            "judge_progression": ["JUDGE_NOT_RUN"],
            "judge_verified_exploits": 0,
            "does_not_prove": ["exploit success", "Blue block", "Blue bypass", "target contact as exploit success"],
        },
        "claim_boundary": {
            "may_claim": MAY_CLAIM,
            "must_not_claim": MUST_NOT_CLAIM,
            "compile_passed_is_not_runnable": True,
            "target_contact_is_not_exploit_success": True,
        },
        "receipt_refs": _receipt_refs(root=root, run_receipt=run_receipt, scoreboard=scoreboard, specimen_receipts=specimen_receipts),
        "provenance": {
            "source_run_label": "exploit_combiner_proof",
            "normalizer_schema": "battle.normalized_runtime_judge_fixture_builder.v1",
            "source_receipt_count": 2 + len(specimen_receipts),
            "raw_paths_redacted": True,
            "tau_runtime_paths_exposed": False,
            "command_loop_paths_exposed": False,
            "provider_workspace_paths_exposed": False,
            "raw_stdout_paths_exposed": False,
            "raw_stderr_paths_exposed": False,
            "docker_mount_paths_exposed": False,
            "credentials_exposed": False,
        },
        "copy": {
            "headline": "Docker runtime receipts captured",
            "subhead": "Battle executed specimen code in Docker and kept Judge status explicit as not run.",
            "status_label": "Runtime unproven; Judge not run",
            "boundary_notice": "Runnable and target contact are not exploit success. Judge replay is required for exploit or Blue outcome claims.",
        },
    }


def _normalized_run(*, root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    status = _runtime_status(receipt)
    target_observed = bool(receipt.get("target_contact", {}).get("observed"))
    stdout_path = root / str(receipt.get("stdout_path"))
    stderr_path = root / str(receipt.get("stderr_path"))
    return {
        "specimen_id": receipt.get("specimen_id"),
        "runtime_status": "TARGET_CONTACT_UNPROVEN" if target_observed else status,
        "raw_status": receipt.get("status"),
        "exit_code": receipt.get("exit_code"),
        "compile_ok": bool(receipt.get("compile_ok")),
        "runtime_ok": bool(receipt.get("runtime_ok")),
        "elapsed_seconds": receipt.get("elapsed_seconds"),
        "target_contact": {
            "observed": target_observed,
            "status": "TARGET_CONTACT_UNPROVEN" if target_observed else "NOT_OBSERVED",
            "entrypoint": receipt.get("target_contact", {}).get("entrypoint"),
            "does_not_prove": ["exploit success", "path traversal", "Blue bypass"],
        },
        "stdout_summary": _text_summary(stdout_path),
        "stderr_summary": _text_summary(stderr_path),
        "does_not_prove": receipt.get("does_not_prove", []),
    }


def _runtime_status(receipt: dict[str, Any]) -> str:
    value = receipt.get("status")
    if value == "SPECIMEN_COMPILE_FAILED":
        return "COMPILE_FAILED"
    if value == "SPECIMEN_RUNTIME_FAILED":
        return "RUNTIME_FAILED"
    if value == "SPECIMEN_RUNNABLE_UNPROVEN":
        return "RUNNABLE_UNPROVEN"
    return "POLICY_BLOCKED"


def _docker_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    command = [str(item) for item in receipt.get("docker_command", [])]
    image = "unknown"
    if command:
        try:
            image = command[command.index("-w") + 2]
        except (ValueError, IndexError):
            image = next((item for item in command if ":" in item and "/" not in item), "unknown")
    network = _command_value(command, "--network") or "unknown"
    user = _command_value(command, "--user")
    return {
        "image": image,
        "network": network,
        "timeout_seconds": 30,
        "cap_drop_all": "--cap-drop" in command and "ALL" in command,
        "no_new_privileges": "no-new-privileges" in command,
        "user": user,
        "command_shape": ["docker", "run", "--rm", "--network", network, "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", user or "unknown", "<image>", "python", "<compile-and-run-wrapper>"],
    }


def _command_value(command: list[str], flag: str) -> str | None:
    try:
        return command[command.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _text_summary(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    redacted, reasons = _redacted_lines(lines[:24])
    return {
        "available": bool(lines),
        "line_count_total": len(lines),
        "lines": redacted,
        "redacted": bool(reasons),
        "redaction_reasons": sorted(reasons),
    }


def _redacted_lines(lines: list[str]) -> tuple[list[str], set[str]]:
    reasons: set[str] = set()
    redacted: list[str] = []
    path_pattern = re.compile(r"(?P<quote>['\"])(?:/[A-Za-z0-9_.:+@%=-][^'\"]+)(?P=quote)")
    for line in lines:
        value = line
        value, count = path_pattern.subn('"[redacted-path]"', value)
        if count:
            reasons.add("path")
        for marker in PATH_LEAK_MARKERS:
            if marker in value:
                value = value.replace(marker, "[redacted-path-marker]")
                reasons.add("path_marker")
        for marker in PRIVATE_MARKERS:
            if marker in value:
                value = value.replace(marker, "[redacted-private-marker]")
                reasons.add("private_marker")
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                value = pattern.sub("[redacted-secret]", value)
                reasons.add("secret_pattern")
        redacted.append(value)
    return redacted, reasons


def _validate_source_run_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("schema") != "battle.exploit_specimen_run.v1":
        raise ValueError("source run receipt schema must be battle.exploit_specimen_run.v1")
    claims = " ".join(receipt.get("proves", []))
    if "exploit success" in claims.lower() or "exploited the target" in claims.lower():
        raise ValueError("runtime source receipt must not claim exploit success")


def _source_index(*, root: Path, run_receipt: dict[str, Any], scoreboard: dict[str, Any], specimen_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    refs = _receipt_refs(root=root, run_receipt=run_receipt, scoreboard=scoreboard, specimen_receipts=specimen_receipts)
    return {
        "schema": "battle.normalized_runtime_judge_source_receipt_index.v1",
        "status": "PASS",
        "battle_id": run_receipt.get("battle_id") or scoreboard.get("battle_id"),
        "fixture_kind": FIXTURE_KIND_PR4,
        "source_receipt_count": len(refs),
        "receipts": refs,
        "raw_paths_redacted": True,
    }


def _receipt_refs(*, root: Path, run_receipt: dict[str, Any], scoreboard: dict[str, Any], specimen_receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[tuple[str, Path, dict[str, Any]]] = [
        ("combiner_run_receipt", root / "run-receipt.json", run_receipt),
        ("combiner_scoreboard", root / "scoreboard.json", scoreboard),
    ]
    for receipt in specimen_receipts:
        specimen_id = str(receipt.get("specimen_id"))
        items.append((f"specimen_run_{specimen_id}", root / "specimens" / specimen_id / "run-receipt.json", receipt))
    return [
        {"id": item_id, "schema": payload.get("schema"), "status": payload.get("status") or payload.get("verdict"), "label": path.name, "sha256": _sha256_file(path)}
        for item_id, path, payload in items
    ]


def _resolve_proof_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_dir():
        return resolved
    if resolved.name == "run-receipt.json":
        return resolved.parent
    raise RuntimeError(f"runtime/Judge proof source must be a directory or run-receipt.json: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
