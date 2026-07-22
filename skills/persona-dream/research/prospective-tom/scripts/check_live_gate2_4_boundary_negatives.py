#!/usr/bin/env python3
"""Mutate live-originated Gate 2-4 artifacts and require fail-closed receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_LIVE_GATE2_4_BOUNDARY_NEGATIVES"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_GATE2_4_BOUNDARY_NEGATIVES"
SCHEMA = "persona_dream.research.prospective_tom.live_gate2_4_boundary_negatives_receipt.v1"
RESEARCH_ROOT = Path(__file__).resolve().parents[1]
CHECK_GATE2 = RESEARCH_ROOT / "scripts" / "check_tom_belief_distributions.py"
CHECK_GATE3 = RESEARCH_ROOT / "scripts" / "check_counterfactual_branches.py"
CHECK_GATE4 = RESEARCH_ROOT / "scripts" / "check_tom_prediction_commitments.py"

ARTIFACT_DISTRIBUTIONS = "tom_belief_distribution_bundle.json"
ARTIFACT_BRANCHES = "counterfactual_branch_bundle.json"
ARTIFACT_COMMITMENTS = "tom_prediction_commitment_bundle.json"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_json_command(command: list[str], output_path: Path) -> tuple[int, dict[str, Any] | None, str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    output_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path = output_path.with_suffix(output_path.suffix + ".stderr.txt")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    parsed = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed = None
    return completed.returncode, parsed, str(output_path), str(stderr_path)


def _copy_source_artifacts(case_root: Path, output_root: Path) -> dict[str, Path]:
    source_dir = output_root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "distributions": case_root / ARTIFACT_DISTRIBUTIONS,
        "branches": case_root / ARTIFACT_BRANCHES,
        "commitments": case_root / ARTIFACT_COMMITMENTS,
    }
    copied = {}
    for key, path in paths.items():
        target = source_dir / path.name
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        copied[key] = target
    return copied


def _mutate_gate2_bad_probability(source: Path, target: Path) -> None:
    bundle = _load_json(source)
    distributions = bundle.get("distributions")
    if not isinstance(distributions, list) or not distributions:
        raise RuntimeError("gate2_source_missing_distributions")
    entries = distributions[0].get("distribution")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("gate2_source_missing_distribution_entries")
    entries[0]["probability"] = 0.99
    _write_json(target, bundle)


def _mutate_gate3_counterfactual_not_synthetic(source: Path, target: Path) -> None:
    bundle = _load_json(source)
    branches = bundle.get("branches")
    if not isinstance(branches, list) or not branches:
        raise RuntimeError("gate3_source_missing_branches")
    for branch in branches:
        if isinstance(branch, dict) and branch.get("branch_type") == "counterfactual":
            branch["synthetic"] = False
            intervention = branch.get("intervention")
            if isinstance(intervention, dict):
                intervention["synthetic"] = False
            _write_json(target, bundle)
            return
    raise RuntimeError("gate3_source_missing_counterfactual_branch")


def _mutate_gate4_payload_hash_mismatch(source: Path, target: Path) -> None:
    bundle = _load_json(source)
    commitments = bundle.get("commitments")
    if not isinstance(commitments, list) or not commitments:
        raise RuntimeError("gate4_source_missing_commitments")
    payload = commitments[0].get("prediction_payload")
    if not isinstance(payload, dict):
        raise RuntimeError("gate4_source_missing_prediction_payload")
    payload["tamper_marker"] = "mutated-after-seal-without-hash-update"
    _write_json(target, bundle)


def _case_summary(name: str, receipt: dict[str, Any] | None, exit_code: int, expected_errors: list[str]) -> dict[str, Any]:
    errors = receipt.get("errors") if isinstance(receipt, dict) else []
    if not isinstance(errors, list):
        errors = []
    status = receipt.get("status") if isinstance(receipt, dict) else None
    matched_errors = [needle for needle in expected_errors if any(needle in str(error) for error in errors)]
    return {
        "case": name,
        "exit_code": exit_code,
        "status": status,
        "expected_status_blocked": isinstance(status, str) and status.startswith("BLOCKED_"),
        "expected_error_needles": expected_errors,
        "matched_error_needles": matched_errors,
        "expected_errors_matched": len(matched_errors) == len(expected_errors),
        "errors": errors,
        "receipt_path": receipt.get("receipt_path") if isinstance(receipt, dict) else None,
    }


def build_receipt(corpus_path: Path, case_root: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    output_root.mkdir(parents=True, exist_ok=True)
    copied = _copy_source_artifacts(case_root, output_root)
    positive_dir = output_root / "positive_source"
    negative_dir = output_root / "negative_cases"

    positive_commands = [
        (
            "gate2_source_positive",
            [
                sys.executable,
                str(CHECK_GATE2),
                "--corpus",
                str(corpus_path),
                "--bundle",
                str(copied["distributions"]),
                "--receipt-out",
                str(positive_dir / "gate2_source_positive_receipt.json"),
                "--json",
            ],
        ),
        (
            "gate3_source_positive",
            [
                sys.executable,
                str(CHECK_GATE3),
                "--corpus",
                str(corpus_path),
                "--distributions",
                str(copied["distributions"]),
                "--branches",
                str(copied["branches"]),
                "--receipt-out",
                str(positive_dir / "gate3_source_positive_receipt.json"),
                "--json",
            ],
        ),
        (
            "gate4_source_positive",
            [
                sys.executable,
                str(CHECK_GATE4),
                "--corpus",
                str(corpus_path),
                "--distributions",
                str(copied["distributions"]),
                "--branches",
                str(copied["branches"]),
                "--commitments",
                str(copied["commitments"]),
                "--receipt-out",
                str(positive_dir / "gate4_source_positive_receipt.json"),
                "--json",
            ],
        ),
    ]
    positive_results = []
    for name, command in positive_commands:
        exit_code, parsed, stdout_path, stderr_path = _run_json_command(command, positive_dir / f"{name}.stdout.json")
        status = parsed.get("status") if isinstance(parsed, dict) else None
        positive_results.append(
            {
                "case": name,
                "exit_code": exit_code,
                "status": status,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "receipt_path": parsed.get("receipt_path") if isinstance(parsed, dict) else None,
            }
        )
        if exit_code != 0 or not isinstance(status, str) or not status.startswith("PASS_"):
            errors.append(f"source_positive_not_pass:{name}:{status}:{exit_code}")

    gate2_bad_probability = negative_dir / "gate2_bad_probability_sum" / ARTIFACT_DISTRIBUTIONS
    gate3_not_synthetic = negative_dir / "gate3_counterfactual_not_synthetic" / ARTIFACT_BRANCHES
    gate4_hash_mismatch = negative_dir / "gate4_prediction_payload_hash_mismatch" / ARTIFACT_COMMITMENTS
    _mutate_gate2_bad_probability(copied["distributions"], gate2_bad_probability)
    _mutate_gate3_counterfactual_not_synthetic(copied["branches"], gate3_not_synthetic)
    _mutate_gate4_payload_hash_mismatch(copied["commitments"], gate4_hash_mismatch)

    negative_specs = [
        (
            "gate2_bad_probability_sum",
            [
                sys.executable,
                str(CHECK_GATE2),
                "--corpus",
                str(corpus_path),
                "--bundle",
                str(gate2_bad_probability),
                "--receipt-out",
                str(gate2_bad_probability.with_name("receipt.json")),
                "--json",
            ],
            ["distribution_0_distribution_sum"],
            gate2_bad_probability,
        ),
        (
            "gate3_counterfactual_not_synthetic",
            [
                sys.executable,
                str(CHECK_GATE3),
                "--corpus",
                str(corpus_path),
                "--distributions",
                str(copied["distributions"]),
                "--branches",
                str(gate3_not_synthetic),
                "--receipt-out",
                str(gate3_not_synthetic.with_name("receipt.json")),
                "--json",
            ],
            ["counterfactual_synthetic_not_true", "intervention_not_synthetic"],
            gate3_not_synthetic,
        ),
        (
            "gate4_prediction_payload_hash_mismatch",
            [
                sys.executable,
                str(CHECK_GATE4),
                "--corpus",
                str(corpus_path),
                "--distributions",
                str(copied["distributions"]),
                "--branches",
                str(copied["branches"]),
                "--commitments",
                str(gate4_hash_mismatch),
                "--receipt-out",
                str(gate4_hash_mismatch.with_name("receipt.json")),
                "--json",
            ],
            ["prediction_payload_sha256_mismatch"],
            gate4_hash_mismatch,
        ),
    ]
    negative_results = []
    for name, command, expected_error_needles, mutated_artifact in negative_specs:
        exit_code, parsed, stdout_path, stderr_path = _run_json_command(command, mutated_artifact.with_name("stdout.json"))
        summary = _case_summary(name, parsed, exit_code, expected_error_needles)
        summary.update(
            {
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "mutated_artifact_path": str(mutated_artifact.resolve()),
                "mutated_artifact_sha256": _file_sha256(mutated_artifact),
            }
        )
        negative_results.append(summary)
        if exit_code == 0:
            errors.append(f"negative_case_unexpected_exit_zero:{name}")
        if summary["expected_status_blocked"] is not True:
            errors.append(f"negative_case_not_blocked:{name}:{summary['status']}")
        if summary["expected_errors_matched"] is not True:
            errors.append(f"negative_case_expected_errors_missing:{name}:{summary['matched_error_needles']}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "corpus_sha256": _file_sha256(corpus_path),
        "case_root": str(case_root.resolve()),
        "output_root": str(output_root.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "source_artifacts": {
            key: {"path": str(path.resolve()), "sha256": _file_sha256(path)}
            for key, path in copied.items()
        },
        "source_artifacts_sha256": _stable_json_sha256(
            {key: _file_sha256(path) for key, path in copied.items()}
        ),
        "positive_results": positive_results,
        "negative_results": negative_results,
        "errors": errors,
        "counts": {
            "positive_source_checks": len(positive_results),
            "positive_source_passes": sum(1 for result in positive_results if str(result.get("status", "")).startswith("PASS_")),
            "negative_cases": len(negative_results),
            "negative_cases_blocked": sum(1 for result in negative_results if result.get("expected_status_blocked") is True),
            "negative_cases_expected_errors_matched": sum(1 for result in negative_results if result.get("expected_errors_matched") is True),
        },
        "checks": {
            "source_gate2_3_4_pass": all(str(result.get("status", "")).startswith("PASS_") for result in positive_results),
            "gate2_bad_probability_fails_closed": any(
                result["case"] == "gate2_bad_probability_sum"
                and result["expected_status_blocked"]
                and result["expected_errors_matched"]
                for result in negative_results
            ),
            "gate3_counterfactual_synthetic_boundary_fails_closed": any(
                result["case"] == "gate3_counterfactual_not_synthetic"
                and result["expected_status_blocked"]
                and result["expected_errors_matched"]
                for result in negative_results
            ),
            "gate4_sealed_payload_hash_boundary_fails_closed": any(
                result["case"] == "gate4_prediction_payload_hash_mismatch"
                and result["expected_status_blocked"]
                and result["expected_errors_matched"]
                for result in negative_results
            ),
        },
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "live_originated_artifacts_consumed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_required": False,
        "claims": {
            "proves": [
                "a live-originated Gate 2-4 case still passes source validators before mutation",
                "Gate 2 rejects a malformed probability distribution before accepting the bundle",
                "Gate 3 rejects a counterfactual branch whose synthetic marker is stripped",
                "Gate 4 rejects a sealed prediction payload edited without recomputing its commitment hash",
            ]
            if status == PASS_STATUS
            else [
                "the live-originated Gate 2-4 negative-boundary harness did not meet its fail-closed contract",
            ],
            "does_not_prove": [
                "new Tau text-call execution",
                "new Memory recall",
                "paid provider execution",
                "semantic dream quality",
                "long-duration wall-clock retention",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.corpus, args.case_root, args.output_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
