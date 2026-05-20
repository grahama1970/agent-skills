"""Nightly persona refresh workflow for discovering and ingesting new knowledge.

/ask nightly — Scheduled persona knowledge updates.

This script is designed to run nightly (via cron, systemd timer, or scheduler skill)
to incrementally update stored personas with new content.

Workflow:
1. Query memory for all persona profiles
2. For each persona, search for new content since last update
3. Ingest new YouTube videos, papers, news articles
4. Update the persona profile with new sources
5. Report summary to task-monitor

Usage:
    ./nightly.py                    # Update all personas
    ./nightly.py --scope behavioral # Update personas in specific scope
    ./nightly.py --persona "Lisa Feldman Barrett"  # Update single persona
    ./nightly.py --dry-run          # Preview without storing
"""


from .env import load_dotenv_once

load_dotenv_once()
import typer
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger as log

# Import from split modules (same directory)
from .skills_exec import run_skill, parse_memory_output, parse_json_output
from .persona import run_memory_recall, detect_persona, LEARNING_DEPTHS
from .monitor import AskMonitor
from .pipeline import learn
from .dry_run_spec import build_nightly_dry_run_spec, print_execution_spec
from .run_state import AskRunState, make_run_id

# Nightly update configuration
NIGHTLY_SCOPE = os.environ.get("ASK_NIGHTLY_SCOPE", "ask")
NIGHTLY_MAX_VIDEOS = 3  # Max new videos per persona per night
NIGHTLY_MAX_PAPERS = 2  # Max new papers per persona per night
NIGHTLY_LOOKBACK_DAYS = 7  # How far back to search for "new" content


def get_all_persona_profiles(scope: str = NIGHTLY_SCOPE) -> list[dict]:
    """Query memory for all stored persona profiles.

    Returns:
        List of persona profile dicts with name, scope, sources, last_updated
    """
    result = run_memory_recall("persona profile", scope, k=50, timeout=30)

    if result["returncode"] != 0:
        log.error("Failed to recall persona profiles: %s", result["stderr"][:100])
        return []

    items = parse_memory_output(result["stdout"])
    profiles = []

    for item in items:
        problem = item.get("problem", "")
        solution = item.get("solution", "")

        # Parse persona profile from solution JSON
        if "persona profile" in problem.lower():
            try:
                profile = json.loads(solution)
                if "name" in profile:
                    profiles.append(profile)
            except json.JSONDecodeError:
                # Not valid JSON, skip
                pass

    log.info("Found %d persona profiles in scope '%s'", len(profiles), scope)
    return profiles


def find_new_content(persona_name: str, since: datetime) -> dict:
    """Search for new content about a persona since the given date.

    Args:
        persona_name: Name of the persona (e.g., "Lisa Feldman Barrett")
        since: Only find content newer than this date

    Returns:
        Dict with new_videos, new_papers, new_articles lists
    """
    result = {
        "new_videos": [],
        "new_papers": [],
        "new_articles": [],
    }

    since_str = since.strftime("%Y-%m-%d")
    log.info("Searching for new content about '%s' since %s", persona_name, since_str)

    # Search YouTube for new videos
    yt_result = run_skill("ingest-youtube", [
        "search", f'"{persona_name}" lecture OR interview',
        "-n", str(NIGHTLY_MAX_VIDEOS * 2),  # Search more, filter later
        "--no-interactive",
    ], timeout=60)

    if yt_result["returncode"] == 0:
        # Parse YouTube URLs from output
        import re
        urls = re.findall(
            r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+',
            yt_result["stdout"]
        )
        result["new_videos"] = urls[:NIGHTLY_MAX_VIDEOS]
        log.info("Found %d potential new videos", len(result["new_videos"]))

    # Search ArXiv for new papers (if persona has academic papers)
    arxiv_result = run_skill("arxiv", [
        "search",
        "-q", persona_name,
        "-n", str(NIGHTLY_MAX_PAPERS * 2),
        "--months", "1",  # Only last month for nightly updates
    ], timeout=60)

    if arxiv_result["returncode"] == 0:
        # Parse arxiv IDs from output (format: arXiv:2401.12345)
        import re
        arxiv_ids = re.findall(r'arXiv:(\d+\.\d+)', arxiv_result["stdout"])
        for arxiv_id in arxiv_ids[:NIGHTLY_MAX_PAPERS]:
            result["new_papers"].append({"arxiv_id": arxiv_id})
        log.info("Found %d potential new papers", len(result["new_papers"]))

    return result


