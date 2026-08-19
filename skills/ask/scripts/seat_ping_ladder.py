#!/usr/bin/env python3
"""Concurrent ping ladder: every seat answers its token or names its blocker.

The FIRST live eval, because everything else depends on it: if seats cannot
return "Reply with exactly: LIVE-<token>", roundtables and competitions are
noise. All seats run CONCURRENTLY (each browser seat gets its own fresh
window via the normal tau-dag lifecycle), and the contract is honesty, not
availability: PASS per seat = token returned OR a named failure_code. The only
failure is a seat that produces neither -- a dead end nobody can act on.

Exit 0 when every seat is honest; exit 1 listing violating seats. Per-seat
JSON artifacts land in --out-dir for the eval report trail.
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEATS = [
    "webgpt", "webgemini", "webkimi", "webclaude", "webgrok", "webdeepseek",
    "claude-opus-5-low", "gpt-5.5-low", "deepseek-v4-flash",
]


def _ping(seat: str, out_dir: Path, timeout: int) -> dict:
    out_path = out_dir / f"{seat}.json"
    started = time.time()
    proc = subprocess.run(
        [str(SKILL_ROOT / "run.sh"), "live-seat-probe", seat, "--json"],
        capture_output=True, text=True, timeout=timeout, cwd=SKILL_ROOT,
    )
    payload: dict = {}
    text = proc.stdout
    try:
        payload = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        payload = {"parse_error": True, "stdout_tail": text[-300:], "stderr_tail": proc.stderr[-300:]}
    payload["seat"] = seat
    payload["elapsed_s"] = round(time.time() - started, 1)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def _honest(payload: dict) -> bool:
    if payload.get("parse_error"):
        return False
    if payload.get("violations"):
        return False
    outcome = payload.get("outcome")
    return outcome in {"answered", "named_blocker"}


@app.command()
def main(
    out_dir: Path = typer.Option(Path("/tmp/seat-ping-ladder"), "--out-dir"),
    timeout: int = typer.Option(1200, "--timeout"),
    seat: list[str] = typer.Option(None, "--seat", help="Override the default nine seats."),
) -> None:
    seats = list(seat) if seat else DEFAULT_SEATS
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(seats)) as pool:
        futures = {pool.submit(_ping, s, out_dir, timeout): s for s in seats}
        for fut in concurrent.futures.as_completed(futures):
            s = futures[fut]
            try:
                results[s] = fut.result()
            except Exception as exc:  # timeout or spawn failure is a dishonest end
                results[s] = {"seat": s, "outcome": "runner_error", "error": str(exc)[:200]}
            r = results[s]
            typer.echo(f"SEAT {s}: outcome={r.get('outcome')} answered={r.get('answered')}")
    violators = [s for s in seats if not _honest(results.get(s, {}))]
    answered = sum(1 for s in seats if results.get(s, {}).get("outcome") == "answered")
    typer.echo(f"LADDER: {answered}/{len(seats)} answered, {len(seats) - len(violators)}/{len(seats)} honest")
    if violators:
        typer.echo("DISHONEST_SEATS: " + ", ".join(violators), err=True)
        raise typer.Exit(1)
    typer.echo("ALL_SEATS_HONEST")


if __name__ == "__main__":
    app()
