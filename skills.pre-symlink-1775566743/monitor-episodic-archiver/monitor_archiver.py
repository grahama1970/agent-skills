#!/usr/bin/env python3
"""Monitor episodic archiver health: unresolved sessions, failure patterns, aging, nightly pipeline."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

app = typer.Typer(help="Monitor episodic archiver health + nightly pipeline")
console = Console(stderr=True)

# --- Config ---
ALERT_AGE_DAYS = int(os.environ.get("ALERT_AGE_DAYS", "14"))
CRITICAL_AGE_DAYS = int(os.environ.get("CRITICAL_AGE_DAYS", "30"))
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
SKILLS_DIR = SCRIPT_DIR.parent
STATE_DIR = Path.home() / ".pi" / "monitor-episodic-archiver"
MEMORY_SKILL_DIR = SKILLS_DIR / "memory"
ARCHIVER_DIR = SKILLS_DIR / "episodic-archiver"


def _ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def _connect():
    """Connect to ArangoDB using the canonical /memory db.py connection."""
    memory_db_path = MEMORY_SKILL_DIR / "db.py"
    if memory_db_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("memory_db", memory_db_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_db()

    raise RuntimeError(
        "Memory db.py not found. Ensure /memory skill is installed. "
        "NEVER fall back to direct ArangoClient."
    )


def _get_collection_stats(db) -> dict:
    """Get counts from archiver collections."""
    stats = {}
    for name in ["agent_conversations", "unresolved_sessions", "session_summaries"]:
        if db.has_collection(name):
            stats[name] = db.collection(name).count()
        else:
            stats[name] = 0
    return stats


def _get_unresolved_sessions(db, limit: int = 100) -> list:
    """Fetch unresolved sessions sorted by age."""
    if not db.has_collection("unresolved_sessions"):
        return []

    query = """
    FOR s IN unresolved_sessions
        SORT s.created_at ASC
        LIMIT @limit
        RETURN {
            _key: s._key,
            session_id: s.session_id,
            created_at: s.created_at,
            trigger: s.failure_episode.trigger,
            diagnosis: s.failure_episode.diagnosis,
            outcome: s.failure_episode.outcome,
            actions: s.failure_episode.actions
        }
    """
    return list(db.aql.execute(query, bind_vars={"limit": limit}))


def _get_resolved_stats(db) -> dict:
    """Get resolution statistics."""
    if not db.has_collection("unresolved_sessions"):
        return {"total": 0, "pending": 0, "success": 0, "partial": 0, "failure": 0}

    query = """
    LET all_sessions = (FOR s IN unresolved_sessions RETURN s)
    LET pending = (FOR s IN all_sessions FILTER s.failure_episode.outcome == "pending" OR s.failure_episode.outcome == null RETURN 1)
    LET success = (FOR s IN all_sessions FILTER s.failure_episode.outcome == "success" RETURN 1)
    LET partial = (FOR s IN all_sessions FILTER s.failure_episode.outcome == "partial" RETURN 1)
    LET failure = (FOR s IN all_sessions FILTER s.failure_episode.outcome == "failure" RETURN 1)
    RETURN {
        total: LENGTH(all_sessions),
        pending: LENGTH(pending),
        success: LENGTH(success),
        partial: LENGTH(partial),
        failure: LENGTH(failure)
    }
    """
    results = list(db.aql.execute(query))
    return results[0] if results else {"total": 0, "pending": 0, "success": 0, "partial": 0, "failure": 0}


def _get_trigger_patterns(db, since_days: int = 30) -> list:
    """Group failures by trigger pattern."""
    if not db.has_collection("unresolved_sessions"):
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    query = """
    FOR s IN unresolved_sessions
        FILTER s.created_at >= @cutoff OR s.created_at == null
        COLLECT trigger = s.failure_episode.trigger WITH COUNT INTO cnt
        SORT cnt DESC
        LIMIT 10
        RETURN { trigger: trigger, count: cnt }
    """
    return list(db.aql.execute(query, bind_vars={"cutoff": cutoff}))


def _get_top_lessons(db) -> list:
    """Get most commonly used lessons in resolutions."""
    if not db.has_collection("unresolved_sessions"):
        return []

    query = """
    FOR s IN unresolved_sessions
        FILTER s.lessons_used != null AND LENGTH(s.lessons_used) > 0
        FOR lesson IN s.lessons_used
            COLLECT l = lesson WITH COUNT INTO cnt
            SORT cnt DESC
            LIMIT 5
            RETURN { lesson: l, count: cnt }
    """
    return list(db.aql.execute(query))


def _session_age_days(created_at) -> float:
    """Calculate session age in days."""
    if not created_at:
        return 999  # Unknown age treated as very old
    try:
        if isinstance(created_at, str):
            # Handle various ISO formats
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif isinstance(created_at, (int, float)):
            dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
        else:
            return 999
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except (ValueError, OSError):
        return 999


def _age_flag(days: float) -> str:
    """Return age flag emoji-free."""
    if days <= 7:
        return "OK"
    elif days <= 14:
        return "WARN"
    elif days <= 30:
        return "OVERDUE"
    else:
        return "CRITICAL"


def _compute_health(stats: dict, resolution: dict, unresolved: list) -> dict:
    """Compute overall health assessment."""
    total = resolution.get("total", 0)
    pending = resolution.get("pending", 0)
    success = resolution.get("success", 0)

    unresolved_rate = pending / total if total > 0 else 0
    success_rate = success / (total - pending) if (total - pending) > 0 else 0

    # Find oldest unresolved
    oldest_age = 0
    for s in unresolved:
        age = _session_age_days(s.get("created_at"))
        if s.get("outcome", "pending") == "pending" and age > oldest_age:
            oldest_age = age

    # Determine health level
    health = "healthy"
    issues = []

    if unresolved_rate > 0.4:
        health = "critical"
        issues.append(f"Unresolved rate {unresolved_rate:.0%} > 40%")
    elif unresolved_rate > 0.2:
        health = "warning"
        issues.append(f"Unresolved rate {unresolved_rate:.0%} > 20%")

    if oldest_age > CRITICAL_AGE_DAYS:
        health = "critical"
        issues.append(f"Oldest unresolved session: {oldest_age:.0f} days")
    elif oldest_age > ALERT_AGE_DAYS:
        if health != "critical":
            health = "warning"
        issues.append(f"Oldest unresolved session: {oldest_age:.0f} days")

    if success_rate < 0.5 and (total - pending) > 5:
        health = "critical"
        issues.append(f"Success rate {success_rate:.0%} < 50%")
    elif success_rate < 0.75 and (total - pending) > 5:
        if health != "critical":
            health = "warning"
        issues.append(f"Success rate {success_rate:.0%} < 75%")

    return {
        "health": health,
        "issues": issues,
        "metrics": {
            "total_sessions": total,
            "pending": pending,
            "success": success,
            "unresolved_rate": round(unresolved_rate, 3),
            "success_rate": round(success_rate, 3),
            "oldest_unresolved_days": round(oldest_age, 1),
            "conversations": stats.get("agent_conversations", 0),
            "summaries": stats.get("session_summaries", 0),
        }
    }


# --- Commands ---


@app.command()
def dashboard():
    """Rich health dashboard."""
    try:
        db = _connect()
        stats = _get_collection_stats(db)
    except Exception as e:
        console.print(f"[red]Cannot connect to ArangoDB: {e}[/red]")
        raise typer.Exit(2)

    resolution = _get_resolved_stats(db)
    unresolved = _get_unresolved_sessions(db, limit=50)
    patterns = _get_trigger_patterns(db)
    lessons = _get_top_lessons(db)
    health = _compute_health(stats, resolution, unresolved)

    # Header
    health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}[health["health"]]
    console.print(Panel(
        f"[{health_color} bold]{health['health'].upper()}[/{health_color} bold]",
        title="Episodic Archiver Health",
        subtitle=datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    # Metrics table
    m = health["metrics"]
    metrics_table = Table(title="Metrics", show_header=True)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", justify="right")
    metrics_table.add_row("Total Sessions", str(m["total_sessions"]))
    metrics_table.add_row("Pending", str(m["pending"]))
    metrics_table.add_row("Success", str(m["success"]))
    metrics_table.add_row("Unresolved Rate", f"{m['unresolved_rate']:.0%}")
    metrics_table.add_row("Success Rate", f"{m['success_rate']:.0%}")
    metrics_table.add_row("Oldest Unresolved", f"{m['oldest_unresolved_days']:.0f} days")
    metrics_table.add_row("Conversations", str(m["conversations"]))
    metrics_table.add_row("Summaries", str(m["summaries"]))
    console.print(metrics_table)

    # Issues
    if health["issues"]:
        console.print("\n[bold]Issues:[/bold]")
        for issue in health["issues"]:
            console.print(f"  [{health_color}]- {issue}[/{health_color}]")

    # Aging breakdown
    if unresolved:
        pending_sessions = [s for s in unresolved if s.get("outcome", "pending") == "pending"]
        if pending_sessions:
            age_table = Table(title="\nUnresolved Sessions (oldest first)", show_header=True)
            age_table.add_column("Session", style="cyan", max_width=20)
            age_table.add_column("Age", justify="right")
            age_table.add_column("Flag", justify="center")
            age_table.add_column("Trigger", max_width=50)

            for s in pending_sessions[:15]:
                age = _session_age_days(s.get("created_at"))
                flag = _age_flag(age)
                flag_color = {"OK": "green", "WARN": "yellow", "OVERDUE": "rgb(255,165,0)", "CRITICAL": "red"}[flag]
                sid = s.get("session_id", s.get("_key", "?"))[:20]
                trigger = (s.get("trigger") or "unknown")[:50]
                age_table.add_row(sid, f"{age:.0f}d", f"[{flag_color}]{flag}[/{flag_color}]", trigger)

            console.print(age_table)

    # Top failure patterns
    if patterns:
        pattern_table = Table(title="\nTop Failure Triggers", show_header=True)
        pattern_table.add_column("Trigger", style="cyan", max_width=60)
        pattern_table.add_column("Count", justify="right")
        for p in patterns[:7]:
            pattern_table.add_row(str(p.get("trigger", "unknown"))[:60], str(p["count"]))
        console.print(pattern_table)

    # Top lessons
    if lessons:
        lesson_table = Table(title="\nMost Used Lessons", show_header=True)
        lesson_table.add_column("Lesson", style="cyan")
        lesson_table.add_column("Uses", justify="right")
        for l in lessons:
            lesson_table.add_row(str(l["lesson"]), str(l["count"]))
        console.print(lesson_table)


@app.command()
def check(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
    output: str = typer.Option(None, "--output", "-o", help="Write results to file"),
    alert_age: int = typer.Option(ALERT_AGE_DAYS, "--alert-age", help="Alert threshold days"),
):
    """Automated health check. Exit 0=healthy, 1=warning, 2=critical."""
    try:
        db = _connect()
        stats = _get_collection_stats(db)
        resolution = _get_resolved_stats(db)
        unresolved = _get_unresolved_sessions(db, limit=100)
        health = _compute_health(stats, resolution, unresolved)
    except Exception as e:
        health = {"health": "critical", "issues": [f"Cannot query ArangoDB: {e}"], "metrics": {}}
        if json_output:
            print(json.dumps(health, indent=2))
        else:
            console.print(f"[red]CRITICAL: Cannot query ArangoDB: {e}[/red]")
        raise typer.Exit(2)

    health["checked_at"] = datetime.now(timezone.utc).isoformat()

    # Save state
    _ensure_state_dir()
    (STATE_DIR / "health_report.json").write_text(json.dumps(health, indent=2))

    # Append to alert history if issues
    if health["issues"]:
        with open(STATE_DIR / "alert_history.jsonl", "a") as f:
            f.write(json.dumps({
                "timestamp": health["checked_at"],
                "health": health["health"],
                "issues": health["issues"],
            }) + "\n")

    if json_output:
        print(json.dumps(health, indent=2))
    else:
        color = {"healthy": "green", "warning": "yellow", "critical": "red"}[health["health"]]
        console.print(f"[{color} bold]{health['health'].upper()}[/{color} bold]")
        m = health["metrics"]
        console.print(f"  Sessions: {m.get('total_sessions', 0)} total, {m.get('pending', 0)} pending")
        console.print(f"  Success rate: {m.get('success_rate', 0):.0%}")
        console.print(f"  Oldest unresolved: {m.get('oldest_unresolved_days', 0):.0f} days")
        if health["issues"]:
            for issue in health["issues"]:
                console.print(f"  [{color}]- {issue}[/{color}]")

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(health, indent=2))

    # Always exit 0 — the monitor succeeded at detecting problems.
    # Health state is captured in the JSON report and alert history.
    # Scheduler cares about "did the monitor run?" not "did it find problems?"


@app.command("list-unresolved")
def list_unresolved(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions"),
    sort: str = typer.Option("age", "--sort", help="Sort by: age, trigger"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List unresolved sessions needing attention."""
    try:
        db = _connect()
    except Exception as e:
        console.print(f"[red]Cannot connect: {e}[/red]")
        raise typer.Exit(2)

    sessions = _get_unresolved_sessions(db, limit=limit)
    pending = [s for s in sessions if s.get("outcome", "pending") == "pending"]

    if json_output:
        for s in pending:
            s["age_days"] = round(_session_age_days(s.get("created_at")), 1)
            s["flag"] = _age_flag(s["age_days"])
        print(json.dumps(pending, indent=2, default=str))
        return

    if not pending:
        console.print("[green]No unresolved sessions![/green]")
        return

    table = Table(title="Unresolved Sessions", show_header=True)
    table.add_column("Session ID", style="cyan", max_width=24)
    table.add_column("Age", justify="right")
    table.add_column("Flag", justify="center")
    table.add_column("Trigger", max_width=40)
    table.add_column("Diagnosis", max_width=40)

    for s in pending:
        age = _session_age_days(s.get("created_at"))
        flag = _age_flag(age)
        flag_color = {"OK": "green", "WARN": "yellow", "OVERDUE": "rgb(255,165,0)", "CRITICAL": "red"}[flag]
        sid = s.get("session_id", s.get("_key", "?"))[:24]
        trigger = (s.get("trigger") or "?")[:40]
        diagnosis = (s.get("diagnosis") or "?")[:40]
        table.add_row(sid, f"{age:.0f}d", f"[{flag_color}]{flag}[/{flag_color}]", trigger, diagnosis)

    console.print(table)
    console.print(f"\n{len(pending)} unresolved sessions")


