#!/usr/bin/env python3
"""Second rung of the live E2E ladder: a real task across mixed seats.

The human-equivalent prompt: "write a Python function that adds two numbers,
complying with best-practices-python". Seats run as a concurrent roundtable
through the real tau-dag path (browser and API lanes as peers). The contract
stays honesty plus a DETERMINISTIC compliance floor per answering lane:

- a `def` with two parameters and a `return`
- type hints on the signature
- a docstring

Full best-practices-python compliance is judgment; these floors are the
machine-checkable subset that catches a seat returning prose, a stub, or bare
untyped code. A lane is honest when it meets the floor OR names a
failure_code. Exit 0 only when every lane is honest; per-lane verdicts print
as they are read from the run's own node artifacts.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

SKILL_ROOT = Path(__file__).resolve().parents[1]

PROMPT = (
    "Write one Python function that adds two numbers and return it in a single "
    "fenced python block. It must comply with best-practices-python: a module "
    "docstring naming purpose, inputs, outputs, and failure modes; type hints "
    "on the signature; a function docstring; no classes; no runtime asserts. "
    "No prose outside the fenced block."
)

FLOOR = {
    "has_def": re.compile(r"def\s+\w+\s*\(\s*\w+\s*:\s*[\w\[\]| .]+\s*,\s*\w+\s*:\s*[\w\[\]| .]+\s*\)"),
    "has_return_hint": re.compile(r"\)\s*->\s*[\w\[\]| .]+\s*:"),
    "has_docstring": re.compile(r'"""'),
    "has_return": re.compile(r"\breturn\b"),
}


def _floor_verdict(text: str) -> list[str]:
    return [name for name, rx in FLOOR.items() if not rx.search(text)]