def update_persona(
    profile: dict,
    dry_run: bool = False,
    monitor: Optional[AskMonitor] = None,
) -> dict:
    """Incrementally update a persona with new content.

    Args:
        profile: Existing persona profile dict
        dry_run: Preview without storing
        monitor: Optional progress monitor

    Returns:
        Update stats dict
    """
    name = profile.get("name", "Unknown")
    scope = profile.get("scope", NIGHTLY_SCOPE)
    last_updated_str = profile.get("last_updated", "")

    # Parse last update time
    if last_updated_str:
        try:
            last_updated = datetime.fromisoformat(last_updated_str)
        except ValueError:
            last_updated = datetime.now() - timedelta(days=NIGHTLY_LOOKBACK_DAYS)
    else:
        last_updated = datetime.now() - timedelta(days=NIGHTLY_LOOKBACK_DAYS)

    log.info("Updating persona '%s' (last updated: %s)", name, last_updated)

    # Find new content
    new_content = find_new_content(name, last_updated)

    stats = {
        "name": name,
        "new_videos": len(new_content["new_videos"]),
        "new_papers": len(new_content["new_papers"]),
        "new_articles": len(new_content["new_articles"]),
        "items_stored": 0,
    }

    # Skip if no new content
    if not any([new_content["new_videos"], new_content["new_papers"], new_content["new_articles"]]):
        log.info("No new content found for '%s'", name)
        return stats

    # Use learn() with the new URLs (incremental update)
    if new_content["new_videos"] and not dry_run:
        learn_result = learn(
            topic=name,
            scope=scope,
            youtube_urls=new_content["new_videos"],
            youtube_only=True,  # Only ingest the new videos
            max_videos=NIGHTLY_MAX_VIDEOS,
            depth="quick",  # Fast incremental update
            monitor=monitor,
        )
        stats["items_stored"] += learn_result.get("stored", 0)

    return stats


def nightly_update(
    scope: str = NIGHTLY_SCOPE,
    persona_name: Optional[str] = None,
    dry_run: bool = False,
    run_state: Optional[AskRunState] = None,
) -> dict:
    """Run nightly persona update job.

    Args:
        scope: Memory scope to update
        persona_name: Optional single persona to update
        dry_run: Preview without storing

    Returns:
        Summary dict with personas_updated, items_stored, errors
    """
    start_time = time.time()

    summary = {
        "scope": scope,
        "personas_checked": 0,
        "personas_updated": 0,
        "items_stored": 0,
        "errors": [],
        "timestamp": datetime.now().isoformat(),
    }

    print(f"\n== /ask nightly update ==")
    print(f"   Scope: {scope}")
    if persona_name:
        print(f"   Persona: {persona_name}")
    if dry_run:
        print("   [DRY RUN]")
    print()

    # Get personas to update
    if run_state:
        run_state.step_started("nightly_persona_discovery", scope=scope, single_persona=bool(persona_name))
    if persona_name:
        # Single persona mode
        profile = {
            "name": persona_name,
            "scope": scope,
            "last_updated": (datetime.now() - timedelta(days=NIGHTLY_LOOKBACK_DAYS)).isoformat(),
        }
        profiles = [profile]
    else:
        # Get all personas from memory
        profiles = get_all_persona_profiles(scope)

    if not profiles:
        print("   No personas found to update")
        if run_state:
            run_state.step_finished("nightly_persona_discovery", personas_found=0)
        return summary

    summary["personas_checked"] = len(profiles)
    if run_state:
        run_state.step_finished("nightly_persona_discovery", personas_found=len(profiles))
    print(f"   Found {len(profiles)} persona(s) to check\n")

    # Update each persona
    if run_state:
        run_state.step_started("nightly_persona_updates", personas=len(profiles))
    for i, profile in enumerate(profiles):
        name = profile.get("name", "Unknown")
        print(f"   [{i + 1}/{len(profiles)}] Checking {name}...")

        try:
            stats = update_persona(profile, dry_run=dry_run)

            if stats["items_stored"] > 0 or stats["new_videos"] > 0:
                summary["personas_updated"] += 1
                summary["items_stored"] += stats["items_stored"]
                print(f"         Updated: {stats['new_videos']} videos, {stats['new_papers']} papers")
            else:
                print(f"         No new content")

        except Exception as e:
            log.error("Error updating persona '%s': %s", name, e)
            summary["errors"].append(f"{name}: {str(e)[:100]}")
            print(f"         Error: {str(e)[:60]}")
    if run_state:
        run_state.step_finished(
            "nightly_persona_updates",
            personas_updated=summary["personas_updated"],
            items_stored=summary["items_stored"],
            errors=len(summary["errors"]),
        )

    # Summary
    elapsed = time.time() - start_time
    print(f"\n== Nightly Update Complete ({elapsed:.1f}s) ==")
    print(f"   Personas checked:  {summary['personas_checked']}")
    print(f"   Personas updated:  {summary['personas_updated']}")
    print(f"   Items stored:      {summary['items_stored']}")
    if summary["errors"]:
        print(f"   Errors:            {len(summary['errors'])}")
    print()

    return summary


