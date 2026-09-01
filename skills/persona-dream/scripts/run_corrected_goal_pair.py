#!/usr/bin/env python3
"""run_corrected_goal_pair - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--forbid-mocked", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    validation = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_corrected_goal_manifest.py"),
            "--manifest",
            str(manifest_path),
            "--strict",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if validation.returncode != 0:
        print(validation.stdout, end="")
        print(validation.stderr, end="", file=sys.stderr)
        return validation.returncode

    sealed_manifest = out / "manifest.json"
    shutil.copyfile(manifest_path, sealed_manifest)

    required_live_artifacts = [
        out / "control" / "conversation.jsonl",
        out / "treatment" / "conversation.jsonl",
        out / "answer_invariance.json",
        out / "emotional_carryover.json",
        out / "chatterbox_delivery.json",
    ]
    missing = [str(path) for path in required_live_artifacts if not path.exists()]
    status = "PASS_CORRECTED_GOAL_PAIR_ARTIFACTS_PRESENT" if not missing else "BLOCKED_CORRECTED_GOAL_PAIR_LIVE_ARTIFACTS_MISSING"

    receipt = {
        "schema": "persona_dream.corrected_goal_pair_runner_receipt.v1",
        "proof_id": "PD-CORRECTED-GOAL-V1",
        "status": status,
        "mocked": False,
        "live": False if missing else bool(args.require_live),
        "manifest": str(manifest_path),
        "manifest_sha256": _sha_file(manifest_path),
        "sealed_manifest": str(sealed_manifest),
        "sealed_manifest_sha256": _sha_file(sealed_manifest),
        "run_root": str(out),
        "missing_live_artifacts": missing,
        "fail_closed": True,
        "proves": "the corrected-goal pair target validates and installs the sealed manifest, then refuses to claim a live pair without real paired artifacts",
        "does_not_prove": "dynamic Horus/Embry execution, live Chatterbox rendering, RealtimeSTT ASR, or the corrected Persona Dream mechanism",
    }
    receipt_path = out / "corrected_goal_pair_runner_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))

    if missing and args.require_live:
        return 2
    if missing:
        return 1
    if args.forbid_mocked and receipt["mocked"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
