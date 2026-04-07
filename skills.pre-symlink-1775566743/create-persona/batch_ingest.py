#!/usr/bin/env python3
"""
Batch persona ingestion - orchestrates /dogpile, /discover-*, /ingest-* skills
to gather comprehensive content for each persona.

Usage:
    python batch_ingest.py --dry-run                    # Preview what would be ingested
    python batch_ingest.py --category directors         # Ingest one category
    python batch_ingest.py --persona "Alan Turing"      # Ingest single persona
    python batch_ingest.py --all                        # Ingest all (LONG!)
    python batch_ingest.py --resume                     # Resume from checkpoint
"""

import typer
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger as log

# Paths
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent.parent.parent / ".agent" / "skills"
CHECKPOINT_FILE = SCRIPT_DIR / "ingest_checkpoint.json"
RESULTS_DIR = SCRIPT_DIR / "ingest_results"


@dataclass
class IngestResult:
    """Results from ingesting a single persona."""
    persona_name: str
    category: str
    dogpile_done: bool = False
    books_found: list = field(default_factory=list)
    books_ingested: list = field(default_factory=list)
    movies_found: list = field(default_factory=list)
    youtube_videos: list = field(default_factory=list)
    github_repos: list = field(default_factory=list)
    feeds_added: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self):
        return {
            "persona_name": self.persona_name,
            "category": self.category,
            "dogpile_done": self.dogpile_done,
            "books_found": self.books_found,
            "books_ingested": self.books_ingested,
            "movies_found": self.movies_found,
            "youtube_videos": self.youtube_videos,
            "github_repos": self.github_repos,
            "feeds_added": self.feeds_added,
            "errors": self.errors,
            "timestamp": self.timestamp,
        }


