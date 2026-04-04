"""Typer CLI for ops-nzbgeek."""

import sys
import typer
from typing import Optional
from pathlib import Path

# Add parent directory to path for imports
SKILL_DIR = Path(__file__).parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from ops_nzbgeek.search import search_nzb, format_search_results
from ops_nzbgeek.download import add_nzb, format_download_result
from ops_nzbgeek.status import get_queue, get_history, control_download, format_queue_status, format_control_result
from ops_nzbgeek.interview_helper import handle_multiple_results
from ops_nzbgeek.monitor_helper import register_download, mark_complete, mark_failed

app = typer.Typer(add_completion=False)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    category: str = typer.Option("all", "--category", "-c", help="Category filter (movies, tv, music, apps, books, all)"),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of results"),
    json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Search NZBGeek for content."""
    try:
        results = search_nzb(query, category=category, limit=limit)
        output = format_search_results(results, json_output=json)
        typer.echo(output)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Search failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def download(
    nzb_url: str = typer.Argument(..., help="NZB URL or ID"),
    monitor: bool = typer.Option(False, "--monitor", help="Enable task-monitor progress tracking"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show API call without executing"),
    category: Optional[str] = typer.Option(None, "--category", help="SABnzbd category"),
    priority: int = typer.Option(0, "--priority", help="Priority (0=normal, 1=high, 2=force)"),
):
    """Download NZB via SABnzbd."""
    try:
        result = add_nzb(nzb_url, category=category, priority=priority, dry_run=dry_run)

        if not dry_run and monitor and result.get("nzb_id"):
            # Register with task-monitor
            nzb_id = result["nzb_id"]
            title = nzb_url.split("/")[-1][:50]  # Use URL as title (shortened)

            if register_download(nzb_id, title):
                typer.echo(f"Registered with task-monitor (ID: {nzb_id})")
                typer.echo("Check progress: ~/.pi/skills/task-monitor/run.sh tui --filter nzbgeek")
            else:
                typer.echo("Note: Task-monitor registration failed (monitor may not be available)")

        output = format_download_result(result)
        typer.echo(output)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Download failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def status(
    nzb_id: Optional[str] = typer.Option(None, "--nzb-id", help="Specific NZB ID to check"),
    json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check SABnzbd queue/download status. Also checks history for completed downloads."""
    try:
        queue_data = get_queue(nzb_id=nzb_id)

        # Also check history for specific NZB ID (may have completed)
        history_data = None
        if nzb_id:
            history_data = get_history(nzb_id=nzb_id, limit=20)

        # Combine queue and history for JSON output
        if json:
            import json as json_lib
            combined = {
                "queue": queue_data,
            }
            if history_data:
                combined["history"] = history_data
            typer.echo(json_lib.dumps(combined, indent=2))
        else:
            output = format_queue_status(queue_data, json_output=False)
            typer.echo(output)
            # Show history match if found
            if history_data and history_data.get("slots"):
                slot = history_data["slots"][0]
                typer.echo(f"\n=== History (Completed) ===")
                typer.echo(f"Name: {slot.get('name', 'Unknown')}")
                typer.echo(f"Status: {slot.get('status', 'Unknown')}")
                typer.echo(f"Path: {slot.get('storage', 'Unknown')}")
                if slot.get("fail_message"):
                    typer.echo(f"Error: {slot.get('fail_message')}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Status check failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def pause(nzb_id: str = typer.Argument(..., help="NZB ID to pause")):
    """Pause download."""
    try:
        result = control_download("pause", nzb_id)
        output = format_control_result(result)
        typer.echo(output)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Pause failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def resume(nzb_id: str = typer.Argument(..., help="NZB ID to resume")):
    """Resume download."""
    try:
        result = control_download("resume", nzb_id)
        output = format_control_result(result)
        typer.echo(output)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Resume failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def cancel(nzb_id: str = typer.Argument(..., help="NZB ID to cancel")):
    """Cancel download."""
    try:
        result = control_download("delete", nzb_id)
        output = format_control_result(result)
        typer.echo(output)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Cancel failed: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
