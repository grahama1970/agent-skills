"""Deterministic timeout estimation for scheduled skill jobs.

Two modes:
  1. RECORD: After a skill runs, store its actual duration to /memory.
  2. ESTIMATE: Before scheduling, compute timeout from historical p95 durations
     stored in /memory — falling back to static benchmarks when no history exists.

Every skill should call `record()` after completing, and `estimate()` before
registering with the scheduler. This creates a flywheel: more runs → better
estimates → fewer timeouts.

Usage from Python:
    from estimate_timeout import record, estimate_skill, estimate_monitor_codebase

    # After a skill finishes:
    record("security-scan", duration_seconds=142.5, units=1)

    # Before scheduling:
    timeout = estimate_skill("monitor-codebase", units=28)

Usage from shell:
    # Record:
    python3 .../common/estimate_timeout.py record --skill security-scan --duration 142.5

    # Estimate:
    timeout=$(python3 .../common/estimate_timeout.py estimate --skill monitor-codebase --units 28)

    # Estimate monitor-codebase specifically:
    timeout=$(python3 .../common/estimate_timeout.py estimate --full 20 --light 8)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

MEMORY_SOCK = "/run/user/1000/embry/memory.sock"
COLLECTION = "skill_durations"
SCOPE = "skill_durations"

# ── Static benchmarks (cold-start fallback, seconds) ─────────────────────────
# Source: manual p95 benchmarks 2026-03-31.
# Used ONLY when /memory has < 3 data points for a skill.

STATIC_BUDGETS: dict[str, float] = {
    # monitor-codebase per-project steps
    "project-state": 30,
    "cleanup": 60,
    "quality-checks": 5,
    "security-scan": 180,
    "duplication": 5,
    "dep-graph": 5,
    "coverage": 5,
    "ingest-code": 60,
    "skills-ci": 120,
    "dogpile": 60,
    "aggregate": 5,
    "light-scan": 30,
    # skills-ci-nightly phases (flat)
    "safety-commit": 30,
    "autofix": 120,
    "scan": 120,
    "orchestrate": 3600,
    "git-sync": 30,
    "report": 15,
    # individual skills (total runtime)
    "monitor-codebase": 600,
    # code-runner per-backend (claude is slower, codex/text are faster)
    "code-runner-claude": 600,
    "code-runner-codex": 180,
    "code-runner-text": 180,
    "code-runner-gemini": 240,
    "code-runner-deepseek": 180,
    "code-runner-test": 60,
    "skills-ci-nightly": 3900,
    "monitor-skill-health": 120,
    "episodic-archiver": 300,
    "mine-transcripts": 300,
    "recommend-skill-chain": 180,
    "monitor-workstation": 60,
    "monitor-memory": 120,
    "ops-arango": 60,
    "consume-feed": 120,
    "monitor-pi": 10,
    "monitor-claude": 10,
    "learn-datalake": 60,
    "code-runner": 180,
}

# ── Composite profiles ───────────────────────────────────────────────────────

PROFILES: dict[str, dict] = {
    "monitor-codebase-full": {
        "per_unit_steps": [
            "project-state", "cleanup", "quality-checks", "security-scan",
            "duplication", "dep-graph", "coverage", "ingest-code",
            "skills-ci", "dogpile", "aggregate",
        ],
        "flat_steps": [],
        "overhead": 120,
    },
    "monitor-codebase-light": {
        "per_unit_steps": ["light-scan"],
        "flat_steps": [],
        "overhead": 30,
    },
    "skills-ci-nightly": {
        "per_unit_steps": [],
        "flat_steps": [
            "safety-commit", "autofix", "scan", "orchestrate",
            "git-sync", "report",
        ],
        "overhead": 60,
    },
}

DEFAULT_BUFFER = 1.2
MIN_HISTORY = 3  # need this many data points before trusting history over static


# ── Memory client ────────────────────────────────────────────────────────────

def _memory_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCK)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0)


def _recall_durations(skill: str, limit: int = 30) -> list[dict]:
    """Recall historical durations for a skill from /memory."""
    try:
        with _memory_client() as client:
            resp = client.post("/recall", json={
                "q": f"skill_duration:{skill}",
                "scope": SCOPE,
                "k": limit,
                "tags": [f"skill:{skill}", "duration"],
            })
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            # Memory daemon returns {"items": [...], "found": bool}
            return data.get("items", data.get("results", data.get("documents", [])))
    except Exception:
        return []


def _parse_duration_from_result(result: dict) -> float | None:
    """Extract duration_seconds from a /memory recall result."""
    solution = result.get("solution", result.get("doc", ""))
    if isinstance(solution, str):
        try:
            solution = json.loads(solution)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(solution, dict):
        val = solution.get("duration_seconds")
        if val is not None:
            return float(val)
    return None


# ── Record ───────────────────────────────────────────────────────────────────

def record(
    skill: str,
    duration_seconds: float,
    units: int = 1,
    outcome: str = "success",
    trigger: str | None = None,
    composed_skills: list[str] | None = None,
    command: str | None = None,
    step_durations: dict[str, float] | None = None,
    metadata: dict | None = None,
) -> bool:
    """Store a skill execution trace to /memory for estimation and analysis.

    Args:
        skill: Skill name (e.g. "security-scan", "monitor-codebase").
        duration_seconds: Total wall-clock time in seconds.
        units: Number of work items processed (projects, files, etc.).
        outcome: "success", "timeout", "failed".
        trigger: What initiated this run ("scheduler", "user", "orchestrate", etc.).
        composed_skills: Other skills called during execution.
        command: The command/args that were run (e.g. "scan --all --force").
        step_durations: Per-step timing breakdown (e.g. {"security-scan": 142.5}).
        metadata: Extra context (project name, error messages, etc.).

    Returns:
        True if stored successfully.
    """
    solution = {
        "skill": skill,
        "duration_seconds": round(duration_seconds, 2),
        "units": units,
        "per_unit_seconds": round(duration_seconds / max(units, 1), 2),
        "outcome": outcome,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if trigger:
        solution["trigger"] = trigger
    if composed_skills:
        solution["composed_skills"] = composed_skills
    if command:
        solution["command"] = command
    if step_durations:
        solution["step_durations"] = {k: round(v, 2) for k, v in step_durations.items()}
    if metadata:
        solution["metadata"] = metadata

    tags = [f"skill:{skill}", "duration", f"outcome:{outcome}"]
    if trigger:
        tags.append(f"trigger:{trigger}")
    if composed_skills:
        for cs in composed_skills:
            tags.append(f"composed:{cs}")

    run_id = f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}_{skill}"
    payload = {
        "problem": f"skill_duration:{skill} run={run_id} dur={round(duration_seconds, 1)}s outcome={outcome}",
        "solution": json.dumps(solution, sort_keys=True),
        "scope": SCOPE,
        "tags": tags,
    }

    try:
        with _memory_client() as client:
            resp = client.post("/learn", json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        print(f"estimate_timeout: failed to record duration for {skill}: {exc}",
              file=sys.stderr)
        return False


@contextmanager
def timed(
    skill: str,
    units: int = 1,
    trigger: str | None = None,
    composed_skills: list[str] | None = None,
    command: str | None = None,
    metadata: dict | None = None,
):
    """Context manager that records the duration of a block.

    Usage:
        with timed("security-scan", units=1, trigger="scheduler"):
            run_security_scan()

        with timed("monitor-codebase", units=28, trigger="scheduler",
                   composed_skills=["project-state", "security-scan", "skills-ci"],
                   command="scan --all"):
            run_nightly_scan()
    """
    start = time.monotonic()
    outcome = "success"
    try:
        yield
    except Exception:
        outcome = "failed"
        raise
    finally:
        elapsed = time.monotonic() - start
        record(skill, elapsed, units=units, outcome=outcome, trigger=trigger,
               composed_skills=composed_skills, command=command, metadata=metadata)


# ── Estimate ─────────────────────────────────────────────────────────────────

def _p95(values: list[float]) -> float:
    """Compute the 95th percentile of a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = math.ceil(0.95 * len(sorted_vals)) - 1
    return sorted_vals[max(idx, 0)]


