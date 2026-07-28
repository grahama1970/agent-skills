#!/usr/bin/env python3
"""Dogpile: Comprehensive deep search aggregator (CLI command layer).

Thin Typer command surface. Search orchestration lives in
``dogpile.search_engine``; this module wires CLI options to it and provides the
resources/presets/errors/extract/version commands.

Orchestrates searches across:
- Brave Search (Web)
- Concurrent Brave question lanes (retired Perplexity replacement)
- GitHub (Repos & Issues)
- ArXiv (Papers)
- YouTube (Videos)
- Readarr (Books/Usenet, opt-in)
- Wayback Machine (Archives, opt-in)
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import typer
from loguru import logger

from dogpile.config import (
    app,
    console,
    REGISTRY_AVAILABLE,
    get_registry,
    VERSION,
)
from dogpile.utils import log_status
from dogpile.error_tracking import (
    start_session as start_error_session,
    end_session as end_error_session,
    get_error_summary,
)
from dogpile.error_hints import get_error_hint
from dogpile.task_monitor_integration import (
    start_search as start_monitor,
    end_search as end_monitor,
)
from dogpile.search_engine import PartialResultsPublisher, _run_search


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    preset: Optional[str] = typer.Option(None, "--preset", "-p", help="Use a resource preset (vulnerability_research, red_team, blue_team, etc.)"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Enable ambiguity/intent check"),
    tailor: bool = typer.Option(True, "--tailor/--no-tailor", help="Tailor queries per service"),
    use_github_skill: bool = typer.Option(True, "--github-skill/--no-github-skill", help="Use /github-search skill"),
    auto_preset: bool = typer.Option(False, "--auto-preset", help="Auto-detect preset from query"),
    with_perplexity: bool = typer.Option(False, "--with-perplexity", help="Deprecated: record Perplexity as skipped; never calls the paid API"),
    with_readarr: bool = typer.Option(False, "--with-readarr", help="Include local Readarr/Usenet book search"),
    with_wayback: bool = typer.Option(False, "--with-wayback", help="Include Wayback archive lookup"),
    with_feeds: bool = typer.Option(False, "--with-feeds", help="Include configured consume-feed RSS monitor dry-run"),
    feed_limit: int = typer.Option(3, "--feed-limit", min=1, max=25, help="Max feed items per source when --with-feeds is used"),
    feed_pack: str = typer.Option("security_code", "--feed-pack", help="Dogpile feed pack to use with --with-feeds; empty string uses consume-feed config"),
    html_report: bool = typer.Option(False, "--html-report", help="Write a self-contained HTML/CSS report"),
    open_report: bool = typer.Option(False, "--open-report", help="Open the HTML report in your browser"),
    report_file: Optional[Path] = typer.Option(None, "--report-file", help="Write the HTML report to a specific path"),
):
    """Aggregate search results from multiple sources."""

    # Initialize error tracking, task-monitor, and execution collector
    session_id = start_error_session(query)
    monitor = start_monitor(query, name=f"dogpile-{session_id[-8:]}")
    publisher = PartialResultsPublisher(query)

    from dogpile.utils import init_execution_collector
    init_execution_collector(session_id)
    search_success = False

    try:
        _run_search(
            query=query,
            preset=preset,
            interactive=interactive,
            tailor=tailor,
            use_github_skill=use_github_skill,
            auto_preset=auto_preset,
            monitor=monitor,
            with_perplexity=with_perplexity,
            with_readarr=with_readarr,
            with_wayback=with_wayback,
            with_feeds=with_feeds,
            feed_limit=feed_limit,
            feed_pack=feed_pack,
            html_report=html_report,
            open_report=open_report,
            report_file=report_file,
            publisher=publisher,
        )
        search_success = True
    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        log_status(f"Search failed: {e}", provider="dogpile", status="ERROR", error_type="unknown")
        publisher.complete(False, error=str(e))
    finally:
        if search_success:
            publisher.complete(True)
        # End monitoring and log summary
        end_error_session("completed" if search_success else "failed")
        end_monitor(search_success)

        # Print error summary with actionable hints
        summary = get_error_summary()
        session = summary.get("current_session")
        if session and session.get("error_count", 0) > 0:
            console.print("\n[yellow]--- Error Summary (with troubleshooting) ---[/yellow]")

            # Show succeeded providers first (partial success)
            if session.get("succeeded"):
                console.print(f"  [green]Succeeded:[/green] {', '.join(session['succeeded'])}")

            # Show failed providers with actionable hints
            if session.get("failed"):
                console.print(f"  [red]Failed:[/red]")
                recent_errors = summary.get("recent_errors", [])
                for provider in session["failed"]:
                    # Find the most recent error for this provider
                    provider_errors = [e for e in recent_errors if e.get("provider") == provider]
                    if provider_errors:
                        err = provider_errors[-1]
                        msg = err.get("message", "Unknown error")[:80]
                        hint_info = get_error_hint(provider, msg)
                        console.print(f"    [cyan]{provider}:[/cyan] {msg}")
                        if hint_info:
                            console.print(f"      → [yellow]{hint_info['hint']}[/yellow]")
                    else:
                        console.print(f"    [cyan]{provider}:[/cyan] Failed (check logs)")

            # Show rate limits with recovery hints
            if session.get("rate_limits_hit"):
                console.print(f"  [yellow]Rate limits hit:[/yellow]")
                for provider, count in session["rate_limits_hit"].items():
                    hint_info = get_error_hint(provider, "rate limit")
                    hint_text = hint_info["hint"] if hint_info else "Wait 30-60s before retrying"
                    console.print(f"    {provider}: {count}x → {hint_text}")

            console.print(f"\n  [dim]Total errors: {session.get('error_count', 0)} | Log: dogpile_errors.json[/dim]")


@app.command()
def resources(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category (security, default)"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    search_query: Optional[str] = typer.Option(None, "--search", "-s", help="Search resources"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    markdown: bool = typer.Option(False, "--markdown", help="Output as Markdown table"),
):
    """List and search available research resources."""
    if not REGISTRY_AVAILABLE:
        console.print("[red]Resource registry not available. Check resources/ directory.[/red]")
        raise typer.Exit(1)

    registry = get_registry()

    # Build filter chain
    results = registry.all()

    if category:
        results = [r for r in results if r.category == category]

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        results = [r for r in results if r.matches_tags(tag_list)]

    if search_query:
        results = [r for r in results if r.matches_search(search_query)]

    # Output
    if output_json:
        output = [
            {
                "name": r.name,
                "url": r.url,
                "api_url": r.api_url,
                "type": r.type,
                "tags": r.tags,
                "category": r.category,
                "auth_required": r.auth_required,
                "description": r.description,
            }
            for r in results
        ]
        print(json.dumps(output, indent=2))
    elif markdown:
        print(registry.to_markdown_table(results))
    else:
        console.print(f"[bold]Found {len(results)} resources:[/bold]\n")
        for r in results:
            auth_badge = "[yellow]AUTH[/yellow]" if r.auth_required else "[green]FREE[/green]"
            console.print(f"  [{r.category}] [bold]{r.name}[/bold] {auth_badge}")
            console.print(f"    [dim]{r.url}[/dim]")
            console.print(f"    Tags: [cyan]{', '.join(r.tags[:5])}[/cyan]")
            console.print(f"    {r.description}")
            console.print()


@app.command()
def presets(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List available research presets for agents."""
    if not REGISTRY_AVAILABLE:
        console.print("[red]Resource registry not available.[/red]")
        raise typer.Exit(1)

    registry = get_registry()
    preset_list = registry.list_presets()

    if output_json:
        print(json.dumps(preset_list, indent=2))
    else:
        console.print("[bold]Available Presets[/bold]\n")
        console.print("Pick ONE preset that matches your research goal:\n")

        for p in preset_list:
            api_badge = f"[green]{len(p['api_resources'])} APIs[/green]" if p['api_resources'] else ""
            sites_badge = f"[cyan]{p['brave_sites_count']} sites[/cyan]"

            console.print(f"  [bold]{p['name']}[/bold] {sites_badge} {api_badge}")
            console.print(f"    {p['description']}")
            console.print(f"    [dim]Use when: {p['use_when'][0] if p['use_when'] else 'General'}[/dim]")
            console.print()

        console.print("[dim]Usage: dogpile search 'query' --preset red_team[/dim]")
        console.print("[dim]       dogpile search 'query' --auto-preset[/dim]")


