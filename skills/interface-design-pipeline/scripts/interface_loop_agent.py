#!/usr/bin/env python3
"""Load a named top-level interface agent contract, then delegate to loop's Scillm adapter."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DELEGATE = REPO_ROOT / "skills" / "loop" / "scripts" / "scillm_agent.py"


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"prompt_text": raw}
    return value if isinstance(value, dict) else {"prompt": value}


def main() -> int:
    parser = argparse.ArgumentParser(description="Named interface agent adapter for $loop.")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--role", choices=["explorer", "coder", "code-reviewer"], required=True)
    args, delegate_args = parser.parse_known_args()

    contract_path = REPO_ROOT / "agents" / args.agent / "AGENTS.md"
    if not contract_path.is_file():
        print(json.dumps({"verdict": "BLOCKED", "findings": [f"missing agent contract: {contract_path}"]}))
        return 2
    if not DELEGATE.is_file():
        print(json.dumps({"verdict": "BLOCKED", "findings": [f"missing loop delegate: {DELEGATE}"]}))
        return 2

    payload = read_payload()
    payload["named_agent"] = args.agent
    payload["named_agent_contract"] = contract_path.read_text(encoding="utf-8")
    payload["interface_pipeline_invariants"] = [
        "Stay inside the loop allowed globs.",
        "Do not declare the tournament winner; the interface-adjudicator owns selection.",
        "Do not copy proprietary product chrome; cite and abstract reference patterns.",
        "Reviewer roles are read-only and must fail closed when visual or deterministic evidence is missing.",
    ]

    command = [sys.executable, str(DELEGATE), "--role", args.role, *delegate_args]
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
