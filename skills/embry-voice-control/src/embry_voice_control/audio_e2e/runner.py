"""Durable execution for audio-first Embry E2E campaigns.

Counted listener input must enter through the existing managed listener and live
voice journal.  This runner composes the already-proven journal -> Memory -> Tau
and Tau -> Chatterbox proof lanes with explicit event identifiers and durable
per-turn receipt locators.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from embry_voice_control.event_journal import append_event, session_snapshot
from .case_executor import CaseExecutor, ManagedListenerProcess


PRODUCER = "embry-voice-control.audio-e2e"
TURN_STAGE_ORDER = (
    "pending",
    "listener_complete",
    "source_evidence_complete",
    "memory_tau_complete",
    "render_complete",
    "completed",
)
PHYSICAL_SOURCE_MODES = {
    "physical_live_horus",
    "recorded_physical_horus",
}
CLONE_SOURCE_MODES = {
    "qualified_horus_clone",
    # Backward-compatible alias used by the first compiled manifest.
    "qualified_horus_audio",
}
INTERMEDIATE_PROOF_SCOPE = {
    "id": "mixed_qualified_audio_intermediate_regression",
    "listener_required": True,
    "memory_live_required": True,
    "tau_live_required": True,
    "chatterbox_live_required": True,
    "typed_transcript_allowed": False,
    "mocked_services_allowed": False,
    "release_readiness_authority": False,
}
SKILL_ROOT = Path(__file__).resolve().parents[3]
JOURNAL_MEMORY_TAU_SCRIPT = (
    SKILL_ROOT
    / "proofs/tau/embry-journal-memory-tau-live/scripts/"
    "run_journal_memory_tau_proof.py"
)
RENDER_TAU_PLAN_SCRIPT = (
    SKILL_ROOT
    / "proofs/tau/embry-journal-memory-tau-live/scripts/"
    "render_tau_turn_plan.py"
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def artifact_locator(path: Path) -> dict[str, str]:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": sha256_path(path)}


def load_locator(locator: dict[str, Any], *, label: str) -> tuple[Path, dict[str, Any]]:
    path = Path(str(locator.get("path") or "")).resolve()
    expected = str(locator.get("sha256") or "")
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    actual = sha256_path(path)
    if actual != expected:
        raise ValueError(f"{label}_hash_mismatch:{expected}:{actual}")
    return path, read_json(path)


def verify_file_locator(locator: dict[str, Any], *, label: str) -> Path:
    path = Path(str(locator.get("path") or "")).resolve()
    expected = str(locator.get("sha256") or "")
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    actual = sha256_path(path)
    if actual != expected:
        raise ValueError(f"{label}_hash_mismatch:{expected}:{actual}")
    return path


def default_state_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(manifest_path.suffix + ".state.json")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != "embry.audio_e2e_campaign_manifest.v1":
        raise ValueError("campaign_manifest_schema_invalid")
    execution = manifest.get("execution", {})
    if execution.get("typed_transcript_allowed") is not False:
        raise ValueError("typed_transcript_not_allowed")
    if execution.get("fixture_substitution_allowed") is not False:
        raise ValueError("fixture_substitution_not_allowed")
    if execution.get("browser_microphone_allowed") is not False:
        raise ValueError("browser_microphone_not_allowed")
    allowed_modes = {
        "physical_live_horus",
        "recorded_physical_horus",
        "qualified_horus_clone",
        "qualified_horus_audio",
    }
    for case in manifest.get("cases", []):
        if case.get("source_mode") not in allowed_modes:
            raise ValueError("source_mode_not_countable")
        if not case.get("turn_script"):
            raise ValueError(f"case_turn_script_empty:{case.get('case_id')}")


def _new_turn_state() -> dict[str, Any]:
    return {
        "stage": "pending",
        "receipts": {},
        "failure": None,
        "failure_history": [],
        "updated_at": utc_now(),
    }


def initial_state(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "embry.audio_e2e_stage_state.v2",
        "campaign_id": manifest["campaign_id"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_value(manifest),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "running",
        "suite_ready": False,
        "proof_scope": dict(INTERMEDIATE_PROOF_SCOPE),
        "cases": {
            case["case_id"]: {
                "session_id": case["session_id"],
                "attempt_id": case["attempt_id"],
                "stage": "compiled",
                "turns": {
                    turn["turn_id"]: _new_turn_state()
                    for turn in case["turn_script"]
                },
                "failure_bundle": None,
                "failure_history": [],
            }
            for case in manifest["cases"]
        },
    }


def _upgrade_state(manifest: dict[str, Any], state: dict[str, Any]) -> None:
    state["schema"] = "embry.audio_e2e_stage_state.v2"
    state["suite_ready"] = False
    state["proof_scope"] = dict(INTERMEDIATE_PROOF_SCOPE)
    for case in manifest["cases"]:
        case_state = state.setdefault("cases", {}).setdefault(
            case["case_id"],
            {
                "session_id": case["session_id"],
                "attempt_id": case["attempt_id"],
                "stage": "compiled",
            },
        )
        turns = case_state.setdefault("turns", {})
        for turn in case["turn_script"]:
            turn_state = turns.setdefault(turn["turn_id"], _new_turn_state())
            if turn_state.get("stage") == "speaker_evidence_complete":
                turn_state["stage"] = "source_evidence_complete"
            receipts = turn_state.setdefault("receipts", {})
            if "speaker_evidence" in receipts and "source_evidence" not in receipts:
                receipts["source_evidence"] = receipts.pop("speaker_evidence")
        case_state.setdefault("failure_history", [])
        case_state.setdefault("failure_bundle", None)


def load_or_create_state(
    manifest_path: Path,
    state_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(manifest_path)
    validate_manifest(manifest)
    if state_path.exists():
        state = read_json(state_path)
        if state.get("manifest_sha256") != sha256_value(manifest):
            raise ValueError("state_manifest_hash_mismatch")
        _upgrade_state(manifest, state)
        return manifest, state
    state = initial_state(manifest_path, manifest)
    write_json(state_path, state)
    return manifest, state


def _event(
    *,
    event_type: str,
    case: dict[str, Any],
    campaign_id: str,
    payload: dict[str, Any],
    causation_id: str = "root",
) -> dict[str, Any]:
    seed = {
        "type": event_type,
        "session_id": case["session_id"],
        "payload": payload,
    }
    return {
        "schema": "embry.voice_event.v1",
        "event_id": event_type + "." + hashlib.sha256(canonical(seed)).hexdigest()[:16],
        "session_id": case["session_id"],
        "turn_id": (
            case["turn_script"][0]["turn_id"]
            if case.get("turn_script")
            else case["case_id"]
        ),
        "type": event_type,
        "created_at": utc_now(),
        "causation_id": causation_id,
        "correlation_id": campaign_id,
        "producer": PRODUCER,
        "mocked": False,
        "live": True,
        "artifact_hashes": {
            key: value for key, value in payload.items() if key.endswith("sha256")
        },
        "receipt_hash": sha256_value(seed),
        "payload": payload,
    }


def _turn_dir(live_config: dict[str, Any], case_id: str, turn_id: str) -> Path:
    return (
        Path(live_config["campaign_dir"])
        / "cases"
        / case_id
        / "turns"
        / turn_id
    )


def _persist_listener_receipt(
    live_config: dict[str, Any],
    case_id: str,
    turn_id: str,
    receipt: dict[str, Any],
) -> dict[str, str]:
    path = _turn_dir(live_config, case_id, turn_id) / "listener" / "receipt.json"
    write_json(path, receipt)
    return artifact_locator(path)


def _managed_listener_state(
    run_dir: Path,
    *,
    expected_source_node: str,
) -> tuple[int, int] | None:
    state_path = run_dir / "state.json"
    if not state_path.exists():
        if run_dir.exists() and any(run_dir.iterdir()):
            raise ValueError(f"managed_listener_run_state_missing:{run_dir}")
        return None
    if not state_path.is_file():
        raise ValueError(f"managed_listener_run_state_not_file:{state_path}")
    state = read_json(state_path)
    if state.get("schema") != "realtimestt.physical_hot_mic_listener_state.v1":
        raise ValueError(f"managed_listener_run_state_schema_invalid:{state_path}")
    if state.get("source_node") != expected_source_node:
        raise ValueError(f"managed_listener_run_source_node_mismatch:{run_dir}")
    try:
        target_cycles = int(state["target_cycles"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"managed_listener_run_target_invalid:{state_path}") from exc
    completed_cycles = state.get("completed_cycles")
    if target_cycles < 1 or not isinstance(completed_cycles, list):
        raise ValueError(f"managed_listener_run_cycles_invalid:{state_path}")
    completed_count = len(completed_cycles)
    if completed_count > target_cycles:
        raise ValueError(
            "managed_listener_run_completed_exceeds_target:"
            f"{state_path}:{completed_count}:{target_cycles}"
        )
    return target_cycles, completed_count


def _select_managed_listener_run(
    *,
    campaign_dir: Path,
    source_node: str,
    campaign_turn_count: int,
    pending_turn_count: int,
) -> tuple[Path, int]:
    base_run_dir = campaign_dir / "managed-listener"
    base_state = _managed_listener_state(
        base_run_dir,
        expected_source_node=source_node,
    )
    if base_state is None:
        return base_run_dir, campaign_turn_count
    base_target, base_completed = base_state
    if base_completed < base_target:
        return base_run_dir, base_target

    rollover_index = 1
    while True:
        rollover_dir = campaign_dir / f"managed-listener-rollover-{rollover_index:03d}"
        rollover_state = _managed_listener_state(
            rollover_dir,
            expected_source_node=source_node,
        )
        if rollover_state is None:
            return rollover_dir, pending_turn_count
        rollover_target, rollover_completed = rollover_state
        if rollover_completed < rollover_target:
            return rollover_dir, rollover_target
        rollover_index += 1


def _migrate_inline_listener_receipts(
    state: dict[str, Any],
    manifest: dict[str, Any],
    live_config: dict[str, Any],
) -> None:
    for case in manifest["cases"]:
        case_state = state["cases"][case["case_id"]]
        inline = case_state.pop("listener_turns", None)
        if not isinstance(inline, list):
            continue
        for receipt in inline:
            turn_id = str(receipt.get("turn_id") or "")
            if turn_id not in case_state["turns"]:
                raise ValueError(f"legacy_listener_turn_unknown:{turn_id}")
            normalized = {
                "schema": "embry.audio_e2e.listener_turn_receipt.v1",
                "status": "PASS",
                "case_id": case["case_id"],
                "source_mode": case["source_mode"],
                "fresh_physical_human_speech": (
                    case["source_mode"] == "physical_live_horus"
                ),
                **receipt,
            }
            locator = _persist_listener_receipt(
                live_config,
                case["case_id"],
                turn_id,
                normalized,
            )
            turn_state = case_state["turns"][turn_id]
            turn_state["receipts"]["listener"] = locator
            turn_state["stage"] = "listener_complete"
            turn_state["updated_at"] = utc_now()
        case_state["stage"] = "listener_complete"
        case_state.pop("failed_stage", None)


def _read_audio_assets(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    value = read_json(Path(path))
    if value.get("schema") != "embry.audio_e2e_audio_assets.v1":
        raise ValueError("audio_assets_manifest_schema_invalid")
    if not isinstance(value.get("cases"), dict):
        raise ValueError("audio_assets_cases_missing")
    return value


def _verified_audio_locator(value: Any, *, label: str) -> Path:
    if not isinstance(value, dict):
        raise ValueError(f"{label}_locator_missing")
    return verify_file_locator(value, label=label)


def _source_contract_name(case: dict[str, Any]) -> str:
    source_mode = str(case.get("source_mode") or "")
    if source_mode in PHYSICAL_SOURCE_MODES:
        return "physical_horus_identity"
    if source_mode in CLONE_SOURCE_MODES:
        return "qualified_horus_clone"
    raise ValueError(f"source_mode_not_executable:{source_mode}")


def _json_contains_scalar(value: Any, expected: str) -> bool:
    expected_normalized = str(expected).removeprefix("sha256:")
    if isinstance(value, dict):
        return any(_json_contains_scalar(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_json_contains_scalar(item, expected) for item in value)
    if isinstance(value, str):
        actual = value.removeprefix("sha256:")
        return actual == expected_normalized
    return False


def _post_wake_query(spoken_text: str) -> str:
    text = spoken_text.strip()
    prefix = "hey embry"
    if text.lower().startswith(prefix):
        text = text[len(prefix):].lstrip(" ,.!?;:-")
    if not text:
        raise ValueError("post_wake_query_empty")
    return text


def _clone_contract_locator(
    case: dict[str, Any],
    live_config: dict[str, Any],
) -> dict[str, str]:
    case_locator = case.get("clone_source_contract")
    if isinstance(case_locator, dict):
        load_locator(case_locator, label=f"clone_source_contract:{case['case_id']}")
        return {
            "path": str(Path(case_locator["path"]).resolve()),
            "sha256": str(case_locator["sha256"]),
        }
    configured = live_config.get("clone_source_contract_receipt")
    if not configured:
        raise ValueError("clone_source_contract_receipt_required")
    return artifact_locator(Path(configured))


def _physical_qualification_locator(
    case: dict[str, Any],
    live_config: dict[str, Any],
) -> dict[str, str]:
    case_locator = case.get("speaker_qualification")
    if isinstance(case_locator, dict):
        load_locator(case_locator, label=f"speaker_qualification:{case['case_id']}")
        return {
            "path": str(Path(case_locator["path"]).resolve()),
            "sha256": str(case_locator["sha256"]),
        }
    configured = live_config.get("speaker_qualification_receipt")
    if not configured:
        raise ValueError("speaker_qualification_receipt_required")
    return artifact_locator(Path(configured))


def _load_source_contract(
    case: dict[str, Any],
    live_config: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    contract_name = _source_contract_name(case)
    if contract_name == "physical_horus_identity":
        locator = _physical_qualification_locator(case, live_config)
        _, receipt = load_locator(
            locator,
            label=f"speaker_qualification:{case['case_id']}",
        )
        required = (
            "speaker_id",
            "profile_sha256",
            "threshold",
            "ambiguity_margin",
        )
        missing = [key for key in required if receipt.get(key) is None]
        if missing:
            raise ValueError(
                "speaker_qualification_fields_missing:" + ",".join(missing)
            )
        if receipt.get("status") != "PASS":
            raise ValueError("speaker_qualification_not_pass")
        if receipt.get("mocked") is True:
            raise ValueError("speaker_qualification_mocked")
        if receipt.get("live") is not True:
            raise ValueError("speaker_qualification_not_live")
        if receipt.get("speaker_id") != "horus_lupercal":
            raise ValueError("speaker_qualification_not_horus")
        threshold = float(receipt["threshold"])
        ambiguity_margin = float(receipt["ambiguity_margin"])
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("speaker_qualification_threshold_invalid")
        if not 0.0 <= ambiguity_margin <= 1.0:
            raise ValueError("speaker_qualification_margin_invalid")
        return locator, {
            **receipt,
            "source_contract": contract_name,
            "source_identity": "horus_lupercal",
            "voice_persona": "horus_lupercal",
            "speaker_identity_proven": True,
            "allow_personal_memory": True,
            "release_readiness_authority": False,
            "suite_ready": False,
        }

    locator = _clone_contract_locator(case, live_config)
    _, receipt = load_locator(
        locator,
        label=f"clone_source_contract:{case['case_id']}",
    )
    if receipt.get("schema") != "embry.audio_e2e.clone_source_contract.v1":
        raise ValueError("clone_source_contract_schema_invalid")
    required_exact = {
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": "qualified_horus_clone",
        "source_identity": "qualified_horus_clone",
        "voice_persona": "horus_lupercal",
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "memory_source_policy": "non_personal_persona_project_scope",
        "release_readiness_authority": False,
        "suite_ready": False,
    }
    for key, expected in required_exact.items():
        if receipt.get(key) != expected:
            raise ValueError(
                f"clone_source_contract_field_invalid:{key}:"
                f"{receipt.get(key)!r}:{expected!r}"
            )
    checkpoint = receipt.get("checkpoint") or {}
    checkpoint_id = str(checkpoint.get("id") or "")
    checkpoint_sha256 = str(checkpoint.get("sha256") or "")
    if not checkpoint_id or not checkpoint_sha256.startswith("sha256:"):
        raise ValueError("clone_checkpoint_provenance_missing")
    training_locator = checkpoint.get("training_receipt")
    if not isinstance(training_locator, dict):
        raise ValueError("clone_training_receipt_locator_missing")
    _, training_receipt = load_locator(
        training_locator,
        label="clone_training_receipt",
    )
    if not _json_contains_scalar(training_receipt, checkpoint_id):
        raise ValueError("clone_training_checkpoint_id_missing")
    if not _json_contains_scalar(training_receipt, checkpoint_sha256):
        raise ValueError("clone_training_checkpoint_hash_missing")
    persona = receipt.get("persona_provenance") or {}
    if persona.get("speaker_id") != "horus_lupercal":
        raise ValueError("clone_persona_provenance_not_horus")
    profile_sha256 = str(persona.get("profile_sha256") or "")
    if not profile_sha256.startswith("sha256:"):
        raise ValueError("clone_persona_profile_hash_missing")
    enrollment_locator = persona.get("physical_enrollment_receipt")
    if not isinstance(enrollment_locator, dict):
        raise ValueError("clone_persona_enrollment_locator_missing")
    _, enrollment = load_locator(
        enrollment_locator,
        label="clone_persona_enrollment",
    )
    if not _json_contains_scalar(enrollment, profile_sha256):
        raise ValueError("clone_persona_profile_hash_mismatch")
    return locator, receipt


def _verified_clone_asset(
    value: Any,
    *,
    label: str,
    contract_locator: dict[str, str],
    contract: dict[str, Any],
    expected_role: str,
    expected_case_id: str | None = None,
    expected_turn_id: str | None = None,
    expected_spoken_text_sha256: str | None = None,
    expected_generated_prompt: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}_bundle_missing")
    audio_locator = value.get("audio")
    inference_locator = value.get("inference_receipt")
    if not isinstance(audio_locator, dict):
        raise ValueError(f"{label}_audio_locator_missing")
    if not isinstance(inference_locator, dict):
        raise ValueError(f"{label}_inference_receipt_locator_missing")
    audio_path = verify_file_locator(audio_locator, label=f"{label}:audio")
    _, inference = load_locator(
        inference_locator,
        label=f"{label}:inference_receipt",
    )
    required_binding = {
        "schema": "embry.audio_e2e.orpheus_inference_binding.v1",
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": "qualified_horus_clone",
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": expected_role,
    }
    for key, expected in required_binding.items():
        if inference.get(key) != expected:
            raise ValueError(
                f"{label}_inference_binding_field_invalid:{key}:"
                f"{inference.get(key)!r}:{expected!r}"
            )

    if expected_case_id is not None and inference.get("case_id") != expected_case_id:
        raise ValueError(f"{label}_case_binding_mismatch")
    if expected_turn_id is not None and inference.get("turn_id") != expected_turn_id:
        raise ValueError(f"{label}_turn_binding_mismatch")
    if (
        expected_spoken_text_sha256 is not None
        and inference.get("planned_spoken_text_sha256")
        != expected_spoken_text_sha256
    ):
        raise ValueError(f"{label}_spoken_text_hash_mismatch")

    original_locator = inference.get("original_inference_receipt")
    if not isinstance(original_locator, dict):
        raise ValueError(f"{label}_original_inference_receipt_missing")
    _, original_inference = load_locator(
        original_locator,
        label=f"{label}:original_inference_receipt",
    )
    if original_inference.get("status") != "PASS":
        raise ValueError(f"{label}_original_inference_not_pass")
    if original_inference.get("speaker") != "horus":
        raise ValueError(f"{label}_original_inference_not_horus")
    if original_inference.get("mocked") is True:
        raise ValueError(f"{label}_original_inference_mocked")
    if (
        "live" in original_inference
        and original_inference.get("live") is not True
    ):
        raise ValueError(f"{label}_original_inference_not_live")
    if expected_generated_prompt is not None:
        original_prompt = str(original_inference.get("prompt") or "")
        if original_prompt.casefold() != expected_generated_prompt.casefold():
            raise ValueError(f"{label}_original_inference_prompt_mismatch")
        prompt_sha256 = "sha256:" + hashlib.sha256(
            original_prompt.encode("utf-8")
        ).hexdigest()
        if inference.get("generated_prompt_sha256") != prompt_sha256:
            raise ValueError(f"{label}_generated_prompt_hash_mismatch")

    checkpoint = contract["checkpoint"]
    if str(inference.get("generated_audio_sha256") or "") != str(
        audio_locator["sha256"]
    ):
        raise ValueError(f"{label}_generated_audio_hash_mismatch")
    inference_checkpoint = inference.get("checkpoint") or {}
    if inference_checkpoint.get("id") != checkpoint["id"]:
        raise ValueError(f"{label}_checkpoint_id_mismatch")
    if inference_checkpoint.get("sha256") != checkpoint["sha256"]:
        raise ValueError(f"{label}_checkpoint_hash_mismatch")
    return {
        "audio": {
            "path": str(audio_path),
            "sha256": str(audio_locator["sha256"]),
        },
        "inference_receipt": {
            "path": str(Path(inference_locator["path"]).resolve()),
            "sha256": str(inference_locator["sha256"]),
            "asset_role": expected_role,
            "case_id": inference.get("case_id"),
            "turn_id": inference.get("turn_id"),
            "planned_spoken_text_sha256": inference.get(
                "planned_spoken_text_sha256"
            ),
            "original_inference_receipt": {
                "path": str(Path(original_locator["path"]).resolve()),
                "sha256": str(original_locator["sha256"]),
            },
        },
        "source": {
            "source_contract": "qualified_horus_clone",
            "source_identity": "qualified_horus_clone",
            "voice_persona": "horus_lupercal",
            "fresh_physical_human_speech": False,
            "speaker_identity_proven": False,
            "allow_personal_memory": False,
            "release_readiness_authority": False,
            "source_contract_receipt": contract_locator,
            "checkpoint": {
                "id": checkpoint["id"],
                "sha256": checkpoint["sha256"],
                "training_receipt": checkpoint["training_receipt"],
            },
        },
    }


def _turn_audio_assets(
    case: dict[str, Any],
    turn: dict[str, Any],
    live_config: dict[str, Any],
    assets: dict[str, Any] | None,
    contract_locator: dict[str, str],
    contract: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_mode = case["source_mode"]
    if source_mode == "physical_live_horus":
        return None, None
    if source_mode == "recorded_physical_horus":
        raise ValueError(
            "recorded_physical_horus_requires_event_specific_asset_contract"
        )
    if assets is None:
        raise ValueError("qualified_horus_clone_assets_manifest_required")
    case_assets = (assets.get("cases") or {}).get(case["case_id"])
    if not isinstance(case_assets, dict):
        raise ValueError(f"case_audio_assets_missing:{case['case_id']}")
    turn_assets = case_assets.get("turns") or {}
    source_value = turn_assets.get(turn["turn_id"])
    source_asset = _verified_clone_asset(
        source_value,
        label=f"turn_audio:{case['case_id']}:{turn['turn_id']}",
        contract_locator=contract_locator,
        contract=contract,
        expected_role="turn_query",
        expected_case_id=case["case_id"],
        expected_turn_id=turn["turn_id"],
        expected_spoken_text_sha256=turn.get(
            "spoken_text_sha256",
            turn["utterance_sha256"],
        ),
        expected_generated_prompt=_post_wake_query(
            str(turn.get("spoken_text") or turn["utterance"])
        ),
    )
    wake_value = case_assets.get("wake_audio") or assets.get("wake_audio")
    wake_asset = _verified_clone_asset(
        wake_value,
        label=f"wake_audio:{case['case_id']}",
        contract_locator=contract_locator,
        contract=contract,
        expected_role="wake",
    )
    return wake_asset, source_asset


def _validate_clone_asset_index(
    manifest: dict[str, Any],
    live_config: dict[str, Any],
    assets: dict[str, Any] | None,
    contracts: dict[str, tuple[dict[str, str], dict[str, Any]]],
) -> None:
    inference_receipts: dict[str, tuple[str, str]] = {}
    original_inference_receipts: dict[str, tuple[str, str]] = {}
    source_audio_hashes: dict[str, tuple[str, str]] = {}
    for case in manifest["cases"]:
        if case["source_mode"] not in CLONE_SOURCE_MODES:
            continue
        contract_locator, contract = contracts[case["case_id"]]
        for turn in case["turn_script"]:
            _, source_asset = _turn_audio_assets(
                case,
                turn,
                live_config,
                assets,
                contract_locator,
                contract,
            )
            assert source_asset is not None
            receipt_sha = source_asset["inference_receipt"]["sha256"]
            owner = inference_receipts.get(receipt_sha)
            current = (case["case_id"], turn["turn_id"])
            if owner is not None and owner != current:
                raise ValueError(
                    "clone_inference_receipt_reused_across_turns:"
                    f"{receipt_sha}:{owner}:{current}"
                )
            inference_receipts[receipt_sha] = current

            original_sha = source_asset["inference_receipt"][
                "original_inference_receipt"
            ]["sha256"]
            original_owner = original_inference_receipts.get(original_sha)
            if original_owner is not None and original_owner != current:
                raise ValueError(
                    "clone_original_inference_receipt_reused_across_turns:"
                    f"{original_sha}:{original_owner}:{current}"
                )
            original_inference_receipts[original_sha] = current

            audio_sha = source_asset["audio"]["sha256"]
            audio_owner = source_audio_hashes.get(audio_sha)
            if audio_owner is not None and audio_owner != current:
                raise ValueError(
                    "clone_source_audio_reused_across_turns:"
                    f"{audio_sha}:{audio_owner}:{current}"
                )
            source_audio_hashes[audio_sha] = current


def _ensure_case_started(
    journal_db: Path,
    campaign_id: str,
    case: dict[str, Any],
    case_state: dict[str, Any],
    contract_locator: dict[str, str],
    contract: dict[str, Any],
) -> None:
    if case_state.get("stage") not in {"compiled", "listener_complete"}:
        return
    snapshot = session_snapshot(journal_db, case["session_id"])
    existing = next(
        (
            event
            for event in snapshot["events"]
            if event.get("type") == "audio_e2e.case_started"
            and event.get("payload", {}).get("case_id") == case["case_id"]
        ),
        None,
    )
    event = existing or append_event(
        journal_db,
        _event(
            event_type="audio_e2e.case_started",
            case=case,
            campaign_id=campaign_id,
            payload={
                "case_id": case["case_id"],
                "contract_sha256": case["contract_sha256"],
                "source_mode": case["source_mode"],
                "fresh_physical_human_speech": (
                    case["source_mode"] == "physical_live_horus"
                ),
                "source_contract": _source_contract_name(case),
                "source_identity": contract["source_identity"],
                "speaker_identity_proven": bool(
                    contract["speaker_identity_proven"]
                ),
                "allow_personal_memory": bool(
                    contract["allow_personal_memory"]
                ),
                "release_readiness_authority": False,
                "suite_ready": False,
                "source_contract_receipt_path": contract_locator["path"],
                "source_contract_receipt_sha256": contract_locator["sha256"],
            },
        ),
    )
    case_state["stage"] = "running"
    case_state["last_event_id"] = event["event_id"]


def _resolve_final_event(
    journal_db: Path,
    case: dict[str, Any],
    turn: dict[str, Any],
    listener_receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = session_snapshot(journal_db, case["session_id"])
    source = next(
        (
            event
            for event in snapshot["events"]
            if event.get("event_id") == listener_receipt["final_event_id"]
        ),
        None,
    )
    if source is None or source.get("type") != "listener.final_transcript":
        raise ValueError("listener_final_event_missing")
    actual = (
        source.get("session_id"),
        source.get("turn_id"),
        source.get("sequence"),
    )
    expected = (
        case["session_id"],
        turn["turn_id"],
        listener_receipt["final_sequence"],
    )
    if actual != expected:
        raise ValueError(f"listener_final_lineage_mismatch:{actual}:{expected}")
    if source.get("live") is not True or source.get("mocked") is not False:
        raise ValueError("listener_final_not_live")
    if listener_receipt.get("typed_transcript_used") is not False:
        raise ValueError("listener_typed_transcript_not_forbidden")
    if case["source_mode"] in CLONE_SOURCE_MODES:
        if listener_receipt.get("fresh_physical_human_speech") is not False:
            raise ValueError("clone_listener_claims_fresh_physical_speech")
        if listener_receipt.get("speaker_identity_proven") is not False:
            raise ValueError("clone_listener_claims_speaker_identity")
        if listener_receipt.get("allow_personal_memory") is not False:
            raise ValueError("clone_listener_claims_personal_memory")
    payload = source.get("payload") or {}
    if not str(payload.get("text") or payload.get("request_text") or "").strip():
        raise ValueError("listener_final_text_empty")
    if payload.get("audio_sha256") != listener_receipt.get("audio_sha256"):
        raise ValueError("listener_final_audio_hash_mismatch")
    return source, snapshot


def _source_evidence_event(
    journal_db: Path,
    campaign_id: str,
    case: dict[str, Any],
    source: dict[str, Any],
    listener_receipt: dict[str, Any],
    contract_locator: dict[str, str],
    contract: dict[str, Any],
) -> dict[str, Any]:
    snapshot = session_snapshot(journal_db, case["session_id"])
    if case["source_mode"] in PHYSICAL_SOURCE_MODES:
        matching = [
            event
            for event in snapshot["events"]
            if event.get("type") == "speaker.verification.completed"
            and event.get("turn_id") == source["turn_id"]
            and (event.get("payload") or {}).get("audio_sha256")
                == source.get("payload", {}).get("audio_sha256")
        ]
        if len(matching) != 1:
            raise ValueError(
                "physical_event_specific_speaker_verification_required:"
                f"count={len(matching)}"
            )
        event = matching[0]
        payload = event.get("payload") or {}
        if payload.get("profile_hash") != contract["profile_sha256"]:
            raise ValueError("physical_speaker_profile_hash_mismatch")
        if payload.get("speaker_id") != "horus_lupercal":
            raise ValueError("physical_speaker_identity_not_horus")
        candidates = payload.get("candidates") or []
        horus = next(
            (
                candidate
                for candidate in candidates
                if candidate.get("speaker_id") == "horus_lupercal"
            ),
            None,
        )
        if horus is None:
            raise ValueError("physical_horus_candidate_missing")
        if float(horus.get("confidence") or 0.0) < float(contract["threshold"]):
            raise ValueError("physical_horus_candidate_below_threshold")
        if payload.get("speaker_identity_proven") is False:
            raise ValueError("physical_speaker_identity_not_proven")
        return event

    matching = [
        event
        for event in snapshot["events"]
        if event.get("type") == "audio_source.qualification.completed"
        and event.get("turn_id") == source["turn_id"]
        and event.get("causation_id") == source["event_id"]
    ]
    if len(matching) > 1:
        raise ValueError("multiple_clone_source_evidence_events")
    source_asset = listener_receipt.get("source_asset")
    if not isinstance(source_asset, dict):
        raise ValueError("clone_listener_source_asset_missing")
    if matching:
        event = matching[0]
        payload = event.get("payload") or {}
        expected = {
            "source_contract": "qualified_horus_clone",
            "source_identity": "qualified_horus_clone",
            "speaker_identity_proven": False,
            "fresh_physical_human_speech": False,
            "allow_personal_memory": False,
            "listener_audio_sha256": source["payload"]["audio_sha256"],
            "source_audio_sha256": source_asset["audio"]["sha256"],
            "inference_receipt_sha256": source_asset["inference_receipt"]["sha256"],
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError("existing_clone_source_evidence_conflict")
        return event

    payload = {
        "source_contract": "qualified_horus_clone",
        "source_identity": "qualified_horus_clone",
        "voice_persona": "horus_lupercal",
        "source_mode": case["source_mode"],
        "source_authority_id": listener_receipt["source_authority_id"],
        "listener_audio_sha256": source["payload"]["audio_sha256"],
        "source_audio_sha256": source_asset["audio"]["sha256"],
        "inference_receipt": source_asset["inference_receipt"],
        "inference_receipt_sha256": source_asset["inference_receipt"]["sha256"],
        "checkpoint": source_asset["source"]["checkpoint"],
        "persona_provenance": contract["persona_provenance"],
        "source_contract_receipt": contract_locator,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "memory_source_policy": "non_personal_persona_project_scope",
    }
    seed = {
        "source_event_id": source["event_id"],
        "type": "audio_source.qualification.completed",
        "payload": payload,
    }
    event = {
        "schema": source.get("schema") or "embry.voice_event.v1",
        "event_id": "audio_source.qualification.completed."
        + hashlib.sha256(canonical(seed)).hexdigest()[:16],
        "session_id": source["session_id"],
        "turn_id": source["turn_id"],
        "type": "audio_source.qualification.completed",
        "created_at": utc_now(),
        "causation_id": source["event_id"],
        "correlation_id": source.get("correlation_id") or campaign_id,
        "producer": PRODUCER + ".source-contract",
        "mocked": False,
        "live": True,
        "artifact_hashes": {
            "listener_audio_sha256": payload["listener_audio_sha256"],
            "source_audio_sha256": payload["source_audio_sha256"],
            "inference_receipt_sha256": payload["inference_receipt_sha256"],
            "checkpoint_sha256": payload["checkpoint"]["sha256"],
            "source_contract_receipt_sha256": contract_locator["sha256"],
        },
        "receipt_hash": sha256_value(seed),
        "payload": payload,
    }
    return append_event(journal_db, event)


def _run_command(
    command: list[str],
    *,
    cwd: Path | None,
    output_dir: Path,
    timeout_seconds: float,
    stage: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    (output_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout).strip().replace("\n", " ")
        raise RuntimeError(
            f"{stage}_command_failed:{completed.returncode}:{error[-1000:]}"
        )


def _memory_tau_stage(
    live_config: dict[str, Any],
    case: dict[str, Any],
    turn: dict[str, Any],
    source: dict[str, Any],
    source_evidence_event: dict[str, Any],
    contract_locator: dict[str, str],
    turn_state: dict[str, Any],
) -> dict[str, Any]:
    existing = turn_state["receipts"].get("memory_tau")
    if existing:
        _, receipt = load_locator(existing, label="memory_tau_receipt")
        if receipt.get("status") != "PASS" or receipt.get("ok") is not True:
            raise ValueError("stored_memory_tau_receipt_not_pass")
        stored_contract = receipt.get("source_contract") or {}
        if stored_contract.get("name") != _source_contract_name(case):
            raise ValueError("stored_memory_tau_source_contract_mismatch")
        if stored_contract.get("suite_ready") is not False:
            raise ValueError("stored_memory_tau_suite_ready_invalid")
        if not turn_state["receipts"].get("tau_step"):
            raise ValueError("stored_tau_step_locator_missing")
        load_locator(turn_state["receipts"]["tau_step"], label="tau_step_receipt")
        turn_state["stage"] = "memory_tau_complete"
        turn_state["updated_at"] = utc_now()
        return receipt

    output = _turn_dir(
        live_config,
        case["case_id"],
        turn["turn_id"],
    ) / "memory-tau"
    consumer = (
        f"audio-e2e:{live_config['campaign_id']}:"
        f"{case['case_id']}:{turn['turn_id']}"
    )
    command = [
        str(live_config.get("controller_python") or sys.executable),
        str(JOURNAL_MEMORY_TAU_SCRIPT),
        "--journal-url",
        live_config["journal_url"],
        "--consumer-name",
        consumer,
        "--event-id",
        source["event_id"],
        "--source-evidence-event-id",
        source_evidence_event["event_id"],
        "--expected-session-id",
        source["session_id"],
        "--expected-turn-id",
        source["turn_id"],
        "--expected-sequence",
        str(source["sequence"]),
        "--source-contract-receipt",
        contract_locator["path"],
        "--source-mode",
        case["source_mode"],
        "--memory-url",
        live_config["memory_url"],
        "--tau-repo",
        live_config["tau_repo"],
        "--output-dir",
        str(output),
        "--memory-read-timeout-seconds",
        str(live_config["memory_answer_read_timeout_seconds"]),
    ]
    answer_path = output / "memory-answer-receipt.json"
    prior_timeout = any(
        failure.get("stage") == "memory_tau"
        and "ReadTimeout" in str(failure.get("error") or "")
        for failure in turn_state.get("failure_history", [])
    )
    if prior_timeout and not answer_path.exists():
        if not live_config.get("allow_memory_answer_retry_after_timeout"):
            raise RuntimeError("memory_answer_retry_requires_explicit_authorization")
        failure = next(
            failure
            for failure in reversed(turn_state["failure_history"])
            if failure.get("stage") == "memory_tau"
            and "ReadTimeout" in str(failure.get("error") or "")
        )
        retry_not_before = datetime.fromisoformat(failure["created_at"]) + timedelta(
            seconds=60
        )
        if datetime.now(timezone.utc) < retry_not_before:
            raise RuntimeError(
                "memory_answer_retry_not_before:" + retry_not_before.isoformat()
            )
        partials = [
            output / "source-event-claim-receipt.json",
            output / "memory-speaker-resolution-receipt.json",
            output / "memory-intent-receipt.json",
            output / "stderr.log",
        ]
        if not all(path.is_file() for path in partials):
            raise RuntimeError("memory_answer_retry_partial_receipts_missing")
        authorization = {
            "schema": "embry.audio_e2e.memory_answer_retry_authorization.v1",
            "status": "PASS",
            "campaign_id": live_config["campaign_id"],
            "case_id": case["case_id"],
            "turn_id": turn["turn_id"],
            "source_event_id": source["event_id"],
            "source_event_sequence": source["sequence"],
            "session_id": source["session_id"],
            "prior_result": "transport_timeout_response_unknown",
            "provider_execution_may_have_continued": True,
            "idempotent_recovery_available": False,
            "explicit_second_provider_execution_authorized": True,
            "authorized_execution_index": 2,
            "retry_not_before": retry_not_before.isoformat(),
            "source_failure": failure,
            "suite_ready": False,
            "release_readiness_authority": False,
            "created_at": utc_now(),
        }
        authorization_path = output / "memory-answer-retry-authorization.json"
        write_json(authorization_path, authorization)
        command.extend(["--answer-retry-authorization", str(authorization_path)])
    _run_command(
        command,
        cwd=SKILL_ROOT,
        output_dir=output,
        timeout_seconds=live_config["memory_tau_timeout_seconds"],
        stage="memory_tau",
    )
    receipt_path = output / "receipt.json"
    receipt = read_json(receipt_path)
    if receipt.get("status") != "PASS" or receipt.get("ok") is not True:
        raise RuntimeError("memory_tau_receipt_not_pass")
    if (
        receipt.get("lineage", {}).get("source_event", {}).get("event_id")
        != source["event_id"]
    ):
        raise ValueError("memory_tau_receipt_lineage_mismatch")
    source_contract = receipt.get("source_contract") or {}
    if source_contract.get("name") != _source_contract_name(case):
        raise ValueError("memory_tau_source_contract_mismatch")
    if source_contract.get("suite_ready") is not False:
        raise ValueError("memory_tau_suite_ready_must_be_false")
    turn_state["receipts"]["memory_tau"] = artifact_locator(receipt_path)
    tau_step = output / "tau-run/command-loop/command-loop-step-001.receipt.json"
    turn_state["receipts"]["tau_step"] = artifact_locator(tau_step)
    turn_state["stage"] = "memory_tau_complete"
    turn_state["updated_at"] = utc_now()
    return receipt


def _render_stage(
    live_config: dict[str, Any],
    case: dict[str, Any],
    turn: dict[str, Any],
    source: dict[str, Any],
    turn_state: dict[str, Any],
) -> dict[str, Any]:
    existing = turn_state["receipts"].get("render")
    if existing:
        _, receipt = load_locator(existing, label="render_receipt")
        if receipt.get("status") != "PASS" or receipt.get("ok") is not True:
            raise ValueError("stored_render_receipt_not_pass")
        if int(receipt.get("chatterbox", {}).get("audio_bytes") or 0) <= 44:
            raise ValueError("stored_render_audio_empty")
        audio_locator = turn_state["receipts"].get("audio")
        if not isinstance(audio_locator, dict):
            raise ValueError("stored_render_audio_locator_missing")
        verify_file_locator(audio_locator, label="render_audio")
        turn_state["stage"] = "render_complete"
        turn_state["updated_at"] = utc_now()
        return receipt

    tau_step_locator = turn_state["receipts"].get("tau_step")
    if not tau_step_locator:
        raise ValueError("tau_step_locator_missing")
    tau_step_path, _ = load_locator(tau_step_locator, label="tau_step_receipt")
    output = _turn_dir(
        live_config,
        case["case_id"],
        turn["turn_id"],
    ) / "render"
    command = [
        str(live_config.get("controller_python") or sys.executable),
        str(RENDER_TAU_PLAN_SCRIPT),
        "--tau-step-receipt",
        str(tau_step_path),
        "--expected-event-id",
        source["event_id"],
        "--expected-sequence",
        str(source["sequence"]),
        "--expected-session-id",
        source["session_id"],
        "--expected-turn-id",
        source["turn_id"],
        "--chatterbox-url",
        live_config["chatterbox_url"],
        "--output-dir",
        str(output),
    ]
    _run_command(
        command,
        cwd=SKILL_ROOT,
        output_dir=output,
        timeout_seconds=live_config["render_timeout_seconds"],
        stage="chatterbox_render",
    )
    receipt_path = output / "receipt.json"
    receipt = read_json(receipt_path)
    if receipt.get("status") != "PASS" or receipt.get("ok") is not True:
        raise RuntimeError("render_receipt_not_pass")
    audio = receipt.get("chatterbox") or {}
    if int(audio.get("audio_bytes") or 0) <= 44:
        raise RuntimeError("render_audio_empty")
    if receipt.get("source_event", {}).get("event_id") != source["event_id"]:
        raise ValueError("render_receipt_lineage_mismatch")
    turn_state["receipts"]["render"] = artifact_locator(receipt_path)
    audio_path = Path(str(audio["audio_path"]))
    if not audio_path.is_file():
        raise FileNotFoundError(f"render_audio_missing:{audio_path}")
    if "sha256:" + hashlib.sha256(audio_path.read_bytes()).hexdigest() != (
        "sha256:" + str(audio["audio_sha256"]).removeprefix("sha256:")
    ):
        raise ValueError("render_audio_hash_mismatch")
    turn_state["receipts"]["audio"] = {
        "path": str(audio_path.resolve()),
        "sha256": "sha256:" + str(audio["audio_sha256"]).removeprefix("sha256:"),
        "bytes": int(audio["audio_bytes"]),
    }
    turn_state["stage"] = "render_complete"
    turn_state["updated_at"] = utc_now()
    return receipt


def _turn_completed_event(
    journal_db: Path,
    campaign_id: str,
    case: dict[str, Any],
    turn: dict[str, Any],
    source: dict[str, Any],
    turn_state: dict[str, Any],
) -> dict[str, Any]:
    snapshot = session_snapshot(journal_db, case["session_id"])
    existing = next(
        (
            event
            for event in snapshot["events"]
            if event.get("type") == "audio_e2e.turn_completed"
            and event.get("turn_id") == turn["turn_id"]
            and event.get("payload", {}).get("source_event_id")
                == source["event_id"]
        ),
        None,
    )
    if existing:
        return existing

    _, memory_tau = load_locator(
        turn_state["receipts"]["memory_tau"],
        label="memory_tau_receipt",
    )
    _, render = load_locator(
        turn_state["receipts"]["render"],
        label="render_receipt",
    )
    audio = turn_state["receipts"]["audio"]
    tau_event_id = (
        memory_tau.get("journal_events", {})
        .get("tau_tick_completed", {})
        .get("event_id")
    )
    if not tau_event_id:
        raise ValueError("tau_tick_completed_event_id_missing")
    payload = {
        "case_id": case["case_id"],
        "source_event_id": source["event_id"],
        "source_event_sequence": source["sequence"],
        "memory_tau_receipt_sha256":
            turn_state["receipts"]["memory_tau"]["sha256"],
        "render_receipt_sha256":
            turn_state["receipts"]["render"]["sha256"],
        "audio_path": audio["path"],
        "audio_sha256": audio["sha256"],
        "audio_bytes": audio["bytes"],
        "source_contract": memory_tau["source_contract"],
        "source_evidence_receipt_sha256":
            turn_state["receipts"]["source_evidence"]["sha256"],
        "suite_ready": False,
    }
    seed = {
        "type": "audio_e2e.turn_completed",
        "session_id": case["session_id"],
        "turn_id": turn["turn_id"],
        "payload": payload,
    }
    event = {
        "schema": source.get("schema") or "embry.voice_event.v1",
        "event_id": "audio_e2e.turn_completed."
        + hashlib.sha256(canonical(seed)).hexdigest()[:16],
        "session_id": case["session_id"],
        "turn_id": turn["turn_id"],
        "type": "audio_e2e.turn_completed",
        "created_at": utc_now(),
        "causation_id": tau_event_id,
        "correlation_id": source.get("correlation_id") or campaign_id,
        "producer": PRODUCER,
        "mocked": False,
        "live": True,
        "artifact_hashes": {
            "memory_tau_receipt_sha256": payload["memory_tau_receipt_sha256"],
            "render_receipt_sha256": payload["render_receipt_sha256"],
            "audio_sha256": payload["audio_sha256"],
            "source_evidence_receipt_sha256":
                payload["source_evidence_receipt_sha256"],
        },
        "receipt_hash": sha256_value(seed),
        "payload": payload,
    }
    return append_event(journal_db, event)


def _record_failure(
    case_state: dict[str, Any],
    turn_state: dict[str, Any] | None,
    *,
    case_id: str,
    turn_id: str | None,
    stage: str,
    error: Exception,
) -> None:
    subsystem = {
        "listener": "realtimestt_listener",
        "source_contract": "source_contract",
        "source_evidence": "source_contract",
        "speaker_evidence": "source_contract",
        "memory_tau": "memory_or_tau",
        "render": "chatterbox",
        "case_completion": "journal",
    }.get(stage, stage)
    failure = {
        "schema": "embry.audio_e2e_live_failure.v1",
        "case_id": case_id,
        "turn_id": turn_id,
        "stage": stage,
        "subsystem": subsystem,
        "error_type": type(error).__name__,
        "error": str(error),
        "created_at": utc_now(),
    }
    case_state["failure_bundle"] = failure
    case_state.setdefault("failure_history", []).append(failure)
    case_state["stage"] = "blocked"
    if turn_state is not None:
        turn_state["failure"] = failure
        turn_state.setdefault("failure_history", []).append(failure)
        turn_state["updated_at"] = utc_now()


def _case_turn_receipt_summary(
    case: dict[str, Any],
    case_state: dict[str, Any],
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    contract_name = _source_contract_name(case)
    for turn in case["turn_script"]:
        turn_id = turn["turn_id"]
        turn_state = case_state["turns"][turn_id]
        receipts = turn_state.get("receipts") or {}
        listener_locator = receipts.get("listener")
        source_locator = receipts.get("source_evidence")
        memory_tau_locator = receipts.get("memory_tau")
        render_locator = receipts.get("render")
        audio_locator = receipts.get("audio")
        if not all(
            isinstance(item, dict)
            for item in (
                listener_locator,
                source_locator,
                memory_tau_locator,
                render_locator,
                audio_locator,
            )
        ):
            raise ValueError(f"case_turn_receipt_locator_missing:{turn_id}")

        _, listener = load_locator(
            listener_locator,
            label=f"case_listener_receipt:{turn_id}",
        )
        _, source_evidence = load_locator(
            source_locator,
            label=f"case_source_evidence_receipt:{turn_id}",
        )
        _, memory_tau = load_locator(
            memory_tau_locator,
            label=f"case_memory_tau_receipt:{turn_id}",
        )
        _, render = load_locator(
            render_locator,
            label=f"case_render_receipt:{turn_id}",
        )
        audio_path = verify_file_locator(
            audio_locator,
            label=f"case_audio_artifact:{turn_id}",
        )

        memory_forbidden = memory_tau.get("forbidden_activity") or {}
        render_source_contract = render.get("source_contract") or {}
        acceptance = {
            "listener_live": (
                listener.get("status") == "PASS"
                and listener.get("live") is True
                and listener.get("mocked") is False
            ),
            "listener_used_audio_not_typed_text": (
                listener.get("typed_transcript_used") is False
                and bool(listener.get("audio_sha256"))
            ),
            "listener_source_contract_matches": (
                listener.get("source_contract") == contract_name
            ),
            "source_evidence_live": (
                source_evidence.get("status") == "PASS"
                and (
                    source_evidence.get("source_evidence_event") or {}
                ).get("live") is True
                and (
                    source_evidence.get("source_evidence_event") or {}
                ).get("mocked") is False
            ),
            "source_evidence_contract_matches": (
                source_evidence.get("source_contract") == contract_name
            ),
            "memory_tau_live": (
                memory_tau.get("status") == "PASS"
                and memory_tau.get("ok") is True
                and memory_tau.get("live") is True
                and memory_tau.get("mocked") is False
            ),
            "memory_tau_no_typed_transcript": (
                memory_forbidden.get("typed_transcript_used") is False
            ),
            "memory_tau_no_synthetic_physical_relabel": (
                memory_forbidden.get(
                    "synthetic_audio_relabelled_as_physical"
                )
                is False
            ),
            "memory_tau_suite_ready_false": (
                memory_tau.get("suite_ready") is False
                and (memory_tau.get("source_contract") or {}).get(
                    "suite_ready"
                )
                is False
            ),
            "render_live": (
                render.get("status") == "PASS"
                and render.get("ok") is True
                and render.get("live") is True
                and render.get("mocked") is False
            ),
            "render_source_contract_matches": (
                render_source_contract.get("name") == contract_name
            ),
            "render_suite_ready_false": render.get("suite_ready") is False,
            "chatterbox_audio_nonempty": (
                int((render.get("chatterbox") or {}).get("audio_bytes") or 0)
                > 44
                and audio_path.stat().st_size > 44
            ),
        }
        if contract_name == "qualified_horus_clone":
            acceptance.update(
                {
                    "clone_not_fresh_physical": (
                        listener.get("fresh_physical_human_speech") is False
                        and source_evidence.get(
                            "fresh_physical_human_speech"
                        )
                        is False
                    ),
                    "clone_identity_not_proven": (
                        listener.get("speaker_identity_proven") is False
                        and source_evidence.get("speaker_identity_proven")
                        is False
                    ),
                    "clone_personal_memory_disabled": (
                        source_evidence.get("allow_personal_memory") is False
                        and (memory_tau.get("memory") or {}).get(
                            "allow_personal_memory"
                        )
                        is False
                    ),
                    "clone_memory_resolution_unknown": (
                        (
                            (memory_tau.get("memory") or {}).get(
                                "source_resolution"
                            )
                            or {}
                        ).get("status")
                        == "unknown"
                    ),
                }
            )
        if not all(acceptance.values()):
            failed = sorted(
                key for key, value in acceptance.items() if not value
            )
            raise ValueError(
                f"case_turn_acceptance_failed:{turn_id}:"
                + ",".join(failed)
            )
        summaries[turn_id] = {
            "receipts": receipts,
            "acceptance": acceptance,
        }
    return summaries


def _complete_case(
    journal_db: Path,
    campaign_id: str,
    case: dict[str, Any],
    case_state: dict[str, Any],
    live_config: dict[str, Any],
) -> None:
    if not all(
        case_state["turns"][turn["turn_id"]].get("stage") == "completed"
        for turn in case["turn_script"]
    ):
        return
    snapshot = session_snapshot(journal_db, case["session_id"])
    existing = next(
        (
            event
            for event in snapshot["events"]
            if event.get("type") == "audio_e2e.case_completed"
            and event.get("payload", {}).get("case_id") == case["case_id"]
        ),
        None,
    )
    event = existing or append_event(
        journal_db,
        _event(
            event_type="audio_e2e.case_completed",
            case=case,
            campaign_id=campaign_id,
            payload={
                "case_id": case["case_id"],
                "journal_sha256": snapshot["sha256"],
                "turn_count": len(case["turn_script"]),
                "all_turns_rendered": True,
                "source_contract": _source_contract_name(case),
                "suite_ready": False,
                "release_readiness_authority": False,
            },
            causation_id=case_state.get("last_event_id", "root"),
        ),
    )
    contract_locator, contract = _load_source_contract(case, live_config)
    turn_summaries = _case_turn_receipt_summary(case, case_state)
    receipt = {
        "schema": "embry.audio_e2e_case_receipt.v2",
        "status": "PASS",
        "ok": True,
        "live": True,
        "mocked": False,
        "campaign_id": campaign_id,
        "case_id": case["case_id"],
        "session_id": case["session_id"],
        "source_mode": case["source_mode"],
        "source_contract": _source_contract_name(case),
        "source_identity": contract["source_identity"],
        "voice_persona": contract.get("voice_persona"),
        "fresh_physical_human_speech": (
            case["source_mode"] == "physical_live_horus"
        ),
        "speaker_identity_proven": bool(
            contract["speaker_identity_proven"]
        ),
        "allow_personal_memory": bool(
            contract["allow_personal_memory"]
        ),
        "memory_source_policy": (
            contract.get("memory_source_policy")
            or "event_specific_physical_identity_personal_memory"
        ),
        "source_contract_receipt": contract_locator,
        "proof_scope": dict(INTERMEDIATE_PROOF_SCOPE),
        "suite_ready": False,
        "release_readiness_authority": False,
        "case_completed_event_id": event["event_id"],
        "turns": turn_summaries,
        "acceptance": {
            "all_turns_live": True,
            "all_turns_audio_driven": True,
            "all_memory_tau_live": True,
            "all_chatterbox_live_with_audio": True,
            "typed_transcript_used": False,
            "mocked_service_used": False,
            "synthetic_audio_relabelled_as_physical": False,
            "suite_ready": False,
        },
        "completed_at": utc_now(),
    }
    receipt_path = (
        Path(live_config["campaign_dir"])
        / "cases"
        / case["case_id"]
        / "receipt.json"
    )
    write_json(receipt_path, receipt)
    case_state["receipt"] = artifact_locator(receipt_path)
    case_state["stage"] = "completed"
    case_state["failure_bundle"] = None
    case_state["last_event_id"] = event["event_id"]


def _write_campaign_receipt(
    manifest: dict[str, Any],
    state: dict[str, Any],
    live_config: dict[str, Any],
) -> dict[str, str]:
    case_receipts: dict[str, dict[str, Any]] = {}
    for case in manifest["cases"]:
        case_state = state["cases"][case["case_id"]]
        locator = case_state.get("receipt")
        if not isinstance(locator, dict):
            raise ValueError(
                f"campaign_case_receipt_missing:{case['case_id']}"
            )
        _, receipt = load_locator(
            locator,
            label=f"case_receipt:{case['case_id']}",
        )
        if receipt.get("status") != "PASS" or receipt.get("ok") is not True:
            raise ValueError(
                f"campaign_case_receipt_not_pass:{case['case_id']}"
            )
        if receipt.get("suite_ready") is not False:
            raise ValueError(
                f"campaign_case_suite_ready_invalid:{case['case_id']}"
            )
        acceptance = receipt.get("acceptance") or {}
        required_acceptance = {
            "all_turns_live": True,
            "all_turns_audio_driven": True,
            "all_memory_tau_live": True,
            "all_chatterbox_live_with_audio": True,
            "typed_transcript_used": False,
            "mocked_service_used": False,
            "synthetic_audio_relabelled_as_physical": False,
            "suite_ready": False,
        }
        if any(
            acceptance.get(key) != expected
            for key, expected in required_acceptance.items()
        ):
            raise ValueError(
                f"campaign_case_acceptance_invalid:{case['case_id']}"
            )
        case_receipts[case["case_id"]] = locator

    source_contract_counts: dict[str, int] = {}
    for case_state in state["cases"].values():
        name = str(case_state.get("source_contract") or "unknown")
        source_contract_counts[name] = source_contract_counts.get(name, 0) + 1

    receipt = {
        "schema": "embry.audio_e2e_campaign_receipt.v1",
        "status": "PASS",
        "ok": True,
        "live": True,
        "mocked": False,
        "campaign_id": manifest["campaign_id"],
        "case_count": len(manifest["cases"]),
        "completed_case_count": len(case_receipts),
        "source_contract_counts": source_contract_counts,
        "case_receipts": case_receipts,
        "proof_scope": dict(INTERMEDIATE_PROOF_SCOPE),
        "suite_ready": False,
        "release_readiness_authority": False,
        "forbidden_activity": {
            "typed_transcript_used": False,
            "mocked_memory": False,
            "mocked_tau": False,
            "mocked_chatterbox": False,
            "synthetic_audio_relabelled_as_physical": False,
        },
        "completed_at": utc_now(),
    }
    path = Path(live_config["campaign_dir"]) / "campaign-receipt.json"
    write_json(path, receipt)
    return artifact_locator(path)


def run_campaign(
    *,
    manifest_path: Path,
    state_path: Path | None,
    journal_db: Path,
    live_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state_path = state_path or default_state_path(manifest_path)
    manifest, state = load_or_create_state(manifest_path, state_path)
    state["status"] = "running"
    state["updated_at"] = utc_now()
    write_json(state_path, state)

    if live_config is None:
        state["status"] = "waiting_for_live_runtime_configuration"
        state["updated_at"] = utc_now()
        write_json(state_path, state)
        return state

    live_config = {
        **live_config,
        "campaign_id": manifest["campaign_id"],
        "manifest_case_count": len(manifest["cases"]),
    }
    Path(live_config["campaign_dir"]).mkdir(parents=True, exist_ok=True)
    assets = _read_audio_assets(live_config.get("audio_assets_manifest"))
    _migrate_inline_listener_receipts(state, manifest, live_config)

    by_id = {case["case_id"]: case for case in manifest["cases"]}
    contracts: dict[
        str, tuple[dict[str, str], dict[str, Any]]
    ] = {}
    current_contract_case = manifest["cases"][0]
    try:
        for case in manifest["cases"]:
            current_contract_case = case
            contract_locator, contract = _load_source_contract(
                case,
                live_config,
            )
            contracts[case["case_id"]] = (contract_locator, contract)
            case_state = state["cases"][case["case_id"]]
            case_state["source_contract"] = _source_contract_name(case)
            case_state["source_identity"] = contract["source_identity"]
            case_state["speaker_identity_proven"] = bool(
                contract["speaker_identity_proven"]
            )
            case_state["memory_source_policy"] = (
                contract.get("memory_source_policy")
                or "event_specific_physical_identity_personal_memory"
            )
            case_state["suite_ready"] = False
            if case_state.get("stage") == "completed":
                continue
            _ensure_case_started(
                journal_db,
                manifest["campaign_id"],
                case,
                case_state,
                contract_locator,
                contract,
            )
        _validate_clone_asset_index(
            manifest,
            live_config,
            assets,
            contracts,
        )
    except Exception as exc:
        case_state = state["cases"][current_contract_case["case_id"]]
        _record_failure(
            case_state,
            None,
            case_id=current_contract_case["case_id"],
            turn_id=None,
            stage="source_contract",
            error=exc,
        )
        state["status"] = "blocked_live_failure"
        state["updated_at"] = utc_now()
        write_json(state_path, state)
        return state
    write_json(state_path, state)

    listener_pending: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for case in manifest["cases"]:
        case_state = state["cases"][case["case_id"]]
        if case_state.get("stage") == "completed":
            continue
        for turn in case["turn_script"]:
            turn_state = case_state["turns"][turn["turn_id"]]
            if not turn_state["receipts"].get("listener"):
                listener_pending.append((case, turn, turn_state))

    if listener_pending:
        listener_config = {**live_config, "journal_db": str(journal_db)}
        unrecovered: list[
            tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
        ] = []
        for case, turn, turn_state in listener_pending:
            case_state = state["cases"][case["case_id"]]
            try:
                contract_locator, contract = contracts[case["case_id"]]
                wake_asset, source_asset = _turn_audio_assets(
                    case,
                    turn,
                    live_config,
                    assets,
                    contract_locator,
                    contract,
                )
                wake_audio = (
                    Path(wake_asset["audio"]["path"])
                    if wake_asset is not None
                    else None
                )
                source_audio = (
                    Path(source_asset["audio"]["path"])
                    if source_asset is not None
                    else None
                )
                receipt = CaseExecutor.recover_listener_turn(
                    listener_config,
                    manifest["campaign_id"],
                    case,
                    turn,
                    journal_db=journal_db,
                    wake_audio=wake_audio,
                    source_audio=source_audio,
                    wake_asset=wake_asset,
                    source_asset=source_asset,
                )
                if receipt is None:
                    unrecovered.append((case, turn, turn_state))
                    continue
                turn_state["receipts"]["listener"] = _persist_listener_receipt(
                    live_config,
                    case["case_id"],
                    turn["turn_id"],
                    receipt,
                )
                turn_state["stage"] = "listener_complete"
                turn_state["failure"] = None
                turn_state["updated_at"] = utc_now()
                case_state["stage"] = "running"
                write_json(state_path, state)
                print(
                    json.dumps(
                        {
                            "status": "LISTENER_RECEIPT_RECOVERED_FROM_JOURNAL",
                            "case_id": case["case_id"],
                            "turn_id": turn["turn_id"],
                            "arm_event_id": receipt["arm_event_id"],
                            "final_event_id": receipt["final_event_id"],
                            "completed_event_id": receipt["completed_event_id"],
                            "listener_process_spawned": False,
                            "audio_replayed": False,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception as exc:
                _record_failure(
                    case_state,
                    turn_state,
                    case_id=case["case_id"],
                    turn_id=turn["turn_id"],
                    stage="listener",
                    error=exc,
                )
                state["status"] = "blocked_live_failure"
                state["updated_at"] = utc_now()
                write_json(state_path, state)
                return state
        listener_pending = unrecovered

    if listener_pending:
        physical_cases = {
            case["case_id"]
            for case, _, _ in listener_pending
            if case["source_mode"] == "physical_live_horus"
        }
        if physical_cases and (
            len(physical_cases) != 1
            or any(
                case["source_mode"] != "physical_live_horus"
                for case, _, _ in listener_pending
            )
        ):
            raise ValueError("manual_physical_mode_requires_one_exclusive_case")
        listener_required = (
            "realtimestt_repo",
            "realtimestt_python",
            "managed_listener_socket",
            "listener_source_node",
        )
        missing = [key for key in listener_required if not live_config.get(key)]
        if missing:
            raise ValueError(
                "live_listener_configuration_incomplete:" + ",".join(missing)
            )
        if any(
            case["source_mode"] != "physical_live_horus"
            for case, _, _ in listener_pending
        ) and not live_config.get("source_playback_target"):
            raise ValueError("source_playback_target_required")

        total_turn_count = len(listener_pending)
        campaign_turn_count = sum(
            len(case["turn_script"])
            for case in manifest["cases"]
        )
        listener_run_dir, listener_target_turn_count = _select_managed_listener_run(
            campaign_dir=Path(live_config["campaign_dir"]),
            source_node=live_config["listener_source_node"],
            campaign_turn_count=campaign_turn_count,
            pending_turn_count=total_turn_count,
        )
        try:
            with ManagedListenerProcess(
                listener_config,
                target_turn_count=listener_target_turn_count,
                turns_this_run=total_turn_count,
                run_dir=listener_run_dir,
            ) as listener:
                executor = CaseExecutor(listener_config, listener)
                for case, turn, turn_state in listener_pending:
                    case_state = state["cases"][case["case_id"]]
                    try:
                        contract_locator, contract = contracts[case["case_id"]]
                        wake_asset, source_asset = _turn_audio_assets(
                            case,
                            turn,
                            live_config,
                            assets,
                            contract_locator,
                            contract,
                        )
                        wake_audio = (
                            Path(wake_asset["audio"]["path"])
                            if wake_asset is not None
                            else None
                        )
                        source_audio = (
                            Path(source_asset["audio"]["path"])
                            if source_asset is not None
                            else None
                        )
                        receipt = executor.execute_listener_turn(
                            manifest["campaign_id"],
                            case,
                            turn,
                            wake_audio=wake_audio,
                            source_audio=source_audio,
                            wake_asset=wake_asset,
                            source_asset=source_asset,
                        )
                        turn_state["receipts"]["listener"] = (
                            _persist_listener_receipt(
                                live_config,
                                case["case_id"],
                                turn["turn_id"],
                                receipt,
                            )
                        )
                        turn_state["stage"] = "listener_complete"
                        turn_state["failure"] = None
                        turn_state["updated_at"] = utc_now()
                        case_state["stage"] = "running"
                        write_json(state_path, state)
                    except Exception as exc:
                        _record_failure(
                            case_state,
                            turn_state,
                            case_id=case["case_id"],
                            turn_id=turn["turn_id"],
                            stage="listener",
                            error=exc,
                        )
                        state["status"] = "blocked_live_failure"
                        state["updated_at"] = utc_now()
                        write_json(state_path, state)
                        return state
        except Exception as exc:
            if not listener_pending:
                raise
            case, turn, turn_state = listener_pending[0]
            case_state = state["cases"][case["case_id"]]
            _record_failure(
                case_state,
                turn_state,
                case_id=case["case_id"],
                turn_id=turn["turn_id"],
                stage="listener",
                error=exc,
            )
            state["status"] = "blocked_live_failure"
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            return state

    for case_id, case in by_id.items():
        case_state = state["cases"][case_id]
        if case_state.get("stage") == "completed":
            continue
        contract_locator, contract = contracts[case_id]
        for turn in case["turn_script"]:
            turn_state = case_state["turns"][turn["turn_id"]]
            if turn_state.get("stage") == "completed":
                continue
            try:
                listener_locator = turn_state["receipts"].get("listener")
                if not listener_locator:
                    raise ValueError("listener_receipt_missing")
                _, listener_receipt = load_locator(
                    listener_locator,
                    label="listener_receipt",
                )
                source, _ = _resolve_final_event(
                    journal_db,
                    case,
                    turn,
                    listener_receipt,
                )
                existing_source_locator = turn_state["receipts"].get(
                    "source_evidence"
                )
                if existing_source_locator:
                    _, source_receipt = load_locator(
                        existing_source_locator,
                        label="source_evidence_receipt",
                    )
                    if source_receipt.get("status") != "PASS":
                        raise ValueError("stored_source_evidence_not_pass")
                    if source_receipt.get("source_contract") != _source_contract_name(case):
                        raise ValueError(
                            "stored_source_evidence_contract_mismatch"
                        )
                    if source_receipt.get("source_identity") != contract["source_identity"]:
                        raise ValueError(
                            "stored_source_evidence_identity_mismatch"
                        )
                    if source_receipt.get("suite_ready") is not False:
                        raise ValueError(
                            "stored_source_evidence_suite_ready_invalid"
                        )
                    stored_source_evidence_event = source_receipt.get(
                        "source_evidence_event"
                    )
                    if not isinstance(stored_source_evidence_event, dict):
                        raise ValueError(
                            "stored_source_evidence_event_missing"
                        )
                    source_evidence_event = _source_evidence_event(
                        journal_db,
                        manifest["campaign_id"],
                        case,
                        source,
                        listener_receipt,
                        contract_locator,
                        contract,
                    )
                    if (
                        source_evidence_event.get("event_id")
                        != stored_source_evidence_event.get("event_id")
                    ):
                        raise ValueError(
                            "stored_source_evidence_event_mismatch"
                        )
                else:
                    source_evidence_event = _source_evidence_event(
                        journal_db,
                        manifest["campaign_id"],
                        case,
                        source,
                        listener_receipt,
                        contract_locator,
                        contract,
                    )
                    source_receipt_path = (
                        _turn_dir(live_config, case_id, turn["turn_id"])
                        / "source-evidence"
                        / "receipt.json"
                    )
                    source_receipt = {
                        "schema":
                            "embry.audio_e2e.source_evidence_receipt.v1",
                        "status": "PASS",
                        "source_event_id": source["event_id"],
                        "source_evidence_event": source_evidence_event,
                        "source_contract_receipt": contract_locator,
                        "source_mode": case["source_mode"],
                        "source_contract": _source_contract_name(case),
                        "source_identity": contract["source_identity"],
                        "voice_persona": contract.get("voice_persona"),
                        "fresh_physical_human_speech": (
                            case["source_mode"] == "physical_live_horus"
                        ),
                        "speaker_identity_proven": bool(
                            contract["speaker_identity_proven"]
                        ),
                        "allow_personal_memory": bool(
                            contract["allow_personal_memory"]
                        ),
                        "release_readiness_authority": False,
                        "suite_ready": False,
                    }
                    write_json(source_receipt_path, source_receipt)
                    turn_state["receipts"][
                        "source_evidence"
                    ] = artifact_locator(source_receipt_path)
                turn_state["stage"] = "source_evidence_complete"
                turn_state["failure"] = None
                turn_state["updated_at"] = utc_now()
                write_json(state_path, state)

                _memory_tau_stage(
                    live_config,
                    case,
                    turn,
                    source,
                    source_evidence_event,
                    contract_locator,
                    turn_state,
                )
                write_json(state_path, state)
                _render_stage(
                    live_config,
                    case,
                    turn,
                    source,
                    turn_state,
                )
                turn_event = _turn_completed_event(
                    journal_db,
                    manifest["campaign_id"],
                    case,
                    turn,
                    source,
                    turn_state,
                )
                turn_state["completion_event_id"] = turn_event["event_id"]
                turn_state["stage"] = "completed"
                turn_state["failure"] = None
                turn_state["updated_at"] = utc_now()
                case_state["last_event_id"] = turn_event["event_id"]
                write_json(state_path, state)
            except Exception as exc:
                if turn_state.get("stage") in {"pending", "listener_complete"}:
                    failed_stage = "source_evidence"
                elif turn_state.get("stage") == "source_evidence_complete":
                    failed_stage = "memory_tau"
                else:
                    failed_stage = "render"
                _record_failure(
                    case_state,
                    turn_state,
                    case_id=case_id,
                    turn_id=turn["turn_id"],
                    stage=failed_stage,
                    error=exc,
                )
                state["status"] = "blocked_live_failure"
                state["updated_at"] = utc_now()
                write_json(state_path, state)
                return state
        try:
            _complete_case(
                journal_db,
                manifest["campaign_id"],
                case,
                case_state,
                live_config,
            )
            write_json(state_path, state)
        except Exception as exc:
            _record_failure(
                case_state,
                None,
                case_id=case_id,
                turn_id=None,
                stage="case_completion",
                error=exc,
            )
            state["status"] = "blocked_live_failure"
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            return state

    state["status"] = (
        "completed"
        if all(
            case_state.get("stage") == "completed"
            for case_state in state["cases"].values()
        )
        else "running"
    )
    state["suite_ready"] = False
    state["proof_scope"] = dict(INTERMEDIATE_PROOF_SCOPE)
    if state["status"] == "completed":
        state["campaign_receipt"] = _write_campaign_receipt(
            manifest,
            state,
            live_config,
        )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return state


def status(*, manifest_path: Path, state_path: Path | None) -> dict[str, Any]:
    state_path = state_path or default_state_path(manifest_path)
    if not state_path.exists():
        manifest = read_json(manifest_path)
        validate_manifest(manifest)
        return {
            "schema": "embry.audio_e2e_status.v1",
            "campaign_id": manifest["campaign_id"],
            "status": "not_started",
            "suite_ready": False,
            "proof_scope": dict(INTERMEDIATE_PROOF_SCOPE),
            "state_path": str(state_path),
        }
    state = read_json(state_path)
    cases = state.get("cases", {})
    return {
        "schema": "embry.audio_e2e_status.v1",
        "campaign_id": state["campaign_id"],
        "status": state["status"],
        "suite_ready": False,
        "proof_scope": state.get(
            "proof_scope",
            dict(INTERMEDIATE_PROOF_SCOPE),
        ),
        "campaign_receipt": state.get("campaign_receipt"),
        "state_path": str(state_path),
        "completed_case_count": sum(
            case.get("stage") == "completed" for case in cases.values()
        ),
        "blocked_case_count": sum(
            case.get("stage") == "blocked" for case in cases.values()
        ),
        "case_count": len(cases),
        "cases": cases,
    }


def bundle_failure(
    *,
    manifest_path: Path,
    state_path: Path | None,
    output: Path,
    reason: str,
) -> dict[str, Any]:
    state_path = state_path or default_state_path(manifest_path)
    manifest = read_json(manifest_path)
    state = (
        read_json(state_path)
        if state_path.exists()
        else initial_state(manifest_path, manifest)
    )
    bundle = {
        "schema": "embry.audio_e2e_fix_forward_failure_bundle.v1",
        "created_at": utc_now(),
        "reason": reason,
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_value(manifest),
        "state_path": str(state_path),
        "state_sha256": sha256_value(state),
        "campaign_id": manifest.get("campaign_id"),
        "failed_cases": {
            case_id: case
            for case_id, case in state.get("cases", {}).items()
            if case.get("stage") != "completed"
        },
        "fix_forward": (
            "resume with the same manifest, state file, audio asset index, "
            "source-contract receipt, and live journal after correcting the "
            "recorded stage/subsystem failure"
        ),
    }
    write_json(output, bundle)
    return bundle
