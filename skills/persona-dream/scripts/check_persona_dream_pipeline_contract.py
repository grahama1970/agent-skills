#!/usr/bin/env python3
"""Validate the canonical Persona Dream pipeline contract."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "persona_dream_pipeline.v1.yaml"
REQUIRED_PHASES = [f"{idx:02d}" for idx in range(1, 17)]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pipeline contract must be a YAML mapping")
    return data


def check_pipeline_contract(path: Path) -> dict[str, Any]:
    path = path.resolve()
    blockers: list[str] = []
    data = _load_yaml(path)

    phases = data.get("phases")
    if not isinstance(phases, dict):
        blockers.append("BLOCKED_PHASES_NOT_MAPPING")
        phases = {}

    observed_phase_ids = sorted(str(key) for key in phases)
    if observed_phase_ids != REQUIRED_PHASES:
        blockers.append(
            "BLOCKED_PHASE_ID_SET:"
            + ",".join(observed_phase_ids)
            + ":expected:"
            + ",".join(REQUIRED_PHASES)
        )

    for phase_id in REQUIRED_PHASES:
        phase = phases.get(phase_id)
        if not isinstance(phase, dict):
            blockers.append(f"BLOCKED_PHASE_{phase_id}_MISSING")
            continue
        for field in ("name", "owner", "question", "evidence_class", "side_effect_class", "required_outputs", "pass_statuses", "non_claims", "invalidated_by"):
            if field not in phase:
                blockers.append(f"BLOCKED_PHASE_{phase_id}_MISSING_{field.upper()}")
        if phase_id != "16" and str(phase.get("next_allowed_phase")) != f"{int(phase_id) + 1:02d}":
            blockers.append(f"BLOCKED_PHASE_{phase_id}_NEXT_PHASE")

    workstreams = data.get("workstreams")
    if not isinstance(workstreams, dict) or sorted(workstreams) != ["A", "B", "E"]:
        blockers.append("BLOCKED_WORKSTREAMS_A_B_E_MISSING")

    publication = data.get("publication_backend")
    if not isinstance(publication, dict):
        blockers.append("BLOCKED_PUBLICATION_BACKEND_MISSING")
    else:
        truth = publication.get("required_truth_after_publication_without_submit")
        if not isinstance(truth, dict):
            blockers.append("BLOCKED_PUBLICATION_TRUTH_MISSING")
        else:
            expected_truth = {
                "provider_live": False,
                "actual_provider_call_attempts": 0,
                "submitted": False,
                "provider_ready": False,
                "live_submit_ready": False,
            }
            for key, expected in expected_truth.items():
                if truth.get(key) != expected:
                    blockers.append(f"BLOCKED_PUBLICATION_TRUTH_{key.upper()}")

    return {
        "schema": "persona_dream.pipeline_contract_check_receipt.v1",
        "created_at": _now_iso(),
        "contract_path": str(path),
        "status": "PASS_PERSONA_DREAM_PIPELINE_CONTRACT" if not blockers else "BLOCKED_PERSONA_DREAM_PIPELINE_CONTRACT",
        "phase_count": len(observed_phase_ids),
        "required_phase_count": len(REQUIRED_PHASES),
        "workstreams": sorted(workstreams) if isinstance(workstreams, dict) else [],
        "publication_backend": publication.get("name") if isinstance(publication, dict) else None,
        "blockers": blockers,
        "mocked": "no",
        "live": "no",
        "actual_provider_call_attempts": 0,
        "claims": {
            "proves": ["canonical pipeline contract shape is internally consistent"] if not blockers else [],
            "does_not_prove": [
                "runtime phase execution",
                "Phase 10 reproducibility",
                "Tailscale Funnel availability",
                "provider readiness",
                "provider submit",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = check_pipeline_contract(args.contract)
    except Exception as exc:  # noqa: BLE001 - fail-closed receipt.
        receipt = {
            "schema": "persona_dream.pipeline_contract_check_receipt.v1",
            "created_at": _now_iso(),
            "contract_path": str(args.contract),
            "status": "BLOCKED_PERSONA_DREAM_PIPELINE_CONTRACT",
            "blockers": [f"BLOCKED_SCHEMA_OR_PARSE:{exc}"],
            "mocked": "no",
            "live": "no",
            "actual_provider_call_attempts": 0,
        }

    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == "PASS_PERSONA_DREAM_PIPELINE_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())

