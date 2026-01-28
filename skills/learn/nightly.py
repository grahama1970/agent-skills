#!/usr/bin/env python3
"""
Nightly Learning Cycle for Persona Agents

Automated reflection → research → learning → transcript archiving loop.
Run via cron or scheduler.

Usage:
    ./nightly.py --scope horus_lore --max-gaps 5
    ./nightly.py --scope horus_lore --dry-run
    ./nightly.py collect-transcripts  # Archive new transcripts from all agents
"""

import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "rich", "-q"])
    import typer
    from rich.console import Console
    from rich.table import Table

console = Console()
app = typer.Typer(help="Nightly learning and transcript collection for persona agents")
SKILL_DIR = Path(__file__).resolve().parent
LOG_DIR = Path.home() / ".learn" / "nightly-logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Transcript locations for various coding agents
TRANSCRIPT_SOURCES = {
    "claude_code": {
        "base": Path.home() / ".claude" / "projects",
        "pattern": "**/*.jsonl",
        "format": "jsonl",
    },
    "codex": {
        "base": Path.home() / ".codex" / "sessions",
        "pattern": "**/*.jsonl",
        "format": "jsonl",
    },
    "pi": {
        "base": Path.home() / ".pi" / "sessions",
        "pattern": "**/*.json*",
        "format": "json",
    },
    "kilocode": {
        "base": Path.home() / ".kilocode" / "cli",
        "pattern": "history.json",
        "format": "json",
    },
}

# Track which transcripts have been processed
PROCESSED_FILE = LOG_DIR / "processed_transcripts.json"


def log_cycle(scope: str, data: dict):
    """Log the nightly cycle results."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{scope}_{timestamp}.json"
    log_file.write_text(json.dumps(data, indent=2, default=str))
    console.print(f"[dim]Logged to {log_file}[/dim]")


def load_processed() -> dict:
    """Load set of already-processed transcript files."""
    if PROCESSED_FILE.exists():
        return json.loads(PROCESSED_FILE.read_text())
    return {"files": {}, "last_run": None}


def save_processed(data: dict):
    """Save processed transcript tracking."""
    data["last_run"] = datetime.now(timezone.utc).isoformat()
    PROCESSED_FILE.write_text(json.dumps(data, indent=2))


def find_new_transcripts(since_hours: int = 24) -> List[Dict]:
    """Find transcripts modified in the last N hours that haven't been processed."""
    processed = load_processed()
    processed_files = processed.get("files", {})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    new_transcripts = []

    for agent, config in TRANSCRIPT_SOURCES.items():
        base = config["base"]
        if not base.exists():
            continue

        pattern = str(base / config["pattern"])
        for filepath in glob.glob(pattern, recursive=True):
            path = Path(filepath)
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

            # Skip if older than cutoff or already processed with same mtime
            if mtime < cutoff:
                continue

            file_key = str(path)
            if file_key in processed_files:
                if processed_files[file_key] == mtime.isoformat():
                    continue  # Already processed at this mtime

            new_transcripts.append({
                "agent": agent,
                "path": str(path),
                "mtime": mtime.isoformat(),
                "format": config["format"],
                "size_kb": path.stat().st_size / 1024,
            })

    return sorted(new_transcripts, key=lambda x: x["mtime"], reverse=True)


