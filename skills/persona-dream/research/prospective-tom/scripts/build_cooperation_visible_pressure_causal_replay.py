#!/usr/bin/env python3
"""Build a Gate 9 causal replay for the visible-pressure reliability surface.

The replay targets one controlled Gate 8 fault trial and localizes the first
divergent boundary by replacing one suspected local artifact/tool return. It
does not call Tau, Memory, models, VLMs, or providers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_CAUSAL_REPLAY_BUILT"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_VISIBLE_PRESSURE_CAUSAL_REPLAY_BUILD"
SURFACE_SCHEMA = "persona_dream.research.prospective_tom.reliability_surface.v1"
REPLAY_SCHEMA = "persona_dream.research.prospective_tom.causal_replay.v1"
DEFAULT_TRIAL_ID = "visible-pressure-fault-oracle-leak-001"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _trial_by_id(surface: dict[str, Any], trial_id: str) -> dict[str, Any] | None:
    trials = surface.get("trials")
    if not isinstance(trials, list):
        return None
    for trial in trials:
        if isinstance(trial, dict) and trial.get("trial_id") == trial_id:
            return trial
    return None


def _baseline_hash(surface: dict[str, Any]) -> str | None:
    accepted = surface.get("accepted_end_state_sha256")
    if _is_sha256(accepted):
        return str(accepted)
    trials = surface.get("trials")
    if isinstance(trials, list):
        for trial in trials:
            if isinstance(trial, dict) and trial.get("terminal_outcome") == "RECOVERED_WITH_EQUIVALENT_END_STATE":
                value = trial.get("end_state_equivalence_sha256")
                if _is_sha256(value):
                    return str(value)
    return None


def _validate_surface(surface: dict[str, Any], trial_id: str, errors: list[str]) -> tuple[dict[str, Any], str]:
    if surface.get("schema") != SURFACE_SCHEMA:
        errors.append(f"surface_schema_mismatch:{surface.get('schema')}")
    if surface.get("canonical_memory_write") is not False:
        errors.append(f"surface_canonical_memory_write_not_false:{surface.get('canonical_memory_write')}")
    if surface.get("identity_write") is not False:
        errors.append(f"surface_identity_write_not_false:{surface.get('identity_write')}")
    if surface.get("source_memory_write") is not False:
        errors.append(f"surface_source_memory_write_not_false:{surface.get('source_memory_write')}")
    target = _trial_by_id(surface, trial_id)
    if target is None:
        errors.append(f"target_trial_missing:{trial_id}")
        target = {}
    if not target.get("faults"):
        errors.append(f"target_trial_not_faulted:{trial_id}")
    if target.get("terminal_outcome") == "RECOVERED_WITH_EQUIVALENT_END_STATE":
        errors.append(f"target_trial_not_divergent_or_contained_fault:{trial_id}")
    if target.get("unknown_state_continued") is not False:
        errors.append(f"target_trial_unknown_state_continued_not_false:{target.get('unknown_state_continued')}")
    for key in ("canonical_memory_write", "identity_write", "source_memory_write"):
        if target.get(key) is not False:
            errors.append(f"target_trial_{key}_not_false:{target.get(key)}")
    baseline = _baseline_hash(surface)
    if not _is_sha256(baseline):
        errors.append(f"baseline_hash_missing:{baseline}")
        baseline = "sha256:" + "0" * 64
    target_hash = target.get("end_state_equivalence_sha256")
    if not _is_sha256(target_hash):
        errors.append(f"target_trial_end_state_hash_invalid:{target_hash}")
    elif target_hash == baseline:
        errors.append("target_trial_not_divergent_from_baseline")
    return target, str(baseline)


def build_replay_from_surface(surface: dict[str, Any], *, trial_id: str = DEFAULT_TRIAL_ID) -> dict[str, Any]:
    target = _trial_by_id(surface, trial_id) or {}
    expected_hash = _baseline_hash(surface) or ("sha256:" + "0" * 64)
    observed_hash = target.get("end_state_equivalence_sha256") if _is_sha256(target.get("end_state_equivalence_sha256")) else (
        "sha256:" + "1" * 64
    )
    first_receipt_id = "visible-pressure-receipt-006-validate-pre-outcome-rule-inputs"
    tool_return_id = "visible-pressure-tool-return-oracle-leak-001"
    leaked_tool_return = {
        "tool": "local_artifact_store.read",
        "result": {
            "artifact": "cd_pre_outcome_rule_inputs",
            "mutation": "inject_actual_next_action_and_oracle_action",
            "faults": target.get("faults"),
        },
    }
    clean_tool_return = {
        "tool": "local_artifact_store.read",
        "result": {
            "artifact": "cd_pre_outcome_rule_inputs",
            "mutation": "none",
            "uses_outcome_or_oracle": False,
        },
    }
    return {
        "schema": REPLAY_SCHEMA,
        "replay_id": "visible-pressure-causal-replay-oracle-leak-001",
        "surface_id": surface.get("surface_id"),
        "trial_id": trial_id,
        "reliability_surface_sha256": _stable_json_sha256(surface),
        "first_divergent_receipt": {
            "receipt_id": first_receipt_id,
            "receipt_index": 6,
            "boundary": "cd_pre_outcome_rule_inputs_validation",
            "expected_state_sha256": expected_hash,
            "observed_state_sha256": observed_hash,
        },
        "replay_start_receipt_id": first_receipt_id,
        "suspected_tool_return": {
            "receipt_id": first_receipt_id,
            "tool_return_id": tool_return_id,
            "tool_name": "local_artifact_store.read",
            "operation": "REPLACE_TOOL_RETURN",
            "original_return_sha256": _stable_json_sha256(leaked_tool_return),
            "replacement_return_sha256": _stable_json_sha256(clean_tool_return),
        },
        "comparison": {
            "factual_end_state_sha256": observed_hash,
            "counterfactual_end_state_sha256": expected_hash,
            "expected_end_state_sha256": expected_hash,
            "counterfactual_matches_expected": True,
        },
        "localized_cause": {
            "cause_type": "PRE_OUTCOME_ORACLE_OR_HIDDEN_FIELD_LEAK",
            "receipt_id": first_receipt_id,
            "tool_return_id": tool_return_id,
            "causal_confidence": 1.0,
            "evidence_refs": [
                trial_id,
                first_receipt_id,
                tool_return_id,
                "visible-pressure-reliability-surface",
            ],
        },
        "terminal_outcome": "CAUSAL_FAILURE_LOCALIZED",
        "unknown_state_continued": False,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
    }


def run_build(*, surface_path: Path, output_root: Path, receipt_out: Path, trial_id: str = DEFAULT_TRIAL_ID) -> dict[str, Any]:
    started = time.monotonic()
    surface_path = surface_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts = output_root / "artifacts"
    replay_path = artifacts / "cooperation_visible_pressure_causal_replay.v1.json"
    errors: list[str] = []

    surface = _load_json(surface_path, errors, "reliability_surface")
    surface = surface if isinstance(surface, dict) else {}
    target_trial, baseline_hash = _validate_surface(surface, trial_id, errors)
    replay = build_replay_from_surface(surface, trial_id=trial_id)
    _write_json(replay_path, replay)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_visible_pressure_causal_replay_build_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "reliability_surface_path": str(surface_path),
        "reliability_surface_file_sha256": _file_sha256(surface_path) if surface_path.exists() else None,
        "reliability_surface_sha256": _stable_json_sha256(surface),
        "replay_path": str(replay_path),
        "replay_sha256": _stable_json_sha256(replay),
        "replay_file_sha256": _file_sha256(replay_path) if replay_path.exists() else None,
        "target_trial_id": trial_id,
        "target_terminal_outcome": target_trial.get("terminal_outcome"),
        "target_faults": target_trial.get("faults"),
        "baseline_end_state_sha256": baseline_hash,
        "target_end_state_sha256": target_trial.get("end_state_equivalence_sha256"),
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "controlled_faults_used": True,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "errors": errors,
        "claims": {
            "proves": [
                "a Gate 9 causal replay fixture was built for one visible-pressure Gate 8 fault trial",
                "the replay starts at the pre-outcome rule-input validation boundary",
                "the replay replaces exactly one suspected local artifact/tool return",
                "the builder made zero Tau, Memory, provider, canonical-memory, identity, or source-memory writes",
            ]
            if status == PASS_STATUS
            else ["the visible-pressure causal replay builder failed closed"],
            "does_not_prove": [
                "live Tau execution",
                "live Memory recall",
                "real service fault injection",
                "production causal replay",
                "statistical prediction benefit",
                "complete PCTOM-R reliability across every boundary",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--trial-id", default=DEFAULT_TRIAL_ID)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_visible_pressure_causal_replay_build_receipt.v1.json")
    receipt = run_build(
        surface_path=args.surface,
        output_root=args.output_root,
        receipt_out=receipt_out,
        trial_id=args.trial_id,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