app = typer.Typer(help="/ask nightly — Scheduled persona knowledge updates")


def nightly_os_refresh(dry_run: bool = False) -> dict:
    """Re-crawl OS knowledge nightly to catch skill/package changes."""
    from .os_learn import learn_os
    log.info("Nightly OS refresh starting")
    return learn_os(depth="standard", dry_run=dry_run)


@app.command()
def main(
    scope: str = typer.Option(NIGHTLY_SCOPE, help="Memory scope to update"),
    persona: str = typer.Option(None, help="Update a single persona by name"),
    os_refresh: bool = typer.Option(False, "--os", help="Also refresh OS knowledge"),
    dry_run: bool = typer.Option(False, help="Preview without storing"),
    as_json: bool = typer.Option(False, "--json", help="Output summary as JSON"),
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this nightly call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    if debug:
        log.enable("")

    request = {
        "command": "nightly",
        "scope": scope,
        "persona": persona,
        "os_refresh": os_refresh,
        "dry_run": dry_run,
    }
    if dry_run:
        print_execution_spec(build_nightly_dry_run_spec(request), as_json=as_json)
        raise typer.Exit(code=0)

    run_state = AskRunState(
        ask_id or make_run_id(f"nightly {scope} {persona or ''}"),
        output_root=run_output_root,
        overwrite=overwrite_run,
        resume=resume_run,
    )
    run_state.write_request(request)
    try:
        summary = nightly_update(
            scope=scope,
            persona_name=persona,
            dry_run=dry_run,
            run_state=run_state,
        )

        # OS refresh if requested or scope is "os"
        if os_refresh or scope == "os":
            run_state.step_started("nightly_os_refresh", dry_run=dry_run)
            os_stats = nightly_os_refresh(dry_run=dry_run)
            summary["os_refresh"] = {
                "skills_crawled": os_stats.get("skills_crawled", 0),
                "qras_generated": os_stats.get("qras_generated", 0),
                "stored": os_stats.get("stored", 0),
            }
            run_state.step_finished("nightly_os_refresh", **summary["os_refresh"])
    except Exception as exc:
        run_state.fail(exc)
        raise

    if as_json:
        print(json.dumps(summary, indent=2))

    # Exit 0 if any updates made, 1 if nothing
    any_updates = summary["personas_updated"] > 0 or summary.get("os_refresh", {}).get("stored", 0) > 0
    run_state.finish(summary, state="completed" if any_updates or dry_run else "no_results")

    if dry_run and not summary["errors"]:
        sys.exit(0)

    sys.exit(0 if any_updates else 1)


if __name__ == "__main__":
    app()