def _historical_budget(skill: str) -> float | None:
    """Get p95 per-unit duration from /memory history.

    Returns None if insufficient history (< MIN_HISTORY data points).
    """
    results = _recall_durations(skill)
    durations = []
    per_unit_durations = []

    for r in results:
        solution = r.get("solution", r.get("doc", ""))
        if isinstance(solution, str):
            try:
                solution = json.loads(solution)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(solution, dict):
            continue
        # Skip timeout/failed runs — they don't represent real completion time
        if solution.get("outcome") not in ("success", None):
            continue
        d = solution.get("duration_seconds")
        pu = solution.get("per_unit_seconds")
        if d is not None:
            durations.append(float(d))
        if pu is not None:
            per_unit_durations.append(float(pu))

    if len(durations) < MIN_HISTORY:
        return None

    # Prefer per_unit if available, else total duration
    if per_unit_durations and len(per_unit_durations) >= MIN_HISTORY:
        return _p95(per_unit_durations)
    return _p95(durations)


def get_budget(skill: str) -> float:
    """Get the best available budget for a skill: historical p95, or static fallback.

    Uses max(historical, static) so the static budget acts as a floor —
    prevents fast-task P95 from setting timeouts too low for complex tasks.
    """
    static = STATIC_BUDGETS.get(skill, 300)  # 5min default for unknown skills
    historical = _historical_budget(skill)
    if historical is not None:
        return max(historical, static)
    return static


