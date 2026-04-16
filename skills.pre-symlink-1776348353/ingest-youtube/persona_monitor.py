#!/usr/bin/env python3
"""
Persona YouTube Monitor - Nightly check for new content across all personas.

This is CRUCIAL for keeping persona knowledge current.

Usage:
    uv run python persona_monitor.py check      # Check for new videos
    uv run python persona_monitor.py ingest     # Check and ingest new videos
    uv run python persona_monitor.py status     # Show monitoring status
    uv run python persona_monitor.py register   # Register with scheduler
"""

import os
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Persona YouTube monitoring for nightly updates")

# All YouTube personas to monitor
YOUTUBE_PERSONAS = {
    # Video generation experts (CRITICAL for create-movie)
    "dankieft": {
        "name": "Dan Kieft",
        "handle": "https://www.youtube.com/channel/UCdNj_PP__5kKtjZabuEjbqA",
        "priority": "HIGH",
        "scope": "dan-kieft",
        "category": "video-generation",
    },
    # ML/Training experts (CRITICAL for model training)
    "trelisresearch": {
        "name": "Trelis Research",
        "handle": "https://www.youtube.com/@TrelisResearch",
        "priority": "HIGH",
        "scope": "trelis",
        "category": "ml-training",
    },
    "ronanmcgovern": {
        "name": "Ronan McGovern",
        "handle": "https://www.youtube.com/@RonanMcGovern",
        "priority": "HIGH",
        "scope": "ronan",
        "category": "ml-training",
    },
    "deeplearningai": {
        "name": "DeepLearningAI (Andrew Ng)",
        "handle": "https://www.youtube.com/@Deeplearningai",
        "priority": "HIGH",
        "scope": "andrew-ng",
        "category": "ml-training",
    },
    "karpathy": {
        "name": "Andrej Karpathy",
        "handle": "https://www.youtube.com/@karpathy",
        "priority": "HIGH",
        "scope": "karpathy",
        "category": "ml-training",
    },
    # Programming/Dev education
    "fireship": {
        "name": "Fireship",
        "handle": "https://www.youtube.com/@Fireship",
        "priority": "MEDIUM",
        "scope": "fireship",
        "category": "programming",
    },
    "3blue1brown": {
        "name": "3Blue1Brown",
        "handle": "https://www.youtube.com/@3blue1brown",
        "priority": "MEDIUM",
        "scope": "3blue1brown",
        "category": "math-education",
    },
    "code4ai": {
        "name": "Code4AI",
        "handle": "https://www.youtube.com/@code4AI",
        "priority": "MEDIUM",
        "scope": "code4ai",
        "category": "ai-coding",
    },
    # Horus lore (40K content)
    "luetin09": {
        "name": "Luetin09",
        "handle": "https://www.youtube.com/@Luetin09",
        "priority": "MEDIUM",
        "scope": "horus_lore",
        "category": "40k-lore",
    },
    "remembrancer": {
        "name": "TheRemembrancer",
        "handle": "https://www.youtube.com/@TheRemembrancer",
        "priority": "MEDIUM",
        "scope": "horus_lore",
        "category": "40k-lore",
    },
    # Filmmaking/Creative
    "nobodyandthecomputer": {
        "name": "Nobody & The Computer",
        "handle": "https://www.youtube.com/@nobodyandthecomputer",
        "priority": "HIGH",
        "scope": "horus-filmmaking",
        "category": "filmmaking",
    },
    "aivideoschool": {
        "name": "AI Video School",
        "handle": "https://www.youtube.com/@aivideoschool",
        "priority": "MEDIUM",
        "scope": "ai-video",
        "category": "video-generation",
    },
}

TRANSCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "run" / "youtube-transcripts"
STATE_FILE = TRANSCRIPT_DIR / ".persona_monitor_state.json"


@dataclass
class PersonaStatus:
    """Status of a persona's YouTube content."""
    name: str
    youtube_count: int = 0
    ingested_count: int = 0
    new_videos: int = 0
    last_checked: Optional[str] = None
    last_ingested: Optional[str] = None
    error: Optional[str] = None


def get_youtube_video_count(handle: str) -> int:
    """Get total video count from YouTube channel."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "id", f"{handle}/videos"],
            capture_output=True,
            text=True,
            timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    except Exception as e:
        return -1


def get_ingested_count(persona_id: str) -> int:
    """Get count of ingested transcripts for a persona."""
    persona_dir = TRANSCRIPT_DIR / persona_id
    if not persona_dir.exists():
        return 0
    return len(list(persona_dir.glob("*.json"))) - (1 if (persona_dir / ".batch_state.json").exists() else 0)


def load_state() -> dict:
    """Load monitoring state from file."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"personas": {}, "last_full_check": None}


