"""Normalize PR3d compile-repair receipts for UX consumption."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


NORMALIZED_COMPILE_SCHEMA = "battle.normalized_compile_fixture.v1"
FIXTURE_KIND_PR3D = "pr3d_compile_repair"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.normalized_compile_fixture.v1.schema.json"
PR3D_NODES = ["lineage-summarizer", "research-scout", "method-combiner", "exploit-code-author", "compile-repair"]
EXCLUDED_NODES = ["artifact-reviewer", "battle-handoff-writer"]
PATH_LEAK_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "/home/",
    "/tmp/",
    "/mnt/",
    "pr3c-provider-workspaces",
    "pr3d-provider-workspaces",
    "provider-workspace",
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
    "provider_authored_specimen_existed",
    "compile_attempted",
    "compile_failed",
    "compile_passed",
    "repair_attempted",
    "repair_exhausted",
    "specimen_version_hashes",
]
MUST_NOT_CLAIM = [
    "runnable",
    "runtime_success",
    "target_contact",
    "exploit_success",
    "blue_detection",
    "blue_bypass",
    "blue_kill",
    "blue_block",
    "judge_success",
    "packet_level_behavior",
    "memory_promotion",
]


def normalize_pr3d_compile_fixture(
    *,
    live_tau_canary: Path,
    out_dir: Path,
    public_out_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write a PR3d-only normalized compile fixture and validation artifacts."""

    canary_root = _resolve_canary_root(live_tau_canary)
    receipt = _read_json(canary_root / "live-tau-child-dag-canary-receipt.json")
    tau_run = canary_root / "tau-dag-run"
    dag_receipt = _read_json(tau_run / "dag-receipt.json")
    node_receipts = _node_receipts(tau_run)
    for node_id in PR3D_NODES:
        if node_id not in node_receipts:
            raise RuntimeError(f"required PR3d node receipt missing: {node_id}")

    exploit_node = node_receipts["exploit-code-author"]
    compile_node = node_receipts["compile-repair"]
    authorship_path = _required_evidence_path(exploit_node, "provider-authorship-receipt.json")
    specimen_path = _required_evidence_path(exploit_node, "specimen.json")
    original_code_path = _required_evidence_path(exploit_node, "exploit_specimen.py")
    compile_receipt_path = _required_evidence_path(compile_node, "compile_receipt.json")
    compiled_code_path = _required_evidence_path(compile_node, "repaired_exploit_specimen.py")

    authorship = _read_json(authorship_path)
    specimen = _read_json(specimen_path)
    compile_receipt = _read_json(compile_receipt_path)
    original_bytes = original_code_path.read_bytes()
    compiled_bytes = compiled_code_path.read_bytes()
    original_sha = _sha256_bytes(original_bytes)
    compiled_sha = _sha256_bytes(compiled_bytes)
    _validate_source_boundary(
        authorship=authorship,
        specimen=specimen,
        compile_receipt=compile_receipt,
        original_sha=original_sha,
        compiled_sha=compiled_sha,
        original_text=original_bytes.decode("utf-8", errors="replace"),
        compiled_text=compiled_bytes.decode("utf-8", errors="replace"),
    )

    compile_status = _compile_status(compile_receipt)
    compile_passed = compile_status == "PASSED"
    compile_failed = compile_status == "FAILED"
    repair_attempted = bool(compile_receipt.get("repair_attempted") or compile_receipt.get("repair_count") or compiled_sha != original_sha)
    repair_exhausted = bool(compile_receipt.get("repair_exhausted"))
    repair_attempt_count = int(compile_receipt.get("repair_count") or (1 if repair_attempted else 0))

    receipt_sources = _receipt_sources(
        receipt=receipt,
        dag_receipt=dag_receipt,
        node_receipts=node_receipts,
        authorship=authorship,
        specimen=specimen,
        compile_receipt=compile_receipt,
        paths={
            "live_tau_child_dag_canary": canary_root / "live-tau-child-dag-canary-receipt.json",
            "tau_dag_receipt": tau_run / "dag-receipt.json",
            **{f"{node_id}_node": _node_receipt_path(tau_run, node_id) for node_id in PR3D_NODES},
            "provider_authorship": authorship_path,
            "specimen": specimen_path,
            "compile_receipt": compile_receipt_path,
        },
    )
    source_index = {
        "schema": "battle.normalized_compile_source_receipt_index.v1",
        "status": "PASS",
        "battle_id": receipt.get("battle_id") or authorship.get("battle_id"),
        "fixture_kind": FIXTURE_KIND_PR3D,
        "source_receipt_count": len(receipt_sources),
        "receipts": receipt_sources,
        "raw_paths_redacted": True,
    }
    fixture = _fixture(
        canary_root=canary_root,
        receipt=receipt,
        dag_receipt=dag_receipt,
        node_receipts=node_receipts,
        authorship=authorship,
        specimen=specimen,
        compile_receipt=compile_receipt,
        original_sha=original_sha,
        original_bytes=len(original_bytes),
        compiled_sha=compiled_sha,
        compiled_bytes=len(compiled_bytes),
        compile_status=compile_status,
        compile_passed=compile_passed,
        compile_failed=compile_failed,
        repair_attempted=repair_attempted,
        repair_exhausted=repair_exhausted,
        repair_attempt_count=repair_attempt_count,
        source_index=source_index,
        generated_at=generated_at,
    )
    report = validate_normalized_compile_fixture(fixture)

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / "battle.normalized_compile_fixture.json"
    validation_path = out_dir / "validation.json"
    source_index_path = out_dir / "source-receipt-index.json"
    _write_json(fixture_path, fixture)
    _write_json(validation_path, report)
    _write_json(source_index_path, source_index)

    if public_out_dir is not None:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        public_fixture = public_out_dir / "battle.normalized_compile_fixture.json"
        shutil.copyfile(fixture_path, public_fixture)
        if _sha256_file(public_fixture) != _sha256_file(fixture_path):
            raise RuntimeError("public compile fixture hash mismatch after copy")
    return fixture


