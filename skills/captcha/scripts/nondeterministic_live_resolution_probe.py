#!/usr/bin/env python3
"""Run or honestly block an authorized nondeterministic local ReCAP campaign."""

from __future__ import annotations

import argparse
import json
import random
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
RUN_SH = SKILL_ROOT / "run.sh"
DEFAULT_MANIFEST = SKILL_ROOT / "fixtures" / "authorization-valid-red-team-local.json"
sys.path.insert(0, str(SKILL_ROOT / "src"))

from captcha_skill.constants import DEFAULT_OUTPUT_ROOT, DEFAULT_RECAP_ROOT  # noqa: E402
from captcha_skill.models import EvaluationAction, RunStatus  # noqa: E402
from captcha_skill.policy import load_manifest, validate_authorization, write_json_atomic  # noqa: E402
from captcha_skill.runtime import build_evaluation_plan, default_recap_python, status_report  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--recap-root", type=Path, default=DEFAULT_RECAP_ROOT)
    parser.add_argument("--recap-python", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _emit(receipt: dict[str, Any], output: Path | None, json_output: bool) -> None:
    if output is not None:
        write_json_atomic(output, receipt)
    if json_output:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"status={receipt['status']} schema={receipt['schema_version']}")


def _blocked_receipt(
    *,
    seed: int,
    samples: int,
    blockers: list[str],
    plan_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "captcha.nondeterministic_resolution_probe.v1",
        "status": "BLOCKED_EXTERNAL",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "seed": seed,
        "samples_requested": samples,
        "blockers": blockers,
        "plan_path": str(plan_path) if plan_path is not None else None,
        "proof_boundary": {
            "proves": "the nondeterministic live campaign gate did not silently pass without authorized local prerequisites",
            "does_not_prove": "captcha resolution success, ReCAP model accuracy, or public-site CAPTCHA handling",
        },
    }


def main() -> int:
    args = _parse_args()
    if args.samples < 2 or args.samples > 50:
        raise SystemExit("--samples must be in the bounded range 2..50")

    seed = args.seed if args.seed is not None else secrets.randbelow(2_147_483_648)
    rng = random.Random(seed)
    sampled_offsets = [rng.randrange(0, 2_147_483_648) for _ in range(args.samples)]
    runtime_python = args.recap_python or default_recap_python(args.recap_root)

    blockers: list[str] = []
    status = status_report(
        recap_root=args.recap_root,
        recap_python=runtime_python,
        storage_root=args.output_root.parent,
    )
    if status.status is not RunStatus.PASS:
        blockers.extend(f"status:{item}" for item in status.blockers)

    manifest_value = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_value["test_size"] = args.samples
    manifest_value["max_tasks"] = max(int(manifest_value.get("max_tasks", 1)), args.samples)
    manifest_value["seed"] = seed
    manifest_path = Path(tempfile.mkdtemp(prefix="captcha-nondet-manifest-")) / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest, manifest_sha256 = load_manifest(manifest_path)
    authorization = validate_authorization(
        manifest,
        manifest_sha256=manifest_sha256,
        required_action=EvaluationAction.EVALUATE,
    )
    plan = build_evaluation_plan(
        manifest,
        authorization,
        recap_root=args.recap_root,
        recap_python=runtime_python,
        output_root=args.output_root,
    )
    plan_path = manifest_path.parent / "plan.json"
    write_json_atomic(plan_path, plan.model_dump(mode="json"))
    if plan.readiness is not RunStatus.PASS:
        blockers.extend(f"plan:{item}" for item in plan.blockers)

    if blockers:
        receipt = _blocked_receipt(
            seed=seed,
            samples=args.samples,
            blockers=blockers,
            plan_path=plan_path,
        )
        receipt["sampled_offsets"] = sampled_offsets
        _emit(receipt, args.output, args.json)
        return 0

    command = [
        str(RUN_SH),
        "evaluate",
        "--manifest",
        str(manifest_path),
        "--recap-root",
        str(args.recap_root),
        "--recap-python",
        str(runtime_python),
        "--output-root",
        str(args.output_root),
        "--execute",
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=SKILL_ROOT,
        text=True,
        capture_output=True,
        timeout=manifest.timeout_seconds + 120,
        check=False,
    )
    try:
        evaluate_payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        evaluate_payload = None
    receipt = {
        "schema_version": "captcha.nondeterministic_resolution_probe.v1",
        "status": "PASS" if completed.returncode == 0 else "FAILED",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "seed": seed,
        "samples_requested": args.samples,
        "sampled_offsets": sampled_offsets,
        "command": command,
        "exit_code": completed.returncode,
        "evaluate_payload": evaluate_payload,
        "proof_boundary": {
            "proves": "authorized local ReCAP evaluation ran with a randomized bounded sample campaign",
            "does_not_prove": "public-site CAPTCHA solving or third-party provider bypass",
        },
    }
    _emit(receipt, args.output, args.json)
    return 0 if completed.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