def estimate_skill(skill: str, units: int = 1, buffer: float = DEFAULT_BUFFER) -> int:
    """Estimate timeout for a single skill run.

    Checks /memory for historical p95, falls back to static budget.
    """
    budget = get_budget(skill)
    return math.ceil(budget * units * buffer)


def estimate(
    *,
    profile: str | None = None,
    steps: list[str] | None = None,
    units: int = 1,
    overhead: int = 0,
    buffer: float = DEFAULT_BUFFER,
) -> int:
    """Calculate timeout from profile or explicit steps.

    Each step's budget is looked up from /memory history first,
    falling back to STATIC_BUDGETS.
    """
    total = overhead

    if profile and profile in PROFILES:
        p = PROFILES[profile]
        for step in p.get("per_unit_steps", []):
            total += get_budget(step) * units
        for step in p.get("flat_steps", []):
            total += get_budget(step)
        total += p.get("overhead", 0)
    elif steps:
        for step in steps:
            total += get_budget(step) * units
    else:
        return math.ceil(total * buffer)

    return math.ceil(total * buffer)


def estimate_monitor_codebase(
    full_count: int,
    light_count: int,
    buffer: float = DEFAULT_BUFFER,
) -> int:
    """Estimate timeout for monitor-codebase scan --all."""
    full_budget = estimate(profile="monitor-codebase-full", units=full_count, buffer=1.0)
    light_budget = estimate(profile="monitor-codebase-light", units=light_count, buffer=1.0)
    return math.ceil((full_budget + light_budget) * buffer)


def estimate_nightly(buffer: float = DEFAULT_BUFFER) -> int:
    """Estimate timeout for skills-ci-nightly."""
    return estimate(profile="skills-ci-nightly", buffer=buffer)


