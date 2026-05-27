"""Minimal ping-pong review controller."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
import typer

try:
    from ..ping_pong_state import PingPongRun, iter_events_since, read_state
    from ..reviewer_adapters import parse_reviewer_spec, run_ask_reviewer
except ImportError:  # direct script execution
    from ping_pong_state import PingPongRun, iter_events_since, read_state
    from reviewer_adapters import parse_reviewer_spec, run_ask_reviewer


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _load_run(output_dir: Path) -> PingPongRun:
    state_path = output_dir / "state.json"
    if not state_path.is_file():
        _fail(f"Invalid ping-pong state: missing {state_path}")
    try:
        state = read_state(state_path)
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed on invalid state
        _fail(f"Invalid ping-pong state: {exc}")
    run = PingPongRun(
        output_dir,
        run_id=state.run_id,
        idle_timeout_seconds=state.idle_timeout_seconds,
        max_wall_clock_seconds=state.max_wall_clock_seconds,
        requested_model=state.requested_model,
        requested_reasoning=state.requested_reasoning,
        bundle_path=state.bundle_path,
        artifact_paths=state.artifact_paths,
    )
    run.state = state
    events = iter_events_since(run.events_path).records
    commands = run.commands_since(0).records
    run._event_sequence = max([int(e.get("sequence", 0)) for e in events] or [0])  # type: ignore[attr-defined]
    run._command_sequence = max([int(c.get("sequence", 0)) for c in commands] or [0])  # type: ignore[attr-defined]
    return run


def _state_json(run: PingPongRun, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = run.state.to_json_dict()
    data["output_dir"] = str(run.root)
    data["events_path"] = str(run.events_path)
    data["commands_path"] = str(run.commands_path)
    if extra:
        data.update(extra)
    return data


def _print_status(run: PingPongRun, *, json_output: bool) -> None:
    data = _state_json(run)
    if json_output:
        typer.echo(json.dumps(data, sort_keys=True))
    else:
        typer.echo(f"{data['status']} {data['run_id']} rounds={data['rounds_completed']}")


def _watch(output_dir: Path) -> None:
    events_path = output_dir / "events.jsonl"
    if not (output_dir / "state.json").is_file() or not events_path.is_file():
        _fail(f"Invalid ping-pong state: missing durable artifacts in {output_dir}")
    for record in iter_events_since(events_path).records:
        typer.echo(json.dumps(record, sort_keys=True))


def _start_run(
    *,
    bundle: Path,
    output_dir: Path,
    reviewer: str,
    reasoning: str,
    idle_timeout: float,
    max_wall_clock: float,
) -> PingPongRun:
    if not bundle.is_file():
        _fail(f"Missing review bundle: {bundle}")
    try:
        spec = parse_reviewer_spec(reviewer)
    except ValueError as exc:
        _fail(str(exc))
    if reasoning != spec.reasoning:
        _fail(f"Unsupported reasoning for {reviewer}: {reasoning}; expected {spec.reasoning}")
    run = PingPongRun(
        output_dir,
        idle_timeout_seconds=idle_timeout,
        max_wall_clock_seconds=max_wall_clock,
        requested_model=spec.model,
        requested_reasoning=reasoning,
        bundle_path=str(bundle),
        artifact_paths={"bundle": str(bundle)},
    ).initialize()
    run.append_event("run_started", bundle_path=str(bundle), reviewer=reviewer, reasoning=reasoning)
    return run


def _effective_timeout(started: float, idle_timeout: float | None, max_wall_clock: float | None) -> float | None:
    values: list[float] = []
    if idle_timeout and idle_timeout > 0:
        values.append(idle_timeout)
    if max_wall_clock and max_wall_clock > 0:
        values.append(max(0.001, max_wall_clock - (time.monotonic() - started)))
    return min(values) if values else None


def _review_round(run: PingPongRun, reviewer: str, rounds: int, started: float) -> None:
    if not run.state.bundle_path:
        _fail("Invalid ping-pong state: missing bundle path")
    if not Path(run.state.bundle_path).is_file():
        _fail(f"Missing review bundle: {run.state.bundle_path}")
    if run.state.rounds_completed >= rounds:
        run.append_event("run_completed", reason="round limit reached")
        return

    round_no = run.state.rounds_completed + 1
    round_dir = run.root / f"round-{round_no}"
    run.append_event("reviewer_started", round=round_no, reviewer=reviewer)
    try:
        result = run_ask_reviewer(
            reviewer_spec=reviewer,
            bundle_path=run.state.bundle_path,
            output_dir=round_dir,
            timeout=_effective_timeout(started, run.state.idle_timeout_seconds, run.state.max_wall_clock_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        # The child boundary owns preservation where supported; the durable
        # controller records needs_attention rather than inventing unrelated
        # status files.
        run.append_event("error", reason="needs_attention", detail=str(exc), round=round_no)
        run.update_state(status="needs_attention")  # type: ignore[arg-type]
        return
    except Exception as exc:  # noqa: BLE001 - fail closed and persist the reason
        run.append_event("error", reason="reviewer_failed", detail=str(exc), round=round_no)
        raise

    artifacts = dict(run.state.artifact_paths)
    artifacts[f"round_{round_no}"] = str(round_dir)
    if result.artifact_path:
        artifacts[f"round_{round_no}_result"] = result.artifact_path
    run.update_state(
        actual_model=result.actual_model,
        actual_reasoning=result.actual_reasoning,
        artifact_paths=artifacts,
    )
    run.append_event(
        "reviewer_completed",
        round=round_no,
        rounds_completed=round_no,
        terminal_status=result.terminal_status,
        artifact_path=result.artifact_path,
    )
    if result.terminal_status == "clarification_request":
        event_data = result.events[0] if result.events else {"content": result.content}
        run.append_event("clarification_requested", round=round_no, **event_data)
        return
    run.append_event("recommendation", round=round_no, content=result.content, terminal_status=result.terminal_status)
    run.append_event("run_completed", rounds_completed=round_no)


def ping_pong(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Review bundle path"),
    reviewer: str = typer.Option("ask:gpt-5.5", "--reviewer", help="Reviewer spec"),
    reasoning: str = typer.Option("high", "--reasoning", help="Reviewer reasoning effort"),
    rounds: int = typer.Option(1, "--rounds", help="Maximum review rounds"),
    idle_timeout: float = typer.Option(60.0, "--idle-timeout", help="Seconds without controller-visible events before attention is needed"),
    max_wall_clock: float = typer.Option(300.0, "--max-wall-clock", help="Hard wall-clock stop in seconds"),
    output_dir: Path = typer.Option(..., "--output-dir", help="Ping-pong output/run directory"),
    watch: bool = typer.Option(False, "--watch", help="Stream durable events"),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable final status"),
    parent_response: Optional[str] = typer.Option(None, "--parent-response", help="Resume a clarification request with parent text"),
) -> None:
    """Run, inspect, watch, or resume a durable ping-pong review."""

    if watch:
        _watch(output_dir)
        return

    if parent_response is not None:
        run = _load_run(output_dir)
        if run.state.status not in {"waiting_for_parent", "needs_attention"}:
            _fail(f"Stale/invalid state for parent response: status={run.state.status}")
        run.append_command("parent_response", response=parent_response)
        run.append_event("parent_response", response=parent_response)
        reviewer = run.state.artifact_paths.get("reviewer", reviewer)
        rounds = int(run.state.artifact_paths.get("rounds", rounds))
        started = time.monotonic()
        _review_round(run, reviewer, rounds, started)
        _print_status(run, json_output=json_output)
        return

    if file is None:
        run = _load_run(output_dir)
        _print_status(run, json_output=json_output)
        return

    if rounds < 1:
        _fail("--rounds must be at least 1")
    started = time.monotonic()
    run = _start_run(
        bundle=file,
        output_dir=output_dir,
        reviewer=reviewer,
        reasoning=reasoning,
        idle_timeout=idle_timeout,
        max_wall_clock=max_wall_clock,
    )
    artifacts = dict(run.state.artifact_paths)
    artifacts["reviewer"] = reviewer
    artifacts["rounds"] = str(rounds)
    run.update_state(artifact_paths=artifacts)
    _review_round(run, reviewer, rounds, started)
    _print_status(run, json_output=json_output)
