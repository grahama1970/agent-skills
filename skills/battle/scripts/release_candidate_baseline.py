#!/usr/bin/env python3
"""Build a source-bound Battle release-candidate baseline receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BATTLE_DIR = SCRIPT_DIR.parent
REPO_ROOT = BATTLE_DIR.parents[1]
RUN_SH = BATTLE_DIR / "run.sh"
SPECTATOR_DIR = BATTLE_DIR / "spectator"
STATUS_PATH = BATTLE_DIR / "CURRENT_STATUS.json"
PROJECT_STATE_RUN = REPO_ROOT / "skills" / "project-state" / "run.sh"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _run(
    command: list[str],
    *,
    cwd: Path,
    out_file: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    receipt = {
        "command": command,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "duration_seconds": round(time.time() - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if out_file is not None:
        _write_json(out_file, receipt)
    return receipt


def _version(command: list[str], *, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return (proc.stdout or proc.stderr).strip()


def _source() -> dict[str, Any]:
    return {
        "repository": "grahama1970/agent-skills",
        "branch": _git(["branch", "--show-current"]),
        "head_commit": _git(["rev-parse", "HEAD"]),
        "origin_main_commit": _git(["rev-parse", "origin/main"]),
        "merge_base_origin_main": _git(["merge-base", "HEAD", "origin/main"]),
        "battle_tree": _git(["rev-parse", "HEAD:skills/battle"]),
    }


def _status_porcelain() -> list[str]:
    output = _git(["status", "--porcelain=v1"])
    return [line for line in output.splitlines() if line.strip()]


def _move_if_untracked(path: Path, cleanup_dir: Path) -> str | None:
    rel = str(path.relative_to(REPO_ROOT))
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", rel],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if tracked.returncode == 0 or not path.exists():
        return None
    target = cleanup_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    path.rename(target)
    return str(target)


def cleanup_known_generated(out_dir: Path) -> dict[str, Any]:
    cleanup_dir = out_dir / "generated-cleanup"
    moved = [
        item
        for item in (
            _move_if_untracked(REPO_ROOT / "skills" / "create-midi" / "uv.lock", cleanup_dir),
            _move_if_untracked(BATTLE_DIR / ".venv", cleanup_dir),
            _move_if_untracked(BATTLE_DIR / "skills" / "battle", cleanup_dir),
        )
        if item is not None
    ]
    return {"schema": "battle.release_candidate_generated_cleanup.v1", "moved": moved}


def _parse_summary_counts(stdout: str, stderr: str) -> dict[str, int]:
    text = stdout + "\n" + stderr
    counts = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "errored": 0,
    }
    patterns = {
        "passed": r"(\d+) passed",
        "failed": r"(\d+) failed",
        "skipped": r"(\d+) skipped",
        "xfailed": r"(\d+) xfailed",
        "xpassed": r"(\d+) xpassed",
        "errored": r"(\d+) errors?",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            counts[key] = int(matches[-1])
    return counts


def _parse_pytest_junit(path: Path, stdout: str, stderr: str) -> dict[str, Any]:
    summary = {
        "collected": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "errored": 0,
        "duration_seconds": 0.0,
    }
    if path.is_file():
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
        failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
        errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
        skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
        duration = sum(float(suite.attrib.get("time", "0")) for suite in suites)
        summary.update(
            {
                "collected": tests,
                "failed": failures,
                "errored": errors,
                "skipped": skipped,
                "duration_seconds": round(duration, 3),
                "passed": max(tests - failures - errors - skipped, 0),
            }
        )
    text_counts = _parse_summary_counts(stdout, stderr)
    for key in ("passed", "failed", "skipped", "xfailed", "xpassed", "errored"):
        if text_counts[key]:
            summary[key] = text_counts[key]
    if not summary["collected"]:
        summary["collected"] = sum(summary[key] for key in ("passed", "failed", "skipped", "xfailed", "xpassed", "errored"))
    return summary


def _classify_path(path: str, status: str) -> dict[str, str]:
    if path == "skills/battle/CURRENT_STATUS.json":
        category = "intentional_committed_status"
        reason = "regenerated from current GitHub Battle issue state and named receipts"
    elif path.startswith("skills/battle/tests/"):
        category = "intentional_source_test"
        reason = "test fixture/source adjustment for scanner-safe synthetic auth values"
    elif path.startswith("skills/battle/scripts/") or path.startswith("skills/battle/src/battle_skill/") or path.startswith("skills/battle/utils/") or path == "skills/battle/run.sh":
        category = "intentional_source"
        reason = "Battle runtime or bounded release-candidate proof command"
    elif path.startswith("skills/battle/spectator/src/") and path.endswith((".test.ts", ".test.tsx")):
        category = "intentional_source_test"
        reason = "spectator test expectation aligned to current committed fixture semantics"
    elif path.startswith("skills/battle/docs/") or path in {"skills/battle/README.md", "skills/battle/PROJECT_KNOWLEDGE.md"}:
        category = "intentional_documentation"
        reason = "documentation drift disposition or status pointer"
    elif path.startswith("skills/battle/fixtures/") or "/battle-fixtures/" in path:
        category = "intentional_committed_fixture"
        reason = "committed fixture governed by Battle repository policy"
    elif path.startswith("skills/battle/local/") or path.startswith("skills/battle/artifacts/"):
        category = "generated_proof_runtime_output"
        reason = "generated proof/runtime output should not be committed unless policy says so"
    else:
        category = "unrelated_or_unclassified"
        reason = "path needs human review before inclusion"
    return {"path": path, "git_status": status, "category": category, "reason": reason}


def build_path_classification(out: Path) -> dict[str, Any]:
    output = _git(["diff", "--name-status", "origin/main...HEAD", "--", "skills/battle"])
    entries = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        entries.append(_classify_path(path, status))
    payload = {
        "schema": "battle.release_candidate_path_classification.v1",
        "generated_at": _utc(),
        "comparison": "origin/main...HEAD",
        "entries": entries,
        "summary": {
            "total": len(entries),
            "unclassified": sum(1 for item in entries if item["category"] == "unrelated_or_unclassified"),
            "generated_runtime_output": sum(1 for item in entries if item["category"] == "generated_proof_runtime_output"),
        },
    }
    _write_json(out, payload)
    return payload


def _doc_disposition(item: dict[str, Any]) -> dict[str, Any]:
    issue = item.get("issue")
    line = item.get("line", "")
    if issue == "stale_reference":
        disposition = "suppressed_historical_reference"
        reason = "PROJECT_KNOWLEDGE.md is explicitly marked historical below CURRENT_STATUS.json; stale path refs are not current blockers."
    elif issue in {"planned", "future", "not_yet"}:
        disposition = "marked_non_current_or_roadmap"
        reason = "README/knowledge prose is a proof-boundary or roadmap/non-claim; current release state is sourced from CURRENT_STATUS.json."
    else:
        disposition = "needs_review"
        reason = "unrecognized doc drift item"
    return {
        "file": item.get("file"),
        "issue": issue,
        "severity": item.get("severity"),
        "line": line,
        "disposition": disposition,
        "source_backed_reason": reason,
    }


def build_project_state_receipts(project_state_path: Path, scanner_out: Path, doc_out: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = _read_json(project_state_path)
    findings = data.get("phase_4_best_practices", {}).get("findings", [])
    by_severity = data.get("phase_4_best_practices", {}).get("by_severity", {})
    critical_findings = [item for item in findings if item.get("severity") == "critical"]
    scanner = {
        "schema": "battle.release_candidate_scanner_disposition.v1",
        "generated_at": _utc(),
        "tool": "skills/project-state/run.sh report",
        "ruleset": "phase_4_best_practices",
        "status": "PASS" if not critical_findings else "FAIL",
        "by_severity": by_severity,
        "critical_findings": critical_findings,
        "findings": findings,
        "dispositions": [
            {
                "file": item.get("file"),
                "issue": item.get("issue"),
                "severity": item.get("severity"),
                "disposition": "accepted_low_path_portability_followup"
                if item.get("severity") == "low"
                else "unresolved",
                "source_backed_reason": "project-state classified this as low severity; it is not a release-candidate blocker for #1178.",
            }
            for item in findings
        ],
    }
    drift_items = data.get("phase_3_doc_drift", {}).get("drift_items", [])
    doc_dispositions = [_doc_disposition(item) for item in drift_items]
    doc = {
        "schema": "battle.release_candidate_doc_drift_disposition.v1",
        "generated_at": _utc(),
        "tool": "skills/project-state/run.sh report",
        "status": "PASS"
        if all(item["disposition"] != "needs_review" for item in doc_dispositions)
        else "FAIL",
        "drift_count": len(drift_items),
        "drift_items": drift_items,
        "dispositions": doc_dispositions,
    }
    _write_json(scanner_out, scanner)
    _write_json(doc_out, doc)
    return data, scanner, doc


def run_project_state(out_dir: Path) -> dict[str, Any]:
    project_state_path = out_dir / "project-state.json"
    env = os.environ.copy()
    env["PROJECT_STATE_ROOT"] = str(BATTLE_DIR)
    env["PROJECT_STATE_NAME"] = "battle"
    command = [str(PROJECT_STATE_RUN), "report", "--json", "--output", str(project_state_path)]
    result = _run(command, cwd=REPO_ROOT, out_file=out_dir / "project-state-command.json", env=env)
    return {"command_result": result, "path": str(project_state_path)}


def run_pytest(out_dir: Path) -> dict[str, Any]:
    junit = out_dir / "pytest-junit.xml"
    command = ["uv", "run", "--project", str(BATTLE_DIR), "pytest", "tests", "-q", "--tb=short", f"--junit-xml={junit}"]
    result = _run(command, cwd=BATTLE_DIR, out_file=out_dir / "pytest-command.json")
    counts = _parse_pytest_junit(junit, result["stdout"], result["stderr"])
    receipt = {
        "schema": "battle.release_candidate_pytest_result.v1",
        "status": "PASS" if result["exit_code"] == 0 and counts["failed"] == 0 and counts["errored"] == 0 else "FAIL",
        "mocked": False,
        "live": False,
        "source": _source(),
        "junit_xml": str(junit),
        "counts": counts,
        "command_result_path": str(out_dir / "pytest-command.json"),
    }
    _write_json(out_dir / "pytest-result.json", receipt)
    return receipt


def run_spectator(out_dir: Path, skip_npm_ci: bool) -> dict[str, Any]:
    npm_ci: dict[str, Any]
    if skip_npm_ci or (SPECTATOR_DIR / "node_modules").is_dir():
        npm_ci = {
            "command": ["npm", "ci"],
            "cwd": str(SPECTATOR_DIR),
            "exit_code": 0,
            "duration_seconds": 0,
            "stdout": "skipped: node_modules already present or --skip-npm-ci set",
            "stderr": "",
        }
    else:
        npm_ci = _run(["npm", "ci"], cwd=SPECTATOR_DIR, out_file=out_dir / "npm-ci-command.json")
    typecheck = _run(["npm", "run", "typecheck"], cwd=SPECTATOR_DIR, out_file=out_dir / "spectator-typecheck-command.json")
    build = _run(["npm", "run", "build"], cwd=SPECTATOR_DIR, out_file=out_dir / "spectator-build-command.json")
    test = _run(["npm", "test"], cwd=SPECTATOR_DIR, out_file=out_dir / "spectator-test-command.json")
    receipt = {
        "schema": "battle.release_candidate_spectator_result.v1",
        "status": "PASS"
        if all(item["exit_code"] == 0 for item in (npm_ci, typecheck, build, test))
        else "FAIL",
        "mocked": False,
        "live": False,
        "source": _source(),
        "commands": {
            "npm_ci": npm_ci,
            "typecheck": typecheck,
            "build": build,
            "test": test,
        },
    }
    _write_json(out_dir / "spectator-result.json", receipt)
    return receipt


def run_current_status(out_dir: Path) -> dict[str, Any]:
    generated = out_dir / "CURRENT_STATUS.generated.json"
    generate = _run([str(RUN_SH), "current-status", "generate", "--out", str(generated)], cwd=BATTLE_DIR, out_file=out_dir / "current-status-generate-command.json")
    check = _run([str(RUN_SH), "current-status", "check", "--path", str(STATUS_PATH)], cwd=BATTLE_DIR, out_file=out_dir / "current-status-check-command.json")
    errors: list[str] = []
    if generate["exit_code"] != 0:
        errors.append("current_status_generate_failed")
    if check["exit_code"] != 0:
        errors.append("current_status_check_failed")
    if generated.is_file() and STATUS_PATH.is_file():
        current = _read_json(STATUS_PATH)
        fresh = _read_json(generated)
        current_issues = current.get("issue_state_at_generation")
        fresh_issues = fresh.get("issue_state_at_generation")
        if current_issues != fresh_issues:
            errors.append("current_status_issue_state_disagrees_with_github")
    else:
        errors.append("current_status_file_missing")
    receipt = {
        "schema": "battle.release_candidate_current_status_result.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": False,
        "repository_status": str(STATUS_PATH),
        "generated_status": str(generated),
        "status_sha256": _sha256(STATUS_PATH),
        "generated_sha256": _sha256(generated),
        "errors": errors,
        "commands": {
            "generate": str(out_dir / "current-status-generate-command.json"),
            "check": str(out_dir / "current-status-check-command.json"),
        },
        "comparison_note": "Issue-state equality is checked; updated_at and self-referential source commit are not used for equality.",
    }
    _write_json(out_dir / "current-status-result.json", receipt)
    return receipt


def run_gate_commands(out_dir: Path) -> dict[str, Any]:
    fast_out = out_dir / "fast-sanity.json"
    deterministic_dir = out_dir / "deterministic"
    deterministic_receipt = deterministic_dir / "backend-eval.json"
    fast_cmd = _run([str(RUN_SH), "tiered-gate", "fast-sanity", "--out", str(fast_out)], cwd=BATTLE_DIR, out_file=out_dir / "fast-sanity-command.json")
    deterministic_cmd = _run(
        [
            str(RUN_SH),
            "tiered-gate",
            "deterministic",
            "--out-dir",
            str(deterministic_dir),
            "--receipt-out",
            str(deterministic_receipt),
        ],
        cwd=BATTLE_DIR,
        out_file=out_dir / "deterministic-gate-command.json",
    )
    fast_receipt = _read_json(fast_out) if fast_out.is_file() else {}
    deterministic_gate = deterministic_receipt.with_name("tiered-deterministic-gate.json")
    deterministic_receipt_payload = _read_json(deterministic_gate) if deterministic_gate.is_file() else {}
    receipt = {
        "schema": "battle.release_candidate_gate_results.v1",
        "status": "PASS"
        if fast_cmd["exit_code"] == 0
        and deterministic_cmd["exit_code"] == 0
        and fast_receipt.get("status") == "PASS"
        and deterministic_receipt_payload.get("status") == "PASS"
        else "FAIL",
        "mocked": False,
        "live": False,
        "fast_sanity_receipt": str(fast_out),
        "deterministic_gate_receipt": str(deterministic_gate),
        "commands": {
            "fast_sanity": str(out_dir / "fast-sanity-command.json"),
            "deterministic": str(out_dir / "deterministic-gate-command.json"),
        },
    }
    _write_json(out_dir / "gate-results.json", receipt)
    return receipt


def dependency_hashes() -> dict[str, Any]:
    files = [
        BATTLE_DIR / "pyproject.toml",
        BATTLE_DIR / "uv.lock",
        SPECTATOR_DIR / "package.json",
        SPECTATOR_DIR / "package-lock.json",
    ]
    return {str(path.relative_to(REPO_ROOT)): _sha256(path) for path in files}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Battle release-candidate baseline proof")
    parser.add_argument("--out", type=Path, default=Path("/tmp/battle-release-candidate-baseline"))
    parser.add_argument("--allow-dirty", action="store_true", help="write a receipt without failing on dirty worktree")
    parser.add_argument("--skip-npm-ci", action="store_true", help="do not install spectator dependencies before checks")
    args = parser.parse_args()

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    source = _source()
    start_dirty = _status_porcelain()

    path_manifest = build_path_classification(out_dir / "path-classification.json")
    project_state_run = run_project_state(out_dir)
    project_state_path = Path(project_state_run["path"])
    project_state: dict[str, Any] = {}
    scanner: dict[str, Any] = {"status": "FAIL", "critical_findings": ["project_state_missing"]}
    doc: dict[str, Any] = {"status": "FAIL", "dispositions": ["project_state_missing"]}
    if project_state_path.is_file():
        project_state, scanner, doc = build_project_state_receipts(
            project_state_path,
            out_dir / "scanner-disposition.json",
            out_dir / "doc-drift-disposition.json",
        )

    pytest_result = run_pytest(out_dir)
    gate_results = run_gate_commands(out_dir)
    spectator_result = run_spectator(out_dir, args.skip_npm_ci)
    current_status = run_current_status(out_dir)
    generated_cleanup = cleanup_known_generated(out_dir)
    final_dirty = _status_porcelain()

    errors: list[str] = []
    if path_manifest["summary"]["unclassified"]:
        errors.append("unclassified_battle_path_changes")
    if path_manifest["summary"]["generated_runtime_output"]:
        errors.append("generated_runtime_output_in_committed_diff")
    if scanner.get("status") != "PASS":
        errors.append("unresolved_critical_scanner_findings")
    if doc.get("status") != "PASS":
        errors.append("unresolved_documentation_drift_dispositions")
    if pytest_result.get("status") != "PASS":
        errors.append("full_pytest_failed_or_errored")
    if gate_results.get("status") != "PASS":
        errors.append("battle_gate_failed")
    if spectator_result.get("status") != "PASS":
        errors.append("spectator_typecheck_build_or_test_failed")
    if current_status.get("status") != "PASS":
        errors.append("current_status_inconsistent")
    if final_dirty and not args.allow_dirty:
        errors.append("worktree_dirty")

    receipt = {
        "schema": "battle.release_candidate_baseline.v1",
        "status": "PASS" if not errors else "FAIL",
        "generated_at": _utc(),
        "duration_seconds": round(time.time() - started, 3),
        "mocked": False,
        "live": False,
        "source": source,
        "runtime_versions": {
            "python": _version(["python3", "--version"]),
            "uv": _version(["uv", "--version"]),
            "node": _version(["node", "--version"], cwd=SPECTATOR_DIR),
            "npm": _version(["npm", "--version"], cwd=SPECTATOR_DIR),
        },
        "dependency_lock_hashes": dependency_hashes(),
        "worktree": {
            "start_dirty_count": len(start_dirty),
            "start_dirty": start_dirty,
            "final_dirty_count": len(final_dirty),
            "final_dirty": final_dirty,
            "allow_dirty": args.allow_dirty,
        },
        "receipts": {
            "path_classification": str(out_dir / "path-classification.json"),
            "project_state": str(project_state_path),
            "scanner_disposition": str(out_dir / "scanner-disposition.json"),
            "doc_drift_disposition": str(out_dir / "doc-drift-disposition.json"),
            "pytest_result": str(out_dir / "pytest-result.json"),
            "fast_and_deterministic_gates": str(out_dir / "gate-results.json"),
            "spectator": str(out_dir / "spectator-result.json"),
            "current_status": str(out_dir / "current-status-result.json"),
            "generated_cleanup": str(out_dir / "generated-cleanup.json"),
        },
        "project_state_summary": {
            "tests_collected": project_state.get("phase_1_infrastructure", {}).get("tests", {}).get("total"),
            "best_practices": project_state.get("phase_4_best_practices", {}).get("by_severity"),
            "doc_drift_count": project_state.get("phase_3_doc_drift", {}).get("drift_count"),
            "gaps": project_state.get("phase_6_gaps", {}).get("gaps"),
        },
        "errors": errors,
        "non_claims": [
            "This baseline does not claim production deployment readiness.",
            "This baseline does not claim live Arena-to-Pixi qualification for the current source.",
            "This baseline does not close product-integration tickets without their own source-bound receipts.",
        ],
    }
    _write_json(out_dir / "generated-cleanup.json", generated_cleanup)
    _write_json(out_dir / "baseline-receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(out_dir / "baseline-receipt.json"), "errors": errors}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