def save_state(state: dict):
    """Save monitoring state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


@app.command()
def check(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Filter by priority (HIGH, MEDIUM, LOW)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check all personas for new YouTube content."""
    state = load_state()
    results = []

    for persona_id, config in YOUTUBE_PERSONAS.items():
        # Apply filters
        if category and config["category"] != category:
            continue
        if priority and config["priority"] != priority:
            continue

        typer.echo(f"Checking {config['name']}...", err=True)

        youtube_count = get_youtube_video_count(config["handle"])
        ingested_count = get_ingested_count(persona_id)

        status = PersonaStatus(
            name=config["name"],
            youtube_count=youtube_count,
            ingested_count=ingested_count,
            new_videos=max(0, youtube_count - ingested_count) if youtube_count >= 0 else 0,
            last_checked=datetime.now().isoformat(),
            error="Failed to fetch YouTube count" if youtube_count < 0 else None,
        )

        # Update state
        state["personas"][persona_id] = {
            "youtube_count": youtube_count,
            "ingested_count": ingested_count,
            "last_checked": status.last_checked,
            "priority": config["priority"],
            "category": config["category"],
        }

        results.append({
            "id": persona_id,
            "name": config["name"],
            "priority": config["priority"],
            "category": config["category"],
            "youtube": youtube_count,
            "ingested": ingested_count,
            "new": status.new_videos,
            "error": status.error,
        })

    state["last_full_check"] = datetime.now().isoformat()
    save_state(state)

    if json_output:
        typer.echo(json.dumps(results, indent=2))
    else:
        typer.echo("\n=== PERSONA YOUTUBE MONITORING ===\n")
        typer.echo(f"{'Persona':<25} {'Priority':<8} {'YouTube':<8} {'Ingested':<10} {'New':<6}")
        typer.echo("-" * 65)

        total_new = 0
        for r in sorted(results, key=lambda x: (-x["new"], x["priority"])):
            new_str = str(r["new"]) if r["new"] > 0 else "-"
            if r["new"] > 0:
                new_str = f"**{r['new']}**"
                total_new += r["new"]
            typer.echo(f"{r['name']:<25} {r['priority']:<8} {r['youtube']:<8} {r['ingested']:<10} {new_str:<6}")

        typer.echo("-" * 65)
        typer.echo(f"Total new videos to ingest: {total_new}")


def learn_transcript_to_memory(transcript_path: Path, scope: str, persona_name: str) -> bool:
    """
    Learn a transcript to memory with taxonomy classification.

    Pipeline: Transcript → Taxonomy Classification → Memory Learn
    """
    try:
        transcript_data = json.loads(transcript_path.read_text())
        full_text = transcript_data.get("full_text", "")
        video_id = transcript_data.get("meta", {}).get("video_id", transcript_path.stem)

        if not full_text or len(full_text) < 100:
            return False

        # Step 1: Apply taxonomy classification
        # Uses /taxonomy to get bridge attributes
        taxonomy_cmd = [
            "uv", "run", "--directory",
            str(Path(__file__).parent.parent / "taxonomy"),
            "python", "classify.py",
            "--text", full_text[:2000],  # Use first 2000 chars for classification
            "--json",
        ]

        taxonomy_result = subprocess.run(
            taxonomy_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        tags = []
        if taxonomy_result.returncode == 0:
            try:
                taxonomy_data = json.loads(taxonomy_result.stdout)
                tags = taxonomy_data.get("bridge_tags", [])
            except json.JSONDecodeError:
                pass

        # Step 2: Learn to memory with scope and tags
        problem = f"YouTube transcript from {persona_name}: {video_id}"
        solution = full_text[:5000]  # First 5000 chars as solution

        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=60.0) as client:
            body = {
                "problem": problem,
                "solution": solution,
                "scope": scope,
            }
            if tags:
                body["tags"] = tags
            resp = client.post("/learn", json=body)
            return resp.status_code == 200

    except Exception as e:
        typer.echo(f"    Error learning to memory: {e}", err=True)
        return False


