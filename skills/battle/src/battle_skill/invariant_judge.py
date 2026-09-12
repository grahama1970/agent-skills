"""Pluggable invariant Judge for Battle.

Battle's default scoring targets exploitation (system-down, command injection).
But the most common real use of an adversarial Red/Blue loop is verifying a
PROJECT-SPECIFIC INVARIANT: "no PII value leaks", "the ledger always balances",
"the parser never drops a record", "the authz check cannot be bypassed".

An invariant Judge is a small, independent, deterministic module the operator
supplies. Red's objective becomes "produce an input/mutation that makes the
Judge fail"; Blue's is "make it pass again". The scorekeeper reads the Judge
result, never an agent's self-report. This is the honest core: the Judge, not
the LLM, decides.

Contract: a judge module exposes

    def judge(target_dir: str, params: dict) -> dict

and returns a dict matching InvariantResult (schema
battle.invariant_result.v1): {passed: bool, violations: [str], evidence: dict}.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InvariantResult:
    schema: str = "battle.invariant_result.v1"
    passed: bool = False
    violations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    judge_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_judge(judge_path: str):
    """Load a judge module's judge(target_dir, params) callable from a file."""
    path = Path(judge_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"judge module not found: {path}")
    spec = importlib.util.spec_from_file_location("battle_invariant_judge", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load judge module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "judge") or not callable(module.judge):
        raise AttributeError(f"judge module {path} must define judge(target_dir, params)")
    return module.judge


def run_judge(judge_path: str, target_dir: str, params: dict[str, Any] | None = None) -> InvariantResult:
    """Run an invariant judge and normalize its output. Fail-closed: any error
    is a FAILED invariant, never a silent pass."""
    params = params or {}
    try:
        raw = load_judge(judge_path)(target_dir, params)
    except Exception as exc:  # a judge that cannot run has NOT proven the invariant
        return InvariantResult(passed=False, violations=[f"judge error: {exc}"], judge_path=judge_path)
    if not isinstance(raw, dict) or "passed" not in raw:
        return InvariantResult(passed=False,
                               violations=["judge returned a malformed result (missing 'passed')"],
                               judge_path=judge_path)
    return InvariantResult(
        passed=bool(raw.get("passed")),
        violations=list(raw.get("violations", [])),
        evidence=dict(raw.get("evidence", {})),
        judge_path=judge_path,
    )


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run a Battle invariant judge against a target directory.")
    ap.add_argument("--judge", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--params", default="{}", help="JSON params passed to the judge")
    args = ap.parse_args(argv)
    result = run_judge(args.judge, args.target, json.loads(args.params))
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