@app.command()
def resource_stats():
    """Show statistics about available resources."""
    if not REGISTRY_AVAILABLE:
        console.print("[red]Resource registry not available.[/red]")
        raise typer.Exit(1)

    registry = get_registry()
    stats = registry.stats()

    console.print("[bold]Resource Registry Statistics[/bold]\n")
    console.print(f"  Total resources: [cyan]{stats['total_resources']}[/cyan]")
    console.print(f"  Unique tags: [cyan]{stats['unique_tags']}[/cyan]")
    console.print(f"  With API: [cyan]{stats['with_api']}[/cyan]")
    console.print(f"  Free: [green]{stats['free']}[/green]")
    console.print(f"  Auth required: [yellow]{stats['auth_required']}[/yellow]")
    console.print("\n  [bold]Categories:[/bold]")
    for cat, count in stats["categories"].items():
        console.print(f"    {cat}: {count}")


@app.command()
def errors(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    clear: bool = typer.Option(False, "--clear", help="Clear error log after display"),
):
    """Show error summary and rate limit status for debugging."""
    from dogpile.error_tracking import get_error_summary, get_tracker
    from pathlib import Path

    summary = get_error_summary()

    if output_json:
        print(json.dumps(summary, indent=2))
    else:
        console.print("[bold]Dogpile Error Summary[/bold]\n")

        # Current/last session
        session = summary.get("current_session")
        if session:
            console.print(f"[bold cyan]Last Session:[/bold cyan] {session.get('session_id', 'unknown')}")
            console.print(f"  Query: {session.get('query', 'N/A')}")
            console.print(f"  Status: {session.get('status', 'unknown')}")
            if session.get("succeeded"):
                console.print(f"  [green]Succeeded:[/green] {', '.join(session['succeeded'])}")
            if session.get("failed"):
                console.print(f"  [red]Failed:[/red] {', '.join(session['failed'])}")
            if session.get("rate_limits_hit"):
                console.print(f"  [yellow]Rate limits:[/yellow] {session['rate_limits_hit']}")
            console.print(f"  Error count: {session.get('error_count', 0)}")
            console.print()

        # Rate limits by provider
        rate_limits = summary.get("rate_limits", {})
        if rate_limits:
            console.print("[bold yellow]Rate Limit Status:[/bold yellow]")
            for provider, state in rate_limits.items():
                hits = state.get("total_hits", 0)
                backoff = state.get("backoff_multiplier", 1.0)
                last_hit = state.get("last_hit", "never")
                status = "[red]ACTIVE[/red]" if backoff > 1.5 else "[green]OK[/green]"
                console.print(f"  {provider}: {hits} hits, backoff x{backoff:.1f} {status}")
                if last_hit != "never":
                    console.print(f"    Last hit: {last_hit}")
            console.print()

        # Recent errors
        recent = summary.get("recent_errors", [])
        if recent:
            console.print(f"[bold red]Recent Errors ({len(recent)}):[/bold red]")
            for err in recent[-5:]:  # Last 5
                console.print(f"  [{err.get('provider', '?')}] {err.get('error_type', 'unknown')}: {err.get('message', '')[:60]}")
            console.print()

        # Total stats
        console.print(f"[dim]Total errors logged: {summary.get('total_errors', 0)}[/dim]")

        # Log file locations
        tracker = get_tracker()
        console.print(f"\n[dim]Error log: {tracker.error_log}[/dim]")
        console.print(f"[dim]Human log: {tracker.human_log}[/dim]")

    if clear:
        # Clear error logs
        tracker = get_tracker()
        try:
            tracker.error_log.unlink(missing_ok=True)
            tracker.human_log.unlink(missing_ok=True)
            Path(tracker.log_dir / "rate_limit_state.json").unlink(missing_ok=True)
            console.print("[green]Error logs cleared.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to clear logs: {e}[/red]")


