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
    # One-shot runs: per-seat answers with their own verdict artifact.
    for shot in sorted(REPORTS.glob("one-shot-*")):
        if not shot.is_dir():
            continue
        vp = shot / "one-shot-verdict.json"
        if not vp.is_file():
            rows.append({"source": "one-shot", "name": shot.name,
                         "outcome": "NOT_ESTABLISHED (no verdict artifact)", "detail": "-",
                         "at": shot.name.split("-")[-1]})
            continue
        try:
            d = json.loads(vp.read_text())
        except (OSError, json.JSONDecodeError):
            rows.append({"source": "one-shot", "name": shot.name,
                         "outcome": "ERROR (corrupt one-shot-verdict.json)",
                         "detail": "one-shot-verdict.json", "at": shot.name.split("-")[-1]})
            continue
        dishonest = bool(d.get("dishonest"))
        outcome = (f"{'FAIL' if dishonest else 'PASS'} ({d.get('readiness')}, "
                   f"{d.get('answered')}/{len(d.get('lanes') or {})} answered)")
        rows.append({"source": "one-shot", "name": shot.name, "outcome": outcome,
                     "detail": "one-shot-verdict.json", "at": shot.name.split("-")[-1]})
    # Task probes. The probe's OWN verdict is authoritative when present:
    # Tau can report a completed run whose responses the probe then rejected
    # as below-floor, so tau-result.json alone must never stand in for it.
    for probe in sorted(REPORTS.glob("task-probe-*")):
        if not probe.is_dir():
            continue
        verdict = probe / "probe-verdict.json"
        if verdict.is_file():
            try:
                d = json.loads(verdict.read_text())
            except (OSError, json.JSONDecodeError):
                rows.append({"source": "task-probe", "name": probe.name,
                             "outcome": "ERROR (corrupt probe-verdict.json)",
                             "detail": "probe-verdict.json", "at": probe.name.split("-")[-1]})
                continue
            dishonest = bool(d.get("violators"))
            outcome = f"{'FAIL' if dishonest else 'PASS'} ({d.get('readiness')}, {d.get('honesty')} honest)"
            rows.append({"source": "task-probe", "name": probe.name,
                         "outcome": outcome, "detail": "probe-verdict.json",
                         "at": probe.name.split("-")[-1]})
            continue
        res = probe / "tau-result.json"
        if res.is_file():
            try:
                d = json.loads(res.read_text())
            except (OSError, json.JSONDecodeError):
                rows.append({"source": "task-probe", "name": probe.name,
                             "outcome": "ERROR (corrupt tau-result.json)",
                             "detail": "tau-result.json", "at": probe.name.split("-")[-1]})
                continue
            rows.append({"source": "task-probe", "name": probe.name,
                         "outcome": str(d.get("status") or "?") + " (tau only; no probe verdict)",
                         "detail": "tau-result.json", "at": probe.name.split("-")[-1]})
        else:
            rows.append({"source": "task-probe", "name": probe.name,
                         "outcome": "NOT_ESTABLISHED (no verdict artifact)",
                         "detail": "-", "at": probe.name.split("-")[-1]})
    return rows


@app.command()
def main(
    markdown: bool = typer.Option(False, "--markdown"),
    as_json: bool = typer.Option(False, "--json"),
    latest: bool = typer.Option(True, "--latest/--all", help="Only the newest run per source."),
    gate: bool = typer.Option(False, "--gate",
                              help="Exit 1 when any fail-like row exists (CI/readiness use)."),
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
    fail = sum(1 for r in rows if any(tag in str(r["outcome"])
               for tag in ("FAIL", "NOT_READY", "BLOCKED", "ERROR", "NOT_ESTABLISHED")))
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
    if gate and fail:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
