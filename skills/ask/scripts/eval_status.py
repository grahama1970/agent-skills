#!/usr/bin/env python3
"""Success/failure table over every persisted /ask agentic-eval artifact.

One command answers "which /ask evals are passing" from the artifacts on disk,
never from memory: full agentic-evals reports (deterministic and live runs),
seat-ping ladders, and task-probe runs, newest first per source. Output is a
plain table by default, --markdown for docs/issues, --json for machines.
Absence is reported, never dropped: a source directory with no artifacts is a
row saying so.
"""
from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

REPORTS = Path("/mnt/storage12tb/skills/ask/outputs/eval-reports")


def _rows() -> list[dict]:
    rows: list[dict] = []
    if not REPORTS.is_dir():
        return [{"source": "eval-reports", "name": "(directory missing)", "outcome": "NOT_ESTABLISHED",
                 "detail": str(REPORTS), "at": "-"}]
    # Full runner reports (deterministic fixture and live fixture runs).
    for rp in sorted(REPORTS.glob("*.json")):
        try:
            d = json.loads(rp.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("schema", "").startswith("agentic_evals.report"):
            stamp = rp.stem.replace("-live", "")
            kind = "live-fixture" if "-live" in rp.stem else "deterministic-fixture"
            for c in d.get("cases") or []:
                rows.append({"source": kind, "name": c.get("name"),
                             "outcome": c.get("outcome"), "detail": rp.name, "at": stamp})
            rows.append({"source": kind, "name": "(overall readiness)",
                         "outcome": d.get("readiness"), "detail": rp.name, "at": stamp})
    # Seat-ping ladders: per-seat honesty artifacts.
    for ladder in sorted(REPORTS.glob("seat-pings-*")) + sorted(REPORTS.glob("ping-ladder-*")):
        if not ladder.is_dir():
            continue
        for sp in sorted(ladder.glob("*.json")):
            try:
                d = json.loads(sp.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            outcome = d.get("outcome") or ("answered" if d.get("answered") else "unknown")
            ok = outcome in {"answered", "named_blocker"}
            rows.append({"source": "seat-ping", "name": sp.stem,
                         "outcome": ("PASS" if ok else "FAIL") + f" ({outcome})",
                         "detail": ladder.name, "at": ladder.name.split("-")[-1]})
    # Task probes.
    for probe in sorted(REPORTS.glob("task-probe-*")):
        res = probe / "tau-result.json"
        if res.is_file():
            try:
                d = json.loads(res.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            rows.append({"source": "task-probe", "name": probe.name,
                         "outcome": d.get("status") or "?", "detail": "tau-result.json",
                         "at": probe.name.split("-")[-1]})
    return rows


@app.command()
def main(
    markdown: bool = typer.Option(False, "--markdown"),
    as_json: bool = typer.Option(False, "--json"),
    latest: bool = typer.Option(True, "--latest/--all", help="Only the newest run per source."),
) -> None:
    rows = _rows()
    if latest:
        newest: dict[str, str] = {}
        for r in rows:
            if r["source"] == "task-probe":
                continue
            newest[r["source"]] = max(newest.get(r["source"], ""), str(r["at"]))
        rows = [r for r in rows if r["source"] == "task-probe" or str(r["at"]) == newest.get(r["source"])]
    if as_json:
        typer.echo(json.dumps({"generated_at": datetime.now(UTC).isoformat(),
                               "rows": rows}, indent=2))
        return
    fail = sum(1 for r in rows if "FAIL" in str(r["outcome"]) or r["outcome"] in ("NOT_READY", "FAIL", "BLOCKED", "ERROR"))
    ok = sum(1 for r in rows if "PASS" in str(r["outcome"]) or r["outcome"] in ("READY", "answered"))
    sep = "|" if markdown else "  "
    header = ["source", "case/seat", "outcome", "run"]
    if markdown:
        typer.echo("| " + " | ".join(header) + " |")
        typer.echo("|" + "---|" * len(header))
    else:
        typer.echo(f"{'SOURCE':24}{'CASE/SEAT':58}{'OUTCOME':28}RUN")
    for r in sorted(rows, key=lambda x: (x["source"], str(x["name"]))):
        cells = [str(r["source"])[:23], str(r["name"])[:57], str(r["outcome"])[:27], str(r["at"])]
        if markdown:
            typer.echo("| " + " | ".join(cells) + " |")
        else:
            typer.echo(f"{cells[0]:24}{cells[1]:58}{cells[2]:28}{cells[3]}")
    typer.echo(f"TOTALS: pass-like={ok} fail-like={fail} rows={len(rows)}")


if __name__ == "__main__":
    app()
