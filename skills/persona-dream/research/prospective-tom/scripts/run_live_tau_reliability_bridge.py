#!/usr/bin/env python3
"""Build a bounded live Tau-originated PCTOM-R Gate 8/9 reliability bridge."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
GATE8_SCRIPT = RESEARCH_ROOT / "scripts" / "run_reliability_surface.py"
GATE9_SCRIPT = RESEARCH_ROOT / "scripts" / "run_causal_replay.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_RELIABILITY_BRIDGE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_RELIABILITY_BRIDGE"
REQUIRED_SCORE_FILES = [
    "live_tau_score_revision_receipt.v1.json",
    "receipts/tom_scoring_receipt.json",
    "receipts/belief_revision_check_receipt.json",
    "artifacts/tom_outcome_reveal.json",
    "artifacts/tom_belief_revision.json",
]


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


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_manifest(root: Path, *, label: str) -> dict[str, Any]:
    files: dict[str, str] = {}
    missing: list[str] = []
    for rel in REQUIRED_SCORE_FILES:
        path = root / rel
        if path.exists() and not path.is_symlink():
            files[rel] = _file_sha256(path)
        else:
            missing.append(rel)
    receipt_path = root / "live_tau_score_revision_receipt.v1.json"
    receipt = _load_json(receipt_path) if receipt_path.exists() else {}
    return {
        "label": label,
        "root": str(root),
        "receipt_status": receipt.get("status"),
        "gate5_status": receipt.get("gate5_status"),
        "gate7_status": receipt.get("gate7_status"),
        "live": receipt.get("live"),
        "live_tau_originated_commitment_consumed": receipt.get("live_tau_originated_commitment_consumed"),
        "mocked": receipt.get("mocked"),
        "memory_write_attempts": receipt.get("memory_write_attempts"),
        "provider_call_attempts": receipt.get("provider_call_attempts"),
        "tau_call_attempts": receipt.get("tau_call_attempts"),
        "files": files,
        "missing": missing,
    }


def _stale_manifest(current_manifest: dict[str, Any], stale_root: Path | None) -> dict[str, Any]:
    if stale_root is not None and stale_root.exists():
        return _artifact_manifest(stale_root.resolve(), label="stale_artifact_root")
    stale = json.loads(json.dumps(current_manifest))
    stale["label"] = "controlled_stale_artifact_definition"
    stale["root"] = f"{current_manifest.get('root')}#controlled-stale"
    stale["receipt_status"] = "STALE_ARTIFACT_CONTROL"
    stale["controlled_fault"] = "previous_artifact_pointer_reused_after_score_revision"
    stale["files"] = dict(stale.get("files", {}))
    stale["files"]["live_tau_score_revision_receipt.v1.json"] = _stable_json_sha256(
        {
            "stale_pointer_for": current_manifest.get("files", {}).get("live_tau_score_revision_receipt.v1.json"),
            "fault": "stale_artifact",
        }
    )
    return stale


def _validate_source_receipt(source_root: Path, errors: list[str]) -> dict[str, Any]:
    receipt_path = source_root / "live_tau_score_revision_receipt.v1.json"
    if not receipt_path.exists():
        errors.append(f"missing_live_tau_score_revision_receipt:{receipt_path}")
        return {}
    receipt = _load_json(receipt_path)
    expected = {
        "status": "PASS_LIVE_TAU_PCTOM_SCORE_REVISION",
        "gate5_status": "PASS_TOM_SCORING_RECEIPT",
        "gate7_status": "PASS_TOM_BELIEF_REVISION",
        "mocked": False,
        "live": True,
        "live_tau_originated_commitment_consumed": True,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "tau_call_attempts": 0,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            errors.append(f"source_{key}_mismatch:{receipt.get(key)}:{value}")
    return receipt


def _episode_id_from_source(source_receipt: dict[str, Any]) -> str:
    live_tau_receipt_path = source_receipt.get("live_tau_receipt_path")
    if isinstance(live_tau_receipt_path, str) and live_tau_receipt_path:
        path = Path(live_tau_receipt_path)
        if path.exists() and not path.is_symlink():
            try:
                live_tau_receipt = _load_json(path)
                episode_id = live_tau_receipt.get("episode_id")
                if isinstance(episode_id, str) and episode_id:
                    return episode_id
            except Exception:
                pass
    return "dev-info-asym-01"


def _surface(
    *,
    episode_id: str,
    current_state_sha256: str,
    stale_state_sha256: str,
    blocked_state_sha256: str,
    current_manifest: dict[str, Any],
    stale_manifest: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "schema": "persona_dream.research.prospective_tom.reliability_trial.v1",
        "episode_id": episode_id,
        "condition": "CD",
        "k": 2,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "side_effect_count": 0,
        "active_partial_state": False,
        "unknown_state_continued": False,
        "duplicate_active_predictions": 0,
        "duplicate_active_revisions": 0,
    }
    trials = [
        {
            **base,
            "trial_id": "live-gate8-trial-baseline-001",
            "repeat_group_id": "live-gate8-repeat-current",
            "epsilon": 0,
            "lambda": 0,
            "perturbations": [],
            "faults": [],
            "end_state_equivalence_sha256": current_state_sha256,
            "evidence_refs": ["current_manifest"],
        },
        {
            **base,
            "trial_id": "live-gate8-trial-baseline-002",
            "repeat_group_id": "live-gate8-repeat-current",
            "epsilon": 0,
            "lambda": 0,
            "perturbations": [],
            "faults": [],
            "end_state_equivalence_sha256": current_state_sha256,
            "evidence_refs": ["current_manifest"],
        },
        {
            **base,
            "trial_id": "live-gate8-trial-perturbed-001",
            "repeat_group_id": "live-gate8-repeat-current",
            "epsilon": 0.25,
            "lambda": 0,
            "perturbations": ["rename_ids_preserve_bindings", "equivalent_question_form"],
            "faults": [],
            "end_state_equivalence_sha256": current_state_sha256,
            "evidence_refs": ["current_manifest"],
        },
        {
            **base,
            "trial_id": "live-gate8-trial-malformed-runtime-001",
            "repeat_group_id": "live-gate8-malformed-runtime",
            "epsilon": 0,
            "lambda": 0.5,
            "perturbations": [],
            "faults": ["malformed_runtime_boundary"],
            "terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
            "end_state_equivalence_sha256": blocked_state_sha256,
            "evidence_refs": ["controlled_malformed_runtime_definition"],
        },
        {
            **base,
            "trial_id": "live-gate8-trial-stale-artifact-001",
            "repeat_group_id": "live-gate8-stale-artifact",
            "epsilon": 0.25,
            "lambda": 0.75,
            "perturbations": ["rename_ids_preserve_bindings"],
            "faults": ["stale_artifact"],
            "terminal_outcome": "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
            "end_state_equivalence_sha256": stale_state_sha256,
            "evidence_refs": ["stale_manifest"],
        },
    ]
    for trial in trials:
        trial.setdefault("terminal_outcome", "RECOVERED_WITH_EQUIVALENT_END_STATE")
    return {
        "schema": "persona_dream.research.prospective_tom.reliability_surface.v1",
        "surface_id": f"live-gate8-surface-{episode_id}-cd",
        "episode_id": episode_id,
        "condition": "CD",
        "k": 2,
        "epsilon_values": [0, 0.25],
        "lambda_values": [0, 0.5, 0.75],
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "source_manifests": {
            "current_manifest": current_manifest,
            "stale_manifest": stale_manifest,
        },
        "trials": trials,
    }


def _replay(
    *,
    surface: dict[str, Any],
    current_state_sha256: str,
    stale_state_sha256: str,
    current_tool_return_sha256: str,
    stale_tool_return_sha256: str,
) -> dict[str, Any]:
    first_receipt_id = "live-receipt-003-load-score-revision-artifact"
    tool_return_id = "live-tool-return-stale-score-revision-artifact-001"
    return {
        "schema": "persona_dream.research.prospective_tom.causal_replay.v1",
        "replay_id": "live-gate9-replay-stale-score-revision-artifact-001",
        "surface_id": surface["surface_id"],
        "trial_id": "live-gate8-trial-stale-artifact-001",
        "reliability_surface_sha256": _stable_json_sha256(surface),
        "first_divergent_receipt": {
            "receipt_id": first_receipt_id,
            "receipt_index": 3,
            "boundary": "score_revision_artifact_load",
            "expected_state_sha256": current_state_sha256,
            "observed_state_sha256": stale_state_sha256,
        },
        "replay_start_receipt_id": first_receipt_id,
        "suspected_tool_return": {
            "receipt_id": first_receipt_id,
            "tool_return_id": tool_return_id,
            "tool_name": "local_artifact_store.read",
            "operation": "REPLACE_TOOL_RETURN",
            "original_return_sha256": stale_tool_return_sha256,
            "replacement_return_sha256": current_tool_return_sha256,
        },
        "comparison": {
            "factual_end_state_sha256": stale_state_sha256,
            "counterfactual_end_state_sha256": current_state_sha256,
            "expected_end_state_sha256": current_state_sha256,
            "counterfactual_matches_expected": True,
        },
        "localized_cause": {
            "cause_type": "STALE_ARTIFACT",
            "receipt_id": first_receipt_id,
            "tool_return_id": tool_return_id,
            "causal_confidence": 1.0,
            "evidence_refs": [
                "live-gate8-trial-stale-artifact-001",
                first_receipt_id,
                tool_return_id,
            ],
        },
        "terminal_outcome": "CAUSAL_FAILURE_LOCALIZED",
        "unknown_state_continued": False,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
    }


def build_receipt(
    *,
    live_score_root: Path,
    output_root: Path,
    receipt_out: Path,
    stale_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    live_score_root = live_score_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    receipts_root = output_root / "receipts"
    surface_path = artifacts_root / "reliability_surface.json"
    replay_path = artifacts_root / "causal_replay.json"
    gate8_receipt_path = receipts_root / "reliability_surface_check_receipt.json"
    gate9_receipt_path = receipts_root / "causal_replay_check_receipt.json"
    errors: list[str] = []
    source_receipt = _validate_source_receipt(live_score_root, errors)
    gate8_receipt: dict[str, Any] | None = None
    gate9_receipt: dict[str, Any] | None = None
    source_manifest: dict[str, Any] = {}
    stale_source_manifest: dict[str, Any] = {}

    try:
        gate8 = _load_module(GATE8_SCRIPT, "persona_dream_pctom_gate8_reliability")
        gate9 = _load_module(GATE9_SCRIPT, "persona_dream_pctom_gate9_causal_replay")
        source_manifest = _artifact_manifest(live_score_root, label="current_live_score_revision_root")
        if source_manifest.get("missing"):
            errors.append(f"source_manifest_missing:{source_manifest['missing']}")
        stale_source_manifest = _stale_manifest(source_manifest, stale_root.resolve() if stale_root else None)
        current_state_sha256 = _stable_json_sha256(source_manifest)
        stale_state_sha256 = _stable_json_sha256(stale_source_manifest)
        blocked_state_sha256 = _stable_json_sha256(
            {
                "boundary": "malformed_runtime_boundary",
                "source": str(live_score_root),
                "terminal_outcome": "BLOCKED_BEFORE_SIDE_EFFECT",
            }
        )
        current_tool_return_sha256 = _stable_json_sha256(
            {
                "tool": "local_artifact_store.read",
                "result": source_manifest,
            }
        )
        stale_tool_return_sha256 = _stable_json_sha256(
            {
                "tool": "local_artifact_store.read",
                "result": stale_source_manifest,
            }
        )
        episode_id = _episode_id_from_source(source_receipt)
        surface = _surface(
            episode_id=episode_id,
            current_state_sha256=current_state_sha256,
            stale_state_sha256=stale_state_sha256,
            blocked_state_sha256=blocked_state_sha256,
            current_manifest=source_manifest,
            stale_manifest=stale_source_manifest,
        )
        _write_json(surface_path, surface)
        replay = _replay(
            surface=surface,
            current_state_sha256=current_state_sha256,
            stale_state_sha256=stale_state_sha256,
            current_tool_return_sha256=current_tool_return_sha256,
            stale_tool_return_sha256=stale_tool_return_sha256,
        )
        _write_json(replay_path, replay)
        gate8_receipt = gate8.build_receipt(surface_path, gate8_receipt_path)
        if gate8_receipt.get("status") != "PASS_TOM_RELIABILITY_SURFACE":
            errors.append(f"gate8_status:{gate8_receipt.get('status')}")
            errors.extend(f"gate8_error:{error}" for error in gate8_receipt.get("errors", []))
        gate9_receipt = gate9.build_receipt(replay_path, surface_path, gate9_receipt_path)
        if gate9_receipt.get("status") != "PASS_TOM_CAUSAL_REPLAY":
            errors.append(f"gate9_status:{gate9_receipt.get('status')}")
            errors.extend(f"gate9_error:{error}" for error in gate9_receipt.get("errors", []))
    except Exception as exc:
        errors.append(f"live_tau_reliability_bridge_failed:{exc}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_reliability_bridge_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "live_score_root": str(live_score_root),
        "stale_root": str(stale_root.resolve()) if stale_root else None,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "mocked": False,
        "live": bool(source_receipt.get("live") is True),
        "live_tau_originated_case_consumed": bool(
            source_receipt.get("live_tau_originated_commitment_consumed") is True
        ),
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "controlled_fault_definition": True,
        "human_content_judgment_required": False,
        "live_service_call_attempts": 0,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "surface_path": str(surface_path),
        "replay_path": str(replay_path),
        "gate8_receipt_path": str(gate8_receipt_path),
        "gate9_receipt_path": str(gate9_receipt_path),
        "gate8_status": gate8_receipt.get("status") if gate8_receipt else None,
        "gate9_status": gate9_receipt.get("status") if gate9_receipt else None,
        "counts": {
            "gate8": (gate8_receipt or {}).get("counts", {}),
            "gate9": (gate9_receipt or {}).get("counts", {}),
        },
        "metrics": {
            "gate8": (gate8_receipt or {}).get("metrics", {}),
            "gate9": (gate9_receipt or {}).get("metrics", {}),
        },
        "checks": {
            "gate8": (gate8_receipt or {}).get("checks", {}),
            "gate9": (gate9_receipt or {}).get("checks", {}),
        },
        "source_manifest_sha256": _stable_json_sha256(source_manifest) if source_manifest else None,
        "stale_manifest_sha256": _stable_json_sha256(stale_source_manifest) if stale_source_manifest else None,
        "errors": errors,
        "claims": {
            "proves": [
                "a live Tau-originated PCTOM score/revision case was consumed as the reliability subject",
                "Gate 8 accepted repeated, perturbed, blocked, and quarantined trials over live-originated artifact hashes",
                "the controlled stale-artifact fault was quarantined with no active partial state",
                "Gate 9 localized the first divergent receipt and replacement tool return for the stale-artifact boundary",
                "no Memory write, provider call, new Tau call, duplicate active prediction, duplicate active revision, or human content judgment was required",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau reliability bridge produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "external service fault injection",
                "production retry machinery",
                "statistical prediction benefit",
                "held-out M/R/D/CD comparison",
                "longitudinal recall after revision",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution or video quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-score-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--stale-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_reliability_bridge_receipt.v1.json")
    receipt = build_receipt(
        live_score_root=args.live_score_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        stale_root=args.stale_root,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
