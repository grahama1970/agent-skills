#!/usr/bin/env python3
"""Run deterministic data-qid verifier fixtures and write a JSON result.

The positive fixtures prove accepted literal controls and stable repeated-entity
QIDs. The negative fixtures prove each source-level violation exits non-zero
for the intended code. An optional sanity step runs the skill sanity script.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaseResult:
    name: str
    path: str
    expected_exit: int
    actual_exit: int
    expected_code: str
    observed_codes: list[str]
    stdout: str
    stderr: str
    passed: bool


def run_verifier(skill_dir: Path, target: Path, output_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    report_path = output_dir / f"{target.stem}.json"
    command = [
        sys.executable,
        str(skill_dir / "scripts" / "verify-data-qid.py"),
        str(target),
        "--json",
        "--output",
        str(report_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return completed, report


def verify_case(skill_dir: Path, fixture: Path, expected_exit: int, expected_code: str, output_dir: Path) -> CaseResult:
    completed, report = run_verifier(skill_dir, fixture, output_dir)
    observed_codes = [str(item.get("code")) for item in report.get("violations", [])]
    passed = completed.returncode == expected_exit and (not expected_code or expected_code in observed_codes)
    return CaseResult(
        name=fixture.stem,
        path=str(fixture),
        expected_exit=expected_exit,
        actual_exit=completed.returncode,
        expected_code=expected_code,
        observed_codes=observed_codes,
        stdout=completed.stdout,
        stderr=completed.stderr,
        passed=passed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="JSON result path")
    parser.add_argument("--include-sanity", action="store_true", help="also run skills/best-practices-react/sanity.sh")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parents[1]
    fixtures = skill_dir / "fixtures" / "data-qid"
    case_output_dir = args.output.parent / "data-qid-case-reports"
    case_output_dir.mkdir(parents=True, exist_ok=True)

    cases: list[CaseResult] = []
    for fixture in sorted((fixtures / "positive").glob("*.tsx")):
        cases.append(verify_case(skill_dir, fixture, 0, "", case_output_dir))

    negative_expectations = {
        "duplicate-literal-qid.tsx": "duplicate_literal_qid",
        "index-derived-qid.tsx": "volatile_qid_identity",
        "malformed-qid.tsx": "malformed_qid",
        "missing-qid.tsx": "missing_qid",
    }
    for name, code in negative_expectations.items():
        cases.append(verify_case(skill_dir, fixtures / "negative" / name, 1, code, case_output_dir))

    sanity: dict[str, object] | None = None
    if args.include_sanity:
        completed = subprocess.run(["bash", str(skill_dir / "sanity.sh")], text=True, capture_output=True, check=False, timeout=60)
        sanity = {
            "command": ["bash", str(skill_dir / "sanity.sh")],
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "passed": completed.returncode == 0,
        }

    passed = all(case.passed for case in cases) and (sanity is None or bool(sanity["passed"]))
    result = {
        "schema": "best_practices_react.data_qid_fixture_result.v1",
        "status": "PASS_DATA_QID_FIXTURES" if passed else "FAIL_DATA_QID_FIXTURES",
        "mocked": False,
        "live": False,
        "proof_boundary": "deterministic source fixtures plus optional skill sanity; no live DOM uniqueness claim",
        "case_reports_dir": str(case_output_dir),
        "cases": [asdict(case) for case in cases],
        "sanity": sanity,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