@app.command()
def extract(
    url: str = typer.Argument(..., help="URL of the paper/document to extract"),
    scope: str = typer.Option("dream-research", "--scope", "-s", help="Memory scope to store QRAs"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags (auto-detected if omitted)"),
    domain_context: Optional[str] = typer.Option(None, "--context", "-c", help="Domain context hint for QRA extraction"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and extract but don't store to memory"),
    output_json: bool = typer.Option(False, "--json", help="Output QRA summary as JSON"),
):
    """Fetch a paper, extract QRA knowledge chunks, and store to /memory.

    Use when a /dogpile search found a highly relevant paper and you want to
    deeply extract and persist its knowledge for multi-hop graph traversal.

    Examples:
        dogpile extract https://pmc.ncbi.nlm.nih.gov/.../PMC12345 --scope dream-research
        dogpile extract paper.pdf --scope behavioral --tags "neuroscience,memory"
        dogpile extract https://arxiv.org/abs/... --context "reinforcement learning" --dry-run
    """
    import os as _os
    import subprocess as sp
    import tempfile

    import httpx

    skills_dir = _SCRIPT_DIR.parent
    _CHUTES_CALL_URL = _os.environ.get("CHUTES_CALL_URL", "http://localhost:8630")
    _MEMORY_SOCKET = f"/run/user/{_os.getuid()}/embry/memory.sock"
    _MEMORY_HTTP = _os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")

    def _mem_client() -> httpx.Client:
        socket = Path(_MEMORY_SOCKET)
        if socket.exists():
            transport = httpx.HTTPTransport(uds=str(socket))
            return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
        return httpx.Client(base_url=_MEMORY_HTTP, timeout=30.0)

    # Resolve fetcher for URL → fetch pipeline
    fetcher_sh = skills_dir / "fetcher" / "run.sh"
    if not fetcher_sh.exists():
        fetcher_sh = Path.home() / ".pi" / "skills" / "fetcher" / "run.sh"

    console.print(f"[cyan]Extracting from: {url}[/cyan]")
    console.print(f"[cyan]Scope: {scope} | Tags: {tags or 'auto'}[/cyan]")

    if dry_run:
        console.print(f"[dim][DRY RUN] Would fetch {url} and extract to scope {scope}[/dim]")
        return

    # Step 1: Fetch URL to temp file
    fetch_dir = Path(tempfile.mkdtemp(prefix="dogpile_extract_"))
    fetch_args = ["bash", str(fetcher_sh), "get", url, "--out", str(fetch_dir)]

    fetch_result = sp.run(fetch_args, capture_output=True, text=True, timeout=300)
    fetched_files = list(fetch_dir.glob("*"))
    if not fetched_files or fetch_result.returncode != 0:
        console.print(f"[red]Fetch failed for {url}[/red]")
        if fetch_result.stderr:
            console.print(f"[dim red]{fetch_result.stderr[:200]}[/dim red]")
        raise typer.Exit(1)
    fetched_file = fetched_files[0]

    # Step 2: Extract QRAs via chutes-call /batch HTTP service (port 8630)
    try:
        text = fetched_file.read_text()[:3000]
    except Exception as e:
        console.print(f"[red]Cannot read fetched file: {e}[/red]")
        raise typer.Exit(1)

    qra_system_prompt = (
        "You are a knowledge extraction assistant. Respond with valid JSON only. "
        'Return {"items": [{"question": "string", "reasoning": "string", "answer": "string"}, ...]}'
    )
    payload = {
        "requests": [{
            "messages": [
                {"role": "system", "content": qra_system_prompt},
                {"role": "user", "content": f"Extract all grounded knowledge items from this text.\n\nText:\n{text}\n\nJSON:"},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        }],
        "concurrency": 1,
        "tenacious": True,
        "caller": "dogpile-extract",
    }

    try:
        resp = httpx.post(f"{_CHUTES_CALL_URL}/batch", json=payload, timeout=120.0)
        resp.raise_for_status()
        batch_results = resp.json()
    except Exception as e:
        console.print(f"[red]QRA extraction failed via chutes-call /batch: {e}[/red]")
        raise typer.Exit(1)

    # Parse LLM response and store QRAs to memory
    extracted_count = 0
    stored_count = 0
    if batch_results and isinstance(batch_results, list) and batch_results[0].get("ok"):
        try:
            content_str = batch_results[0].get("content", "")
            data = json.loads(content_str) if isinstance(content_str, str) else content_str
            items = data.get("items", []) if isinstance(data, dict) else []
            extracted_count = len(items)
        except (json.JSONDecodeError, TypeError):
            items = []

        if items:
            client = _mem_client()
            try:
                tag_list = [t.strip() for t in tags.split(",")] if tags else ["qra"]
                for item in items:
                    q = item.get("question", "")
                    a = item.get("answer", "")
                    r = item.get("reasoning", "")
                    if not q or not a:
                        continue
                    solution = f"**Reasoning:** {r}\n\n**Answer:** {a}" if r else a
                    try:
                        mem_resp = client.post("/learn", json={
                            "problem": q, "solution": solution,
                            "scope": scope, "tags": tag_list,
                        })
                        if mem_resp.status_code == 200:
                            stored_count += 1
                    except Exception as e:
                        logger.warning("QRA memory store failed for one item: {}", e)
            finally:
                client.close()

    result_data = {"extracted": extracted_count, "stored": stored_count, "scope": scope}
    console.print(f"[green]Extracted {extracted_count} QRAs, stored={stored_count} to scope '{scope}'[/green]")
    if output_json:
        result_data["tags"] = [t.strip() for t in tags.split(",")] if tags else ["auto"]
        print(json.dumps(result_data, indent=2))

    if extracted_count == 0:
        console.print("[yellow]No QRAs extracted from document[/yellow]")

    # Store tag metadata if tags were explicitly provided
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        tags_csv = ",".join(tag_list)
        try:
            client = _mem_client()
            client.post("/learn", json={
                "problem": f"Source tags for {url}",
                "solution": f"Tags: {tags_csv}",
                "scope": scope,
                "tags": tag_list,
            })
            client.close()
            console.print(f"[green]Tagged with: {tags_csv}[/green]")
        except Exception:
            console.print("[yellow]Tag metadata storage skipped[/yellow]")


@app.command()
def version():
    """Show version."""
    console.print(f"Dogpile v{VERSION} (Modular)")


if __name__ == "__main__":
    app()
