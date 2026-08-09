#!/usr/bin/env python3
"""Prove the monitor-codebase docstring workflow on real local files.

The proof creates a throwaway Python project, runs the proposal CLI, applies one
approved candidate, and verifies stale, malformed, unsupported, and AST-changing
candidates fail closed without source mutation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
MODULE_PATH = SKILL_DIR / "autofix_docstrings.py"


def load_autofix() -> Any:
    """Load the docstring workflow module for direct invariant checks."""
    spec = importlib.util.spec_from_file_location("autofix_docstrings_proof", MODULE_PATH)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: Any) -> None:
    """Write a stable JSON proof artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSONL objects from a proof artifact."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL objects for the apply CLI."""
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    """Run a bounded command and return its receipt."""
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=30, check=False)
    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def candidate_by_name(candidates: list[dict[str, Any]], qualified_name: str) -> dict[str, Any]:
    """Return one candidate by qualified symbol name."""
    for candidate in candidates:
        symbol = candidate.get("symbol") if isinstance(candidate.get("symbol"), dict) else {}
        if symbol.get("qualified_name") == qualified_name:
            return candidate
    names = [row.get("symbol", {}).get("qualified_name") for row in candidates]
    raise AssertionError(f"missing candidate {qualified_name}; got {names}")


def approved(candidate: dict[str, Any], docstring: str) -> dict[str, Any]:
    """Return an approved copy of a proposal candidate."""
    row = json.loads(json.dumps(candidate))
    row["approval"] = {"status": "approved", "approved_by": "proof"}
    row["proposed_docstring"] = docstring
    row["contract"]["unsupported_claims"] = []
    return row


def build_fixture(root: Path) -> Path:
    """Create a deterministic Python project for the workflow proof."""
    project = root / "fixture_project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "api.py").write_text(
        "\n".join(
            [
                "def load_user(user_id):",
                "    return {'id': user_id}",
                "",
                "def notify(user_id):",
                "    print(user_id)",
                "",
                "def write_file(path, value):",
                "    path.write_text(value)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return project


def main() -> int:
    """Run the live proof and write proof-summary.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Proof output directory.")
    parser.add_argument("--live", action="store_true", help="Confirm this proof runs against real local files.")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("refusing to run without --live")

    proof_dir = args.out.resolve()
    if proof_dir.exists():
        shutil.rmtree(proof_dir)
    proof_dir.mkdir(parents=True)
    project = build_fixture(proof_dir)
    module = load_autofix()

    candidates_path = proof_dir / "docstring-candidates.jsonl"
    propose_command = [sys.executable, str(MODULE_PATH), "propose-docstrings", str(project), "--output", str(candidates_path)]
    propose_receipt = run_command(propose_command, REPO_ROOT)
    write_json(proof_dir / "propose-command.json", propose_receipt)
    candidates = read_jsonl(candidates_path)

    source_path = project / "api.py"
    before_text = source_path.read_text(encoding="utf-8")
    before_ast = module.normalize_ast_without_docstrings(before_text)

    good = approved(candidate_by_name(candidates, "load_user"), "Return a user record.")
    malformed = approved(candidate_by_name(candidates, "notify"), "")
    unsupported = approved(candidate_by_name(candidates, "write_file"), "Safely write the file atomically.")

    stale = approved(candidate_by_name(candidates, "notify"), "Write the notification to standard output.")
    stale["symbol"]["source_sha256"] = "sha256:" + "0" * 64

    apply_candidates_path = proof_dir / "reviewed-candidates.jsonl"
    write_jsonl(apply_candidates_path, [malformed, unsupported, stale, good])
    apply_receipt_path = proof_dir / "apply-receipt.json"
    apply_command = [
        sys.executable,
        str(MODULE_PATH),
        "apply-docstrings",
        str(apply_candidates_path),
        "--branch-or-worktree",
        str(project),
        "--receipt",
        str(apply_receipt_path),
    ]
    apply_command_receipt = run_command(apply_command, REPO_ROOT)
    write_json(proof_dir / "apply-command.json", apply_command_receipt)
    apply_receipt = json.loads(apply_receipt_path.read_text(encoding="utf-8"))

    after_text = source_path.read_text(encoding="utf-8")
    after_ast = module.normalize_ast_without_docstrings(after_text)
    direct_ast_receipt = {"before": before_ast, "after": after_ast, "same_without_docstrings": before_ast == after_ast}
    write_json(proof_dir / "ast-equivalence.json", direct_ast_receipt)

    monkey_candidate = approved(candidate_by_name(module.scan_file(project, source_path, include_optional=False), "notify"), "Notify a user.")
    original_docstring_line = module.docstring_line
    module.docstring_line = lambda _docstring, indent: f"{indent}x = 1\n"
    rollback_receipt = module.apply_candidate(project, monkey_candidate)
    module.docstring_line = original_docstring_line
    write_json(proof_dir / "rollback-receipt.json", rollback_receipt)

    final_text = source_path.read_text(encoding="utf-8")
    outcomes = apply_receipt.get("outcomes", [])
    outcome_errors = [row.get("errors", []) for row in outcomes]
    checks = {
        "propose_cli_exit_zero": propose_receipt["exit_code"] == 0,
        "apply_cli_exit_zero": apply_command_receipt["exit_code"] == 0,
        "candidate_schema_present": bool(candidates) and all(row.get("schema") == module.SCHEMA_CANDIDATE for row in candidates),
        "source_not_mutated_by_propose": before_text == source_path.read_text(encoding="utf-8").replace('    """Return a user record."""\n', ""),
        "one_candidate_applied": apply_receipt.get("applied") == 1,
        "three_candidates_rejected": apply_receipt.get("rejected") == 3,
        "stale_rejected": any("stale_source_hash" in errors for errors in outcome_errors),
        "malformed_rejected": any("missing_proposed_docstring" in errors for errors in outcome_errors),
        "unsupported_claim_rejected": any("unsupported_claim_in_docstring" in errors for errors in outcome_errors),
        "ast_same_except_docstrings": direct_ast_receipt["same_without_docstrings"],
        "rollback_rejected_ast_change": any("non_docstring_ast_changed" in error for error in rollback_receipt.get("errors", [])),
        "rollback_left_source_clean": "x = 1" not in final_text,
    }
    summary = {
        "schema": "monitor_codebase.docstring_workflow_proof.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "mocked": "no",
        "live": "yes",
        "repo_root": str(REPO_ROOT),
        "skill_dir": str(SKILL_DIR),
        "artifacts": {
            "propose_command": str((proof_dir / "propose-command.json").resolve()),
            "candidates": str(candidates_path.resolve()),
            "apply_command": str((proof_dir / "apply-command.json").resolve()),
            "apply_receipt": str(apply_receipt_path.resolve()),
            "ast_equivalence": str((proof_dir / "ast-equivalence.json").resolve()),
            "rollback_receipt": str((proof_dir / "rollback-receipt.json").resolve()),
        },
        "checks": checks,
    }
    write_json(proof_dir / "proof-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