def run_skill(skill_name: str, args: list, timeout: int = 300) -> dict:
    """Run a skill and capture output."""
    skill_dir = SKILLS_DIR / skill_name
    run_script = skill_dir / "run.sh"

    if not run_script.exists():
        return {"returncode": 1, "stdout": "", "stderr": f"Skill not found: {skill_name}"}

    cmd = [str(run_script)] + args
    log.debug(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(skill_dir),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Timeout"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def run_dogpile(persona_name: str, domain: str, timeout: int = 180) -> dict:
    """Run /dogpile research for a persona."""
    query = f"{persona_name} {domain} major works contributions biography"

    result = run_skill("dogpile", ["search", query], timeout=timeout)
    return result


def discover_books(persona_name: str, max_books: int = 3) -> list:
    """Find top books by/about a persona using /discover-books."""
    result = run_skill("discover-books", [
        "search", f'"{persona_name}"',
        "--limit", str(max_books * 2),  # Get extra to filter
        "--json"
    ], timeout=60)

    if result["returncode"] != 0:
        return []

    try:
        # Parse JSON output
        books = json.loads(result["stdout"])
        return books[:max_books]
    except json.JSONDecodeError:
        return []


def discover_movies(persona_name: str, max_movies: int = 3) -> list:
    """Find movies by a director/performer using /discover-movies."""
    result = run_skill("discover-movies", [
        "search", f'"{persona_name}"',
        "--limit", str(max_movies * 2),
        "--json"
    ], timeout=60)

    if result["returncode"] != 0:
        return []

    try:
        movies = json.loads(result["stdout"])
        return movies[:max_movies]
    except json.JSONDecodeError:
        return []


def search_youtube(persona_name: str, keywords: list, max_videos: int = 5) -> list:
    """Search YouTube for talks/lectures by persona."""
    query = f"{persona_name} {' '.join(keywords[:3])} lecture talk interview"

    result = run_skill("ingest-youtube", [
        "search", query,
        "--limit", str(max_videos),
        "--json"
    ], timeout=60)

    if result["returncode"] != 0:
        return []

    try:
        videos = json.loads(result["stdout"])
        return videos[:max_videos]
    except json.JSONDecodeError:
        return []


def search_github(persona_name: str, domain: str) -> list:
    """Search GitHub for repos related to persona (for coders)."""
    result = run_skill("github-search", [
        "repos", f"{persona_name} {domain}",
        "--limit", "5",
        "--json"
    ], timeout=60)

    if result["returncode"] != 0:
        return []

    try:
        repos = json.loads(result["stdout"])
        return repos[:3]
    except json.JSONDecodeError:
        return []


def ingest_youtube_video(video_url: str) -> bool:
    """Ingest a single YouTube video transcript."""
    result = run_skill("ingest-youtube", ["ingest", video_url], timeout=120)
    return result["returncode"] == 0


def trigger_ask_learn(persona_name: str, scope: str = "personas", depth: str = "standard") -> bool:
    """Trigger /ask learn to consolidate knowledge."""
    result = run_skill("ask", [
        "learn", persona_name,
        "--scope", scope,
        "--depth", depth,
    ], timeout=300)
    return result["returncode"] == 0


def ingest_persona(persona: dict, category: str, dry_run: bool = False) -> IngestResult:
    """Ingest all content for a single persona."""
    name = persona["name"]
    domain = persona.get("domain", "")
    template = persona.get("template", "expert")
    expertise = persona.get("expertise", [])

    result = IngestResult(
        persona_name=name,
        category=category,
        timestamp=datetime.now().isoformat(),
    )

    log.info(f"{'[DRY-RUN] ' if dry_run else ''}Ingesting: {name} ({category})")

    # 1. Run /dogpile research
    log.info(f"  Running /dogpile for {name}...")
    if not dry_run:
        dogpile_result = run_dogpile(name, domain, timeout=180)
        result.dogpile_done = dogpile_result["returncode"] == 0
        if not result.dogpile_done:
            result.errors.append(f"dogpile failed: {dogpile_result['stderr'][:100]}")
    else:
        result.dogpile_done = True

    # 2. Discover books (for most personas)
    log.info(f"  Discovering books for {name}...")
    if not dry_run:
        books = discover_books(name, max_books=3)
        result.books_found = [b.get("title", str(b)) for b in books]
    else:
        result.books_found = ["[would discover 3 books]"]

    # 3. Discover movies (for directors, performers)
    if category in ["directors", "performers"]:
        log.info(f"  Discovering movies for {name}...")
        if not dry_run:
            movies = discover_movies(name, max_movies=3)
            result.movies_found = [m.get("title", str(m)) for m in movies]
        else:
            result.movies_found = ["[would discover 3 movies]"]

    # 4. Search YouTube
    log.info(f"  Searching YouTube for {name}...")
    keywords = expertise[:3] if expertise else [domain]
    if not dry_run:
        videos = search_youtube(name, keywords, max_videos=5)
        result.youtube_videos = [v.get("title", str(v))[:50] for v in videos]

        # Ingest top 3 videos
        for video in videos[:3]:
            url = video.get("url") or video.get("video_url")
            if url:
                success = ingest_youtube_video(url)
                if not success:
                    result.errors.append(f"Failed to ingest video: {url}")
    else:
        result.youtube_videos = ["[would ingest 3-5 videos]"]

    # 5. Search GitHub (for coders, cs_pioneers, hackers)
    if category in ["coders", "cs_pioneers", "hackers_whitehat", "redteam", "blueteam"]:
        log.info(f"  Searching GitHub for {name}...")
        if not dry_run:
            repos = search_github(name, domain)
            result.github_repos = [r.get("full_name", str(r)) for r in repos]
        else:
            result.github_repos = ["[would find relevant repos]"]

    # 6. Trigger /ask learn to consolidate
    log.info(f"  Triggering /ask learn for {name}...")
    if not dry_run:
        learn_success = trigger_ask_learn(name, scope="personas", depth="standard")
        if not learn_success:
            result.errors.append("ask learn failed")

    # Rate limit protection
    if not dry_run:
        time.sleep(2)

    return result


def load_personas(manifest_path: Path) -> dict:
    """Load personas from YAML manifest."""
    with open(manifest_path) as f:
        data = yaml.safe_load(f)

    # Remove defaults
    data.pop("defaults", None)

    return data


def save_checkpoint(completed: list, current_category: str, current_index: int):
    """Save progress checkpoint."""
    checkpoint = {
        "completed": completed,
        "current_category": current_category,
        "current_index": current_index,
        "timestamp": datetime.now().isoformat(),
    }
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2)


