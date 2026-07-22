#!/usr/bin/env python3
"""Mutate live-originated Gate 5-7 artifacts and require fail-closed receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_LIVE_GATE5_7_BOUNDARY_NEGATIVES"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_GATE5_7_BOUNDARY_NEGATIVES"
SCHEMA = "persona_dream.research.prospective_tom.live_gate5_7_boundary_negatives_receipt.v1"
RESEARCH_ROOT = Path(__file__).resolve().parents[1]
CHECK_GATE5 = RESEARCH_ROOT / "scripts" / "reveal_and_score_trial.py"
CHECK_GATE6 = RESEARCH_ROOT / "scripts" / "run_action_selection_trial.py"
CHECK_GATE7 = RESEARCH_ROOT / "scripts" / "check_tom_belief_revision.py"


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


def _copy_source_artifacts(
    case_root: Path,
    scoring_receipt: Path,
    action_selection: Path,
    belief_revision: Path,
    output_root: Path,
) -> dict[str, Path]:
    source_dir = output_root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "distributions": case_root / "tom_belief_distribution_bundle.json",
        "branches": case_root / "counterfactual_branch_bundle.json",
        "commitments": case_root / "tom_prediction_commitment_bundle.json",
        "outcome": case_root / "tom_outcome_reveal.json",
        "scoring_receipt": scoring_receipt,
        "action_selection": action_selection,
        "belief_revision": belief_revision,
    }
    copied: dict[str, Path] = {}
    for key, path in sources.items():
        target = source_dir / path.name
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        copied[key] = target
    return copied


def _mutate_gate5_invalid_actual_action(source: Path, target: Path) -> None:
    outcome = _load_json(source)
    outcome["actual_next_action"] = "__INVALID_COUNTERPART_ACTION__"
    _write_json(target, outcome)


def _mutate_gate6_invalid_selected_action(source: Path, target: Path) -> None:
    action = _load_json(source)
    action["selected_action"] = "__INVALID_AGENT_ACTION__"
    _write_json(target, action)


def _mutate_gate7_prior_not_auditable(source: Path, target: Path) -> None:
    revision = _load_json(source)
    revision["prior_remains_auditable"] = False
    revision["evidence_mutations"] = [{"mutation": "fixture_tamper_prior_audit_boundary"}]
    _write_json(target, revision)


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


def build_receipt(
    corpus_path: Path,
    case_root: Path,
    scoring_receipt: Path,
    action_selection: Path,
    belief_revision: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    output_root.mkdir(parents=True, exist_ok=True)
    copied = _copy_source_artifacts(case_root, scoring_receipt, action_selection, belief_revision, output_root)
    positive_dir = output_root / "positive_source"
    negative_dir = output_root / "negative_cases"

    positive_commands = [
        (
            "gate5_source_positive",
            [
                sys.executable,
                str(CHECK_GATE5),
                "--corpus",
                str(corpus_path),
                "--distributions",
                str(copied["distributions"]),
                "--branches",
                str(copied["branches"]),
                "--commitments",
                str(copied["commitments"]),
                "--outcome",
                str(copied["outcome"]),
                "--receipt-out",
                str(positive_dir / "gate5_source_positive_receipt.json"),
                "--json",
            ],
        ),
        (
            "gate6_source_positive",
            [
                sys.executable,
                str(CHECK_GATE6),
                "--corpus",
                str(corpus_path),
                "--scoring-receipt",
                str(copied["scoring_receipt"]),
                "--outcome",
                str(copied["outcome"]),
                "--action-selection",
                str(copied["action_selection"]),
                "--receipt-out",
                str(positive_dir / "gate6_source_positive_receipt.json"),
                "--json",
            ],
        ),
        (
            "gate7_source_positive",
            [
                sys.executable,
                str(CHECK_GATE7),
                "--distributions",
                str(copied["distributions"]),
                "--scoring-receipt",
                str(copied["scoring_receipt"]),
                "--outcome",
                str(copied["outcome"]),
                "--belief-revision",
                str(copied["belief_revision"]),
                "--receipt-out",
                str(positive_dir / "gate7_source_positive_receipt.json"),
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

    gate5_invalid_outcome = negative_dir / "gate5_invalid_actual_action" / "tom_outcome_reveal.json"
    gate6_invalid_action = negative_dir / "gate6_invalid_selected_action" / "action_selection.json"
    gate7_prior_not_auditable = negative_dir / "gate7_prior_not_auditable" / "tom_belief_revision.json"
    _mutate_gate5_invalid_actual_action(copied["outcome"], gate5_invalid_outcome)
    _mutate_gate6_invalid_selected_action(copied["action_selection"], gate6_invalid_action)
    _mutate_gate7_prior_not_auditable(copied["belief_revision"], gate7_prior_not_auditable)

    negative_specs = [
        (
            "gate5_invalid_actual_action",
            [
                sys.executable,
                str(CHECK_GATE5),
                "--corpus",
                str(corpus_path),
                "--distributions",
                str(copied["distributions"]),
                "--branches",
                str(copied["branches"]),
                "--commitments",
                str(copied["commitments"]),
                "--outcome",
                str(gate5_invalid_outcome),
                "--receipt-out",
                str(gate5_invalid_outcome.with_name("receipt.json")),
                "--json",
            ],
            ["outcome_actual_next_action_not_allowed"],
            gate5_invalid_outcome,
        ),
        (
            "gate6_invalid_selected_action",
            [
                sys.executable,
                str(CHECK_GATE6),
                "--corpus",
                str(corpus_path),
                "--scoring-receipt",
                str(copied["scoring_receipt"]),
                "--outcome",
                str(copied["outcome"]),
                "--action-selection",
                str(gate6_invalid_action),
                "--receipt-out",
                str(gate6_invalid_action.with_name("receipt.json")),
                "--json",
            ],
            ["selected_action_not_in_vocabulary"],
            gate6_invalid_action,
        ),
        (
            "gate7_prior_not_auditable",
            [
                sys.executable,
                str(CHECK_GATE7),
                "--distributions",
                str(copied["distributions"]),
                "--scoring-receipt",
                str(copied["scoring_receipt"]),
                "--outcome",
                str(copied["outcome"]),
                "--belief-revision",
                str(gate7_prior_not_auditable),
                "--receipt-out",
                str(gate7_prior_not_auditable.with_name("receipt.json")),
                "--json",
            ],
            ["prior_remains_auditable_not_true", "evidence_mutations_not_empty"],
            gate7_prior_not_auditable,
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
        "scoring_receipt": str(scoring_receipt.resolve()),
        "action_selection": str(action_selection.resolve()),
        "belief_revision": str(belief_revision.resolve()),
        "output_root": str(output_root.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "source_artifacts": {
            key: {"path": str(path.resolve()), "sha256": _file_sha256(path)}
            for key, path in copied.items()
        },
        "source_artifacts_sha256": _stable_json_sha256({key: _file_sha256(path) for key, path in copied.items()}),
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
            "source_gate5_6_7_pass": all(str(result.get("status", "")).startswith("PASS_") for result in positive_results),
            "gate5_invalid_actual_action_fails_closed": any(
                result["case"] == "gate5_invalid_actual_action"
                and result["expected_status_blocked"]
                and result["expected_errors_matched"]
                for result in negative_results
            ),
            "gate6_invalid_selected_action_fails_closed": any(
                result["case"] == "gate6_invalid_selected_action"
                and result["expected_status_blocked"]
                and result["expected_errors_matched"]
                for result in negative_results
            ),
            "gate7_prior_audit_boundary_fails_closed": any(
                result["case"] == "gate7_prior_not_auditable"
                and result["expected_status_blocked"]
                and result["expected_errors_matched"]
                for result in negative_results
            ),
            "human_content_judgment_absent": True,
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
        "llm_judge_used": False,
        "claims": {
            "proves": [
                "a live-originated Gate 5-7 case still passes source validators before mutation",
                "Gate 5 rejects an outcome reveal whose actual counterpart action is outside the deterministic episode action set",
                "Gate 6 rejects an action-selection artifact whose selected action is outside the constrained action vocabulary",
                "Gate 7 rejects belief revision that fails to preserve the prior as auditable or mutates evidence",
            ]
            if status == PASS_STATUS
            else [
                "the live-originated Gate 5-7 negative-boundary harness did not meet its fail-closed contract",
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
    parser.add_argument("--scoring-receipt", type=Path, required=True)
    parser.add_argument("--action-selection", type=Path, required=True)
    parser.add_argument("--belief-revision", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(
        args.corpus,
        args.case_root,
        args.scoring_receipt,
        args.action_selection,
        args.belief_revision,
        args.output_root,
        args.receipt_out,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