def format_duration(seconds: int) -> str:
    """Human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining = seconds % 60
    if minutes < 60:
        return f"{minutes}m{remaining}s" if remaining else f"{minutes}m"
    hours = minutes // 60
    remaining_min = minutes % 60
    return f"{hours}h{remaining_min}m"


# ── CLI ──────────────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Record skill durations and estimate scheduler timeouts"
    )
    sub = parser.add_subparsers(dest="command")

    # record subcommand
    rec = sub.add_parser("record", help="Record a skill execution trace")
    rec.add_argument("--skill", required=True, help="Skill name")
    rec.add_argument("--duration", type=float, required=True, help="Duration in seconds")
    rec.add_argument("--units", type=int, default=1, help="Work items processed")
    rec.add_argument("--outcome", default="success",
                     choices=["success", "timeout", "failed"])
    rec.add_argument("--trigger", help="What initiated this (scheduler, user, orchestrate)")
    rec.add_argument("--cmd", dest="run_command", help="The command/args that were run")
    rec.add_argument("--composed", nargs="*", help="Skills composed during execution")

    # estimate subcommand
    est = sub.add_parser("estimate", help="Estimate timeout for a skill or profile")
    est.add_argument("--skill", help="Single skill name")
    est.add_argument("--profile", choices=list(PROFILES.keys()),
                     help="Composite profile")
    est.add_argument("--steps", help="Comma-separated step names")
    est.add_argument("--units", type=int, default=1, help="Number of work items")
    est.add_argument("--full", type=int, default=0,
                     help="Full-scan projects (monitor-codebase)")
    est.add_argument("--light", type=int, default=0,
                     help="Light-scan projects (monitor-codebase)")
    est.add_argument("--buffer", type=float, default=DEFAULT_BUFFER,
                     help="Safety margin multiplier (default 1.2)")
    est.add_argument("--json", action="store_true", help="Output as JSON")

    # history subcommand
    hist = sub.add_parser("history", help="Show recorded durations for a skill")
    hist.add_argument("--skill", required=True, help="Skill name")
    hist.add_argument("--limit", type=int, default=10, help="Max results")

    # list subcommand
    sub.add_parser("list", help="List all known skills and their budgets")

    args = parser.parse_args()

    if args.command == "record":
        ok = record(
            args.skill, args.duration,
            units=args.units, outcome=args.outcome,
            trigger=args.trigger, command=args.run_command,
            composed_skills=args.composed,
        )
        print("OK" if ok else "FAILED")

    elif args.command == "estimate":
        if args.full or args.light:
            timeout = estimate_monitor_codebase(args.full, args.light, args.buffer)
        elif args.skill:
            timeout = estimate_skill(args.skill, units=args.units, buffer=args.buffer)
        elif args.profile:
            timeout = estimate(profile=args.profile, units=args.units, buffer=args.buffer)
        elif args.steps:
            step_list = [s.strip() for s in args.steps.split(",")]
            timeout = estimate(steps=step_list, units=args.units, buffer=args.buffer)
        else:
            est.print_help()
            return

        if args.json:
            result = {
                "timeout_seconds": timeout,
                "timeout_human": format_duration(timeout),
                "buffer": args.buffer,
                "source": "historical+static",
            }
            if args.skill:
                budget = get_budget(args.skill)
                hist_budget = _historical_budget(args.skill)
                result["per_unit_budget"] = budget
                result["source"] = "historical" if hist_budget is not None else "static"
            print(json.dumps(result))
        else:
            print(timeout)

    elif args.command == "history":
        results = _recall_durations(args.skill, limit=args.limit)
        if not results:
            print(f"No recorded durations for {args.skill}")
            return
        print(f"{'Date':20s}  {'Duration':>10s}  {'Per Unit':>10s}  {'Units':>6s}  {'Outcome'}")
        for r in results:
            sol = r.get("solution", r.get("doc", ""))
            if isinstance(sol, str):
                try:
                    sol = json.loads(sol)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(sol, dict):
                continue
            ts = str(sol.get("timestamp", "?"))[:19]
            dur = sol.get("duration_seconds", "?")
            pu = sol.get("per_unit_seconds", "?")
            units = sol.get("units", "?")
            outcome = str(sol.get("outcome", "?"))
            print(f"{ts:20s}  {str(dur):>10s}s  {str(pu):>10s}s  {str(units):>6s}  {outcome}")

        hist = _historical_budget(args.skill)
        static = STATIC_BUDGETS.get(args.skill)
        print(f"\nHistorical p95: {hist:.1f}s" if hist else "\nHistorical p95: insufficient data")
        if static:
            print(f"Static fallback: {static}s")

    elif args.command == "list":
        print(f"{'Skill':25s}  {'Historical':>12s}  {'Static':>8s}  {'Active':>8s}")
        print("-" * 60)
        all_skills = sorted(set(list(STATIC_BUDGETS.keys())))
        for skill in all_skills:
            hist = _historical_budget(skill)
            static = STATIC_BUDGETS.get(skill)
            active = hist if hist is not None else static
            hist_str = f"{hist:.1f}s" if hist is not None else "-"
            static_str = f"{static}s" if static is not None else "-"
            active_str = f"{active:.1f}s" if active is not None else "300s"
            source = "hist" if hist is not None else "static"
            print(f"{skill:25s}  {hist_str:>12s}  {static_str:>8s}  {active_str:>8s}  ({source})")
    else:
        parser.print_help()


if __name__ == "__main__":
    _main()