def validate_normalized_compile_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_compile_fixture(_read_json(path))


def validate_normalized_compile_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(fixture, schema)
    errors: list[str] = []
    if fixture.get("schema") != NORMALIZED_COMPILE_SCHEMA:
        errors.append("schema must be battle.normalized_compile_fixture.v1")
    if fixture.get("fixture_kind") != FIXTURE_KIND_PR3D:
        errors.append("fixture_kind must be pr3d_compile_repair")
    for key, expected in {
        "status": "PASS",
        "mocked": False,
        "agentic": True,
        "provider_live": True,
        "fixture_fallback_used": False,
    }.items():
        if fixture.get(key) != expected:
            errors.append(f"{key} must be {expected!r}")
    node_status = fixture.get("node_status") if isinstance(fixture.get("node_status"), dict) else {}
    if set(node_status) != set(PR3D_NODES):
        errors.append("node_status must contain only the five PR3d nodes")
    for node_id in PR3D_NODES[:4]:
        if node_status.get(node_id) != "PASS":
            errors.append(f"node_status.{node_id} must be PASS")
    if node_status.get("compile-repair") not in {"PASS", "BLOCKED"}:
        errors.append("node_status.compile-repair must be PASS or BLOCKED")
    compile_info = fixture.get("compile") if isinstance(fixture.get("compile"), dict) else {}
    if compile_info.get("compile_attempted") is not True:
        errors.append("compile.compile_attempted must be true")
    compile_failed = bool(compile_info.get("compile_failed"))
    compile_passed = bool(compile_info.get("compile_passed"))
    if compile_failed == compile_passed:
        errors.append("exactly one of compile_failed or compile_passed must be true")
    if compile_info.get("status") == "FAILED" and not compile_failed:
        errors.append("FAILED compile status requires compile_failed")
    if compile_info.get("status") == "PASSED" and not compile_passed:
        errors.append("PASSED compile status requires compile_passed")
    repair = fixture.get("repair") if isinstance(fixture.get("repair"), dict) else {}
    if not isinstance(repair.get("repair_attempted"), bool):
        errors.append("repair.repair_attempted must be boolean")
    if not isinstance(repair.get("repair_exhausted"), bool):
        errors.append("repair.repair_exhausted must be boolean")
    versions = fixture.get("specimen_versions") if isinstance(fixture.get("specimen_versions"), list) else []
    if len(versions) < 2:
        errors.append("specimen_versions must include provider and compile-selected versions")
    selected = fixture.get("selected_version") if isinstance(fixture.get("selected_version"), dict) else {}
    if selected.get("version_id") != compile_info.get("compiled_version_id"):
        errors.append("selected_version.version_id must match compile.compiled_version_id")
    boundary = fixture.get("execution_boundary") if isinstance(fixture.get("execution_boundary"), dict) else {}
    for key in ["runtime_status", "target_contact", "judge_status", "packet_behavior", "memory_promotion"]:
        if boundary.get(key) != "NOT_RUN":
            errors.append(f"execution_boundary.{key} must be NOT_RUN")
    if boundary.get("judge_verified_exploits") != 0:
        errors.append("execution_boundary.judge_verified_exploits must be 0")
    claims = fixture.get("claim_boundary") if isinstance(fixture.get("claim_boundary"), dict) else {}
    may_claim = set(claims.get("may_claim", []))
    must_not_claim = set(claims.get("must_not_claim", []))
    for item in MAY_CLAIM:
        if item not in may_claim:
            errors.append(f"claim_boundary.may_claim missing {item}")
    for item in MUST_NOT_CLAIM:
        if item not in must_not_claim:
            errors.append(f"claim_boundary.must_not_claim missing {item}")
    forbidden_may_claim = {
        "runnable",
        "runtime_success",
        "target_contact",
        "exploit_success",
        "blue_detection",
        "blue_block",
        "judge_success",
        "packet_level_behavior",
        "memory_promotion",
    }
    if forbidden_may_claim & may_claim:
        errors.append(f"claim_boundary.may_claim contains forbidden values: {sorted(forbidden_may_claim & may_claim)}")
    serialized = json.dumps(fixture, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            errors.append(f"normalized compile fixture exposes forbidden marker: {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            errors.append("normalized compile fixture exposes secret-like material")
    if "compile_passed" in may_claim and "runnable" not in must_not_claim:
        errors.append("compile_passed may-claim requires runnable in must_not_claim")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.normalized_compile_fixture_validation.v1",
        "status": "PASS",
        "fixture_kind": fixture["fixture_kind"],
        "battle_id": fixture["battle_id"],
        "node_status_count": len(node_status),
        "receipt_ref_count": len(fixture.get("receipt_refs", [])),
        "raw_paths_redacted": fixture.get("provenance", {}).get("raw_paths_redacted"),
        "compile_status": compile_info.get("status"),
        "compile_failed": compile_info.get("compile_failed"),
        "compile_passed": compile_info.get("compile_passed"),
        "repair_attempted": repair.get("repair_attempted"),
        "judge_verified_exploits": boundary.get("judge_verified_exploits"),
    }


def _fixture(
    *,
    canary_root: Path,
    receipt: dict[str, Any],
    dag_receipt: dict[str, Any],
    node_receipts: dict[str, dict[str, Any]],
    authorship: dict[str, Any],
    specimen: dict[str, Any],
    compile_receipt: dict[str, Any],
    original_sha: str,
    original_bytes: int,
    compiled_sha: str,
    compiled_bytes: int,
    compile_status: str,
    compile_passed: bool,
    compile_failed: bool,
    repair_attempted: bool,
    repair_exhausted: bool,
    repair_attempt_count: int,
    source_index: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    node_status = {node_id: node_receipts[node_id].get("status") for node_id in PR3D_NODES}
    node_verdict = {node_id: node_receipts[node_id].get("verdict") for node_id in PR3D_NODES}
    return {
        "schema": NORMALIZED_COMPILE_SCHEMA,
        "fixture_kind": FIXTURE_KIND_PR3D,
        "battle_id": str(receipt.get("battle_id") or authorship.get("battle_id") or "battle-004"),
        "run_id": "battle-004-pr3d-compile",
        "generated_at": generated_at or _utc_stamp(),
        "proof_mode": "live_tau_child_dag_canary",
        "status": "PASS",
        "mocked": False,
        "live": "local_py_compile",
        "agentic": True,
        "provider_live": True,
        "fixture_fallback_used": False,
        "stage_scope": {
            "included_through": "compile-repair",
            "included_nodes": PR3D_NODES,
            "excluded_nodes": EXCLUDED_NODES,
            "downstream_receipts_ignored": True,
        },
        "source_run": {
            "proof_mode": receipt.get("proof_mode"),
            "overall_status": receipt.get("status"),
            "overall_reason": receipt.get("reason"),
            "tau_receipt_status": receipt.get("tau_receipt_status"),
            "tau_receipt_verdict": dag_receipt.get("verdict"),
        },
        "node_status": node_status,
        "node_verdict": node_verdict,
        "provider_authorship": {
            "status": "PASS",
            "provider_live": True,
            "agentic": True,
            "authored_by": "tau_provider",
            "observed_provider": authorship.get("observed_provider"),
            "observed_model": authorship.get("observed_model"),
            "code_sha256": original_sha,
            "specimen_id": specimen.get("specimen_id"),
            "language": specimen.get("language"),
            "selected_method_ids": specimen.get("selected_method_ids", []),
        },
        "compile": {
            "status": compile_status,
            "verdict": compile_receipt.get("verdict"),
            "compiler": compile_receipt.get("compiler") or "unknown",
            "compile_attempted": True,
            "compile_failed": compile_failed,
            "compile_passed": compile_passed,
            "stderr_summary": _stderr_summary(compile_receipt.get("errors", [])),
            "source_version_id": "v001",
            "compiled_version_id": "v002",
            "does_not_prove": [
                "The specimen runs.",
                "The specimen contacts the target.",
                "The specimen exploits the target.",
                "Judge verified exploit success.",
            ],
        },
        "repair": {
            "repair_attempted": repair_attempted,
            "repair_exhausted": repair_exhausted,
            "attempt_count": repair_attempt_count,
            "provider_repair_live": False,
        },
        "specimen_versions": [
            {
                "version_id": "v001",
                "role": "provider_authored",
                "code_artifact_label": "exploit_specimen.py",
                "code_sha256": original_sha,
                "code_bytes": original_bytes,
                "compile_attempted": False,
                "compile_status": "NOT_RUN",
                "compile_failed": False,
                "compile_passed": False,
            },
            {
                "version_id": "v002",
                "role": "compile_repair_selected",
                "source_version_id": "v001",
                "code_artifact_label": "repaired_exploit_specimen.py",
                "code_sha256": compiled_sha,
                "code_bytes": compiled_bytes,
                "compile_attempted": True,
                "compile_status": compile_status,
                "compile_failed": compile_failed,
                "compile_passed": compile_passed,
                "stderr_summary_ref": "compile.stderr_summary",
            },
        ],
        "selected_version": {
            "version_id": "v002",
            "code_sha256": compiled_sha,
            "compile_status": compile_status,
            "compile_failed": compile_failed,
            "compile_passed": compile_passed,
        },
        "execution_boundary": {
            "runtime_status": "NOT_RUN",
            "target_contact": "NOT_RUN",
            "judge_status": "NOT_RUN",
            "judge_verified_exploits": 0,
            "packet_behavior": "NOT_RUN",
            "memory_promotion": "NOT_RUN",
        },
        "claim_boundary": {
            "may_claim": MAY_CLAIM,
            "must_not_claim": MUST_NOT_CLAIM,
            "compile_passed_is_not_runnable": True,
        },
        "receipt_refs": source_index["receipts"],
        "provenance": {
            "source_run_label": "live_tau_child_dag_canary",
            "normalizer_schema": "battle.normalized_compile_fixture_builder.v1",
            "source_receipt_count": source_index["source_receipt_count"],
            "raw_paths_redacted": True,
            "tau_runtime_paths_exposed": False,
            "command_loop_paths_exposed": False,
            "provider_workspace_paths_exposed": False,
            "compile_stderr_paths_exposed": False,
            "credentials_exposed": False,
        },
        "copy": {
            "headline": "Compile attempt captured",
            "subhead": "Battle ran a local compiler check against the provider-authored specimen version and captured the result.",
            "status_label": "Compile failed" if compile_failed else "Compile passed",
            "boundary_notice": "Compile status is not runtime proof. This PR3d fixture does not include Docker execution, target contact, Judge replay, Blue outcomes, packet behavior, or memory promotion.",
        },
    }


def _validate_source_boundary(
    *,
    authorship: dict[str, Any],
    specimen: dict[str, Any],
    compile_receipt: dict[str, Any],
    original_sha: str,
    compiled_sha: str,
    original_text: str,
    compiled_text: str,
) -> None:
    errors: list[str] = []
    if authorship.get("status") != "PASS":
        errors.append("provider_authorship status must be PASS")
    if authorship.get("provider_live") is not True or authorship.get("agentic") is not True:
        errors.append("provider authorship must be live and agentic")
    if authorship.get("authored_by") != "tau_provider":
        errors.append("provider authorship authored_by must be tau_provider")
    if not authorship.get("observed_provider") or not authorship.get("observed_model"):
        errors.append("observed provider/model are required")
    if specimen.get("code_sha256") != original_sha or authorship.get("code_artifact_sha256") != original_sha:
        errors.append("provider source code hash mismatch")
    compile_status = _compile_status(compile_receipt)
    if compile_status not in {"FAILED", "PASSED"}:
        errors.append("compile receipt must report FAILED or PASSED")
    for key in ["runtime_status", "target_contact", "judge_status"]:
        if compile_receipt.get(key) != "NOT_RUN":
            errors.append(f"compile receipt {key} must be NOT_RUN")
    if compile_receipt.get("judge_verified_exploits", 0) not in {0, None}:
        errors.append("compile receipt judge_verified_exploits must be 0 or absent")
    for text in [original_text, compiled_text, json.dumps(compile_receipt, sort_keys=True)]:
        for marker in PRIVATE_MARKERS:
            if marker in text:
                errors.append(f"source contains private marker {marker}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append("source contains secret-like material")
    if not compiled_sha.startswith("sha256:"):
        errors.append("compiled version hash missing")
    if errors:
        raise ValueError("\n".join(errors))


def _compile_status(compile_receipt: dict[str, Any]) -> str:
    value = compile_receipt.get("compile_status")
    if value in {"PASS", "PASSED"}:
        return "PASSED"
    return "FAILED"


def _stderr_summary(errors: Any) -> dict[str, Any]:
    raw_lines: list[str] = []
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, str):
                raw_lines.extend(item.splitlines())
            elif item is not None:
                raw_lines.extend(str(item).splitlines())
    elif isinstance(errors, str):
        raw_lines.extend(errors.splitlines())
    redacted, reasons = _redacted_lines(raw_lines[:24])
    return {
        "available": bool(redacted),
        "line_count_total": len(raw_lines),
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


def _receipt_sources(
    *,
    receipt: dict[str, Any],
    dag_receipt: dict[str, Any],
    node_receipts: dict[str, dict[str, Any]],
    authorship: dict[str, Any],
    specimen: dict[str, Any],
    compile_receipt: dict[str, Any],
    paths: dict[str, Path],
) -> list[dict[str, Any]]:
    values: list[tuple[str, dict[str, Any]]] = [
        ("live_tau_child_dag_canary", receipt),
        ("tau_dag_receipt", dag_receipt),
        *[(f"{node_id}_node", node_receipts[node_id]) for node_id in PR3D_NODES],
        ("provider_authorship", authorship),
        ("specimen", specimen),
        ("compile_receipt", compile_receipt),
    ]
    result = []
    for source_id, payload in values:
        path = paths[source_id]
        result.append(
            {
                "id": source_id,
                "schema": payload.get("schema"),
                "status": payload.get("status"),
                "verdict": payload.get("verdict") or payload.get("reason"),
                "label": path.name,
                "sha256": _sha256_file(path),
            }
        )
    return result


def _resolve_canary_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_dir():
        return resolved
    if resolved.name == "live-tau-child-dag-canary-receipt.json":
        return resolved.parent
    raise RuntimeError(f"live Tau canary must be a directory or receipt file: {path}")


def _node_receipts(tau_run: Path) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in sorted(tau_run.rglob("*node-receipt.json")):
        payload = _read_json(path)
        node_id = payload.get("node_id")
        if isinstance(node_id, str):
            receipts[node_id] = payload
    return receipts


def _node_receipt_path(tau_run: Path, node_id: str) -> Path:
    for path in sorted(tau_run.rglob("*node-receipt.json")):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            continue
        if payload.get("node_id") == node_id:
            return path
    raise RuntimeError(f"node receipt path missing: {node_id}")


def _required_evidence_path(receipt: dict[str, Any], kind: str) -> Path:
    for item in receipt.get("evidence", []):
        if not isinstance(item, dict) or item.get("kind") != kind:
            continue
        value = item.get("path")
        if isinstance(value, str) and value:
            path = Path(value)
            if path.exists():
                return path
    raise RuntimeError(f"required evidence missing from {receipt.get('node_id')}: {kind}")


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
