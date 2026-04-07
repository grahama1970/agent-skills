"""Conversation Lab — Self-improving convergence loop for SPARTA stress tests.

Reads session JSONL files from /sparta-stress-test, diagnoses failures,
re-runs unsatisfied sessions, and tracks convergence across cycles.

Inputs:
  - Session JSONL files (sessions_*.jsonl) from sparta-stress-test/results/sessions/
  - Convergence state from ~/.pi/conversation-lab/convergence_state.json
  - Episodic archiver data from ArangoDB (via /memory recall)

Outputs:
  - Structured JSON diagnostics for /assess consumption
  - Convergence state tracking across cycles
  - Turn count optimization recommendations

Failure modes:
  - Missing session files → clear error with expected path
  - No rerun candidates → early exit with summary
  - Stress test subprocess failure → logged, convergence continues with remaining
  - Stalled convergence → auto-detected, stops with actionable message

Modules:
  - diagnosis.py: Issue classification, rerun eligibility, structured diagnosis builder
  - promote.py: Nightly QRA promotion pipeline (harvest, dedup, assess, promote)
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

# Re-export public API from sub-modules for backward compatibility
from diagnosis import (  # noqa: F401
    LOGIC_GRAPH_ERROR_TAXONOMY,
    build_diagnosis,
    classify_issues,
    classify_reasoning_error,
    get_persona_evals,
    is_rerun_eligible,
)
from promote import promote_nightly_command  # noqa: F401

app = typer.Typer(help="Conversation convergence lab for SPARTA stress tests.")
console = Console()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILLS_DIR = Path(__file__).parent.parent
STRESS_TEST_DIR = SKILLS_DIR / "sparta-stress-test"
SESSIONS_DIR = STRESS_TEST_DIR / "results" / "sessions"
STATE_DIR = Path.home() / ".pi" / "conversation-lab"
STATE_FILE = STATE_DIR / "convergence_state.json"
TASK_STATE_FILE = Path(__file__).parent / "conversation_lab_task_state.json"

# Task-monitor integration
TM_RUN = SKILLS_DIR / "task-monitor" / "run.sh"


def _tm(args: list[str]) -> bool:
    """Report to task-monitor. Non-fatal if unavailable."""
    if not TM_RUN.exists():
        return False
    try:
        return subprocess.run(
            [str(TM_RUN), *args],
            capture_output=True, text=True, timeout=30,
        ).returncode == 0
    except Exception:
        return False


def _write_task_state(state: dict) -> None:
    """Write task state atomically for task-monitor polling."""
    out = {**state, "last_updated": datetime.now().isoformat()}
    tmp = TASK_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2))
    os.replace(tmp, TASK_STATE_FILE)


# ---------------------------------------------------------------------------
# Session loading
# ---------------------------------------------------------------------------
def _find_session_files(file_path: Optional[str] = None) -> list[Path]:
    """Find session JSONL files, newest first."""
    if file_path:
        p = Path(file_path)
        if p.is_file():
            return [p]
        if p.is_dir():
            files = sorted(p.glob("sessions_*.jsonl"), reverse=True)
            if files:
                return files
    # Default: look in stress test results
    if SESSIONS_DIR.exists():
        files = sorted(SESSIONS_DIR.glob("sessions_*.jsonl"), reverse=True)
        if files:
            return files
    return []


def _load_sessions(file_path: Optional[str] = None) -> list[dict]:
    """Load all sessions from JSONL file(s)."""
    files = _find_session_files(file_path)
    if not files:
        logger.warning(f"No session files found. Expected at: {SESSIONS_DIR}/sessions_*.jsonl")
        return []
    # Use the most recent file
    target = files[0]
    logger.info(f"Loading sessions from: {target}")
    sessions = []
    with open(target) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    sessions.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed line: {e}")
    logger.info(f"Loaded {len(sessions)} sessions")
    return sessions


# ---------------------------------------------------------------------------
# Convergence engine
# ---------------------------------------------------------------------------
def _load_convergence_state() -> dict:
    """Load convergence state from disk."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_convergence_state(state: dict) -> None:
    """Save convergence state atomically."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


def _extract_seeds(sessions: list[dict], candidate_ids: list[str]) -> list[dict]:
    """Extract seed questions from sessions for re-run."""
    candidate_set = set(candidate_ids)
    seeds = []
    for s in sessions:
        sid = s.get("session_id", "")
        if sid not in candidate_set:
            continue
        seed = s.get("seed_question", {})
        if seed:
            seeds.append({
                "original_session_id": sid,
                "question": seed.get("question", ""),
                "target_control": seed.get("target_control", ""),
                "difficulty": seed.get("difficulty", "medium"),
                "expected_action": seed.get("expected_action", "QUERY"),
                "bridge_tags": seed.get("bridge_tags", []),
            })
    return seeds


def _run_stress_test(seeds: list[dict], max_rounds: int = 5) -> Optional[Path]:
    """Run sparta-stress-test with given seeds. Returns path to results.

    Seeds are passed via CONVERSATION_LAB_SEEDS env var pointing to a JSON file.
    The stress test CLI doesn't have a --seeds-file flag, so we use --count
    and let CONVO_MAX_ROUNDS control iteration depth.
    """
    stress_cli = STRESS_TEST_DIR / "run.sh"
    if not stress_cli.exists():
        logger.error(f"sparta-stress-test not found at {stress_cli}")
        return None

    # Write seeds to state dir for traceability
    seeds_file = STATE_DIR / "rerun_seeds.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seeds_file.write_text(json.dumps(seeds, indent=2))

    env = os.environ.copy()
    env["CONVO_MAX_ROUNDS"] = str(max_rounds)
    env["PYTHONUNBUFFERED"] = "1"

    logger.info(f"Running stress test with {len(seeds)} seeds, max_rounds={max_rounds}")
    try:
        result = subprocess.run(
            [
                str(stress_cli), "simulate",
                "--count", str(len(seeds)),
                "--seeds-file", str(seeds_file),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
        )
        if result.returncode != 0:
            logger.error(f"Stress test failed: {result.stderr[:500]}")
            return None
    except subprocess.TimeoutExpired:
        logger.error("Stress test timed out after 1 hour")
        return None

    # Find the newest results file
    files = _find_session_files()
    return files[0] if files else None


def _query_episodic_sessions() -> list[dict]:
    """Query /episodic-archiver via embry-memory daemon for historical session data."""
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/recall", json={
                "q": "sparta stress test conversation sessions",
                "scope": "episodes",
                "k": 50,
                "collections": ["agent_conversations"],
            })
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug(f"Episodic query failed (non-fatal): {e}")
    return []


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
@app.command()
def diagnose(
    file: Optional[str] = typer.Argument(None, help="Session JSONL file or directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Analyze sessions and output structured JSON report for /assess consumption.

    Default JSON output is machine-readable for /assess. Use --format md for Rich tables.
    """
    sessions = _load_sessions(file)
    if not sessions:
        console.print("[red]No sessions found.[/red]")
        raise typer.Exit(1)

    diagnosis = build_diagnosis(sessions)

    if output_format == "md":
        from report_md import build_report_md
        print(build_report_md(sessions, diagnosis))
    else:
        print(json.dumps(diagnosis, indent=2))