@app.command()
def ingest(
    max_new: int = typer.Option(50, "--max-new", "-n", help="Max new videos to ingest per persona"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Only ingest priority level"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be ingested"),
    learn: bool = typer.Option(True, "--learn/--no-learn", help="Learn transcripts to memory"),
):
    """
    Check for new videos and ingest them.

    Full pipeline:
    1. Check YouTube for new videos
    2. Ingest transcripts via batch processor
    3. Apply taxonomy classification
    4. Learn to memory with scope and tags
    """
    state = load_state()

    for persona_id, config in YOUTUBE_PERSONAS.items():
        if priority and config["priority"] != priority:
            continue

        typer.echo(f"\n=== Checking {config['name']} ===")

        # Get current counts
        youtube_count = get_youtube_video_count(config["handle"])
        ingested_count = get_ingested_count(persona_id)
        new_count = max(0, youtube_count - ingested_count) if youtube_count >= 0 else 0

        if new_count == 0:
            typer.echo(f"  No new videos (YouTube: {youtube_count}, Ingested: {ingested_count})")
            continue

        typer.echo(f"  Found {new_count} new videos")

        if dry_run:
            typer.echo(f"  [DRY RUN] Would ingest up to {min(new_count, max_new)} videos")
            continue

        # Create/update video list
        video_list = TRANSCRIPT_DIR / f"{persona_id}_videos.txt"
        typer.echo(f"  Updating video list: {video_list}")

        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "id", f"{config['handle']}/videos"],
            capture_output=True,
            text=True,
            timeout=120,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0:
            video_list.write_text(result.stdout)

            # Start batch ingestion
            persona_dir = TRANSCRIPT_DIR / persona_id
            persona_dir.mkdir(exist_ok=True)

            typer.echo(f"  Starting batch ingestion...")

            # Run supervisor in background
            cmd = [
                "uv", "run", "python", "supervisor.py", "run",
                "--input", str(video_list),
                "--output", str(persona_dir),
                "--delay-min", "3",
                "--delay-max", "10",
            ]

            subprocess.Popen(
                cmd,
                cwd=Path(__file__).parent,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            typer.echo(f"  Batch ingestion started in background")

            # Update state
            state["personas"][persona_id] = {
                "youtube_count": youtube_count,
                "ingested_count": ingested_count,
                "last_checked": datetime.now().isoformat(),
                "last_ingested": datetime.now().isoformat(),
                "priority": config["priority"],
                "category": config["category"],
                "scope": config["scope"],
            }

    save_state(state)
    typer.echo("\n=== Ingestion jobs started ===")


@app.command()
def learn_pending(
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Specific persona to process"),
    max_transcripts: int = typer.Option(100, "--max", "-n", help="Max transcripts to learn"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be learned"),
):
    """
    Learn pending transcripts to memory with taxonomy classification.

    This runs after batch ingestion completes to apply taxonomy
    and store in memory.
    """
    state = load_state()
    learned_file = TRANSCRIPT_DIR / ".learned_transcripts.json"

    # Load already-learned transcripts
    learned = set()
    if learned_file.exists():
        learned = set(json.loads(learned_file.read_text()))

    total_learned = 0

    for persona_id, config in YOUTUBE_PERSONAS.items():
        if persona and persona_id != persona:
            continue

        persona_dir = TRANSCRIPT_DIR / persona_id
        if not persona_dir.exists():
            continue

        typer.echo(f"\n=== Processing {config['name']} → scope: {config['scope']} ===")

        # Find transcripts not yet learned
        transcripts = list(persona_dir.glob("*.json"))
        transcripts = [t for t in transcripts if t.name != ".batch_state.json"]
        pending = [t for t in transcripts if str(t) not in learned]

        typer.echo(f"  Total transcripts: {len(transcripts)}")
        typer.echo(f"  Pending to learn: {len(pending)}")

        if not pending:
            continue

        for transcript in pending[:max_transcripts]:
            if dry_run:
                typer.echo(f"  [DRY RUN] Would learn: {transcript.stem}")
                continue

            typer.echo(f"  Learning: {transcript.stem}...", nl=False)

            if learn_transcript_to_memory(transcript, config["scope"], config["name"]):
                learned.add(str(transcript))
                total_learned += 1
                typer.echo(" ✓")
            else:
                typer.echo(" ✗")

        # Save learned state incrementally
        learned_file.write_text(json.dumps(list(learned)))

    typer.echo(f"\n=== Learned {total_learned} transcripts to memory ===")


@app.command()
def status():
    """Show current monitoring status."""
    state = load_state()

    typer.echo("=== PERSONA MONITORING STATUS ===\n")
    typer.echo(f"Last full check: {state.get('last_full_check', 'Never')}")
    typer.echo(f"State file: {STATE_FILE}")
    typer.echo(f"Transcript dir: {TRANSCRIPT_DIR}\n")

    typer.echo(f"{'Persona':<20} {'Last Check':<20} {'YouTube':<8} {'Ingested':<10}")
    typer.echo("-" * 60)

    for persona_id, data in state.get("personas", {}).items():
        last_check = data.get("last_checked", "Never")
        if last_check != "Never":
            last_check = last_check[:19].replace("T", " ")
        typer.echo(
            f"{persona_id:<20} {last_check:<20} "
            f"{data.get('youtube_count', '?'):<8} {data.get('ingested_count', '?'):<10}"
        )


@app.command()
def register():
    """Register persona monitoring with scheduler for nightly runs."""
    scheduler_cmd = [
        ".agent/skills/scheduler/run.sh", "register",
        "--name", "persona-youtube-monitor",
        "--cron", "0 3 * * *",  # 3 AM daily
        "--command", f"uv run --directory {Path(__file__).parent} python persona_monitor.py ingest --priority HIGH",
        "--workdir", str(Path(__file__).parent.parent.parent.parent),
        "--description", "Nightly persona YouTube monitoring - check and ingest new content",
    ]

    typer.echo("Registering with scheduler...")
    typer.echo(f"Command: {' '.join(scheduler_cmd)}")

    result = subprocess.run(
        scheduler_cmd,
        cwd=Path(__file__).parent.parent.parent.parent,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    if result.returncode == 0:
        typer.echo("Successfully registered persona-youtube-monitor")
        typer.echo("Will run nightly at 3 AM to check HIGH priority personas")
    else:
        typer.echo(f"Failed to register: {result.stderr}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
