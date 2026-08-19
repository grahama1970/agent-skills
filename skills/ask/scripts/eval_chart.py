#!/usr/bin/env python3
"""Render the /ask eval ladder as a phart DAG chart, verdicts from artifacts.

The chart is GENERATED, never hand-drawn: node ids carry the latest verdict
(PASS-/FAIL-/BLOCKED- prefixes) read from the same eval-reports artifacts the
eval-status table uses -- ladder-verdict.json, probe-verdict.json,
one-shot-verdict.json, and the newest full runner report. A failure anywhere
turns its node red on the next render; a chart that can't go red is
decoration, not evidence.

Writes ask.dag.v1 JSON and (when the phart-dag-chart skill is present) prints
the rendered ASCII chart.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

REPORTS = Path("/mnt/storage12tb/skills/ask/outputs/eval-reports")
PHART = Path(__file__).resolve().parents[2] / "phart-dag-chart" / "run.sh"


def _latest(pattern: str) -> Path | None:
    dirs = sorted((p for p in REPORTS.glob(pattern) if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0] if dirs else None


def _read(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _mark(state: str | None, name: str) -> str:
    tag = {"ANSWERED": "PASS", "NAMED_BLOCKER": "PASS", "READY": "PASS",
           "DEGRADED": "DEGRADED", "NOT_READY": "FAIL", "DISHONEST": "FAIL",
           "BELOW_FLOOR": "FAIL", "RUN_BLOCKED": "BLOCKED",
           "NO_SELF_CORRECTION": "FAIL", "STALE_OR_UNBOUND": "FAIL",
           "RUNNER_ERROR": "FAIL"}.get(str(state), "UNKNOWN")
    return f"{tag}_{name}"


@app.command()
def main(
    out: Path = typer.Option(REPORTS / "eval-ladder.dag.json", "--out"),
    render: bool = typer.Option(True, "--render/--no-render"),
) -> None:
    nodes: list[dict] = [{"id": "rung1_seat_ping_ladder", "type": "skill.run",
                          "depends_on": [], "input": {}}]
    # Rung 1: newest ladder (per-seat verdicts) or legacy per-seat ping dirs.
    ladder_dir = _latest("seat-pings-*") or _latest("ping-ladder-*")
    rung1_ids: list[str] = []
    ladder = _read((ladder_dir / "ladder-verdict.json") if ladder_dir else None)
    if ladder.get("seats"):
        for seat, v in sorted(ladder["seats"].items()):
            nid = _mark(v.get("state"), f"{seat}_ping".replace(".", "_").replace("-", "_"))
            rung1_ids.append(nid)
    elif ladder_dir:
        for sp in sorted(ladder_dir.glob("*.json")):
            d = _read(sp)
            state = "ANSWERED" if d.get("outcome") == "answered" else (
                "NAMED_BLOCKER" if d.get("outcome") == "named_blocker" else "DISHONEST")
            rung1_ids.append(_mark(state, f"{sp.stem}_ping".replace(".", "_").replace("-", "_")))
    for nid in rung1_ids:
        nodes.append({"id": nid, "type": "skill.run",
                      "depends_on": ["rung1_seat_ping_ladder"], "input": {}})
    # Rung 2: newest task probe verdict.
    probe = _read((_latest("task-probe-*") or Path("/nonexistent")) / "probe-verdict.json")
    probe_id = _mark(probe.get("readiness") if not probe.get("violators") else "DISHONEST",
                     "rung2_task_probe")
    nodes.append({"id": probe_id, "type": "skill.run",
                  "depends_on": rung1_ids or ["rung1_seat_ping_ladder"], "input": {}})
    seat_ids: list[str] = []
    for seat, v in sorted((probe.get("seats") or {}).items()):
        nid = _mark(v.get("state"), f"{seat}_task".replace(".", "_").replace("-", "_"))
        seat_ids.append(nid)
        nodes.append({"id": nid, "type": "skill.run", "depends_on": [probe_id], "input": {}})
    # One-shot: newest verdict.
    shot = _read((_latest("one-shot-*") or Path("/nonexistent")) / "one-shot-verdict.json")
    shot_id = _mark(shot.get("readiness") if not shot.get("dishonest") else "DISHONEST",
                    "one_shot")
    nodes.append({"id": shot_id, "type": "skill.run",
                  "depends_on": [probe_id], "input": {}})
    # Full runner report: newest agentic_evals report readiness.
    reports = sorted((p for p in REPORTS.glob("*.json") if p.is_file()),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    runner_state = "UNKNOWN"
    for rp in reports:
        d = _read(rp)
        if str(d.get("schema", "")).startswith("agentic_evals.report"):
            runner_state = {"READY": "READY", "USABLE_WITH_GAPS": "DEGRADED"}.get(
                str(d.get("readiness")), "FAIL")
            break
    nodes.append({"id": _mark(runner_state, "agentic_evals_runner"), "type": "skill.run",
                  "depends_on": [shot_id, *seat_ids] or [probe_id], "input": {}})
    dag = {"schema": "ask.dag.v1", "nodes": nodes}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dag, indent=2) + "\n")
    typer.echo(f"DAG_WRITTEN: {out} ({len(nodes)} nodes)")
    if render and PHART.is_file():
        proc = subprocess.run([str(PHART), "chart", str(out)],
                              capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            typer.echo(proc.stdout)
        else:
            typer.echo(f"CHART_RENDER_FAILED: {proc.stderr[-300:]}", err=True)
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
