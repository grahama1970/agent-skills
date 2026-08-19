#!/usr/bin/env python3
"""Concurrent ping ladder: every seat answers its token or names its blocker.

The FIRST live eval, because everything else depends on it: if seats cannot
return "Reply with exactly: LIVE-<token>", roundtables and competitions are
noise. All seats run CONCURRENTLY (each browser seat gets its own fresh
window via the normal tau-dag lifecycle).

Two SEPARATE verdicts, never conflated (review finding 2026-08-19):

- HONESTY: every seat either answered (token proven, child exit 0) or named a
  blocker with a NON-EMPTY failure_code. A named_blocker without a code, a
  payload for the wrong seat, an answered outcome from a failing child
  process, or unparseable output is DISHONEST.
- READINESS: how many seats actually answered. An all-blocked ladder can be
  perfectly honest and still useless; it reports NOT_READY, never a green.

Exit 0 only when honest AND readiness meets --min-answered. Exit 1 on any
dishonest seat. Exit 3 when honest but below the answered floor. Per-seat
JSON artifacts land in --out-dir for EVERY seat including timeouts and spawn
failures, plus a ladder-verdict.json summary for downstream status readers.

--run-sh exists for fault-injection tests of this script itself: point it at
a fake runner and prove the red paths stay red.
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import time
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEATS = [
    "webgpt", "webgemini", "webkimi", "webclaude", "webgrok", "webdeepseek",
    "claude-opus-5-low", "gpt-5.5-low", "oc-deepseek",
]


def _norm(name: str) -> str:
    return name.lower().replace(".", "-")


def _ping(seat: str, out_dir: Path, timeout: int, run_sh: Path) -> dict:
    out_path = out_dir / f"{seat}.json"
    started = time.time()
    payload: dict = {"requested_seat": seat}
    try:
        proc = subprocess.run(
            [str(run_sh), "live-seat-probe", seat, "--json"],
            capture_output=True, text=True, timeout=timeout, cwd=run_sh.parent,
        )
        text = proc.stdout
        try:
            payload.update(json.loads(text[text.index("{"):text.rindex("}") + 1]))
        except (ValueError, json.JSONDecodeError):
            payload.update({"parse_error": True, "stdout_tail": text[-300:],
                            "stderr_tail": proc.stderr[-300:]})
        payload["child_exit"] = proc.returncode
    except Exception as exc:  # timeout / spawn failure still leaves an artifact
        payload.update({"outcome": "runner_error", "error": str(exc)[:200], "child_exit": None})
    payload["elapsed_s"] = round(time.time() - started, 1)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def _verdict(payload: dict) -> tuple[str, str]:
    """Return (state, reason). state in ANSWERED | NAMED_BLOCKER | DISHONEST."""
    if payload.get("parse_error"):
        return "DISHONEST", "unparseable probe output"
    if payload.get("violations"):
        return "DISHONEST", f"probe violations: {payload['violations']}"
    if payload.get("outcome") == "runner_error":
        return "DISHONEST", payload.get("error") or "runner error"
    lanes = payload.get("lanes") or []
    requested = _norm(str(payload.get("requested_seat") or ""))
    # Identity binding: the receipt must be about the seat we asked for. The
    # probe's lane ids look like handler-<seat> with dots normalized away --
    # EXCEPT when the seat answered through its recorded substitution (e.g.
    # webclaude -> claude-opus-5-high), where the lane carries the substitute
    # and the probe's own top-level handler field carries the requested seat.
    if lanes and requested:
        lane_ids = [_norm(str(l.get("lane") or "")) for l in lanes]
        models = [_norm(str(m)) for l in lanes for m in (l.get("models") or [])]
        probe_handler = _norm(str(payload.get("handler") or ""))
        if (
            not any(requested in lid for lid in lane_ids)
            and not any(requested in m or m in requested for m in models)
            and probe_handler != requested
        ):
            return "DISHONEST", f"receipt names {lane_ids or models}, not the requested seat"
    outcome = payload.get("outcome")
    if outcome == "answered":
        if payload.get("child_exit") not in (0,):
            return "DISHONEST", f"claims answered but probe exited {payload.get('child_exit')}"
        if lanes and not any(l.get("has_token") for l in lanes):
            return "DISHONEST", "claims answered but no lane proved the token"
        return "ANSWERED", ""
    if outcome == "named_blocker":
        codes = [str(l.get("failure_code") or "") for l in lanes if l.get("failure_code")]
        if not codes and not payload.get("failure_code"):
            return "DISHONEST", "named_blocker without any failure_code"
        return "NAMED_BLOCKER", ",".join(codes) or str(payload.get("failure_code"))
    if outcome == "timed_out":
        # The probe named the outcome itself -- honest and actionable (retry,
        # raise the deadline, inspect the lane), but it is NOT an answer: it
        # counts against readiness, never against honesty.
        return "NAMED_BLOCKER", f"probe timeout after {payload.get('elapsed_s')}s"
    return "DISHONEST", f"outcome={outcome!r} is neither an answer nor a named blocker"


@app.command()
def main(
    out_dir: Path = typer.Option(Path("/tmp/seat-ping-ladder"), "--out-dir"),
    timeout: int = typer.Option(1200, "--timeout"),
    seat: list[str] = typer.Option(None, "--seat", help="Override the default nine seats."),
    min_answered: int = typer.Option(1, "--min-answered",
                                     help="Readiness floor: honest run still exits 3 below this."),
    run_sh: Path = typer.Option(SKILL_ROOT / "run.sh", "--run-sh",
                                help="Probe runner (fault-injection hook for testing the ladder itself)."),
) -> None:
    seats = list(seat) if seat else DEFAULT_SEATS
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(seats)) as pool:
        futures = {pool.submit(_ping, s, out_dir, timeout, run_sh): s for s in seats}
        for fut in concurrent.futures.as_completed(futures):
            s = futures[fut]
            results[s] = fut.result()
            state, reason = _verdict(results[s])
            suffix = f" ({reason})" if reason else ""
            typer.echo(f"SEAT {s}: {state}{suffix}")
    states = {s: _verdict(results.get(s, {"requested_seat": s})) for s in seats}
    dishonest = [s for s, (st, _) in states.items() if st == "DISHONEST"]
    answered = [s for s, (st, _) in states.items() if st == "ANSWERED"]
    readiness = ("READY" if len(answered) >= max(min_answered, 1) else "NOT_READY")
    if readiness == "READY" and len(answered) < len(seats) - len(dishonest):
        readiness = "DEGRADED"
    (out_dir / "ladder-verdict.json").write_text(json.dumps({
        "schema": "ask.seat_ping_ladder_verdict.v1",
        "seats": {s: {"state": st, "reason": rs} for s, (st, rs) in states.items()},
        "answered": len(answered), "dishonest": dishonest,
        "honesty": "HONEST" if not dishonest else "DISHONEST",
        "readiness": readiness, "min_answered": min_answered,
    }, indent=2) + "\n")
    typer.echo(f"LADDER_HONESTY: {len(seats) - len(dishonest)}/{len(seats)} honest")
    typer.echo(f"LADDER_READINESS: {readiness} ({len(answered)}/{len(seats)} answered, floor {min_answered})")
    if dishonest:
        typer.echo("DISHONEST_SEATS: " + ", ".join(dishonest), err=True)
        raise typer.Exit(1)
    typer.echo("ALL_SEATS_HONEST")
    if readiness == "NOT_READY":
        typer.echo("LADDER_NOT_READY: honest, but below the answered floor", err=True)
        raise typer.Exit(3)


if __name__ == "__main__":
    app()
