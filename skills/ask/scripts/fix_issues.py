#!/usr/bin/env python3
"""/ask fix-issues: diagnose, fix, verify, and close GitHub issues as one receipted flow.

The composition the debugger ladder prescribes, applied to tickets:

  1. GATHER   - read the issue (gh) and any evidence artifacts it names.
  2. DISPATCH - the ladder's rung 0: a diagnosis handler reads the gathered
                evidence FIRST and names the cause, the fix, and -- explicitly --
                whether live runtime state is required (`needs_debugger`).
  3. BREAKPOINT (gated) - only when the diagnosis says the failing transition is
                in-process with no artifact does the flow recommend /debugger,
                emitting the exact capture command. It never sets breakpoints
                for problems a receipt already explains.
  4. VERIFY   - the fix is proven by the issue's own verify command (typically an
                /agentic-evals fixture) actually passing. A diagnosis without a
                passing verify NEVER closes anything.
  5. CLOSE    - only with --execute AND a passing verify: comment the receipt on
                the issue and close it. Default is dry-run: print the plan.

Fail-closed everywhere: gh errors, handler blockers, or a failing verify leave
the issue open and are reported as named blockers, exit != 0.

Usage:
  fix_issues.py --repo owner/name --issue N [--issue M ...]
                [--handler gpt-5.5] [--verify-cmd '...'] [--execute] [--json]

The per-issue receipt is written to
  <outputs>/fix-issues/<repo>/<issue>/receipt.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
OUTPUTS = Path(os.environ.get("ASK_FIX_ISSUES_OUT", "/mnt/storage12tb/skills/ask/outputs/fix-issues"))

DIAGNOSIS_PROMPT = """You are diagnosing GitHub issue #{number} in {repo} to drive a fix.

ISSUE TITLE: {title}

ISSUE BODY:
{body}

RECENT COMMENTS (newest last):
{comments}

Answer as strict JSON with exactly these keys:
{{
  "cause": "<one-paragraph root cause, grounded ONLY in the issue text/evidence above; say 'unknown' if the evidence does not name it>",
  "fix_plan": ["<ordered concrete steps>"],
  "needs_debugger": <true only if the failing transition is in-process runtime state that NO artifact above already explains>,
  "debugger_target": "<file:line or function to break at, empty if needs_debugger is false>",
  "verify_command": "<the command that must pass to prove the fix; prefer the issue's own eval/fixture; empty if none is named>",
  "confidence": "<high|medium|low>"
}}
Put the JSON object in a ```json fenced block. Keep any nonce/acknowledgement lines
your runtime requires OUTSIDE the fenced block."""


def sh(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def gather_issue(repo: str, number: int) -> dict:
    """Read the issue and its comments via gh. Fail-closed on any gh error."""
    result = sh(["gh", "issue", "view", str(number), "--repo", repo,
                 "--json", "number,title,state,body,comments"])
    if result.returncode != 0:
        raise RuntimeError(f"gh issue view failed for #{number}: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


def diagnose(issue: dict, repo: str, handler: str) -> dict:
    """Route diagnosis through /ask one-shot (the sanctioned single-call path)."""
    comments = "\n---\n".join(
        f"{c.get('author', {}).get('login', '?')}: {c.get('body', '')[:1500]}"
        for c in (issue.get("comments") or [])[-5:]
    ) or "(none)"
    prompt = DIAGNOSIS_PROMPT.format(
        number=issue["number"], repo=repo, title=issue.get("title", ""),
        body=(issue.get("body") or "")[:6000], comments=comments,
    )
    child_env = {k: v for k, v in os.environ.items()
                 if k not in ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "UV_LINK_MODE")}
    result = subprocess.run(
        ["bash", str(SKILL / "run.sh"), "one-shot", prompt, "--handler", handler],
        capture_output=True, text=True, timeout=300, env=child_env,
    )
    for row in result.stdout.splitlines():
        if row.startswith("ANSWER ") and ":" in row:
            path = Path(row.split(":", 1)[1].strip())
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                # Prefer a ```json fenced block; fall back to the outermost braces.
                fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
                for candidate in ([fenced.group(1)] if fenced else []) + re.findall(r"\{.*\}", text, re.S):
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
    raise RuntimeError(f"diagnosis handler {handler} returned no parseable JSON "
                       f"(stdout tail: {result.stdout.strip()[-200:]})")


def run_verify(verify_cmd: str, cwd: Path) -> tuple[bool, str]:
    result = subprocess.run(["bash", "-c", verify_cmd], capture_output=True,
                            text=True, timeout=900, cwd=cwd)
    tail = (result.stdout + result.stderr).strip()[-500:]
    return result.returncode == 0, tail


