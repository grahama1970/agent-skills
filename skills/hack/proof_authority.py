"""Validate Hack probe observations against independent proof receipts.

Inputs are local JSON artifacts: Hack probe observations and independent
validation receipts. Outputs are strict status receipts used by reports and
Battle adapters. This module is import-safe: it does not invoke Docker, network
clients, subprocesses, scanners, models, or target runtimes.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console

PROBE_OBSERVATION_SCHEMA = "hack.probe_observation.v1"
PROOF_VALIDATION_SCHEMA = "hack.proof_validation_receipt.v1"
MATRIX_SCHEMA = "hack.proof_authority_matrix.v1"
VALIDATOR_VERSION = "hack.proof-authority-validator.v1"
UNCONFIRMED_STATUS = "OBSERVED_UNCONFIRMED"
TERMINAL_STATUSES = {
    "NOT_ATTEMPTED",
    "OBSERVED_UNCONFIRMED",
    "CONFIRMED",
    "REJECTED",
    "VALIDATION_ERROR",
}
HASH_FIELDS = (
    "authorization_manifest_sha256",
    "target_runtime_sha256",
    "scan_request_sha256",
    "probe_spec_sha256",
)
OBSERVATION_KEYS = {
    "schema",
    "observation_id",
    "created_at",
    "executor_identity",
    "target_identity",
    "target_runtime_sha256",
    "authorization_manifest_sha256",
    "scan_request_sha256",
    "probe_spec_sha256",
    "probe_exit_code",
    "signal_type",
    "finding_class",
    "target_summary",
    "evidence_summary",
    "evidence_artifacts",
    "exploit_confirmed",
    "non_claims",
}
EVIDENCE_KEYS = {"path", "sha256", "redaction", "summary"}
VALIDATION_KEYS = {
    "schema",
    "validation_id",
    "created_at",
    "validator_identity",
    "validator_authority",
    "validator_independent",
    "status",
    "observation_id",
    "observation_artifact_sha256",
    "target_identity",
    "target_runtime_sha256",
    "authorization_manifest_sha256",
    "scan_request_sha256",
    "probe_spec_sha256",
    "replay_spec_sha256",
    "replay_spec_artifact",
    "replay_receipt_sha256",
    "replay_receipt_artifact",
    "replay_command",
    "confirms_exploit",
    "mocked",
    "live",
    "errors",
    "non_claims",
}

console = Console()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest for a local file."""

    return sha256(path.read_bytes()).hexdigest()


def json_sha256(payload: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-serializable value."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON with a trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path, errors: list[str], label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label} cannot be read or parsed: {type(exc).__name__}: {exc}")
        return None


