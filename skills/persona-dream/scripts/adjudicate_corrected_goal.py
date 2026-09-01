#!/usr/bin/env python3
"""adjudicate_corrected_goal - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_ROOT = [
    "manifest.json",
    "answer_invariance.json",
    "emotional_carryover.json",
    "chatterbox_delivery.json",
]


def _sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fail-closed", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    run_root = Path(args.run_root)
    out_path = Path(args.out)
    failures: list[str] = []
    artifacts: dict[str, str] = {}

    if not run_root.exists():
        failures.append("run_root_missing")
    else:
        for rel in REQUIRED_ROOT:
            path = run_root / rel
            if path.exists():
                artifacts[rel] = _sha_file(path)
            else:
                failures.append(f"missing_root_artifact:{rel}")
        for side in ("control", "treatment"):
            if not (run_root / side).exists():
                failures.append(f"missing_condition_dir:{side}")

    manifest = _load_json(manifest_path)
    manifest_digest = _sha_file(manifest_path)

    gate_files = {
        "answer_invariance": run_root / "answer_invariance.json",
        "emotional_carryover": run_root / "emotional_carryover.json",
        "chatterbox_delivery": run_root / "chatterbox_delivery.json",
    }
    gate_statuses: dict[str, str] = {}
    live_values: list[bool] = []
    mocked_values: list[bool] = []
    if run_root.exists():
        for gate, path in gate_files.items():
            if not path.exists():
                continue
            data = _load_json(path)
            gate_statuses[gate] = str(data.get("status"))
            if not str(data.get("status", "")).startswith("PASS_"):
                failures.append(f"gate_not_pass:{gate}:{data.get('status')}")
            if "live" in data:
                live_values.append(bool(data.get("live")))
            if "mocked" in data:
                mocked_values.append(bool(data.get("mocked")))

    if not live_values or not all(live_values):
        failures.append("live_true_missing")
    if any(mocked_values):
        failures.append("mocked_true_forbidden")

    status = "PASS_CORRECTED_GOAL_PAIRED_PROOF" if not failures else "BLOCKED_CORRECTED_GOAL_PAIRED_PROOF"
    receipt = {
        "schema": "persona_dream.corrected_goal_receipt.v1",
        "proof_id": manifest.get("proof_id"),
        "status": status,
        "mocked": bool(any(mocked_values)),
        "live": bool(live_values and all(live_values)),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_digest,
        "run_root": str(run_root),
        "artifacts": artifacts,
        "gate_statuses": gate_statuses,
        "failures": failures,
        "claims": manifest.get("claims"),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else (2 if args.fail_closed else 1)


if __name__ == "__main__":
    sys.exit(main())