def convert_to_episode_format(transcript_path: str, agent: str, fmt: str) -> Optional[Path]:
    """Convert agent transcript to episodic-archiver format."""
    path = Path(transcript_path)

    try:
        if fmt == "jsonl":
            # Claude Code / Codex format - JSONL with messages
            messages = []
            with open(path, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            # Extract message content based on entry type
                            if entry.get("type") == "user":
                                messages.append({
                                    "from": "User",
                                    "content": entry.get("message", {}).get("content", ""),
                                    "timestamp": entry.get("timestamp"),
                                })
                            elif entry.get("type") == "assistant":
                                content = entry.get("message", {}).get("content", "")
                                if isinstance(content, list):
                                    content = " ".join(
                                        c.get("text", "") for c in content if c.get("type") == "text"
                                    )
                                messages.append({
                                    "from": "Agent",
                                    "content": content,
                                    "timestamp": entry.get("timestamp"),
                                })
                            elif entry.get("type") == "summary":
                                # Session summary
                                messages.append({
                                    "from": "System",
                                    "content": f"Session summary: {entry.get('summary', '')}",
                                    "timestamp": None,
                                    "type": "meta",
                                })
                        except json.JSONDecodeError:
                            continue

            if not messages:
                return None

        elif fmt == "json":
            # KiloCode / Pi format - JSON with entries or messages
            data = json.loads(path.read_text())
            messages = []

            if "entries" in data:  # KiloCode history format
                for entry in data.get("entries", []):
                    messages.append({
                        "from": "User",
                        "content": entry.get("prompt", ""),
                        "timestamp": entry.get("timestamp"),
                    })
            elif "messages" in data:  # Standard message format
                messages = data["messages"]
            else:
                # Try to interpret as conversation
                messages = data if isinstance(data, list) else []
        else:
            return None

        if not messages:
            return None

        # Create episode file
        session_id = f"{agent}_{path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        episode = {
            "session_id": session_id,
            "source_agent": agent,
            "source_file": str(path),
            "messages": messages,
        }

        temp_file = Path("/tmp") / f"episode_{session_id}.json"
        temp_file.write_text(json.dumps(episode, indent=2, default=str))
        return temp_file

    except Exception as e:
        console.print(f"[red]Error converting {path}: {e}[/red]")
        return None


def archive_transcript(transcript: Dict) -> Dict:
    """Archive a single transcript via episodic-archiver."""
    episode_file = convert_to_episode_format(
        transcript["path"],
        transcript["agent"],
        transcript["format"]
    )

    if not episode_file:
        return {"success": False, "error": "Failed to convert transcript"}

    archiver_dir = find_skill("episodic-archiver")
    if not archiver_dir:
        return {"success": False, "error": "episodic-archiver skill not found"}

    success, output = run_skill(archiver_dir, ["archive", str(episode_file)], timeout=120)

    # Cleanup temp file
    try:
        episode_file.unlink()
    except (OSError, IOError, PermissionError):
        pass

    return {
        "success": success,
        "output": output[:500] if success else output[:200],
    }