def _unknown_key_errors(data: Any, allowed: set[str], label: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    return [f"{label} contains unknown field: {key}" for key in sorted(set(data) - allowed)]


def _parse_time(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be a valid ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _require_string(payload: dict[str, Any], field: str, errors: list[str]) -> str | None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required")
        return None
    return value


def _validate_hash_fields(payload: dict[str, Any], fields: tuple[str, ...], errors: list[str]) -> None:
    for field in fields:
        if not _is_sha(payload.get(field)):
            errors.append(f"{field} must be a SHA-256 hex digest")


def validate_probe_observation_payload(payload: Any) -> list[str]:
    """Return validation errors for a ``hack.probe_observation.v1`` payload."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["observation payload must be a JSON object"]
    errors.extend(_unknown_key_errors(payload, OBSERVATION_KEYS, "observation"))
    if payload.get("schema") != PROBE_OBSERVATION_SCHEMA:
        errors.append(f"schema must equal {PROBE_OBSERVATION_SCHEMA}")
    for field in (
        "observation_id",
        "executor_identity",
        "target_identity",
        "signal_type",
        "finding_class",
        "target_summary",
        "evidence_summary",
    ):
        _require_string(payload, field, errors)
    _parse_time(payload.get("created_at"), "created_at", errors)
    _validate_hash_fields(payload, HASH_FIELDS, errors)
    if not isinstance(payload.get("probe_exit_code"), int):
        errors.append("probe_exit_code must be an integer")
    if payload.get("exploit_confirmed") is not False:
        errors.append("exploit_confirmed must be false on Hack observations")
    evidence = payload.get("evidence_artifacts")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence_artifacts must be a non-empty array")
    else:
        for index, item in enumerate(evidence):
            label = f"evidence_artifacts[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            errors.extend(_unknown_key_errors(item, EVIDENCE_KEYS, label))
            for field in ("path", "sha256", "redaction", "summary"):
                if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                    errors.append(f"{label}.{field} is required")
            if not _is_sha(item.get("sha256")):
                errors.append(f"{label}.sha256 must be a SHA-256 hex digest")
    non_claims = payload.get("non_claims")
    if not isinstance(non_claims, list) or "observation_is_not_exploit_confirmation" not in non_claims:
        errors.append("non_claims must include observation_is_not_exploit_confirmation")
    return errors


def validate_probe_observation(path: Path) -> dict[str, Any]:
    """Validate an observation file and return a validation receipt."""

    errors: list[str] = []
    payload = _read_json(path, errors, "observation")
    if payload is not None:
        errors.extend(validate_probe_observation_payload(payload))
    return {
        "schema": "hack.probe_observation_validation_receipt.v1",
        "validator_version": VALIDATOR_VERSION,
        "status": "FAIL" if errors else "PASS",
        "valid": not errors,
        "observation_path": str(path),
        "observation_sha256": file_sha256(path) if path.exists() and path.is_file() else None,
        "errors": errors,
        "docker_invoked": False,
        "subprocess_invoked": False,
        "network_invoked": False,
        "execution_started": False,
    }


def validate_proof_validation_payload(payload: Any) -> list[str]:
    """Return schema-level errors for a proof validation receipt."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["validation payload must be a JSON object"]
    errors.extend(_unknown_key_errors(payload, VALIDATION_KEYS, "validation"))
    if payload.get("schema") != PROOF_VALIDATION_SCHEMA:
        errors.append(f"schema must equal {PROOF_VALIDATION_SCHEMA}")
    for field in (
        "validation_id",
        "validator_identity",
        "validator_authority",
        "observation_id",
        "target_identity",
        "live",
        "replay_spec_artifact",
        "replay_receipt_artifact",
    ):
        _require_string(payload, field, errors)
    _parse_time(payload.get("created_at"), "created_at", errors)
    _validate_hash_fields(payload, HASH_FIELDS + ("observation_artifact_sha256", "replay_spec_sha256", "replay_receipt_sha256"), errors)
    if payload.get("status") not in {"CONFIRMED", "REJECTED", "VALIDATION_ERROR"}:
        errors.append("status must be CONFIRMED, REJECTED, or VALIDATION_ERROR")
    if not isinstance(payload.get("replay_command"), list) or not payload.get("replay_command"):
        errors.append("replay_command must be a non-empty argv array")
    elif not all(isinstance(part, str) and part.strip() for part in payload["replay_command"]):
        errors.append("replay_command entries must be non-empty strings")
    if payload.get("validator_independent") is not True:
        errors.append("validator_independent must be true")
    if not isinstance(payload.get("confirms_exploit"), bool):
        errors.append("confirms_exploit must be a boolean")
    if payload.get("mocked") is not False:
        errors.append("mocked must be false")
    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be an array")
    non_claims = payload.get("non_claims")
    if not isinstance(non_claims, list) or "validation_receipt_is_not_patch_proof" not in non_claims:
        errors.append("non_claims must include validation_receipt_is_not_patch_proof")
    return errors


def validate_proof_validation_receipt(validation_path: Path, observation_path: Path) -> dict[str, Any]:
    """Validate a proof receipt against the exact observation artifact."""

    errors: list[str] = []
    validation = _read_json(validation_path, errors, "validation")
    observation = _read_json(observation_path, errors, "observation")
    observation_created: datetime | None = None
    validation_created: datetime | None = None
    if validation is not None:
        errors.extend(validate_proof_validation_payload(validation))
        validation_created = _parse_time(validation.get("created_at"), "validation.created_at", errors) if isinstance(validation, dict) else None
    if observation is not None:
        errors.extend(validate_probe_observation_payload(observation))
        observation_created = _parse_time(observation.get("created_at"), "observation.created_at", errors) if isinstance(observation, dict) else None
    if isinstance(validation, dict) and isinstance(observation, dict):
        if validation.get("validator_identity") == observation.get("executor_identity"):
            errors.append("validator_identity must differ from Hack executor_identity")
        if validation.get("observation_id") != observation.get("observation_id"):
            errors.append("observation_id does not match observation")
        if validation.get("observation_artifact_sha256") != file_sha256(observation_path):
            errors.append("observation_artifact_sha256 does not match observation file")
        for field in ("target_identity", *HASH_FIELDS):
            if validation.get(field) != observation.get(field):
                errors.append(f"{field} does not match observation")
        if validation.get("status") == "CONFIRMED" and validation.get("confirms_exploit") is not True:
            errors.append("CONFIRMED receipts must set confirms_exploit=true")
        if validation.get("status") != "CONFIRMED" and validation.get("confirms_exploit") is True:
            errors.append("only CONFIRMED receipts may set confirms_exploit=true")
        for artifact_field, hash_field in (
            ("replay_spec_artifact", "replay_spec_sha256"),
            ("replay_receipt_artifact", "replay_receipt_sha256"),
        ):
            artifact_value = validation.get(artifact_field)
            if isinstance(artifact_value, str) and artifact_value.strip():
                artifact = Path(artifact_value)
                if not artifact.exists() or not artifact.is_file():
                    errors.append(f"{artifact_field} does not exist")
                elif file_sha256(artifact) != validation.get(hash_field):
                    errors.append(f"{hash_field} does not match {artifact_field}")
    if observation_created is not None and validation_created is not None and validation_created < observation_created:
        errors.append("validation receipt is stale relative to observation")
    status = "FAIL" if errors else "PASS"
    confirms = bool(isinstance(validation, dict) and validation.get("status") == "CONFIRMED" and not errors)
    return {
        "schema": "hack.proof_authority_validation_receipt.v1",
        "validator_version": VALIDATOR_VERSION,
        "status": status,
        "valid": not errors,
        "confirms_exploit": confirms,
        "validation_status": validation.get("status") if isinstance(validation, dict) else "VALIDATION_ERROR",
        "validation_path": str(validation_path),
        "observation_path": str(observation_path),
        "errors": errors,
        "mocked": False,
        "live": "local_deterministic_receipt_validation",
        "docker_invoked": False,
        "subprocess_invoked": False,
        "network_invoked": False,
        "execution_started": False,
    }


def build_probe_observation(
    *,
    observation_id: str,
    executor_identity: str,
    target_identity: str,
    authorization_manifest_sha256: str,
    target_runtime_sha256: str,
    scan_request_sha256: str,
    probe_spec_sha256: str,
    probe_exit_code: int,
    signal_type: str,
    finding_class: str,
    target_summary: str,
    evidence_summary: str,
    evidence_artifacts: list[dict[str, str]],
    created_at: str = "2026-07-29T00:00:00+00:00",
) -> dict[str, Any]:
    """Build a Hack observation that explicitly does not confirm exploitability."""

    return {
        "schema": PROBE_OBSERVATION_SCHEMA,
        "observation_id": observation_id,
        "created_at": created_at,
        "executor_identity": executor_identity,
        "target_identity": target_identity,
        "target_runtime_sha256": target_runtime_sha256,
        "authorization_manifest_sha256": authorization_manifest_sha256,
        "scan_request_sha256": scan_request_sha256,
        "probe_spec_sha256": probe_spec_sha256,
        "probe_exit_code": probe_exit_code,
        "signal_type": signal_type,
        "finding_class": finding_class,
        "target_summary": target_summary,
        "evidence_summary": evidence_summary,
        "evidence_artifacts": evidence_artifacts,
        "exploit_confirmed": False,
        "non_claims": [
            "observation_is_not_exploit_confirmation",
            "probe_exit_code_is_not_exploit_confirmation",
            "proof_file_name_is_not_exploit_confirmation",
        ],
    }


def build_proof_validation_receipt(
    *,
    validation_id: str,
    observation_path: Path,
    replay_spec_sha256: str,
    replay_spec_artifact: Path,
    replay_receipt_sha256: str,
    replay_receipt_artifact: Path,
    replay_command: list[str],
    validator_identity: str = "battle-judge-fixture",
    validator_authority: str = "independent-battle-judge",
    status: str = "CONFIRMED",
    created_at: str = "2026-07-29T00:01:00+00:00",
) -> dict[str, Any]:
    """Build an independent validation receipt bound to one observation file."""

    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    return {
        "schema": PROOF_VALIDATION_SCHEMA,
        "validation_id": validation_id,
        "created_at": created_at,
        "validator_identity": validator_identity,
        "validator_authority": validator_authority,
        "validator_independent": True,
        "status": status,
        "observation_id": observation["observation_id"],
        "observation_artifact_sha256": file_sha256(observation_path),
        "target_identity": observation["target_identity"],
        "target_runtime_sha256": observation["target_runtime_sha256"],
        "authorization_manifest_sha256": observation["authorization_manifest_sha256"],
        "scan_request_sha256": observation["scan_request_sha256"],
        "probe_spec_sha256": observation["probe_spec_sha256"],
        "replay_spec_sha256": replay_spec_sha256,
        "replay_spec_artifact": str(replay_spec_artifact),
        "replay_receipt_sha256": replay_receipt_sha256,
        "replay_receipt_artifact": str(replay_receipt_artifact),
        "replay_command": replay_command,
        "confirms_exploit": status == "CONFIRMED",
        "mocked": False,
        "live": "local_deterministic_receipt_validation",
        "errors": [],
        "non_claims": [
            "validation_receipt_is_not_patch_proof",
            "validation_receipt_is_not_general_target_safety",
            "local_fixture_does_not_prove_arbitrary_target",
        ],
    }


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def resolve_session_proof_status(session_dir: Path) -> dict[str, Any]:
    """Resolve Hack session proof status without trusting file names."""

    attacks_dir = session_dir / "attacks"
    observation_path = _first_existing(sorted(attacks_dir.glob("**/*probe-observation*.json")))
    validation_path = _first_existing(sorted(attacks_dir.glob("**/*proof-validation*.json")))
    legacy_proofs = sorted(attacks_dir.glob("**/proof.*"))
    if observation_path and validation_path:
        receipt = validate_proof_validation_receipt(validation_path, observation_path)
        if receipt["valid"] and receipt["confirms_exploit"]:
            observation = json.loads(observation_path.read_text(encoding="utf-8"))
            return {
                "status": "CONFIRMED",
                "proven": True,
                "artifact": str(validation_path),
                "observation_artifact": str(observation_path),
                "reason": "Independent validation receipt confirmed the bound Hack observation.",
                "finding": observation.get("finding_class", "validated finding"),
                "target_summary": observation.get("target_summary", "typed target"),
                "evidence_summary": observation.get("evidence_summary", "typed evidence"),
                "indicator": observation.get("signal_type", "validated_signal"),
                "validation_errors": [],
            }
        return {
            "status": receipt["validation_status"] if receipt["validation_status"] == "REJECTED" else "VALIDATION_ERROR",
            "proven": False,
            "artifact": str(validation_path),
            "observation_artifact": str(observation_path),
            "reason": "; ".join(receipt["errors"]) or "Independent validation did not confirm the observation.",
            "finding": "typed proof validation did not confirm exploitability",
            "target_summary": "typed observation",
            "evidence_summary": "see validation receipt errors",
            "indicator": "none",
            "validation_errors": receipt["errors"],
        }
    if observation_path:
        receipt = validate_probe_observation(observation_path)
        try:
            observation = json.loads(observation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            observation = {}
        return {
            "status": "VALIDATION_ERROR" if not receipt["valid"] else UNCONFIRMED_STATUS,
            "proven": False,
            "artifact": str(observation_path),
            "observation_artifact": str(observation_path),
            "reason": "; ".join(receipt["errors"]) if not receipt["valid"] else "Hack observation has no independent validation receipt.",
            "finding": observation.get("finding_class", "unconfirmed typed observation"),
            "target_summary": observation.get("target_summary", "typed target"),
            "evidence_summary": observation.get("evidence_summary", "typed evidence requires independent replay"),
            "indicator": observation.get("signal_type", "unconfirmed_signal"),
            "validation_errors": receipt["errors"],
        }
    if legacy_proofs:
        return {
            "status": UNCONFIRMED_STATUS,
            "proven": False,
            "artifact": str(legacy_proofs[0]),
            "observation_artifact": "none",
            "reason": "Legacy proof-like file exists, but no typed independent validation receipt confirmed it.",
            "finding": "unconfirmed legacy probe artifact",
            "target_summary": "untyped target from legacy proof artifact",
            "evidence_summary": "file name and probe exit code are not exploit confirmation",
            "indicator": "legacy_unconfirmed",
            "validation_errors": [],
        }
    if attacks_dir.exists() and any(attacks_dir.glob("**/*")):
        return {
            "status": UNCONFIRMED_STATUS,
            "proven": False,
            "artifact": "none",
            "observation_artifact": "none",
            "reason": "Attack artifacts exist, but no typed proof observation and validation receipt were found.",
            "finding": "unconfirmed attack artifacts",
            "target_summary": "none",
            "evidence_summary": "no typed proof authority artifacts",
            "indicator": "none",
            "validation_errors": [],
        }
    return {
        "status": "NOT_ATTEMPTED",
        "proven": False,
        "artifact": "none",
        "observation_artifact": "none",
        "reason": "No Hack proof observation or independent validation receipt exists.",
        "finding": "no exploit proof observation was produced",
        "target_summary": "none",
        "evidence_summary": "none",
        "indicator": "none",
        "validation_errors": [],
    }


def _fixture_component_hash(fixture: Path, name: str) -> str:
    path = fixture / name
    if path.exists():
        return file_sha256(path)
    return json_sha256({"fixture_missing_component": name})


def _fixture_evidence(fixture: Path) -> list[dict[str, str]]:
    signal = fixture / "observed-signal.json"
    return [
        {
            "path": str(signal),
            "sha256": file_sha256(signal),
            "redaction": "safe_summary_only",
            "summary": "fixture signal that requires independent replay before confirmation",
        }
    ]


def run_proof_authority_matrix(fixture: Path, out: Path) -> dict[str, Any]:
    """Generate deterministic proof-authority fixtures and mutation matrix."""

    out.mkdir(parents=True, exist_ok=True)
    observation = build_probe_observation(
        observation_id="obs-fixture-001",
        executor_identity="hack-probe-fixture",
        target_identity="fixture-target@sha256:fixture",
        authorization_manifest_sha256=_fixture_component_hash(fixture, "authorization-manifest.json"),
        target_runtime_sha256=_fixture_component_hash(fixture, "runtime-state.json"),
        scan_request_sha256=_fixture_component_hash(fixture, "scan-request.json"),
        probe_spec_sha256=_fixture_component_hash(fixture, "probe-spec.json"),
        probe_exit_code=0,
        signal_type="fixture_reflected_signal",
        finding_class="fixture command signal",
        target_summary="fixture local target identity",
        evidence_summary="fixture observed a bounded signal; independent replay is required",
        evidence_artifacts=_fixture_evidence(fixture),
    )
    observed_dir = out / "observed-unconfirmed"
    observation_path = observed_dir / "attacks" / "probe-observation.json"
    write_json(observation_path, observation)
    unconfirmed_status = resolve_session_proof_status(observed_dir)
    write_json(observed_dir / "report.json", unconfirmed_status)

    replay_spec_artifact = fixture / "replay-spec.json"
    replay_receipt_artifact = fixture / "replay-receipt.json"
    replay_spec_sha = _fixture_component_hash(fixture, "replay-spec.json")
    replay_receipt_sha = _fixture_component_hash(fixture, "replay-receipt.json")
    validation = build_proof_validation_receipt(
        validation_id="validation-fixture-001",
        observation_path=observation_path,
        replay_spec_sha256=replay_spec_sha,
        replay_spec_artifact=replay_spec_artifact,
        replay_receipt_sha256=replay_receipt_sha,
        replay_receipt_artifact=replay_receipt_artifact,
        replay_command=["fixture-replay", "--observation", str(observation_path)],
    )
    confirmed_dir = out / "confirmed"
    confirmed_observation_path = confirmed_dir / "attacks" / "probe-observation.json"
    write_json(confirmed_observation_path, observation)
    validation = build_proof_validation_receipt(
        validation_id="validation-fixture-001",
        observation_path=confirmed_observation_path,
        replay_spec_sha256=replay_spec_sha,
        replay_spec_artifact=replay_spec_artifact,
        replay_receipt_sha256=replay_receipt_sha,
        replay_receipt_artifact=replay_receipt_artifact,
        replay_command=["fixture-replay", "--observation", str(confirmed_observation_path)],
    )
    validation_path = confirmed_dir / "attacks" / "proof-validation-receipt.json"
    write_json(validation_path, validation)
    confirmed_receipt = validate_proof_validation_receipt(validation_path, confirmed_observation_path)

    mutation_dir = out / "mutations"
    mutation_cases: list[dict[str, Any]] = []

    def add_case(name: str, mutator: Callable[[dict[str, Any], dict[str, Any]], None]) -> None:
        case_dir = mutation_dir / name
        obs = deepcopy(observation)
        val_observation_path = case_dir / "probe-observation.json"
        write_json(val_observation_path, obs)
        val = build_proof_validation_receipt(
            validation_id=f"validation-{name}",
            observation_path=val_observation_path,
            replay_spec_sha256=replay_spec_sha,
            replay_spec_artifact=replay_spec_artifact,
            replay_receipt_sha256=replay_receipt_sha,
            replay_receipt_artifact=replay_receipt_artifact,
            replay_command=["fixture-replay", "--case", name],
        )
        mutator(obs, val)
        write_json(val_observation_path, obs)
        validation_case_path = case_dir / "proof-validation-receipt.json"
        write_json(validation_case_path, val)
        receipt = validate_proof_validation_receipt(validation_case_path, val_observation_path)
        mutation_cases.append(
            {
                "case": name,
                "expected_status": "FAIL",
                "actual_status": receipt["status"],
                "confirmed": receipt["confirms_exploit"],
                "errors": receipt["errors"],
                "observation_path": str(val_observation_path),
                "validation_path": str(validation_case_path),
            }
        )

    add_case("wrong-target", lambda _obs, val: val.__setitem__("target_identity", "wrong@sha256:target"))
    add_case("wrong-authorization-hash", lambda _obs, val: val.__setitem__("authorization_manifest_sha256", "0" * 64))
    add_case("wrong-runtime-hash", lambda _obs, val: val.__setitem__("target_runtime_sha256", "1" * 64))
    add_case("wrong-probe-hash", lambda _obs, val: val.__setitem__("probe_spec_sha256", "2" * 64))
    add_case("wrong-scan-request-hash", lambda _obs, val: val.__setitem__("scan_request_sha256", "3" * 64))
    add_case("wrong-observation-hash", lambda _obs, val: val.__setitem__("observation_artifact_sha256", "4" * 64))
    add_case("self-validator", lambda _obs, val: val.__setitem__("validator_identity", "hack-probe-fixture"))
    add_case("replay-receipt-hash-mismatch", lambda _obs, val: val.__setitem__("replay_receipt_sha256", "5" * 64))
    add_case("stale-receipt", lambda _obs, val: val.__setitem__("created_at", "2000-01-01T00:00:00+00:00"))

    tampered_dir = mutation_dir / "bound-byte-change"
    tampered_observation = deepcopy(observation)
    tampered_path = tampered_dir / "probe-observation.json"
    write_json(tampered_path, tampered_observation)
    tampered_validation = build_proof_validation_receipt(
        validation_id="validation-bound-byte-change",
        observation_path=tampered_path,
        replay_spec_sha256=replay_spec_sha,
        replay_spec_artifact=replay_spec_artifact,
        replay_receipt_sha256=replay_receipt_sha,
        replay_receipt_artifact=replay_receipt_artifact,
        replay_command=["fixture-replay", "--case", "bound-byte-change"],
    )
    tampered_observation["evidence_summary"] = "changed byte after validation"
    write_json(tampered_path, tampered_observation)
    tampered_validation_path = tampered_dir / "proof-validation-receipt.json"
    write_json(tampered_validation_path, tampered_validation)
    tampered_receipt = validate_proof_validation_receipt(tampered_validation_path, tampered_path)
    mutation_cases.append(
        {
            "case": "bound-byte-change",
            "expected_status": "FAIL",
            "actual_status": tampered_receipt["status"],
            "confirmed": tampered_receipt["confirms_exploit"],
            "errors": tampered_receipt["errors"],
            "observation_path": str(tampered_path),
            "validation_path": str(tampered_validation_path),
        }
    )

    matrix_pass = confirmed_receipt["valid"] and confirmed_receipt["confirms_exploit"] and all(
        case["actual_status"] == "FAIL" and case["confirmed"] is False for case in mutation_cases
    )
    matrix = {
        "schema": MATRIX_SCHEMA,
        "status": "PASS" if matrix_pass else "FAIL",
        "mocked": False,
        "live": "local_deterministic_receipt_validation",
        "fixture": str(fixture),
        "out": str(out),
        "observed_unconfirmed": {
            "status": unconfirmed_status["status"],
            "receipt": str(observation_path),
            "report": str(observed_dir / "report.json"),
            "exploit_proven": False,
        },
        "confirmed": {
            "status": "CONFIRMED" if confirmed_receipt["confirms_exploit"] else "VALIDATION_ERROR",
            "observation": str(confirmed_observation_path),
            "receipt": str(validation_path),
            "validation_receipt": confirmed_receipt,
        },
        "mutation_matrix": mutation_cases,
        "claims": {
            "proves": [
                "typed Hack observations do not confirm exploitability",
                "only an independent bound validation receipt can produce CONFIRMED",
                "target/auth/runtime/probe/scan/observation/replay hash mutations fail closed",
            ],
            "does_not_prove": [
                "arbitrary real targets are exploitable",
                "patch effectiveness",
                "Battle reactive Blue loop readiness",
                "provider or model quality",
            ],
        },
    }
    write_json(out / "proof-authority-matrix.json", matrix)
    return matrix


def create_prove_proof_authority_command() -> Callable[..., None]:
    """Create the Typer command for deterministic proof-authority receipts."""

    def prove_proof_authority(
        fixture: Path = typer.Option(..., "--fixture", help="proof-authority fixture directory"),
        out: Path = typer.Option(..., "--out", help="Output directory for proof-authority receipts"),
        json_output: bool = typer.Option(False, "--json", help="Print the full matrix receipt"),
    ) -> None:
        matrix = run_proof_authority_matrix(fixture=fixture, out=out)
        if json_output:
            console.print(json.dumps(matrix, indent=2, sort_keys=True))
        else:
            console.print(f"Proof authority matrix: {out / 'proof-authority-matrix.json'}")
            console.print(f"Status: {matrix['status']}")
        if matrix["status"] != "PASS":
            raise typer.Exit(2)

    return prove_proof_authority


__all__ = [
    "MATRIX_SCHEMA",
    "PROBE_OBSERVATION_SCHEMA",
    "PROOF_VALIDATION_SCHEMA",
    "VALIDATOR_VERSION",
    "build_probe_observation",
    "build_proof_validation_receipt",
    "create_prove_proof_authority_command",
    "file_sha256",
    "json_sha256",
    "resolve_session_proof_status",
    "run_proof_authority_matrix",
    "validate_probe_observation",
    "validate_probe_observation_payload",
    "validate_proof_validation_payload",
    "validate_proof_validation_receipt",
    "write_json",
]