@app.command()
def report(
    file: Optional[str] = typer.Argument(None, help="Session JSONL file or directory"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output markdown file path"),
) -> None:
    """Generate human-readable markdown report with full conversation transcripts.

    Produces the same format as /tmp/conversation_flows_*.md -- summary table,
    per-session detail with transcripts, metrics, and actionable next steps.
    """
    sessions = _load_sessions(file)
    if not sessions:
        console.print("[red]No sessions found.[/red]")
        raise typer.Exit(1)

    diagnosis = build_diagnosis(sessions)
    from report_md import build_report_md
    md = build_report_md(sessions, diagnosis)

    if output:
        Path(output).write_text(md)
        console.print(f"[green]Report written to {output}[/green]")
        logger.info(f"Report: {len(sessions)} sessions -> {output}")
    else:
        print(md)


@app.command()
def converge(
    file: Optional[str] = typer.Argument(None, help="Session JSONL file or directory"),
    max_cycles: int = typer.Option(5, "--max-cycles", "-c", help="Max convergence cycles"),
    max_rounds: int = typer.Option(5, "--max-rounds", "-r", help="CONVO_MAX_ROUNDS for reruns"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Diagnose only, don't rerun"),
    target_rate: float = typer.Option(0.80, "--target", "-t", help="Target satisfaction rate"),
    json_stream: bool = typer.Option(False, "--json-stream", help="NDJSON streaming output"),
) -> None:
    """Re-run unsatisfied sessions until personas are happy or ceiling hit."""
    _tm(["start-session", "--project", "conversation-lab"])

    sessions = _load_sessions(file)
    if not sessions:
        console.print("[red]No sessions found.[/red]")
        _tm(["end-session", "--notes", "No sessions found"])
        raise typer.Exit(1)

    run_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    state = {
        "run_id": run_id,
        "cycles": [],
        "status": "running",
        "started": datetime.now().isoformat(),
        "total_llm_calls": 0,
    }

    prev_rate = 0.0
    plateau_count = 0

    for cycle in range(1, max_cycles + 1):
        logger.info(f"--- Convergence cycle {cycle}/{max_cycles} ---")
        _write_task_state({
            "completed": cycle - 1,
            "total": max_cycles,
            "progress_pct": round((cycle - 1) / max_cycles * 100, 1),
            "status": "running",
        })

        # Phase 1: Diagnose
        diagnosis = build_diagnosis(sessions)
        satisfied_rate = diagnosis["summary"]["satisfied_rate"]
        avg_composite = diagnosis["summary"]["avg_composite"]
        candidates = diagnosis["rerun_candidates"]

        cycle_record = {
            "cycle": cycle,
            "satisfied_rate": satisfied_rate,
            "avg_composite": avg_composite,
            "sessions_rerun": len(candidates),
            "improved": 0,
            "regressed": 0,
        }

        if json_stream:
            print(json.dumps({"event": "cycle_start", "cycle": cycle, **cycle_record}))

        _tm(["add-accomplishment", "--text",
             f"Cycle {cycle}: satisfied={satisfied_rate:.0%}, candidates={len(candidates)}"])

        # Check stopping conditions
        if satisfied_rate >= target_rate:
            logger.info(f"Target satisfaction rate {target_rate:.0%} reached: {satisfied_rate:.0%}")
            state["status"] = "converged"
            state["cycles"].append(cycle_record)
            break

        if not candidates:
            logger.info("No rerun candidates remaining")
            state["status"] = "no_candidates"
            state["cycles"].append(cycle_record)
            break

        # Plateau detection
        improvement = satisfied_rate - prev_rate
        if cycle > 1 and improvement < 0.05:
            plateau_count += 1
            if plateau_count >= 2:
                logger.info(f"Plateau detected: {plateau_count} cycles with < 5% improvement")
                state["status"] = "plateau"
                state["cycles"].append(cycle_record)
                break
        else:
            plateau_count = 0
        prev_rate = satisfied_rate

        if dry_run:
            logger.info(f"[DRY RUN] Would rerun {len(candidates)} sessions")
            state["cycles"].append(cycle_record)
            continue

        # Phase 2: Extract seeds and rerun
        seeds = _extract_seeds(sessions, candidates)
        if not seeds:
            logger.warning("Could not extract seeds from candidates")
            state["cycles"].append(cycle_record)
            break

        result_file = _run_stress_test(seeds, max_rounds=max_rounds)
        if result_file:
            new_sessions = _load_sessions(str(result_file))
            # Compare and merge
            from converge_helpers import compare_sessions, merge_sessions
            improved, regressed = compare_sessions(sessions, new_sessions)
            cycle_record["improved"] = improved
            cycle_record["regressed"] = regressed
            # Replace improved sessions in working set
            sessions = merge_sessions(sessions, new_sessions)
            state["total_llm_calls"] += len(seeds) * max_rounds * 2  # rough estimate

        state["cycles"].append(cycle_record)
        _save_convergence_state(state)

        if json_stream:
            print(json.dumps({"event": "cycle_end", "cycle": cycle, **cycle_record}))

    # Finalize
    if state["status"] == "running":
        state["status"] = "max_cycles_exhausted"
    state["completed"] = datetime.now().isoformat()
    _save_convergence_state(state)
    _write_task_state({
        "completed": len(state["cycles"]),
        "total": max_cycles,
        "progress_pct": 100.0,
        "status": "completed",
    })

    _tm(["end-session", "--notes",
         f"Convergence {state['status']}: {len(state['cycles'])} cycles"])

    # Final output
    final_diagnosis = build_diagnosis(sessions)
    final_diagnosis["convergence"] = state
    print(json.dumps(final_diagnosis, indent=2))


@app.command()
def optimize(
    file: Optional[str] = typer.Argument(None, help="Session JSONL file or directory"),
) -> None:
    """Analyze session data + episodic archives to recommend optimal turn counts."""
    sessions = _load_sessions(file)
    if not sessions:
        console.print("[red]No session files found.[/red]")
        raise typer.Exit(1)

    # Augment with episodic-archiver data if available
    episodic = _query_episodic_sessions()
    episodic_count = len(episodic)
    if episodic:
        logger.info(f"Loaded {episodic_count} sessions from /episodic-archiver")

    # Group by difficulty and satisfaction
    by_difficulty: dict[str, list[int]] = {}
    by_persona: dict[str, list[int]] = {}
    satisfied_turns = []
    all_turns = []

    for s in sessions:
        difficulty = s.get("seed_question", {}).get("difficulty", "medium")
        persona = s.get("persona", "unknown")
        turn_count = len(s.get("turns", []))
        persona_evals = get_persona_evals(s)
        satisfied = "satisfactory" in persona_evals

        all_turns.append(turn_count)
        by_difficulty.setdefault(difficulty, []).append(turn_count)
        by_persona.setdefault(persona, []).append(turn_count)

        if satisfied:
            satisfied_turns.append(turn_count)

    # Compute recommendations per difficulty
    recommended = {}
    for diff, turns in by_difficulty.items():
        avg = sum(turns) / len(turns) if turns else 4
        # Add 1 round buffer over average
        recommended[diff] = min(round(avg + 1), 10)

    avg_sat = sum(satisfied_turns) / len(satisfied_turns) if satisfied_turns else 0
    avg_all = sum(all_turns) / len(all_turns) if all_turns else 0

    # Diminishing returns: where does each additional round yield < 5% marginal gain?
    # Approximated as average satisfied turns + 2
    diminishing = round(avg_sat + 2) if avg_sat else 5

    result = {
        "recommended_max_rounds": recommended,
        "diminishing_returns_at": min(diminishing, 10),
        "avg_turns_to_satisfaction": round(avg_sat, 1),
        "avg_turns_all": round(avg_all, 1),
        "data_points": len(sessions),
        "episodic_data_points": episodic_count,
        "per_persona": {
            p: {"avg_turns": round(sum(t) / len(t), 1), "sessions": len(t)}
            for p, t in by_persona.items()
        },
    }
    print(json.dumps(result, indent=2))


@app.command()
def status() -> None:
    """Show convergence state (running/complete/stalled)."""
    state = _load_convergence_state()
    if not state:
        console.print("[yellow]No convergence state found.[/yellow]")
        console.print(f"Expected at: {STATE_FILE}")
        raise typer.Exit(0)

    table = Table(title=f"Convergence: {state.get('run_id', 'unknown')}")
    table.add_column("Cycle", style="cyan")
    table.add_column("Satisfied Rate", style="green")
    table.add_column("Avg Composite", style="blue")
    table.add_column("Rerun", style="yellow")
    table.add_column("Improved", style="green")
    table.add_column("Regressed", style="red")

    for c in state.get("cycles", []):
        table.add_row(
            str(c["cycle"]),
            f"{c['satisfied_rate']:.0%}",
            f"{c['avg_composite']:.3f}",
            str(c["sessions_rerun"]),
            str(c.get("improved", 0)),
            str(c.get("regressed", 0)),
        )

    console.print(table)
    console.print(f"\nStatus: [bold]{state.get('status', 'unknown')}[/bold]")
    console.print(f"Started: {state.get('started', '?')}")
    if state.get("completed"):
        console.print(f"Completed: {state['completed']}")
    console.print(f"Total LLM calls: ~{state.get('total_llm_calls', 0)}")


# Session comparison and merging extracted to converge_helpers.py


@app.command()
def data(
    file: Optional[str] = typer.Argument(None, help="Session JSONL file or directory"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
    chart: Optional[str] = typer.Option(None, "--chart", "-c", help="Single chart type"),
) -> None:
    """Export JSON data files for /create-figure visualization."""
    sessions = _load_sessions(file)
    if not sessions:
        console.print("[red]No sessions found.[/red]")
        raise typer.Exit(1)
    diagnosis = build_diagnosis(sessions)
    from chart_data import build_chart_data
    out_dir = Path(output) if output else Path("/tmp/conversation-lab-charts")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = build_chart_data(sessions, diagnosis, out_dir, chart_filter=chart)
    for name, path in written.items():
        console.print(f"[green]{name}[/green] -> {path}")


@app.command(name="promote-nightly")
def promote_nightly(
    file: Optional[str] = typer.Argument(None, help="Session JSONL file or directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count candidates without promoting"),
) -> None:
    """Scan sessions for satisfactory turns and batch-promote QRAs.

    Nightly pipeline:
    1. HARVEST -- Scan session files for "satisfactory" turns with synthesized answers
    2. DEDUPLICATE -- Check if promoted QRA already exists (query hash match)
    3. ENRICH -- /taxonomy extract bridge tags
    4. ASSESS -- Brandon inline assess_qra() on each candidate
    5. PROMOTE -- PASS candidates via QRABridge.upsert_qra()
    """
    sessions = _load_sessions(file)
    if not sessions:
        console.print("[red]No sessions found.[/red]")
        raise typer.Exit(1)

    promote_nightly_command(sessions, dry_run=dry_run)


if __name__ == "__main__":
    app()
