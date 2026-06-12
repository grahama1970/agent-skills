#!/usr/bin/env python3
"""Scillm local-command adapter for one `$loop` artifact transaction."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def _display_command(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(shlex.quote(part) for part in command)


def _run(command: str | list[str], *, cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        shell=isinstance(command, str),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": _display_command(command),
        "cwd": str(cwd),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": _tail(proc.stdout),
        "stderr_tail": _tail(proc.stderr),
    }


def _newest_receipt(repo: Path) -> Path | None:
    runs = repo / ".loop" / "runs"
    if not runs.exists():
        return None
    receipts = [path / "final-receipt.json" for path in runs.iterdir() if path.is_dir()]
    receipts = [path for path in receipts if path.exists()]
    if not receipts:
        return None
    return max(receipts, key=lambda path: path.stat().st_mtime)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _scope_from_receipt(receipt_path: Path, receipt: dict[str, Any]) -> Path | None:
    attempts_used = receipt.get("attempts_used")
    if not isinstance(attempts_used, int) or attempts_used < 1:
        attempts = receipt.get("attempts")
        attempts_used = len(attempts) if isinstance(attempts, list) else 0
    if attempts_used < 1:
        return None
    candidate = receipt_path.parent / "attempts" / f"{attempts_used:02d}" / "changed-files.txt"
    return candidate if candidate.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or consume one `$loop` transaction for a Scillm node.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--prompt")
    parser.add_argument("--launch-command")
    parser.add_argument("--receipt")
    parser.add_argument("--validator", required=True)
    parser.add_argument("--scope-checker")
    parser.add_argument("--scope-from-file")
    parser.add_argument("--scope-include", action="append", default=[])
    parser.add_argument("--scope-exclude", action="append", default=[])
    parser.add_argument("--check-command", action="append", default=[])
    parser.add_argument("--proof-out")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    launch = None
    if args.launch_command:
        launch = _run(args.launch_command, cwd=repo)
        if not launch["ok"]:
            errors.append("launch_command failed")

    receipt_path = Path(args.receipt).expanduser() if args.receipt else None
    if receipt_path is not None and not receipt_path.is_absolute():
        receipt_path = repo / receipt_path
    if receipt_path is None:
        receipt_path = _newest_receipt(repo)
    if receipt_path is None or not receipt_path.exists():
        errors.append("missing final loop receipt")
        receipt: dict[str, Any] = {}
        receipt_path_text = str(receipt_path or "")
    else:
        receipt_path_text = str(receipt_path)
        validator = Path(args.validator).expanduser().resolve()
        result = _run([sys.executable, str(validator), str(receipt_path), "--print-summary"], cwd=repo)
        checks.append(result)
        if not result["ok"]:
            errors.append("validate_loop_receipt failed")
        try:
            receipt = _read_json(receipt_path)
        except json.JSONDecodeError as exc:
            receipt = {}
            errors.append(f"final receipt invalid JSON: {exc}")

    if args.scope_checker:
        scope_checker = Path(args.scope_checker).expanduser().resolve()
        scope_cmd: list[str] = [sys.executable, str(scope_checker)]
        inferred_scope_from = None
        if not args.scope_from_file and receipt_path is not None and receipt:
            inferred_scope_from = _scope_from_receipt(receipt_path, receipt)
        if args.scope_from_file:
            scope_from = Path(args.scope_from_file).expanduser()
            if not scope_from.is_absolute():
                scope_from = repo / scope_from
            scope_cmd.extend(["--from-file", str(scope_from)])
        elif inferred_scope_from:
            scope_cmd.extend(["--from-file", str(inferred_scope_from)])
        for pattern in args.scope_include:
            scope_cmd.extend(["--include", pattern])
        for pattern in args.scope_exclude:
            scope_cmd.extend(["--exclude", pattern])
        result = _run(scope_cmd, cwd=repo)
        checks.append(result)
        if not result["ok"]:
            errors.append("check_changed_files failed")

    for command in args.check_command:
        result = _run(command, cwd=repo)
        checks.append(result)
        if not result["ok"]:
            errors.append(f"check command failed: {command}")

    attempts = receipt.get("attempts") if isinstance(receipt, dict) else []
    final_reviewer = attempts[-1].get("code_reviewer_receipt", {}) if attempts else {}
    if receipt.get("final_verdict") != "PASS":
        errors.append(f"final_verdict is not PASS: {receipt.get('final_verdict')!r}")
    if final_reviewer.get("verdict") != "PASS" or final_reviewer.get("edited_files") != []:
        errors.append("final code-reviewer PASS with edited_files=[] not found")

    payload = {
        "schema": "orchestrate.loop_node_result.v1",
        "ok": not errors,
        "launch": launch,
        "loop_receipt": {
            "path": receipt_path_text,
            "final_verdict": receipt.get("final_verdict"),
            "stop_reason": receipt.get("stop_reason"),
            "attempts_used": receipt.get("attempts_used"),
            "final_changed_files": receipt.get("final_changed_files", []),
            "final_tests_run": receipt.get("final_tests_run", []),
        },
        "checks_run": checks,
        "errors": errors,
    }
    if args.proof_out:
        out = Path(args.proof_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
