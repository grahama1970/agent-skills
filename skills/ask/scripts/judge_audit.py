#!/usr/bin/env python3
"""Judge-integrity audit for an /ask compete run directory.

A judge's scorecard is a claim until checked (best-practices-competition).
This audit verifies, from the run's own receipts, that:

1. a judge node exists with a response;
2. the judge seat is NOT one of the competitor seats (independence);
3. the verdict line names an EXISTING competitor node (`WINNER: handler-x`
   where handler-x has its own node artifacts), or is an explicit
   NEEDS_ATTENTION/tie;
4. the winner actually answered (non-empty response of its own);
5. the rationale is evidence-shaped: it mentions every competitor node id,
   so no candidate was silently ignored;
6. when --run-winner-proof is set and the winner's response carries a
   PROOF_COMMANDS `python -c` line, that command is executed and must exit 0.

Exit 0 with JUDGE_AUDIT_OK only when every check passes; exit 1 listing the
failed checks. The audit never trusts the judge's prose about itself -- every
check reads receipts or executes artifacts.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

WINNER_RE = re.compile(r"^WINNER:\s*(\S+)\s*$", re.M)
PROOF_RE = re.compile(r"(python -c '(?:[^'\\]|\\.)*')|(python -c \"(?:[^\"\\]|\\.)*\")")


@app.command()
def main(
    run_dir: Path = typer.Argument(..., help="A compete run directory (node-artifacts/...)."),
    run_winner_proof: bool = typer.Option(False, "--run-winner-proof",
                                          help="Execute the winner's PROOF_COMMANDS python -c line."),
) -> None:
    problems: list[str] = []
    nodes_dir = run_dir / "node-artifacts"
    judge_dir = nodes_dir / "judge"
    competitors = sorted(
        d.name for d in nodes_dir.glob("handler-*") if d.is_dir()
    ) if nodes_dir.is_dir() else []
    if not competitors:
        typer.echo(f"JUDGE_AUDIT_FAIL: no competitor node artifacts under {nodes_dir}", err=True)
        raise typer.Exit(1)
    judge_response = ""
    resp_path = judge_dir / "response.md"
    if resp_path.is_file():
        judge_response = resp_path.read_text(errors="replace")
    if not judge_response.strip():
        problems.append("judge produced no response")
    # Independence: the judge's model/handler must not be a competitor seat.
    judge_model = ""
    receipt_path = judge_dir / "node-receipt.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text())
        pr = receipt.get("provider_receipt") or receipt
        judge_model = str(pr.get("requested_model") or pr.get("model") or "")
    if not judge_model:
        problems.append("judge receipt does not record its model")
    else:
        norm = judge_model.lower().replace(".", "-")
        for comp in competitors:
            comp_seat = comp.replace("handler-", "")
            if comp_seat == norm or norm.startswith(comp_seat) or comp_seat.startswith(norm):
                problems.append(f"judge model {judge_model!r} is also competitor {comp}")
    # Verdict names an existing competitor.
    winner = None
    m = WINNER_RE.search(judge_response)
    if m:
        winner = m.group(1)
        if winner not in competitors:
            problems.append(f"WINNER {winner!r} is not an existing competitor node "
                            f"(have: {', '.join(competitors)})")
    elif re.search(r"NEEDS_ATTENTION|\bTIE\b", judge_response):
        winner = None  # explicit fail-closed verdicts are legitimate
    else:
        problems.append("judge response has neither a 'WINNER: <node>' line nor an "
                        "explicit NEEDS_ATTENTION/TIE verdict")
    # Winner actually answered.
    winner_response = ""
    if winner and winner in competitors:
        wr = nodes_dir / winner / "response.md"
        winner_response = wr.read_text(errors="replace") if wr.is_file() else ""
        if not winner_response.strip():
            problems.append(f"declared winner {winner} has no response of its own")
    # Every competitor is addressed in the rationale (nobody silently
    # ignored). Judges legitimately name seats without the 'handler-' node
    # prefix (observed 2026-08-20: a rationale addressing webgemini/webgrok by
    # seat name failed the literal node-id match), so accept either form --
    # while a competitor absent under BOTH names is still a violation.
    if judge_response:
        ignored = [
            c for c in competitors
            if c not in judge_response and c.replace("handler-", "") not in judge_response
        ]
        if ignored:
            problems.append("judge rationale never mentions: " + ", ".join(ignored))
    # Optionally execute the winner's own proof command.
    if run_winner_proof and winner_response:
        pm = PROOF_RE.search(winner_response)
        if not pm:
            problems.append(f"winner {winner} response carries no runnable python -c proof")
        else:
            proof_cmd = pm.group(0)
            proc = subprocess.run(["bash", "-c", proof_cmd], capture_output=True,
                                  text=True, timeout=60)
            if proc.returncode != 0:
                problems.append(f"winner proof command exited {proc.returncode}: "
                                f"{(proc.stderr or proc.stdout)[-160:].strip()}")
            else:
                typer.echo(f"WINNER_PROOF_EXECUTED: exit 0 ({proof_cmd[:80]}...)")
    for p in problems:
        typer.echo(f"JUDGE_AUDIT_FAIL: {p}", err=True)
    if problems:
        raise typer.Exit(1)
    verdict = winner or "no-winner (explicit fail-closed verdict)"
    typer.echo(f"JUDGE_AUDIT_OK: independent judge {judge_model!r}, verdict {verdict}, "
               f"{len(competitors)} competitors all addressed")


if __name__ == "__main__":
    app()