def run_skill(skill_dir: Path, args: List[str], timeout: int = 300) -> tuple:
    """Run a skill and return (success, output)."""
    run_script = skill_dir / "run.sh"
    if not run_script.exists():
        return False, f"Skill not found: {skill_dir}"

    try:
        result = subprocess.run(
            [str(run_script)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(skill_dir),
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def find_skill(name: str) -> Path:
    """Find a skill by name."""
    candidates = [
        SKILL_DIR.parent / name,
        Path.home() / ".claude" / "skills" / name,
        Path.home() / ".pi" / "skills" / name,
    ]
    for p in candidates:
        if p.exists() and (p / "run.sh").exists():
            return p
    return None


def get_knowledge_gaps(scope: str) -> List[Dict]:
    """Get knowledge gaps via /learn --from-gaps."""
    # Import the function directly to avoid subprocess overhead
    sys.path.insert(0, str(SKILL_DIR))
    from learn import find_knowledge_gaps
    return find_knowledge_gaps()


def prospective_reflection(gaps: List[Dict]) -> Dict[str, Any]:
    """
    Analyze gaps for patterns: what topics/skills repeatedly fail?

    Returns:
        {
            "recurring_topics": [{"topic": str, "count": int, "examples": list}],
            "failing_skills": [{"skill": str, "count": int}],
            "priority_queries": [str],  # Suggested research queries
        }
    """
    from collections import Counter

    # Count skill failures
    skill_failures = Counter()
    topic_words = Counter()
    examples_by_topic = {}

    for gap in gaps:
        gap_type = gap.get("type", "")
        content = gap.get("content", "")

        # Track skill failures
        if gap_type == "skill_failure":
            skill = gap.get("skill", "unknown")
            skill_failures[skill] += 1

        # Extract topic words (simple: split and count)
        words = content.lower().split()
        # Filter noise words
        noise = {"the", "a", "an", "is", "are", "was", "were", "to", "from", "in", "on", "for", "with", "error", "failed"}
        meaningful = [w for w in words if len(w) > 3 and w not in noise]
        for word in meaningful[:5]:  # First 5 meaningful words per gap
            topic_words[word] += 1
            if word not in examples_by_topic:
                examples_by_topic[word] = []
            if len(examples_by_topic[word]) < 3:
                examples_by_topic[word].append(content[:100])

    # Build recurring topics (appeared 2+ times)
    recurring = [
        {"topic": topic, "count": count, "examples": examples_by_topic.get(topic, [])}
        for topic, count in topic_words.most_common(10)
        if count >= 2
    ]

    # Build failing skills list
    failing = [
        {"skill": skill, "count": count}
        for skill, count in skill_failures.most_common(5)
    ]

    # Generate priority queries from recurring topics
    priority_queries = []
    for item in recurring[:3]:
        topic = item["topic"]
        priority_queries.append(f"how to fix {topic} errors in AI agents")
    for item in failing[:2]:
        skill = item["skill"]
        priority_queries.append(f"best practices for {skill} skill implementation")

    return {
        "recurring_topics": recurring,
        "failing_skills": failing,
        "priority_queries": priority_queries,
    }


def check_memory_first(query: str, scope: str) -> Optional[Dict]:
    """
    Check /memory before researching to avoid repeat work.

    Returns None if no prior knowledge, or the memory result if found.
    """
    memory_skill = find_skill("memory")
    if not memory_skill:
        return None

    success, output = run_skill(memory_skill, ["recall", "--q", query], timeout=30)

    if not success:
        return None

    try:
        # Parse JSON output from memory
        start = output.find("{")
        end = output.rfind("}")
        if start != -1 and end != -1:
            result = json.loads(output[start:end+1])
            if result.get("found"):
                return result
    except (json.JSONDecodeError, ValueError):
        pass

    return None


def research_gap(gap: Dict, scope: str) -> Dict:
    """Research a knowledge gap via /dogpile, checking /memory first."""
    content = gap.get("content", "")[:200]
    gap_type = gap.get("type", "unknown")

    # Build search query from gap
    if gap_type == "skill_failure":
        skill = gap.get("skill", "")
        query = f"how to fix {skill} {content[:100]}"
    elif gap_type == "unresolved_session":
        query = f"solve {content[:150]}"
    elif gap_type == "error":
        query = f"fix error {content[:150]}"
    else:
        query = content[:200]

    console.print(f"[cyan]Researching:[/cyan] {query[:60]}...")

    # MEMORY FIRST: Check if we already have knowledge about this
    memory_result = check_memory_first(query, scope)
    if memory_result:
        console.print(f"[green]Found in memory![/green] Skipping research.")
        items = memory_result.get("items", [])
        if items:
            solution = items[0].get("solution", "")
            return {
                "query": query,
                "success": True,
                "output": f"From memory: {solution}",
                "source": "memory",
            }

    # Not in memory - research via dogpile
    dogpile_dir = find_skill("dogpile")
    if not dogpile_dir:
        return {"success": False, "error": "dogpile skill not found"}

    success, output = run_skill(dogpile_dir, ["search", query], timeout=180)

    return {
        "query": query,
        "success": success,
        "output": output[:2000] if success else output[:500],
        "source": "dogpile",
    }


def learn_from_research(research: Dict, scope: str, context: str) -> Dict:
    """Learn from research results."""
    if not research.get("success"):
        return {"success": False, "error": "Research failed"}

    output = research.get("output", "")
    if len(output) < 100:
        return {"success": False, "error": "Research output too short"}

    # Save research to temp file and distill
    temp_file = Path("/tmp/nightly_research.txt")
    temp_file.write_text(output)

    distill_dir = find_skill("distill")
    if not distill_dir:
        return {"success": False, "error": "distill skill not found"}

    success, result = run_skill(distill_dir, [
        "--file", str(temp_file),
        "--scope", scope,
        "--context", context,
    ])

    return {
        "success": success,
        "output": result[:500],
    }


@app.command()
def learn(
    scope: str = typer.Option(..., "--scope", "-s", help="Memory scope for learning"),
    max_gaps: int = typer.Option(5, "--max-gaps", "-m", help="Max gaps to process"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show plan without executing"),
    context: str = typer.Option("nightly reflection", "--context", "-c", help="Learning context"),
):
    """
    Nightly Learning Cycle.

    1. Reflect on past gaps (errors, failures, questions)
    2. Research each gap via /dogpile
    3. Learn from research via /distill
    4. Log results for auditing
    """
    start_time = datetime.now(timezone.utc)

    console.print()
    console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
    console.print("[bold cyan]  NIGHTLY LEARNING CYCLE[/bold cyan]")
    console.print(f"[bold cyan]  Scope: {scope}[/bold cyan]")
    console.print(f"[bold cyan]  Time: {start_time.isoformat()}[/bold cyan]")
    console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
    console.print()

    # 1. Get knowledge gaps
    console.print("[bold]Phase 1: Reflecting on past gaps...[/bold]")
    gaps = get_knowledge_gaps(scope)

    if not gaps:
        console.print("[green]No knowledge gaps found. Nothing to learn.[/green]")
        return

    console.print(f"Found {len(gaps)} gaps, processing top {max_gaps}...")

    # Show gaps
    table = Table(title="Knowledge Gaps")
    table.add_column("Type", style="cyan")
    table.add_column("Content", style="white", max_width=50)
    table.add_column("Priority", style="yellow")

    for gap in gaps[:max_gaps]:
        table.add_row(
            gap.get("type", "?"),
            gap.get("content", "?")[:50],
            gap.get("priority", "normal"),
        )
    console.print(table)

    # 1b. Prospective reflection - what keeps failing?
    console.print("\n[bold]Phase 1b: Prospective reflection...[/bold]")
    reflection = prospective_reflection(gaps)

    if reflection["recurring_topics"]:
        console.print("[yellow]Recurring topics:[/yellow]")
        for item in reflection["recurring_topics"][:5]:
            console.print(f"  - {item['topic']} ({item['count']}x)")

    if reflection["failing_skills"]:
        console.print("[yellow]Failing skills:[/yellow]")
        for item in reflection["failing_skills"][:3]:
            console.print(f"  - /{item['skill']} ({item['count']} failures)")

    if reflection["priority_queries"]:
        console.print("[yellow]Priority research queries:[/yellow]")
        for q in reflection["priority_queries"][:3]:
            console.print(f"  - {q}")

    if dry_run:
        console.print("\n[yellow]DRY RUN - Would research and learn from these gaps[/yellow]")
        return

    # 2. Research and learn from each gap
    console.print("\n[bold]Phase 2: Research & Learn...[/bold]")

    results = []
    for i, gap in enumerate(gaps[:max_gaps]):
        console.print(f"\n[{i+1}/{max_gaps}] Processing: {gap.get('type')}")

        # Research
        research = research_gap(gap, scope)
        if not research["success"]:
            console.print(f"  [red]Research failed: {research.get('error', 'unknown')}[/red]")
            results.append({"gap": gap, "research": research, "learning": None})
            continue

        console.print(f"  [green]Research complete[/green]")

        # Learn
        learning = learn_from_research(research, scope, context)
        if learning["success"]:
            console.print(f"  [green]Learning complete[/green]")
        else:
            console.print(f"  [yellow]Learning skipped: {learning.get('error', 'unknown')}[/yellow]")

        results.append({"gap": gap, "research": research, "learning": learning})

    # 3. Summary
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    successful = sum(1 for r in results if r.get("learning", {}).get("success"))

    console.print()
    console.print("[bold]" + "=" * 60 + "[/bold]")
    console.print(f"[bold]CYCLE COMPLETE[/bold]")
    console.print(f"  Duration: {duration:.1f}s")
    console.print(f"  Gaps processed: {len(results)}")
    console.print(f"  Successfully learned: {successful}")
    console.print("[bold]" + "=" * 60 + "[/bold]")

    # Log results
    log_cycle(scope, {
        "scope": scope,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "gaps_found": len(gaps),
        "gaps_processed": len(results),
        "successful_learnings": successful,
        "results": results,
    })


@app.command()
def collect_transcripts(
    since_hours: int = typer.Option(24, "--since", "-s", help="Collect transcripts modified in last N hours"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be collected"),
    agents: str = typer.Option("all", "--agents", "-a", help="Comma-separated agents or 'all'"),
):
    """
    Collect and archive transcripts from coding agents.

    Finds new/modified transcripts from Claude Code, Codex, Pi, KiloCode
    and archives them via episodic-archiver for reflection.

    NOTE: Each agent has its own transcript format. If extraction fails,
    the transcript paths are logged for manual review.
    """
    console.print()
    console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
    console.print("[bold cyan]  TRANSCRIPT COLLECTION[/bold cyan]")
    console.print(f"[bold cyan]  Looking back: {since_hours} hours[/bold cyan]")
    console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
    console.print()

    # Filter agents if specified
    if agents != "all":
        requested = set(a.strip().lower() for a in agents.split(","))
        global TRANSCRIPT_SOURCES
        TRANSCRIPT_SOURCES = {k: v for k, v in TRANSCRIPT_SOURCES.items() if k in requested}

    transcripts = find_new_transcripts(since_hours)

    if not transcripts:
        console.print("[green]No new transcripts found.[/green]")
        return

    # Show what we found
    table = Table(title=f"Found {len(transcripts)} New Transcripts")
    table.add_column("Agent", style="cyan")
    table.add_column("Path", style="white", max_width=50)
    table.add_column("Size", style="yellow")
    table.add_column("Modified", style="dim")

    for t in transcripts[:20]:  # Show first 20
        table.add_row(
            t["agent"],
            Path(t["path"]).name,
            f"{t['size_kb']:.1f}KB",
            t["mtime"][:19],
        )
    console.print(table)

    if len(transcripts) > 20:
        console.print(f"[dim]... and {len(transcripts) - 20} more[/dim]")

    if dry_run:
        console.print("\n[yellow]DRY RUN - Would archive these transcripts[/yellow]")
        return

    # Archive each transcript
    console.print("\n[bold]Archiving transcripts...[/bold]")
    processed = load_processed()
    results = {"archived": 0, "failed": 0, "skipped": 0}
    failed_paths = []

    for i, t in enumerate(transcripts):
        console.print(f"[{i+1}/{len(transcripts)}] {t['agent']}: {Path(t['path']).name}... ", end="")

        result = archive_transcript(t)

        if result["success"]:
            console.print("[green]archived[/green]")
            results["archived"] += 1
            # Mark as processed
            processed["files"][t["path"]] = t["mtime"]
        else:
            console.print(f"[red]failed[/red] - {result.get('error', 'unknown')}")
            results["failed"] += 1
            failed_paths.append(t["path"])

    save_processed(processed)

    # Summary
    console.print()
    console.print("[bold]" + "=" * 60 + "[/bold]")
    console.print(f"[bold]COLLECTION COMPLETE[/bold]")
    console.print(f"  Archived: {results['archived']}")
    console.print(f"  Failed: {results['failed']}")
    console.print("[bold]" + "=" * 60 + "[/bold]")

    if failed_paths:
        console.print("\n[yellow]Failed transcripts (may need manual review):[/yellow]")
        for p in failed_paths[:5]:
            console.print(f"  {p}")

    # Log results
    log_cycle("transcripts", {
        "since_hours": since_hours,
        "found": len(transcripts),
        "results": results,
        "failed_paths": failed_paths,
    })


@app.command()
def full(
    scope: str = typer.Option(..., "--scope", "-s", help="Memory scope for learning"),
    max_gaps: int = typer.Option(5, "--max-gaps", "-m", help="Max gaps to process"),
    since_hours: int = typer.Option(24, "--since", help="Collect transcripts from last N hours"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show plan without executing"),
):
    """
    Full nightly cycle: collect transcripts + learn from gaps.

    1. Collect transcripts from all coding agents
    2. Archive them via episodic-archiver
    3. Reflect on knowledge gaps
    4. Research and learn from gaps
    """
    console.print("[bold magenta]Starting full nightly cycle...[/bold magenta]\n")

    # Phase 1: Collect transcripts
    console.print("[bold]Phase 1: Collecting transcripts[/bold]")
    collect_transcripts(since_hours=since_hours, dry_run=dry_run, agents="all")

    # Phase 2: Learn from gaps
    console.print("\n[bold]Phase 2: Learning from gaps[/bold]")
    learn(scope=scope, max_gaps=max_gaps, dry_run=dry_run, context="nightly reflection")


@app.command()
def register(
    scope: str = typer.Option(..., "--scope", "-s", help="Memory scope for learning"),
    cron: str = typer.Option("0 2 * * *", "--cron", help="Cron schedule (default: 2am daily)"),
    transcripts_cron: str = typer.Option("0 */6 * * *", "--transcripts-cron", help="Transcript collection cron"),
    workdir: str = typer.Option(None, "--workdir", "-w", help="Working directory"),
):
    """
    Register nightly jobs with the scheduler.

    Creates two scheduled jobs:
    1. Full nightly learning cycle (default: 2am daily)
    2. Transcript collection (default: every 6 hours)
    """
    scheduler_dir = find_skill("scheduler")
    if not scheduler_dir:
        console.print("[red]Scheduler skill not found![/red]")
        console.print("Install from: .pi/skills/scheduler/")
        raise typer.Exit(1)

    workdir = workdir or str(SKILL_DIR.parents[2])  # pi-mono root
    learn_script = SKILL_DIR / "run.sh"

    # Register full nightly cycle
    console.print(f"[bold]Registering nightly-learn-{scope}...[/bold]")
    success, output = run_skill(scheduler_dir, [
        "register",
        "--name", f"nightly-learn-{scope}",
        "--cron", cron,
        "--command", f"{learn_script} full --scope {scope}",
        "--workdir", workdir,
        "--description", f"Nightly learning cycle for {scope}",
    ])
    if success:
        console.print(f"[green]✓ Registered nightly-learn-{scope} ({cron})[/green]")
    else:
        console.print(f"[red]Failed: {output[:200]}[/red]")

    # Register transcript collection
    console.print(f"[bold]Registering collect-transcripts...[/bold]")
    success, output = run_skill(scheduler_dir, [
        "register",
        "--name", "collect-transcripts",
        "--cron", transcripts_cron,
        "--command", f"{learn_script} collect-transcripts --since 12",
        "--workdir", workdir,
        "--description", "Collect transcripts from all coding agents",
    ])
    if success:
        console.print(f"[green]✓ Registered collect-transcripts ({transcripts_cron})[/green]")
    else:
        console.print(f"[red]Failed: {output[:200]}[/red]")

    console.print()
    console.print("[bold]Registered jobs. Start scheduler with:[/bold]")
    console.print(f"  {scheduler_dir}/run.sh start")
    console.print(f"  {scheduler_dir}/run.sh status")


if __name__ == "__main__":
    app()
