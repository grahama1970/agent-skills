"""Validate provider-authored Battle exploit artifacts without executing them."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PROVIDER_ARTIFACT_VALIDATION_SCHEMA = "battle.provider_artifact_validation.v1"

FORBIDDEN_REFERENCES = (
    "arena/private/",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
)


def validate_provider_artifact(
    *,
    code_path: Path,
    output_root: Path,
    baseline_manifest: dict[str, Any],
    tau_worker_result: dict[str, Any] | None,
    tau_worker_validation: dict[str, Any] | None,
    out_path: Path,
    max_bytes: int = 128_000,
) -> dict[str, Any]:
    """Validate a provider output artifact as data only.

    This intentionally does not parse, compile, import, run, or Docker-execute
    the generated specimen. PR3c proves provenance, not code validity.
    """

    output_root = output_root.expanduser().resolve()
    code_path = code_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not _inside(code_path, output_root):
        errors.append("OUTPUT_PATH_ESCAPE")
    if not code_path.exists():
        errors.append("PROVIDER_OUTPUT_MISSING")
        code_text = ""
        code_bytes = b""
    elif code_path.is_symlink():
        errors.append("OUTPUT_SYMLINK")
        code_text = ""
        code_bytes = b""
    elif not code_path.is_file():
        errors.append("OUTPUT_NOT_REGULAR_FILE")
        code_text = ""
        code_bytes = b""
    else:
        code_bytes = code_path.read_bytes()
        if not code_bytes:
            errors.append("OUTPUT_EMPTY")
        if len(code_bytes) > max_bytes:
            errors.append("OUTPUT_OVERSIZED")
        try:
            code_text = code_bytes.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("OUTPUT_NOT_UTF8")
            code_text = ""

    baseline_outputs = baseline_manifest.get("output_files_present")
    if baseline_outputs not in ([], None):
        errors.append("OUTPUT_PRESENT_BEFORE_PROVIDER_RUN")
    if code_path.name != "exploit_specimen.py":
        errors.append("UNEXPECTED_CODE_FILENAME")

    for forbidden in FORBIDDEN_REFERENCES:
        if forbidden in code_text:
            errors.append(f"PRIVATE_REFERENCE:{forbidden}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(code_text):
            errors.append("SECRET_MATERIAL_PATTERN")

    expected_hash = f"sha256:{hashlib.sha256(code_bytes).hexdigest()}" if code_bytes else None
    result_artifacts = _artifact_names(tau_worker_result)
    if tau_worker_result is not None and "outputs/exploit_specimen.py" not in result_artifacts:
        errors.append("PROVIDER_RESULT_OMITS_CODE_ARTIFACT")
    validation_artifacts = tau_worker_validation.get("result_artifacts", []) if isinstance(tau_worker_validation, dict) else []
    if tau_worker_validation is not None and "outputs/exploit_specimen.py" not in validation_artifacts:
        errors.append("TAU_VALIDATION_OMITS_CODE_ARTIFACT")

    if isinstance(tau_worker_validation, dict) and tau_worker_validation.get("provider_live") is not True:
        errors.append("PROVIDER_EXECUTION_ATTESTATION_MISSING")

    output_manifest = _manifest(output_root)
    unexpected = [
        item["path"]
        for item in output_manifest
        if item["path"] not in {"exploit_specimen.py", "provider-worker-result.json"}
    ]
    if unexpected:
        errors.append(f"UNAUTHORIZED_SECONDARY_OUTPUT:{','.join(unexpected)}")

    receipt = {
        "schema": PROVIDER_ARTIFACT_VALIDATION_SCHEMA,
        "status": "PASS" if not errors else "BLOCKED",
        "mocked": False,
        "live": True,
        "provider_live": bool(isinstance(tau_worker_validation, dict) and tau_worker_validation.get("provider_live") is True),
        "code_artifact_path": str(code_path),
        "code_artifact_sha256": expected_hash,
        "code_artifact_bytes": len(code_bytes),
        "output_root": str(output_root),
        "workspace_baseline_status": baseline_manifest.get("schema"),
        "output_absent_before_provider_run": baseline_outputs == [],
        "output_manifest": output_manifest,
        "errors": errors,
        "warnings": warnings,
        "claims": {
            "proves": ["Battle validated provider output provenance and claim boundaries."] if not errors else [],
            "does_not_prove": [
                "The code compiles.",
                "The code runs.",
                "The code contacts the target.",
                "The code exploits the target.",
            ],
        },
    }
    _write_json(out_path, receipt)
    return receipt


def _artifact_names(result: dict[str, Any] | None) -> set[str]:
    if not isinstance(result, dict):
        return set()
    artifacts = result.get("artifacts") or result.get("result_artifacts")
    names: set[str] = set()
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict) and isinstance(item.get("path"), str):
                names.add(item["path"])
    return names


def _manifest(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        result.append({"path": rel, "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}", "bytes": len(data)})
    return result


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