@app.command()
def main(
    handler: list[str] = typer.Option(["webgpt", "webclaude", "deepseek-v4-flash"], "--handler"),
    timeout: int = typer.Option(1500, "--timeout"),
    out_dir: Path = typer.Option(Path("/tmp/live-task-probe"), "--out-dir"),
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    cmd = [str(SKILL_ROOT / "run.sh"), "tau-dag", PROMPT,
           "--repo", "local/agent-skills", "--target", f"eval-add-two-{token}",
           "--immutable-goal", "Each seat returns a floor-compliant function or names a blocker.",
           "--dag-template", "roundtable", "--topology", "concurrent",
           "--poll-timeout-seconds", str(timeout), "--execute", "--json"]
    for h in handler:
        cmd += ["--handler", h]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 300, cwd=SKILL_ROOT)
    text = proc.stdout
    try:
        result = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        typer.echo("TASK_LADDER_RUNNER_ERROR: unparseable tau-dag output", err=True)
        typer.echo(text[-400:], err=True)
        raise typer.Exit(1)
    run_dir = Path(str(((result.get("execution") or {}).get("run_dir"))
                       or ((result.get("bundle") or {}).get("run_dir")) or ""))
    (out_dir / "tau-result.json").write_text(json.dumps(result, indent=2))
    # Follow recorded substitutions: a removed seat answered by its documented
    # substitute (e.g. webclaude -> claude-opus-5-high) is the substitute's lane.
    substitutions: dict[str, str] = {}
    sel_path = run_dir / "browser-provider-selection.json" if run_dir.is_dir() else None
    if sel_path and sel_path.is_file():
        sel = json.loads(sel_path.read_text())
        for sub in sel.get("local_substitutions") or []:
            if sub.get("from") and sub.get("to"):
                substitutions[sub["from"]] = sub["to"]
    # A run Tau blocked pre-dispatch is a RUN defect, named by its alerts --
    # healthy seats that never ran are victims, not dishonest seats.
    run_alerts: list[str] = []
    exec_path = run_dir / "execution-status.json" if run_dir.is_dir() else None
    if exec_path and exec_path.is_file():
        ex = json.loads(exec_path.read_text())
        if ex.get("status") == "BLOCKED":
            run_alerts = [str(a.get("code")) for a in (ex.get("receipt") or {}).get("alerts") or []]
    lanes: dict[str, dict] = {}
    if run_dir.is_dir():
        for node_dir in sorted((run_dir / "node-artifacts").glob("handler-*")):
            seat = node_dir.name.replace("handler-", "")
            receipt = {}
            rp = node_dir / "node-receipt.json"
            if rp.is_file():
                receipt = json.loads(rp.read_text())
            response = ""
            resp_path = node_dir / "response.md"
            if resp_path.is_file():
                response = resp_path.read_text(errors="replace")
            lanes[seat] = {"receipt": receipt, "response": response}
    violators: list[str] = []
    for seat in handler:
        effective = substitutions.get(seat, seat)
        # Tau normalizes node ids: dots become hyphens (gpt-5.5-low ->
        # handler-gpt-5-5-low). Receipts are the authority; match their naming.
        candidates = {effective, seat, effective.replace(".", "-"), seat.replace(".", "-")}
        lane = next((lanes[c] for c in candidates if c in lanes), {})
        note = f" (substituted -> {effective})" if effective != seat else ""
        seat_label = seat + note
        response = lane.get("response") or ""
        failure = (lane.get("receipt") or {}).get("failure_code")
        if response.strip():
            missing = _floor_verdict(response)
            if missing:
                typer.echo(f"SEAT {seat_label}: answered but BELOW FLOOR (missing: {', '.join(missing)})")
                violators.append(seat)
            else:
                typer.echo(f"SEAT {seat_label}: answered, floor-compliant")
        elif failure:
            # Rung 3, self-correction: a misnamed model must not dead-end. The
            # honest outcomes are a recorded substitution to a valid catalog
            # model, or a recovery packet relaying the transport's own course
            # correction (scillm's 400 enumerates valid ids). A bare
            # model-not-found with neither is a self-correction failure.
            if failure == "scillm_model_not_found":
                lane_dir = run_dir / "node-artifacts" / f"handler-{effective.replace('.', '-')}"
                correction = ""
                for packet_name in ("handler-recovery-packet.json", "browser-recovery-packet.json"):
                    pp = lane_dir / packet_name
                    if pp.is_file():
                        packet = json.loads(pp.read_text())
                        correction = " ".join(str(packet.get(k) or "") for k in
                                              ("fallback_instruction", "next_command", "recommended_action"))
                receipt_text = json.dumps(lane.get("receipt") or {})
                has_valid_ids = bool(re.search(r"valid model|available models|model catalog|supported models", (correction + receipt_text), re.I))
                if substitutions.get(seat) or has_valid_ids:
                    typer.echo(f"SEAT {seat_label}: named_blocker {failure} WITH course correction")
                else:
                    typer.echo(f"SEAT {seat_label}: named_blocker {failure} but NO SELF-CORRECTION "
                               "(no substitution recorded, no valid-model course correction relayed)")
                    violators.append(seat)
            else:
                typer.echo(f"SEAT {seat_label}: named_blocker {failure}")
        elif run_alerts:
            typer.echo(f"SEAT {seat_label}: never dispatched -- run BLOCKED by {','.join(run_alerts)}")
            violators.append(seat)
        else:
            typer.echo(f"SEAT {seat_label}: NO ANSWER AND NO FAILURE CODE")
            violators.append(seat)
    typer.echo(f"TASK_LADDER: {len(handler) - len(violators)}/{len(handler)} honest")
    if violators:
        if run_alerts:
            typer.echo("RUN_BLOCKED_PANEL: one lane's failure blocked healthy seats ("
                       + ",".join(run_alerts) + ") -- /ask contract requires lane-local degradation", err=True)
        typer.echo("FAILED_SEATS: " + ", ".join(violators), err=True)
        raise typer.Exit(1)
    typer.echo("ALL_SEATS_HONEST_ON_TASK")


if __name__ == "__main__":
    app()