def close_issue(repo: str, number: int, receipt: dict) -> None:
    body = (
        f"Closed by `/ask fix-issues` with a passing verify.\n\n"
        f"**Cause:** {receipt['diagnosis'].get('cause', '')[:800]}\n\n"
        f"**Verify:** `{receipt.get('verify_command', '')}` -> PASS\n\n"
        f"Receipt: `{receipt['receipt_path']}`"
    )
    result = sh(["gh", "issue", "close", str(number), "--repo", repo, "--comment", body])
    if result.returncode != 0:
        raise RuntimeError(f"gh issue close failed for #{number}: {result.stderr.strip()[:200]}")


def process_issue(repo: str, number: int, handler: str, verify_override: str | None,
                  execute: bool, workdir: Path) -> dict:
    receipt_dir = OUTPUTS / repo.replace("/", "__") / str(number)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict = {"schema": "ask.fix_issue_receipt.v1", "repo": repo, "issue": number,
                     "handler": handler, "executed": execute, "started_at": time.time(),
                     "receipt_path": str(receipt_dir / "receipt.json")}
    issue = gather_issue(repo, number)
    receipt["title"] = issue.get("title")
    if issue.get("state", "").upper() == "CLOSED":
        receipt["outcome"] = "already-closed"
        return receipt

    diagnosis = diagnose(issue, repo, handler)
    receipt["diagnosis"] = diagnosis

    # Ladder gate: /debugger is recommended ONLY when the diagnosis names
    # in-process runtime state no artifact explains (rung 1, never rung 0).
    if diagnosis.get("needs_debugger"):
        target = diagnosis.get("debugger_target") or "<pick the failing transition>"
        receipt["debugger_recommendation"] = (
            f"skills/debugger/run.sh --break {target} ... (see /debugger SKILL.md); "
            f"attach the debugger.proof.v1 to the issue before fixing"
        )

    # An explicit --verify-cmd (even empty) overrides the diagnosis; only an
    # ABSENT override falls through. --verify-cmd '' therefore means "no verify
    # is named", which the execute path refuses to close on.
    verify_cmd = verify_override if verify_override is not None else (diagnosis.get("verify_command") or "")
    receipt["verify_command"] = verify_cmd

    if not execute:
        receipt["outcome"] = "dry-run"
        return receipt

    # Execute path: a close REQUIRES a passing verify. No verify command, no close.
    if not verify_cmd:
        receipt["outcome"] = "blocked"
        receipt["blocker"] = "no verify command named (issue/diagnosis); refusing to close without proof"
        return receipt
    passed, tail = run_verify(verify_cmd, workdir)
    receipt["verify_passed"] = passed
    receipt["verify_tail"] = tail
    if not passed:
        receipt["outcome"] = "verify-failed"
        return receipt
    close_issue(repo, number, receipt)
    receipt["outcome"] = "closed"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue", type=int, action="append", required=True)
    parser.add_argument("--handler", default=os.environ.get("ASK_FIX_ISSUES_HANDLER", "gpt-5.5"))
    parser.add_argument("--verify-cmd", default=None,
                        help="Override the verify command (else the issue/diagnosis names it).")
    parser.add_argument("--execute", action="store_true",
                        help="Actually run verify and close on pass. Default: dry-run plan only.")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipts, failures = [], 0
    for number in args.issue:
        try:
            receipt = process_issue(args.repo, number, args.handler,
                                    args.verify_cmd, args.execute, args.workdir)
        except Exception as exc:
            receipt = {"schema": "ask.fix_issue_receipt.v1", "repo": args.repo,
                       "issue": number, "outcome": "error", "blocker": str(exc)[:400]}
        receipts.append(receipt)
        path = OUTPUTS / args.repo.replace("/", "__") / str(number) / "receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
        outcome = receipt.get("outcome")
        if outcome in ("error", "verify-failed", "blocked"):
            failures += 1
        print(f"ISSUE #{number}: {outcome}"
              + (f" — {receipt.get('blocker')}" if receipt.get("blocker") else ""))
        if outcome == "dry-run":
            diag = receipt.get("diagnosis", {})
            print(f"  cause: {str(diag.get('cause'))[:160]}")
            print(f"  needs_debugger: {diag.get('needs_debugger')}"
                  + (f" -> {receipt.get('debugger_recommendation')}" if receipt.get("debugger_recommendation") else ""))
            print(f"  verify: {receipt.get('verify_command') or '(none named — would refuse to close)'}")
    if args.json:
        print(json.dumps({"schema": "ask.fix_issues_report.v1", "receipts": receipts},
                         indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
