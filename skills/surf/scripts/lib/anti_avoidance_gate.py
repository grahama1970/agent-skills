#!/usr/bin/env python3
"""Oracle-agnostic anti-avoidance gate for 2-agent (project-agent <-> oracle) loops.

This is deterministic machinery, NOT a third agent. It makes a drifting project
agent unable to launder side-quests + vague updates + passing side-quest unit
tests into progress: credit is granted ONLY when the human-authored
`blocker_evidence.command` flips from failing to passing. The gate runs that
command itself; it never trusts the agent's prose.

Enforced (per the hardening spec):
- immutable goal: `goal_hash` frozen over goal_id/goal_lock/current_milestone/
  top_blocker/blocker_evidence.command; every round must reuse the same gate.
- one milestone only: list-valued milestone/blocker/command is rejected.
- persisted active gate: a new gate is rejected until the current one PASSES or
  an explicit human --override is given.
- blocker-evidence delta: progress == command return code flips 1(fail)->0(pass).
- zero-credit non-blocker work: a round whose changed files are only
  tests/docs/schemas/receipts while the blocker still fails earns no credit.
- scope reconciliation: changed files outside allowed_paths are OUT_OF_SCOPE.
- avoidance halt: `attempt_budget` consecutive no-delta rounds -> AGENT_AVOIDANCE_DETECTED.

Transport-agnostic: works whichever oracle (webgpt/gemini/kimi) is the 2nd agent.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "anti_avoidance_gate.v1"

# Exit codes (stable contract for callers).
EXIT_MILESTONE_CLOSED = 0
EXIT_NO_PROGRESS = 10          # no-delta / zero-credit / out-of-scope / no-changes
EXIT_AVOIDANCE = 20           # two-strike avoidance halt
EXIT_GATE_ERROR = 2          # malformed gate / active-gate / no-open-gate / blocker-not-failing

_REQUIRED = ("goal_id", "goal_lock", "current_milestone", "top_blocker",
             "blocker_evidence", "allowed_paths")

_LOW_VALUE_PATTERNS = (
    "*/tests/*", "*/test/*", "test_*.py", "*_test.py", "*.test.*",
    "*.md", "*/docs/*",
    "*.schema.json", "*/schemas/*",
    "*.receipt.json", "*/receipts/*",
)


class GateError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass
class Result:
    verdict: str
    goal_hash: str
    exit_code: int
    credited: bool = False
    blocker_rc_before: int | None = None
    blocker_rc_after: int | None = None
    changed_files: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    low_value_only: bool = False
    consecutive_no_delta: int = 0
    detail: str = ""

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["schema"] = "anti_avoidance_gate_receipt.v1"
        return d


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_goal_hash(gate: dict) -> str:
    be = gate.get("blocker_evidence") or {}
    core = {
        "goal_id": gate.get("goal_id"),
        "goal_lock": gate.get("goal_lock"),
        "current_milestone": gate.get("current_milestone"),
        "top_blocker": gate.get("top_blocker"),
        "blocker_command": be.get("command") if isinstance(be, dict) else be,
    }
    return "sha256:" + hashlib.sha256(_canonical(core).encode()).hexdigest()


def validate_gate(gate: dict) -> None:
    """Fail closed on malformed / multi-milestone gates."""
    for key in _REQUIRED:
        if key not in gate or gate[key] in (None, ""):
            raise GateError("MALFORMED_GATE", f"missing required field: {key}")
    # Exactly one milestone / one blocker / one command. Lists are rejected.
    for key in ("current_milestone", "top_blocker", "goal_id", "goal_lock"):
        if isinstance(gate[key], list):
            raise GateError("MULTIPLE_MILESTONES", f"{key} must be a single value, not a list")
    be = gate["blocker_evidence"]
    if isinstance(be, list):
        raise GateError("MULTIPLE_MILESTONES", "blocker_evidence must be one object, not a list")
    if not isinstance(be, dict) or not be.get("command"):
        raise GateError("MALFORMED_GATE", "blocker_evidence.command is required")
    if isinstance(be.get("command"), list):
        raise GateError("MULTIPLE_MILESTONES", "blocker_evidence.command must be a single command")
    if not isinstance(gate["allowed_paths"], list) or not gate["allowed_paths"]:
        raise GateError("MALFORMED_GATE", "allowed_paths must be a non-empty list")


def _run_blocker(gate: dict, gate_path: Path | None) -> int:
    be = gate["blocker_evidence"]
    cwd = be.get("cwd")
    if cwd:
        cwd_path = Path(cwd)
    elif gate_path is not None:
        cwd_path = gate_path.parent
    else:
        cwd_path = Path.cwd()
    proc = subprocess.run(be["command"], shell=True, cwd=str(cwd_path),
                          capture_output=True, text=True, timeout=be.get("timeout", 600))
    return proc.returncode


def _match_any(path: str, patterns: list[str]) -> bool:
    base = path.rsplit("/", 1)[-1]
    for pat in patterns:
        p = pat.rstrip("/")
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat):
            return True
        # directory-prefix allow (e.g. "skills/webgpt" or "skills/webgpt/**")
        stem = p[:-2].rstrip("/") if p.endswith("**") else p
        if path == stem or path.startswith(stem + "/"):
            return True
    return False


def _is_low_value(path: str) -> bool:
    return _match_any(path, list(_LOW_VALUE_PATTERNS))


def _state_paths(state_dir: Path, goal_hash: str) -> tuple[Path, Path]:
    digest = goal_hash.split(":", 1)[-1]
    return state_dir / f"{digest}.json", state_dir / "active.json"


def open_gate(gate: dict, state_dir: Path, override: bool = False,
              gate_path: Path | None = None) -> Result:
    validate_gate(gate)
    goal_hash = compute_goal_hash(gate)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path, active_path = _state_paths(state_dir, goal_hash)

    # Persisted active gate: reject a new gate until the current one is closed.
    if active_path.exists():
        active = json.loads(active_path.read_text())
        active_hash = active.get("goal_hash")
        if active_hash and active_hash != goal_hash:
            ast_path, _ = _state_paths(state_dir, active_hash)
            active_state = json.loads(ast_path.read_text()) if ast_path.exists() else {}
            if active_state.get("status") == "OPEN" and not override:
                raise GateError(
                    "ACTIVE_GATE_NOT_CLOSED",
                    f"gate {active_hash} is still OPEN; close it (PASS) or pass --override",
                )

    # A gate whose blocker already passes is meaningless.
    rc = _run_blocker(gate, gate_path)
    if rc == 0:
        raise GateError("GATE_BLOCKER_NOT_FAILING",
                        "blocker_evidence.command already passes; nothing to gate")

    state = {
        "schema": SCHEMA,
        "goal_hash": goal_hash,
        "goal_id": gate["goal_id"],
        "status": "OPEN",
        "attempt_budget": int(gate.get("attempt_budget", 2)),
        "baseline_blocker_rc": rc,
        "last_blocker_rc": rc,
        "consecutive_no_delta": 0,
        "rounds": [],
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    active_path.write_text(json.dumps({"goal_hash": goal_hash}, indent=2) + "\n")
    return Result(verdict="GATE_OPEN", goal_hash=goal_hash, exit_code=EXIT_MILESTONE_CLOSED,
                  blocker_rc_after=rc, detail="gate locked; blocker confirmed failing")


def check_gate(gate: dict, state_dir: Path, changed_files: list[str],
               gate_path: Path | None = None) -> Result:
    validate_gate(gate)
    goal_hash = compute_goal_hash(gate)
    state_path, active_path = _state_paths(state_dir, goal_hash)
    if not state_path.exists():
        raise GateError("NO_OPEN_GATE", f"no open gate for {goal_hash}; run 'open' first")
    state = json.loads(state_path.read_text())
    if state.get("status") != "OPEN":
        raise GateError("NO_OPEN_GATE", f"gate {goal_hash} is {state.get('status')}")

    allowed = gate["allowed_paths"]
    changed = [c for c in changed_files if c]
    out_of_scope = [c for c in changed if not _match_any(c, allowed)]
    low_value_only = bool(changed) and all(_is_low_value(c) for c in changed)

    rc_before = state.get("last_blocker_rc")
    rc_after = _run_blocker(gate, gate_path)

    res = Result(verdict="", goal_hash=goal_hash, exit_code=EXIT_NO_PROGRESS,
                 blocker_rc_before=rc_before, blocker_rc_after=rc_after,
                 changed_files=changed, out_of_scope=out_of_scope,
                 low_value_only=low_value_only)

    if rc_after == 0:
        # The only path to credit: the blocker command now passes.
        res.verdict = "MILESTONE_CLOSED"
        res.credited = True
        res.exit_code = EXIT_MILESTONE_CLOSED
        res.consecutive_no_delta = 0
        state["status"] = "PASSED"
        state["consecutive_no_delta"] = 0
        if active_path.exists():
            active_path.unlink()
    else:
        state["consecutive_no_delta"] = int(state.get("consecutive_no_delta", 0)) + 1
        res.consecutive_no_delta = state["consecutive_no_delta"]
        if out_of_scope:
            res.verdict = "OUT_OF_SCOPE"
            res.detail = f"changed files outside allowed_paths: {out_of_scope}"
        elif not changed:
            res.verdict = "NO_CHANGES"
        elif low_value_only:
            res.verdict = "ZERO_CREDIT_NONBLOCKER"
            res.detail = "only tests/docs/schemas/receipts changed; blocker still fails"
        else:
            res.verdict = "NO_DELTA"
            res.detail = "blocker_evidence.command still fails after this action"
        budget = int(state.get("attempt_budget", 2))
        if res.consecutive_no_delta >= budget:
            res.verdict = "AGENT_AVOIDANCE_DETECTED"
            res.exit_code = EXIT_AVOIDANCE
            res.detail = (f"{res.consecutive_no_delta} consecutive rounds with no "
                          f"blocker delta (budget {budget})")

    state["last_blocker_rc"] = rc_after
    state["rounds"].append({
        "verdict": res.verdict, "credited": res.credited,
        "blocker_rc_before": rc_before, "blocker_rc_after": rc_after,
        "changed_files": changed, "out_of_scope": out_of_scope,
        "low_value_only": low_value_only,
        "consecutive_no_delta": res.consecutive_no_delta,
    })
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return res


# --------------------------------------------------------------------------- CLI

def _load_gate(path: str) -> tuple[dict, Path]:
    p = Path(path)
    return json.loads(p.read_text()), p


def _git_changed(cwd: str) -> list[str]:
    files: set[str] = set()
    for args in (["diff", "--name-only", "HEAD"],
                 ["diff", "--name-only", "--cached"],
                 ["ls-files", "--others", "--exclude-standard"]):
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
        if r.returncode == 0:
            files.update(x for x in r.stdout.splitlines() if x.strip())
    return sorted(files)


def _emit(res: Result, as_json: bool, receipt: str | None) -> None:
    payload = res.to_dict()
    if receipt:
        Path(receipt).write_text(json.dumps(payload, indent=2) + "\n")
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{res.verdict} goal_hash={res.goal_hash} "
              f"blocker_rc={res.blocker_rc_after} credited={res.credited}")
        if res.detail:
            print(f"  {res.detail}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Anti-avoidance gate (deterministic, oracle-agnostic)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("open", "check", "status"):
        s = sub.add_parser(name)
        s.add_argument("--gate", required=True, help="path to gate JSON file")
        s.add_argument("--state-dir", default=str(Path.home() / ".local/state/anti-avoidance-gate"))
        s.add_argument("--json", action="store_true")
        s.add_argument("--receipt", default=None)
        if name == "open":
            s.add_argument("--override", action="store_true")
        if name == "check":
            s.add_argument("--changed-file", action="append", default=[])
            s.add_argument("--git-diff", metavar="REPO_DIR", default=None)

    args = ap.parse_args(argv)
    state_dir = Path(args.state_dir)
    try:
        gate, gate_path = _load_gate(args.gate)
        if args.cmd == "open":
            res = open_gate(gate, state_dir, override=args.override, gate_path=gate_path)
        elif args.cmd == "check":
            changed = list(args.changed_file)
            if args.git_diff:
                changed += _git_changed(args.git_diff)
            res = check_gate(gate, state_dir, changed, gate_path=gate_path)
        else:  # status
            gh = compute_goal_hash(gate)
            sp, _ = _state_paths(state_dir, gh)
            state = json.loads(sp.read_text()) if sp.exists() else {"status": "NONE"}
            print(json.dumps({"goal_hash": gh, **state}, indent=2))
            return 0
    except GateError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return EXIT_GATE_ERROR
    _emit(res, args.json, args.receipt)
    return res.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
