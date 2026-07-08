#!/usr/bin/env python3
"""Validate a Persona Dream 01->02->06->07 spine chain manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CHAIN_SCHEMA = "persona_dream.spine.chain_contract_manifest.v1"
RECEIPT_SCHEMA = "persona_dream.spine.chain_contract_validator_receipt.v1"
PASS_STATUS = "PASS_SPINE_CHAIN_CONTRACT_GATE"
BLOCKED_STATUS = "BLOCKED_SPINE_CHAIN_CONTRACT"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(base: Path, path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path = Path(path_value)
    return path if path.is_absolute() else base / path


def _block(blockers: list[dict[str, Any]], status: str, **fields: Any) -> None:
    item = {"status": status}
    item.update({key: value for key, value in fields.items() if value is not None})
    blockers.append(item)


def _well_formed_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.match(value) is not None


def _check_file_sha(
    *,
    base: Path,
    path_value: Any,
    sha_value: Any,
    blockers: list[dict[str, Any]],
    missing_status: str,
    hash_status: str,
    field: str,
) -> tuple[Path | None, str | None]:
    path = _resolve(base, path_value)
    if path is None:
        _block(blockers, missing_status, field=f"{field}.path")
        return None, None
    if not path.exists():
        _block(blockers, missing_status, field=f"{field}.path", path=str(path))
        return path, None
    if not _well_formed_sha(sha_value):
        _block(blockers, hash_status, field=f"{field}.sha256", actual=sha_value)
        return path, None
    actual = _sha256_path(path)
    if actual != sha_value:
        _block(blockers, hash_status, field=f"{field}.sha256", expected=sha_value, actual=actual, path=str(path))
    return path, actual


def _get_dotted(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _looks_like_serialized_json(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, (dict, list))


def _iter_values(value: Any, path: str = "") -> list[tuple[str, Any]]:
    found = [(path, value)]
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            found.extend(_iter_values(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_iter_values(child, f"{path}[{index}]"))
    return found


def _check_receipt_status(
    *,
    receipt: Any,
    required_status: Any,
    blockers: list[dict[str, Any]],
    stage: str,
    field: str,
) -> None:
    if not isinstance(receipt, Mapping):
        _block(blockers, "BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_MISSING", stage=stage, field=field)
        return
    actual_status = receipt.get("status")
    if actual_status != required_status:
        _block(
            blockers,
            "BLOCKED_VALIDATOR_STATUS_MISMATCH",
            stage=stage,
            field=f"{field}.status",
            expected=required_status,
            actual=actual_status,
        )
    if isinstance(actual_status, str) and not actual_status.startswith("PASS_"):
        _block(
            blockers,
            "BLOCKED_UNVALIDATED_UPSTREAM_CONTRACT",
            stage=stage,
            field=f"{field}.status",
            actual=actual_status,
        )


def _check_source_policy(contract: Any, blockers: list[dict[str, Any]], stage: str) -> None:
    if not isinstance(contract, Mapping):
        return
    policy = contract.get("source_consumption_policy")
    if isinstance(policy, Mapping):
        for key, value in policy.items():
            if key.startswith("raw_") and key.endswith("_used_as_prompt_text") and value is not False:
                _block(blockers, "BLOCKED_DOWNSTREAM_USED_RAW_SOURCE_TEXT", stage=stage, field=f"source_consumption_policy.{key}")
            if key == "serialized_json_as_prompt_text_allowed" and value is not False:
                _block(blockers, "BLOCKED_SERIALIZED_JSON_PROMPT_TEXT", stage=stage, field=f"source_consumption_policy.{key}")
    if contract.get("serialized_json_as_prompt_text_allowed") is not False:
        _block(blockers, "BLOCKED_SERIALIZED_JSON_PROMPT_TEXT", stage=stage, field="serialized_json_as_prompt_text_allowed")
    for value_path, value in _iter_values(contract):
        if value_path.endswith("source_context") and _looks_like_serialized_json(value):
            _block(blockers, "BLOCKED_SERIALIZED_JSON_PROMPT_TEXT", stage=stage, field=value_path)
    for value_path, value in _iter_values(contract.get("typed_source_context")):
        if value_path.endswith("source_context") and _looks_like_serialized_json(value):
            _block(blockers, "BLOCKED_SERIALIZED_JSON_PROMPT_TEXT", stage=stage, field=f"typed_source_context.{value_path}")


def _load_stage(
    *,
    base: Path,
    stage_key: str,
    stage_spec: Mapping[str, Any],
    expected_schema: str,
    blockers: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    contract_path, contract_sha = _check_file_sha(
        base=base,
        path_value=stage_spec.get("contract_path"),
        sha_value=stage_spec.get("contract_sha256"),
        blockers=blockers,
        missing_status="BLOCKED_MISSING_UPSTREAM_CONTRACT",
        hash_status="BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
        field=f"stages.{stage_key}.contract",
    )
    contract: dict[str, Any] | None = None
    if contract_path and contract_path.exists():
        try:
            loaded = _read_json(contract_path)
            if isinstance(loaded, dict):
                contract = loaded
            else:
                _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", stage=stage_key, field="contract")
        except Exception as exc:  # noqa: BLE001 - receipt should preserve parse failure.
            _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", stage=stage_key, field="contract", error=str(exc))
    if contract is not None and contract.get("schema") != expected_schema:
        _block(
            blockers,
            "BLOCKED_CHAIN_MANIFEST_SCHEMA",
            stage=stage_key,
            field="contract.schema",
            expected=expected_schema,
            actual=contract.get("schema"),
        )
    receipt_path, _receipt_sha = _check_file_sha(
        base=base,
        path_value=stage_spec.get("validator_receipt_path"),
        sha_value=stage_spec.get("validator_receipt_sha256"),
        blockers=blockers,
        missing_status="BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_MISSING",
        hash_status="BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_HASH_MISMATCH",
        field=f"stages.{stage_key}.validator_receipt",
    )
    receipt: Any = None
    if receipt_path and receipt_path.exists():
        try:
            receipt = _read_json(receipt_path)
        except Exception as exc:  # noqa: BLE001
            _block(blockers, "BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_MISSING", stage=stage_key, field="validator_receipt", error=str(exc))
    _check_receipt_status(
        receipt=receipt,
        required_status=stage_spec.get("required_validator_status"),
        blockers=blockers,
        stage=stage_key,
        field="validator_receipt",
    )
    if isinstance(receipt, Mapping) and receipt.get("contract_sha256") not in {None, contract_sha}:
        _block(
            blockers,
            "BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_HASH_MISMATCH",
            stage=stage_key,
            field="validator_receipt.contract_sha256",
            expected=contract_sha,
            actual=receipt.get("contract_sha256"),
        )
    if contract is not None:
        _check_source_policy(contract, blockers, stage_key)
    return contract, contract_sha


def _check_edge_bindings(
    *,
    base: Path,
    manifest: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any] | None],
    contract_shas: Mapping[str, str | None],
    blockers: list[dict[str, Any]],
) -> None:
    bindings = manifest.get("edge_bindings")
    if not isinstance(bindings, list) or not bindings:
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="edge_bindings")
        return
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field=f"edge_bindings[{index}]")
            continue
        if binding.get("schema") != "persona_dream.spine.chain_edge_binding.v1":
            _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field=f"edge_bindings[{index}].schema")
        from_stage = str(binding.get("from_stage") or "")
        to_stage = str(binding.get("to_stage") or "")
        if to_stage == "phase07":
            continue
        expected_sha = contract_shas.get(from_stage)
        if binding.get("from_contract_sha256") != expected_sha:
            _block(
                blockers,
                "BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
                edge=f"{from_stage}->{to_stage}",
                field=f"edge_bindings[{index}].from_contract_sha256",
                expected=expected_sha,
                actual=binding.get("from_contract_sha256"),
            )
        to_contract = contracts.get(to_stage)
        bound = _get_dotted(to_contract, str(binding.get("to_field") or ""))
        if not isinstance(bound, Mapping):
            _block(
                blockers,
                "BLOCKED_MISSING_UPSTREAM_CONTRACT",
                edge=f"{from_stage}->{to_stage}",
                field=binding.get("to_field"),
            )
            continue
        if bound.get("path") != binding.get("from_contract_path"):
            _block(
                blockers,
                "BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
                edge=f"{from_stage}->{to_stage}",
                field=f"{binding.get('to_field')}.path",
                expected=binding.get("from_contract_path"),
                actual=bound.get("path"),
            )
        if bound.get("sha256") != expected_sha:
            _block(
                blockers,
                "BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
                edge=f"{from_stage}->{to_stage}",
                field=f"{binding.get('to_field')}.sha256",
                expected=expected_sha,
                actual=bound.get("sha256"),
            )
        receipt_path = bound.get("validator_receipt_path")
        receipt_sha = bound.get("validator_receipt_sha256")
        _check_file_sha(
            base=base,
            path_value=receipt_path,
            sha_value=receipt_sha,
            blockers=blockers,
            missing_status="BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_MISSING",
            hash_status="BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_HASH_MISMATCH",
            field=f"{binding.get('to_field')}.validator_receipt",
        )


def _check_phase07(
    *,
    base: Path,
    phase07_spec: Mapping[str, Any],
    phase06_path: str | None,
    phase06_sha: str | None,
    blockers: list[dict[str, Any]],
) -> None:
    entries = phase07_spec.get("panel_prompt_contracts")
    if not isinstance(entries, list) or len(entries) != 8:
        _block(blockers, "BLOCKED_MISSING_DOWNSTREAM_CONTRACT", stage="phase07", field="panel_prompt_contracts", expected=8, actual=len(entries) if isinstance(entries, list) else None)
        return
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", stage="phase07", field=f"panel_prompt_contracts[{index}]")
            continue
        label = f"stages.phase07.panel_prompt_contracts[{index}]"
        contract_path, contract_sha = _check_file_sha(
            base=base,
            path_value=entry.get("contract_path"),
            sha_value=entry.get("contract_sha256"),
            blockers=blockers,
            missing_status="BLOCKED_MISSING_DOWNSTREAM_CONTRACT",
            hash_status="BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
            field=f"{label}.contract",
        )
        contract: Any = None
        if contract_path and contract_path.exists():
            try:
                contract = _read_json(contract_path)
            except Exception as exc:  # noqa: BLE001
                _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", stage="phase07", field=f"{label}.contract", error=str(exc))
        if not isinstance(contract, Mapping):
            continue
        if contract.get("schema") != "persona_dream.phase07.panel_prompt_contract.v2":
            _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", stage="phase07", field=f"{label}.contract.schema")
        if "compiled_prompt" in contract:
            _block(blockers, "BLOCKED_COMPILED_PROMPT_PROOF_EMBEDDED_IN_CONTRACT", stage="phase07", field=f"{label}.contract.compiled_prompt")
        script_binding = _get_dotted(contract, "input_contracts.phase06_script_prompt_contract")
        if not isinstance(script_binding, Mapping):
            _block(blockers, "BLOCKED_PHASE07_MISSING_SCRIPT_BINDING", stage="phase07", field=f"{label}.input_contracts.phase06_script_prompt_contract")
        elif script_binding.get("path") != phase06_path:
            _block(
                blockers,
                "BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
                edge="phase06->phase07",
                field=f"{label}.input_contracts.phase06_script_prompt_contract.path",
                expected=phase06_path,
                actual=script_binding.get("path"),
            )
        elif script_binding.get("sha256") != phase06_sha:
            _block(
                blockers,
                "BLOCKED_INTER_CONTRACT_HASH_MISMATCH",
                edge="phase06->phase07",
                field=f"{label}.input_contracts.phase06_script_prompt_contract.sha256",
                expected=phase06_sha,
                actual=script_binding.get("sha256"),
            )
        _check_source_policy(contract, blockers, "phase07")
        receipt_path, _ = _check_file_sha(
            base=base,
            path_value=entry.get("validator_receipt_path"),
            sha_value=entry.get("validator_receipt_sha256"),
            blockers=blockers,
            missing_status="BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_MISSING",
            hash_status="BLOCKED_UPSTREAM_VALIDATOR_RECEIPT_HASH_MISMATCH",
            field=f"{label}.validator_receipt",
        )
        receipt = _read_json(receipt_path) if receipt_path and receipt_path.exists() else None
        _check_receipt_status(receipt=receipt, required_status=entry.get("required_validator_status"), blockers=blockers, stage="phase07", field=f"{label}.validator_receipt")

        compiled = entry.get("compiled_prompt")
        if not isinstance(compiled, Mapping):
            _block(blockers, "BLOCKED_PHASE07_MISSING_COMPILED_PROMPT_PROOF", stage="phase07", field=f"{label}.compiled_prompt")
            continue
        if compiled.get("schema") != "persona_dream.phase07.compiled_prompt_proof.v1":
            _block(blockers, "BLOCKED_PHASE07_MISSING_COMPILED_PROMPT_PROOF", stage="phase07", field=f"{label}.compiled_prompt.schema")
        if not _well_formed_sha(compiled.get("sha256")):
            _block(blockers, "BLOCKED_COMPILED_PROMPT_HASH_MISSING", stage="phase07", field=f"{label}.compiled_prompt.sha256")
        else:
            _check_file_sha(
                base=base,
                path_value=compiled.get("path"),
                sha_value=compiled.get("sha256"),
                blockers=blockers,
                missing_status="BLOCKED_COMPILED_PROMPT_HASH_MISSING",
                hash_status="BLOCKED_COMPILED_PROMPT_HASH_MISMATCH",
                field=f"{label}.compiled_prompt",
            )
        if compiled.get("derived_from_contract_path") != entry.get("contract_path"):
            _block(
                blockers,
                "BLOCKED_COMPILED_PROMPT_CONTRACT_PATH_MISMATCH",
                stage="phase07",
                field=f"{label}.compiled_prompt.derived_from_contract_path",
                expected=entry.get("contract_path"),
                actual=compiled.get("derived_from_contract_path"),
            )
        if compiled.get("derived_from_contract_sha256") != contract_sha:
            _block(
                blockers,
                "BLOCKED_COMPILED_PROMPT_CONTRACT_HASH_MISMATCH",
                stage="phase07",
                field=f"{label}.compiled_prompt.derived_from_contract_sha256",
                expected=contract_sha,
                actual=compiled.get("derived_from_contract_sha256"),
            )
        renderer = compiled.get("renderer")
        if not isinstance(renderer, Mapping) or renderer.get("deterministic") is not True or compiled.get("render_mode") != "deterministic":
            _block(blockers, "BLOCKED_COMPILED_PROMPT_HASH_MISMATCH", stage="phase07", field=f"{label}.compiled_prompt.renderer")
        if compiled.get("may_be_hand_edited") is not False:
            _block(blockers, "BLOCKED_COMPILED_PROMPT_HAND_EDITABLE", stage="phase07", field=f"{label}.compiled_prompt.may_be_hand_edited")


def _check_reviewer_preconditions(
    *,
    base: Path,
    manifest: Mapping[str, Any],
    blockers: list[dict[str, Any]],
) -> None:
    preconditions = manifest.get("reviewer_preconditions")
    if not isinstance(preconditions, Mapping):
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="reviewer_preconditions")
        return
    if preconditions.get("schema") != "persona_dream.spine.reviewer_pass_precondition.v1":
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="reviewer_preconditions.schema")
    for index, claim in enumerate(preconditions.get("acceptance_claims") or []):
        if not isinstance(claim, Mapping):
            _block(blockers, "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT", field=f"reviewer_preconditions.acceptance_claims[{index}]")
            continue
        if claim.get("acceptance_claimed") is not True:
            continue
        if claim.get("validator_receipt_required") is not True or not claim.get("validator_receipt_path"):
            _block(blockers, "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT", field=f"reviewer_preconditions.acceptance_claims[{index}].validator_receipt_path")
            continue
        validator_path, _ = _check_file_sha(
            base=base,
            path_value=claim.get("validator_receipt_path"),
            sha_value=claim.get("validator_receipt_sha256"),
            blockers=blockers,
            missing_status="BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT",
            hash_status="BLOCKED_REVIEWER_PASS_WITH_INVALID_CONTRACT",
            field=f"reviewer_preconditions.acceptance_claims[{index}].validator_receipt",
        )
        receipt = _read_json(validator_path) if validator_path and validator_path.exists() else {}
        status = receipt.get("status") if isinstance(receipt, Mapping) else None
        if not isinstance(status, str) or not status.startswith("PASS_"):
            _block(blockers, "BLOCKED_REVIEWER_PASS_WITH_INVALID_CONTRACT", field=f"reviewer_preconditions.acceptance_claims[{index}].validator_receipt.status", actual=status)
        if claim.get("reviewer_verdict_required") is True:
            verdict_path, _ = _check_file_sha(
                base=base,
                path_value=claim.get("reviewer_verdict_path"),
                sha_value=claim.get("reviewer_verdict_sha256"),
                blockers=blockers,
                missing_status="BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT",
                hash_status="BLOCKED_REVIEWER_PASS_ARTIFACT_HASH_MISMATCH",
                field=f"reviewer_preconditions.acceptance_claims[{index}].reviewer_verdict",
            )
            verdict = _read_json(verdict_path) if verdict_path and verdict_path.exists() else {}
            if isinstance(verdict, Mapping) and verdict.get("validated_artifact_sha256") != claim.get("validated_artifact_sha256"):
                _block(blockers, "BLOCKED_REVIEWER_PASS_ARTIFACT_HASH_MISMATCH", field=f"reviewer_preconditions.acceptance_claims[{index}].validated_artifact_sha256")


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    base = manifest_path.parent
    blockers: list[dict[str, Any]] = []
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:  # noqa: BLE001
        manifest = {}
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="manifest", error=str(exc))
    if not isinstance(manifest, Mapping):
        manifest = {}
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="manifest")
    if manifest.get("schema") != CHAIN_SCHEMA:
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="schema", expected=CHAIN_SCHEMA, actual=manifest.get("schema"))
    if manifest.get("provider_live") is not False:
        _block(blockers, "BLOCKED_PROVIDER_LIVE_IN_LOCAL_CHAIN_GATE", field="provider_live", actual=manifest.get("provider_live"))
    if manifest.get("mocked") is not False:
        _block(blockers, "BLOCKED_MOCKED_CHAIN_PROOF", field="mocked", actual=manifest.get("mocked"))
    if manifest.get("live_image_call_started") is not False:
        _block(blockers, "BLOCKED_LIVE_CALL_STARTED_IN_LOCAL_CHAIN_GATE", field="live_image_call_started", actual=manifest.get("live_image_call_started"))

    stages = manifest.get("stages")
    if not isinstance(stages, Mapping):
        stages = {}
        _block(blockers, "BLOCKED_CHAIN_MANIFEST_SCHEMA", field="stages")

    contracts: dict[str, Mapping[str, Any] | None] = {}
    contract_shas: dict[str, str | None] = {}
    for stage_key, expected_schema in (
        ("phase01", "persona_dream.phase01.memory_residue_contract.v1"),
        ("phase02", "persona_dream.phase02.story_contract_prompt.v1"),
        ("phase06", "persona_dream.phase06.script_prompt_contract.v1"),
    ):
        spec = stages.get(stage_key)
        if not isinstance(spec, Mapping):
            _block(blockers, "BLOCKED_MISSING_UPSTREAM_CONTRACT", stage=stage_key, field=f"stages.{stage_key}")
            contracts[stage_key] = None
            contract_shas[stage_key] = None
            continue
        contract, contract_sha = _load_stage(base=base, stage_key=stage_key, stage_spec=spec, expected_schema=expected_schema, blockers=blockers)
        contracts[stage_key] = contract
        contract_shas[stage_key] = contract_sha

    phase07 = stages.get("phase07")
    if not isinstance(phase07, Mapping):
        _block(blockers, "BLOCKED_MISSING_DOWNSTREAM_CONTRACT", stage="phase07", field="stages.phase07")
    else:
        phase06_spec = stages.get("phase06") if isinstance(stages.get("phase06"), Mapping) else {}
        _check_phase07(
            base=base,
            phase07_spec=phase07,
            phase06_path=phase06_spec.get("contract_path") if isinstance(phase06_spec, Mapping) else None,
            phase06_sha=contract_shas.get("phase06"),
            blockers=blockers,
        )
    _check_edge_bindings(base=base, manifest=manifest, contracts=contracts, contract_shas=contract_shas, blockers=blockers)
    _check_reviewer_preconditions(base=base, manifest=manifest, blockers=blockers)

    status = PASS_STATUS if not blockers else BLOCKED_STATUS
    return {
        "schema": RECEIPT_SCHEMA,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha256_path(manifest_path.resolve()) if manifest_path.exists() else None,
        "status": status,
        "verdict": "PASS" if status == PASS_STATUS else "FAIL_CLOSED",
        "provider_live": manifest.get("provider_live") is True,
        "mocked": manifest.get("mocked") is True,
        "live_image_call_started": manifest.get("live_image_call_started") is True,
        "blockers": blockers,
        "claims": {
            "proves": [
                "inter-contract path/SHA binding",
                "validator receipt binding",
                "compiled prompt hash binding",
                "raw-source-safe downstream consumption",
                "reviewer PASS precondition policy where acceptance is claimed",
                "local non-provider chain gate",
            ],
            "does_not_prove": [
                "provider reference attachment",
                "image generation",
                "visual identity pass",
                "story/script creative quality",
                "runtime performance",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    args = parser.parse_args()

    receipt = validate_manifest(args.manifest)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