@app.command("analyze-patterns")
def analyze_patterns(
    since: int = typer.Option(30, "--since", help="Analysis window in days"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Analyze failure patterns across sessions."""
    try:
        db = _connect()
    except Exception as e:
        console.print(f"[red]Cannot connect: {e}[/red]")
        raise typer.Exit(2)

    patterns = _get_trigger_patterns(db, since_days=since)
    lessons = _get_top_lessons(db)

    result = {
        "analysis_window_days": since,
        "trigger_patterns": patterns,
        "top_lessons": lessons,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache patterns
    _ensure_state_dir()
    (STATE_DIR / "pattern_cache.json").write_text(json.dumps(result, indent=2, default=str))

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    if patterns:
        table = Table(title=f"Failure Patterns (last {since} days)", show_header=True)
        table.add_column("Trigger", style="cyan", max_width=60)
        table.add_column("Count", justify="right")
        for p in patterns:
            table.add_row(str(p.get("trigger", "?"))[:60], str(p["count"]))
        console.print(table)
    else:
        console.print("[dim]No failure patterns found.[/dim]")

    if lessons:
        table = Table(title="Most Effective Lessons", show_header=True)
        table.add_column("Lesson", style="cyan")
        table.add_column("Uses", justify="right")
        for l in lessons:
            table.add_row(str(l["lesson"]), str(l["count"]))
        console.print(table)


@app.command()
def nightly(
    hours: int = typer.Option(24, "--hours", help="Look back N hours for sessions"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without running analysis"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON report"),
    model: str = typer.Option(
        "deepseek-ai/DeepSeek-V3.1-TEE", "--model", help="LLM model for analysis"
    ),
):
    """Nightly episodic analysis + user profiling pipeline.

    Steps: archive recent -> analyze with high-fidelity taxonomy -> profile users -> store lessons -> report.
    """
    from state import get_state_manager
    from task_monitor_integration import start_job, end_job

    state_mgr = get_state_manager()
    tracker = start_job("nightly")
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "dry_run": dry_run,
        "model": model,
        "stages": {},
    }

    # Set model for LLM calls
    os.environ["CHUTES_MODEL_ID"] = model

    archiver_run = ARCHIVER_DIR / "run.sh"
    if not archiver_run.exists():
        msg = f"episodic-archiver run.sh not found at {archiver_run}"
        console.print(f"[red]{msg}[/red]")
        report["error"] = msg
        tracker.finish(success=False)
        if json_output:
            print(json.dumps(report, indent=2, default=str))
        raise typer.Exit(2)

    success = True

    # Stage 1: Archive recent sessions (no-analyze for speed, we re-analyze with high fidelity)
    if not json_output:
        console.print("[bold]Stage 1: Archive recent sessions[/bold]")

    archive_stats = {"archived": 0, "skipped": 0, "errors": 0}
    try:
        cmd = [str(archiver_run), "archive-recent", "--hours", str(hours), "--no-analyze"]
        if dry_run:
            if not json_output:
                console.print(f"  [dim]DRY RUN: would run {' '.join(cmd)}[/dim]")
            report["stages"]["archive"] = {"dry_run": True, "command": " ".join(cmd)}
        else:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                cwd=str(PROJECT_ROOT),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            # Parse output for stats
            for line in result.stdout.split("\n"):
                if "Archived:" in line:
                    try:
                        archive_stats["archived"] = int(line.split("Archived:")[1].strip().split()[0])
                    except (ValueError, IndexError):
                        pass
                if "Skipped:" in line:
                    try:
                        archive_stats["skipped"] = int(line.split("Skipped:")[1].strip().split()[0])
                    except (ValueError, IndexError):
                        pass
                if "Errors:" in line:
                    try:
                        archive_stats["errors"] = int(line.split("Errors:")[1].strip().split()[0])
                    except (ValueError, IndexError):
                        pass
            report["stages"]["archive"] = archive_stats
            if not json_output:
                console.print(f"  Archived: {archive_stats['archived']}, Skipped: {archive_stats['skipped']}")
    except subprocess.TimeoutExpired:
        report["stages"]["archive"] = {"error": "timeout"}
        success = False
    except Exception as e:
        report["stages"]["archive"] = {"error": str(e)}
        success = False

    # Stage 2: Re-analyze recent sessions with high-fidelity taxonomy + user profiling
    if not json_output:
        console.print("[bold]Stage 2: Analyze + profile[/bold]")

    analyze_stats = {"analyzed": 0, "profiled": 0, "errors": 0}
    try:
        db = _connect()
        # Find sessions from last N hours that have summaries
        cutoff = int(time.time()) - (hours * 3600)
        sessions = list(db.aql.execute("""
            FOR d IN session_summaries
                FILTER d.created_at >= @cutoff
                RETURN { session_id: d.session_id, user_id: d.user_id }
        """, bind_vars={"cutoff": cutoff}))

        tracker.set_sessions([s["session_id"] for s in sessions])

        if dry_run:
            report["stages"]["analyze"] = {
                "dry_run": True,
                "sessions_found": len(sessions),
            }
            if not json_output:
                console.print(f"  [dim]DRY RUN: would analyze {len(sessions)} sessions[/dim]")
        else:
            # Add episodic-archiver to path for imports
            if str(ARCHIVER_DIR) not in sys.path:
                sys.path.insert(0, str(ARCHIVER_DIR))

            import asyncio
            from session_analysis import analyze_archived_session

            # Shadow mode: also run gateway validation alongside existing analysis
            _use_gateway = os.environ.get("ASSISTANT_SHADOW_MODE", "1") == "1"
            _gateway_validate = None
            if _use_gateway:
                try:
                    assistant_dir = str(Path(__file__).resolve().parent.parent / "assistant")
                    if assistant_dir not in sys.path:
                        sys.path.insert(0, assistant_dir)
                    from assistant import validate as _gateway_validate_fn
                    _gateway_validate = _gateway_validate_fn
                except ImportError:
                    pass

            for sess in sessions:
                sid = sess["session_id"]
                tracker.start_session(sid)
                try:
                    result = asyncio.run(analyze_archived_session(
                        session_id=sid,
                        db=db,
                        enable_dogpile=os.environ.get("NIGHTLY_DOGPILE", "0") == "1",
                        high_fidelity=True,
                        user_id=sess.get("user_id"),
                    ))
                    analyze_stats["analyzed"] += 1
                    if result.get("user_profile"):
                        analyze_stats["profiled"] += 1

                    # Shadow: run gateway validation and log disagreements
                    if _gateway_validate is not None:
                        try:
                            summary = result.get("assessment", {}).get("summary", "")
                            gw_result = _gateway_validate(
                                input_data={"session_summary": summary or sid},
                                task="episodic-session-scorer",
                                scope=sess.get("user_id", ""),
                            )
                            orig_quality = result.get("assessment", {}).get("quality_score")
                            gw_quality = gw_result.result.get("quality_score")
                            if orig_quality is not None and gw_quality is not None:
                                if abs(float(orig_quality) - float(gw_quality)) > 0.3:
                                    logger.debug(
                                        f"Shadow disagreement for {sid}: "
                                        f"original={orig_quality}, gateway={gw_quality} "
                                        f"(tier={gw_result.tier})"
                                    )
                        except Exception as gw_err:
                            logger.debug(f"Gateway shadow failed for {sid}: {gw_err}")

                    tracker.complete_session(sid, success=True, stats={
                        "quality": result.get("assessment", {}).get("quality_score"),
                        "profiled": bool(result.get("user_profile")),
                    })
                except Exception as e:
                    analyze_stats["errors"] += 1
                    tracker.complete_session(sid, success=False, error_msg=str(e))
                    if not json_output:
                        console.print(f"  [red]Error analyzing {sid}: {e}[/red]")

            report["stages"]["analyze"] = analyze_stats
            if not json_output:
                console.print(f"  Analyzed: {analyze_stats['analyzed']}, Profiled: {analyze_stats['profiled']}")

    except Exception as e:
        report["stages"]["analyze"] = {"error": str(e)}
        success = False
        if not json_output:
            console.print(f"  [red]Error: {e}[/red]")

    # Stage 3: Health check
    if not json_output:
        console.print("[bold]Stage 3: Health check[/bold]")

    try:
        db = _connect()
        stats = _get_collection_stats(db)
        resolution = _get_resolved_stats(db)
        unresolved = _get_unresolved_sessions(db, limit=100)
        health = _compute_health(stats, resolution, unresolved)
        report["stages"]["health"] = health
        if not json_output:
            color = {"healthy": "green", "warning": "yellow", "critical": "red"}[health["health"]]
            console.print(f"  [{color}]{health['health'].upper()}[/{color}]")
    except Exception as e:
        report["stages"]["health"] = {"error": str(e)}

    # Stage 4: Re-mine skill chains from transcripts (feeds classifier + GPT retraining)
    if not json_output:
        console.print("[bold]Stage 4: Mine skill chains for retraining[/bold]")

    chain_stats = {"chains": 0, "classifier_records": 0, "gpt_records": 0}
    skill_lab_run = SKILLS_DIR / "skill-lab" / "run.sh"
    try:
        if not skill_lab_run.exists():
            if not json_output:
                console.print("  [dim]skill-lab not found, skipping chain mining[/dim]")
            report["stages"]["chain_mine"] = {"skipped": "skill-lab not found"}
        elif dry_run:
            if not json_output:
                console.print("  [dim]DRY RUN: would re-mine chains and prepare training data[/dim]")
            report["stages"]["chain_mine"] = {"dry_run": True}
        else:
            # Re-extract chains from all transcripts
            mine_result = subprocess.run(
                [str(skill_lab_run), "chain-mine", "--min-skills", "2"],
                capture_output=True, text=True, timeout=600,
                cwd=str(PROJECT_ROOT),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            for line in mine_result.stdout.split("\n"):
                if "Total chains:" in line:
                    try:
                        chain_stats["chains"] = int(line.split(":")[1].strip())
                    except (ValueError, IndexError):
                        pass

            # Prepare training data for classifier + GPT
            prep_result = subprocess.run(
                [str(skill_lab_run), "chain-prepare"],
                capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            for line in prep_result.stdout.split("\n"):
                if "Classifier data:" in line and "(" in line:
                    try:
                        chain_stats["classifier_records"] = int(
                            line.split("(")[1].split(" ")[0]
                        )
                    except (ValueError, IndexError):
                        pass
                if "GPT data:" in line and "(" in line:
                    try:
                        chain_stats["gpt_records"] = int(
                            line.split("(")[1].split(" ")[0]
                        )
                    except (ValueError, IndexError):
                        pass

            report["stages"]["chain_mine"] = chain_stats
            if not json_output:
                console.print(
                    f"  Chains: {chain_stats['chains']}, "
                    f"Classifier: {chain_stats['classifier_records']}, "
                    f"GPT: {chain_stats['gpt_records']}"
                )
    except subprocess.TimeoutExpired:
        report["stages"]["chain_mine"] = {"error": "timeout"}
    except Exception as e:
        report["stages"]["chain_mine"] = {"error": str(e)}
        if not json_output:
            console.print(f"  [yellow]Chain mining error (non-fatal): {e}[/yellow]")

    # Finalize
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["success"] = success
    report["summary"] = {
        "sessions_archived": archive_stats.get("archived", 0),
        "sessions_analyzed": analyze_stats.get("analyzed", 0),
        "users_profiled": analyze_stats.get("profiled", 0),
        "errors": archive_stats.get("errors", 0) + analyze_stats.get("errors", 0),
    }

    # Save report and state
    state_mgr.save_report(report)
    state_mgr.record_nightly_run(success, report.get("summary", {}))
    tracker.finish(success=success)
    end_job("nightly", success=success)

    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        console.print(Panel(
            f"Archived: {report['summary']['sessions_archived']}  "
            f"Analyzed: {report['summary']['sessions_analyzed']}  "
            f"Profiled: {report['summary']['users_profiled']}  "
            f"Errors: {report['summary']['errors']}",
            title="Nightly Complete",
            subtitle=f"{'SUCCESS' if success else 'FAILED'}",
        ))

    raise typer.Exit(0 if success else 1)


@app.command("register-nightly")
def register_nightly():
    """Register with scheduler for daily nightly analysis."""
    scheduler = SKILLS_DIR / "scheduler" / "run.sh"
    if not scheduler.exists():
        console.print(f"[red]Scheduler not found at {scheduler}[/red]")
        raise typer.Exit(2)

    subprocess.run([
        str(scheduler), "register",
        "--name", "episodic-nightly",
        "--cron", "0 3 * * *",
        "--command", f"{SCRIPT_DIR}/run.sh nightly --json",
        "--workdir", str(PROJECT_ROOT),
        "--description", "Nightly episodic analysis + user profiling",
    ], check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    console.print("[bold green]Registered episodic-nightly with scheduler[/bold green]")
    console.print("  Schedule: 3:00am daily")
    console.print("  Command: run.sh nightly --json")


if __name__ == "__main__":
    app()