def load_checkpoint() -> Optional[dict]:
    """Load progress checkpoint."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return None


app = typer.Typer(help="Batch ingest personas")


@app.command()
def main(
    manifest: str = typer.Option("personas.yaml", help="YAML manifest file"),
    category: str = typer.Option(None, help="Only process specific category"),
    persona: str = typer.Option(None, help="Only process specific persona"),
    all: bool = typer.Option(False, help="Process all personas"),
    dry_run: bool = typer.Option(False, help="Preview without ingesting"),
    resume: bool = typer.Option(False, help="Resume from checkpoint"),
    limit: int = typer.Option(0, help="Limit number of personas"),
):
    # Load manifest
    manifest_path = SCRIPT_DIR / manifest
    if not manifest_path.exists():
        log.error(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    personas_by_category = load_personas(manifest_path)

    # Create results directory
    RESULTS_DIR.mkdir(exist_ok=True)

    # Load checkpoint if resuming
    completed = []
    start_category = None
    start_index = 0

    if resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            completed = checkpoint.get("completed", [])
            start_category = checkpoint.get("current_category")
            start_index = checkpoint.get("current_index", 0)
            log.info(f"Resuming from checkpoint: {len(completed)} completed")

    # Collect personas to process
    to_process = []

    for category, personas in personas_by_category.items():
        if not isinstance(personas, list):
            continue

        if category and category != category:
            continue

        for i, persona in enumerate(personas):
            name = persona.get("name", "")

            if persona and name != persona:
                continue

            if name in completed:
                continue

            to_process.append((category, i, persona))

    if not to_process:
        log.info("No personas to process")
        return

    if limit:
        to_process = to_process[:limit]

    log.info(f"{'[DRY-RUN] ' if dry_run else ''}Processing {len(to_process)} personas")

    # Process each persona
    results = []

    for idx, (category, persona_idx, persona) in enumerate(to_process):
        name = persona["name"]

        try:
            result = ingest_persona(persona, category, dry_run=dry_run)
            results.append(result)

            # Save individual result
            result_file = RESULTS_DIR / f"{name.replace(' ', '_').lower()}.json"
            with open(result_file, "w") as f:
                json.dump(result.to_dict(), f, indent=2)

            # Update checkpoint
            completed.append(name)
            save_checkpoint(completed, category, persona_idx)

            log.info(f"  ✓ Completed {name} ({idx + 1}/{len(to_process)})")

            # Summary
            if result.books_found:
                log.info(f"    Books: {len(result.books_found)}")
            if result.youtube_videos:
                log.info(f"    Videos: {len(result.youtube_videos)}")
            if result.movies_found:
                log.info(f"    Movies: {len(result.movies_found)}")
            if result.github_repos:
                log.info(f"    Repos: {len(result.github_repos)}")
            if result.errors:
                log.warning(f"    Errors: {result.errors}")

        except Exception as e:
            log.error(f"  ✗ Failed {name}: {e}")
            results.append(IngestResult(
                persona_name=name,
                category=category,
                errors=[str(e)],
                timestamp=datetime.now().isoformat(),
            ))

    # Summary
    log.info("\n" + "=" * 60)
    log.info(f"Batch ingestion complete: {len(results)} personas processed")

    successful = sum(1 for r in results if r.dogpile_done and not r.errors)
    log.info(f"  Successful: {successful}")
    log.info(f"  With errors: {len(results) - successful}")

    total_books = sum(len(r.books_found) for r in results)
    total_videos = sum(len(r.youtube_videos) for r in results)
    total_movies = sum(len(r.movies_found) for r in results)
    total_repos = sum(len(r.github_repos) for r in results)

    log.info(f"  Total books discovered: {total_books}")
    log.info(f"  Total videos ingested: {total_videos}")
    log.info(f"  Total movies discovered: {total_movies}")
    log.info(f"  Total repos found: {total_repos}")


if __name__ == "__main__":
    app()
