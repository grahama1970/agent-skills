#!/usr/bin/env python3
"""Tiered Battle qualification gates.

The fast and deterministic tiers run local checks. The live tier is a
fail-closed receipt validator: it never upgrades fixture-backed or stale
browser evidence into live Arena/Pixi readiness.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parents[1]
RUN_SH = SKILL_DIR / "run.sh"
SANITY_SH = SKILL_DIR / "sanity.sh"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def current_source() -> dict[str, str]:
    return {
        "commit": _git(["rev-parse", "HEAD"]),
        "battle_tree": _git(["rev-parse", "HEAD:skills/battle"]),
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "cwd": str(cwd),
        "duration_seconds": round(time.time() - started, 3),
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def _field(payload: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        cur: Any = payload
        ok = True
        for part in name.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur
    return None


def _is_live(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        lowered = value.lower()
        return bool(lowered) and "fixture" not in lowered and lowered not in {"false", "none", "local_deterministic_fixture"}
    return False


def _source_values(payload: dict[str, Any]) -> tuple[Any, Any]:
    commit = _field(
        payload,
        [
            "source_commit",
            "repository_commit",
            "current_source_commit",
            "git_commit",
            "commit",
            "source.commit",
            "source.git_commit",
        ],
    )
    tree = _field(
        payload,
        [
            "source_tree",
            "battle_tree",
            "current_source_tree",
            "source.battle_tree",
            "source.source_tree",
        ],
    )
    return commit, tree


def validate_live(arena_receipt: Path, pixi_receipt: Path, out: Path) -> int:
    arena = _read(arena_receipt)
    pixi = _read(pixi_receipt)
    source = current_source()
    errors: list[str] = []

    arena_run_id = _field(arena, ["run_id", "run.id"])
    pixi_run_id = _field(pixi, ["run_id", "arena_run_id", "source_run_id", "run.id"])
    arena_commit, arena_tree = _source_values(arena)
    pixi_commit, pixi_tree = _source_values(pixi)

    if arena.get("status") != "PASS":
        errors.append("arena_receipt_status_not_pass")
    if pixi.get("status") not in {"PASS", "passed", None}:
        errors.append("pixi_receipt_status_not_pass")
    if arena.get("mocked") is not False:
        errors.append("arena_receipt_not_mocked_false")
    if pixi.get("mocked") is not False:
        errors.append("pixi_receipt_not_mocked_false")
    if not _is_live(arena.get("live")):
        errors.append("arena_receipt_not_live")
    if pixi.get("live") is not True:
        errors.append("pixi_receipt_not_live_true")
    if pixi.get("fixture_backed") is True or _field(pixi, ["browser_state.fixture_backed", "source.fixture_backed"]) is True:
        errors.append("browser_state_fixture_backed")
    if not arena_run_id or not pixi_run_id or arena_run_id != pixi_run_id:
        errors.append("same_run_id_mismatch")
    if arena_commit != source["commit"]:
        errors.append("arena_source_commit_stale_or_missing")
    if pixi_commit != source["commit"]:
        errors.append("pixi_source_commit_stale_or_missing")
    if arena_tree != source["battle_tree"]:
        errors.append("arena_source_tree_stale_or_missing")
    if pixi_tree != source["battle_tree"]:
        errors.append("pixi_source_tree_stale_or_missing")

    receipt = {
        "schema": "battle.tiered_live_qualification_gate.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": True,
        "generated_at": _utc(),
        "current_source": source,
        "inputs": {
            "arena_receipt": str(arena_receipt),
            "pixi_receipt": str(pixi_receipt),
            "arena_run_id": arena_run_id,
            "pixi_run_id": pixi_run_id,
            "arena_source_commit": arena_commit,
            "pixi_source_commit": pixi_commit,
            "arena_source_tree": arena_tree,
            "pixi_source_tree": pixi_tree,
        },
        "errors": errors,
        "proves": [
            "Arena and Pixi receipts are from the same run.",
            "Arena and Pixi receipts match the current Battle source commit and tree.",
            "Browser state is not fixture-backed.",
        ],
        "does_not_prove": [
            "A new Arena or browser run was generated by this validator.",
            "Provider reliability beyond the supplied live receipts.",
        ],
    }
    _write(out, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(out), "errors": errors}, indent=2))
    return 0 if not errors else 1


def run_fast(out: Path) -> int:
    command = ["bash", str(SANITY_SH)]
    result = _run(command, cwd=REPO_ROOT)
    receipt = {
        "schema": "battle.tiered_fast_sanity_gate.v1",
        "status": "PASS" if result["exit_code"] == 0 else "FAIL",
        "mocked": False,
        "live": False,
        "generated_at": _utc(),
        "source": current_source(),
        "command_result": result,
        "proof_scope": "offline sanity plus local deterministic fixture checks; no live provider/Docker/browser qualification",
    }
    _write(out, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(out)}, indent=2))
    return result["exit_code"]


def run_deterministic(out_dir: Path, receipt_out: Path) -> int:
    command = ["bash", str(RUN_SH), "backend-eval", "--out-dir", str(out_dir), "--receipt-out", str(receipt_out)]
    result = _run(command, cwd=SKILL_DIR)
    if receipt_out.exists():
        receipt = _read(receipt_out)
    else:
        receipt = {}
    gate = {
        "schema": "battle.tiered_deterministic_gate.v1",
        "status": "PASS" if result["exit_code"] == 0 and receipt.get("status") == "passed" else "FAIL",
        "mocked": False,
        "live": False,
        "generated_at": _utc(),
        "source": current_source(),
        "backend_eval_receipt": str(receipt_out),
        "command_result": result,
        "proof_scope": "deterministic backend contracts and committed spectator fixture integrity; no live Tau/Docker/browser",
    }
    gate_out = receipt_out.with_name("tiered-deterministic-gate.json")
    _write(gate_out, gate)
    print(json.dumps({"status": gate["status"], "receipt": str(gate_out), "backend_eval_receipt": str(receipt_out)}, indent=2))
    return 0 if gate["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or validate Battle qualification tiers")
    sub = parser.add_subparsers(dest="command", required=True)

    fast = sub.add_parser("fast-sanity", help="Run the fast offline sanity tier")
    fast.add_argument("--out", type=Path, required=True)

    deterministic = sub.add_parser("deterministic", help="Run deterministic backend/spectator contract tier")
    deterministic.add_argument("--out-dir", type=Path, required=True)
    deterministic.add_argument("--receipt-out", type=Path, required=True)

    live = sub.add_parser("live", help="Validate live same-run Arena-to-Pixi receipts")
    live.add_argument("--arena-receipt", type=Path, required=True)
    live.add_argument("--pixi-receipt", type=Path, required=True)
    live.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "fast-sanity":
        return run_fast(args.out)
    if args.command == "deterministic":
        return run_deterministic(args.out_dir, args.receipt_out)
    if args.command == "live":
        return validate_live(args.arena_receipt, args.pixi_receipt, args.out)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
