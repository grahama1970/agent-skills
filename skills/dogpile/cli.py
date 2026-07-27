#!/usr/bin/env python3
"""Dogpile: Comprehensive deep search aggregator.

Orchestrates searches across:
- Brave Search (Web)
- Concurrent Brave question lanes (retired Perplexity replacement)
- GitHub (Repos & Issues)
- ArXiv (Papers)
- YouTube (Videos)
- Readarr (Books/Usenet, opt-in)
- Wayback Machine (Archives, opt-in)

Resilience features (based on 2025-2026 best practices):
- Tenacity retries with exponential backoff + jitter
- Per-provider semaphores for concurrency control
- Rate limit header parsing (Retry-After, x-ratelimit-*)
"""
import json
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, Optional

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import typer
from rich.markdown import Markdown
from rich.live import Live
from rich.table import Table

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
    ErrorType,
)
from dogpile.error_hints import get_error_hint, summarize_errors_with_hints
from dogpile.task_monitor_integration import (
    start_search as start_monitor,
    end_search as end_monitor,
    get_monitor,
)
from dogpile.codex import (
    search_codex,
    search_codex_knowledge,
    tailor_queries_for_services,
    analyze_query,
)
from dogpile.brave import (
    build_brave_question_queries,
    search_brave,
    search_brave_questions,
    run_stage2_brave,
)
from dogpile.arxiv_search import search_arxiv, run_stage2_arxiv
from dogpile.github_search import search_github, search_github_via_skill
from dogpile.github_deep import run_stage2_github
from dogpile.youtube_search import search_youtube, run_stage2_youtube
from dogpile.wayback import search_wayback
from dogpile.discord import search_discord_messages
from dogpile.readarr import search_readarr
from dogpile.feeds import search_feeds
from dogpile.html_report import write_html_report
from dogpile.synthesis import generate_report

PARTIAL_RESULTS_PATH = _SCRIPT_DIR / "dogpile_partial_results.json"

# Memory integration (graceful degradation)
try:
    from dogpile.memory_integration import recall_prior_research, learn_research, learn_execution_batch
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    _HAS_MEMORY_INTEGRATION = False


def _flush_execution_records(stage: str) -> None:
    """Drain execution records for a stage and batch-learn to memory."""
    if not _HAS_MEMORY_INTEGRATION:
        return
    try:
        from dogpile.utils import get_execution_collector
        collector = get_execution_collector()
        if collector:
            records = collector.drain(stage)
            if records:
                learn_execution_batch(records)
    except Exception:
        pass  # Graceful degradation — don't block search on metadata failures


def _timed_stage2(name: str, func, *args, **kwargs):
    """Run a stage2 function with manual timing recorded to the collector."""
    import time as _time
    from dogpile.utils import get_execution_collector, ExecutionRecord

    t0 = _time.monotonic()
    outcome = "success"
    error_message = None
    try:
        result = func(*args, **kwargs)
        return result
    except Exception as e:
        outcome = "failure"
        error_message = str(e)[:200]
        raise
    finally:
        collector = get_execution_collector()
        if collector:
            collector.add(ExecutionRecord(
                provider=name,
                query=str(args[0])[:200] if args else "",
                stage="stage2",
                outcome=outcome,
                wall_clock_s=round(_time.monotonic() - t0, 3),
                error_message=error_message,
            ))


def _result_ok(result: Any) -> bool:
    """Return True when a Dogpile result is not an error envelope."""
    if isinstance(result, str):
        return not result.startswith("Error:")
    return not (isinstance(result, dict) and "error" in result)


def _summarize_result(name: str, result: Any) -> Dict[str, Any]:
    """Create a compact summary for incremental progress events."""
    if isinstance(result, dict) and result.get("skipped"):
        return {
            "ok": False,
            "skipped": str(result.get("skipped", ""))[:240],
            "replacement": result.get("replacement"),
        }
    if not _result_ok(result):
        if isinstance(result, dict):
            return {"ok": False, "error": str(result.get("error", "Unknown error"))[:240]}
        return {"ok": False, "error": str(result)[:240]}

    summary: Dict[str, Any] = {"ok": True}
    if name == "brave" and isinstance(result, dict):
        web_results = result.get("web", {}).get("results", []) or result.get("results", [])
        summary["result_count"] = len(web_results)
        if result.get("query"):
            summary["query"] = result["query"]
    elif name == "brave_questions" and isinstance(result, dict):
        summary["queries"] = len(result.get("queries", []) or [])
        summary["succeeded"] = result.get("succeeded", 0)
        summary["total"] = result.get("total", 0)
    elif name == "github" and isinstance(result, dict):
        summary["repos"] = len(result.get("repos", []) or [])
        summary["issues"] = len(result.get("issues", []) or [])
    elif name == "arxiv" and isinstance(result, dict):
        summary["papers"] = len(result.get("items", []) or [])
    elif name in {"youtube", "readarr"} and isinstance(result, list):
        summary["result_count"] = len(result)
    elif name == "feeds" and isinstance(result, dict):
        summary["returncode"] = result.get("returncode")
        summary["limit"] = result.get("limit")
        stdout = str(result.get("stdout", ""))
        summary["output_chars"] = len(stdout)
    elif name == "wayback" and isinstance(result, dict):
        summary["has_snapshot"] = bool(result.get("closest") or result.get("snapshots"))
    elif name == "codex_knowledge":
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        summary["excerpt"] = text[:180]
    elif name == "stage2_github" and isinstance(result, dict):
        summary["repos_examined"] = len(result.get("github_details", []) or [])
        summary["target_repo"] = result.get("target_repo")
        github_deep = result.get("github_deep", {}) or {}
        summary["code_matches"] = len(github_deep.get("code_matches", []) or [])
    elif name == "stage2_arxiv" and isinstance(result, dict):
        summary["paper_details"] = len(result.get("arxiv_details", []) or [])
        summary["deep_extractions"] = len(result.get("arxiv_deep", []) or [])
    elif name == "stage2_youtube" and isinstance(result, list):
        summary["transcripts"] = len(result)
    elif name == "stage2_brave" and isinstance(result, list):
        summary["deep_extractions"] = len(result)
    elif name == "report" and isinstance(result, str):
        summary["chars"] = len(result)
        summary["lines"] = len(result.splitlines())
    else:
        summary["type"] = type(result).__name__
    return summary


class PartialResultsPublisher:
    """Persist partial Dogpile results and emit machine-readable progress events."""

    def __init__(self, requested_query: str):
        self.path = PARTIAL_RESULTS_PATH
        self.state: Dict[str, Any] = {
            "requested_query": requested_query,
            "effective_query": requested_query,
            "status": "starting",
            "updated_at": time.time(),
            "partial_results_path": str(self.path),
            "tailored_queries": {},
            "results": {
                "stage1": {},
                "stage2": {},
            },
            "events": [],
        }
        self._write()
        self.emit(
            {
                "event": "search_started",
                "requested_query": requested_query,
            }
        )

    def _write(self) -> None:
        self.state["updated_at"] = time.time()
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
        tmp_path.replace(self.path)

    def emit(self, event: Dict[str, Any]) -> None:
        payload = {**event, "partial_results_path": str(self.path), "ts": time.time()}
        events = self.state.setdefault("events", [])
        events.append(payload)
        if len(events) > 50:
            del events[:-50]
        self.state["last_event"] = payload
        self._write()
        typer.echo(f"[dogpile-event] {json.dumps(payload, ensure_ascii=False)}", err=True)

    def set_effective_query(self, query: str) -> None:
        self.state["effective_query"] = query
        self._write()

    def set_tailored_queries(self, tailored: Dict[str, str]) -> None:
        self.state["tailored_queries"] = tailored
        self.state["status"] = "running"
        self._write()
        self.emit({"event": "tailored_queries_ready", "services": sorted(tailored.keys())})

    def publish_result(self, stage: str, name: str, result: Any) -> None:
        self.state["results"].setdefault(stage, {})[name] = result
        self.emit(
            {
                "event": "partial_result",
                "stage": stage,
                "provider": name,
                "summary": _summarize_result(name, result),
            }
        )

    def publish_report(self, report: str, report_path: Optional[Path] = None) -> None:
        self.state["final_report"] = report
        if report_path:
            self.state["html_report_path"] = str(report_path)
        self.emit(
            {
                "event": "report_ready",
                "stage": "report",
                "provider": "report",
                "summary": _summarize_result("report", report),
                "html_report_path": str(report_path) if report_path else None,
            }
        )

    def complete(self, success: bool, error: Optional[str] = None) -> None:
        self.state["status"] = "completed" if success else "failed"
        if error:
            self.state["error"] = error
        self.emit(
            {
                "event": "search_finished",
                "status": self.state["status"],
                "error": error,
            }
        )


def _run_github_stage2_bundle(
    github_res: Dict[str, Any],
    query: str,
    is_code_related: bool,
) -> Dict[str, Any]:
    """Run the full GitHub stage2 pipeline, including code explanation."""
    github_details, github_deep, target_repo, deep_code_res = _timed_stage2(
        "github",
        run_stage2_github,
        github_res,
        query,
        is_code_related,
        search_codex,
    )
    code_explanation = None
    if is_code_related and github_deep and target_repo:
        from dogpile.code_explanation import explain_code_results
        code_explanation = explain_code_results(query, target_repo, github_deep)
    return {
        "github_details": github_details,
        "github_deep": github_deep,
        "target_repo": target_repo,
        "deep_code_res": deep_code_res,
        "code_explanation": code_explanation,
    }


def _run_arxiv_stage2_bundle(arxiv_res: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Run the ArXiv stage2 pipeline."""
    arxiv_details, arxiv_deep = _timed_stage2(
        "arxiv",
        run_stage2_arxiv,
        arxiv_res,
        query,
        search_codex,
    )
    return {
        "arxiv_details": arxiv_details,
        "arxiv_deep": arxiv_deep,
    }


def _collect_evidence_digest(
    query: str,
    stage1_results: Dict[str, Any],
    stage2_results: Dict[str, Any],
    max_chars: int = 9000,
) -> str:
    """Collect compact, cited evidence for automatic synthesis."""
    lines = [f"Query: {query}", ""]

    def add_result(prefix: str, title: str, url: str = "", description: str = "") -> None:
        chunk = f"- {prefix}: {title}"
        if url:
            chunk += f" ({url})"
        if description:
            chunk += f" -- {description[:280]}"
        lines.append(chunk)

    brave_res = stage1_results.get("brave", {})
    if isinstance(brave_res, dict):
        lines.append("Brave primary results:")
        for item in (brave_res.get("web", {}).get("results", []) or brave_res.get("results", []))[:5]:
            add_result("brave", item.get("title", "No title"), item.get("url", ""), item.get("description", ""))
        lines.append("")

    brave_questions = stage1_results.get("brave_questions", {})
    if isinstance(brave_questions, dict):
        lines.append("Concurrent Brave question results:")
        for run in brave_questions.get("results", [])[:3]:
            result = run.get("result", {})
            lines.append(f"Question: {run.get('query', '')}")
            if isinstance(result, dict):
                for item in (result.get("web", {}).get("results", []) or result.get("results", []))[:3]:
                    add_result("brave_question", item.get("title", "No title"), item.get("url", ""), item.get("description", ""))
        lines.append("")

    github_res = stage1_results.get("github", {})
    if isinstance(github_res, dict):
        lines.append("GitHub results:")
        for repo in (github_res.get("repos", []) or [])[:5]:
            add_result("github_repo", repo.get("fullName", "unknown"), repo.get("url") or repo.get("html_url", ""), repo.get("description", ""))
        for issue in (github_res.get("issues", []) or [])[:3]:
            add_result("github_issue", issue.get("title", "unknown"), issue.get("url") or issue.get("html_url", ""))
        lines.append("")

    arxiv_res = stage1_results.get("arxiv", {})
    if isinstance(arxiv_res, dict):
        lines.append("ArXiv results:")
        for paper in (arxiv_res.get("items", []) or [])[:5]:
            add_result("arxiv", paper.get("title", "unknown"), paper.get("abs_url", ""), paper.get("abstract", ""))
        lines.append("")

    youtube_res = stage1_results.get("youtube", [])
    if isinstance(youtube_res, list):
        lines.append("YouTube results:")
        for video in youtube_res[:5]:
            add_result("youtube", video.get("title", "unknown"), video.get("url", ""), video.get("description", ""))
        lines.append("")

    feeds_res = stage1_results.get("feeds", {})
    if isinstance(feeds_res, dict) and feeds_res.get("stdout"):
        lines.append("Feed monitor dry-run output:")
        lines.append(str(feeds_res.get("stdout", ""))[-1200:])
        lines.append("")

    for stage_name, stage_result in stage2_results.items():
        lines.append(f"{stage_name} deep results summary: {json.dumps(_summarize_result(stage_name, stage_result), ensure_ascii=False)}")

    digest = "\n".join(lines)
    return digest[:max_chars]


def _generate_auto_synthesis(
    query: str,
    stage1_results: Dict[str, Any],
    stage2_results: Dict[str, Any],
) -> str:
    """Generate a concise synthesis from retrieved evidence, degrading cleanly."""
    digest = _collect_evidence_digest(query, stage1_results, stage2_results)
    prompt = f"""Synthesize this Dogpile research evidence for the user query.

Rules:
- Ground every substantive claim in the evidence below.
- Prefer Brave, ArXiv, YouTube, GitHub, and feed-style retrieved sources over model prior knowledge.
- Mention important gaps, contradictions, or skipped sources.
- Treat threat-intel/feed hits as enrichment-only unless corroborated by multiple high-confidence signals.
- Be concise: 5-8 bullets plus a short "Most useful sources" list.
- Do not invent citations or URLs.

Evidence:
{digest}
"""
    return search_codex(prompt)


def run_stage1_searches(
    tailored: Dict[str, str],
    query: str,
    use_github_skill: bool,
    is_code_related: bool,
    with_perplexity: bool = False,
    with_readarr: bool = False,
    with_wayback: bool = False,
    with_feeds: bool = False,
    feed_limit: int = 3,
    feed_pack: str = "security_code",
    publisher: Optional[PartialResultsPublisher] = None,
    on_result=None,
    monitor=None,
) -> Dict[str, Any]:
    """Stage 1: Run broad parallel searches across all providers.

    Uses ThreadPoolExecutor with provider semaphores for rate limit protection.

    Args:
        tailored: Dict of service-specific queries
        query: Original search query
        use_github_skill: Whether to use /github-search skill
        is_code_related: Whether query is code-related
        with_perplexity: Deprecated; Perplexity is retired and never called.
        with_readarr: Include local Readarr/Usenet book search.
        with_wayback: Include Wayback archive lookup.
        with_feeds: Include consume-feed RSS monitor dry-run.
        feed_limit: Max items per configured feed source.
        feed_pack: Dogpile feed pack name, or empty string for consume-feed config.

    Returns:
        Dict with results from each provider
    """
    # Explicitly define the callable to avoid lambda/decoration issues
    if use_github_skill:
        def github_search_func(q):
            return search_github_via_skill(q, deep=is_code_related, treesitter=False, taxonomy=False)
    else:
        def github_search_func(q):
            return search_github(q)

    STAGE1_TIMEOUT = 180  # 3 minutes max for all Stage 1 searches

    providers = {
        "brave": (search_brave, [tailored["brave"]]),
        "brave_questions": (search_brave_questions, [build_brave_question_queries(query, tailored)]),
        "github": (github_search_func, [tailored["github"]]),
        "arxiv": (search_arxiv, [tailored["arxiv"]]),
        "youtube": (search_youtube, [tailored["youtube"]]),
        "codex_knowledge": (search_codex_knowledge, [query]),
        # Discord removed: requires bot tokens + guild config that most users won't have
    }

    if with_readarr:
        providers["readarr"] = (search_readarr, [tailored.get("readarr", query)])
    if with_wayback:
        providers["wayback"] = (search_wayback, [query])
    if with_feeds:
        providers["feeds"] = (search_feeds, [query, feed_limit, None, feed_pack])

    # Provider status for Rich live display
    status: Dict[str, str] = {name: "[dim]waiting[/dim]" for name in providers}

    def _build_progress_table() -> Table:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Provider", width=16)
        table.add_column("Status", width=40)
        for name in providers:
            table.add_row(f"  [cyan]{name}[/cyan]", status[name])
        done = sum(1 for s in status.values() if "waiting" not in s and "searching" not in s)
        table.add_row("", f"\n  [bold]{done}/{len(providers)} complete[/bold]")
        return table

    results: Dict[str, Any] = {}
    use_live = console.is_terminal

    with ThreadPoolExecutor(max_workers=8) as executor:
        if monitor:
            for name in providers:
                monitor.start_provider(name)
        future_to_name = {
            executor.submit(fn, *args): name
            for name, (fn, args) in providers.items()
        }
        # Mark all as searching
        for name in providers:
            status[name] = "[yellow]searching...[/yellow]"

        live_ctx = Live(_build_progress_table(), console=console, refresh_per_second=4) if use_live else None
        try:
            if live_ctx:
                live_ctx.__enter__()
            for future in as_completed(future_to_name, timeout=STAGE1_TIMEOUT):
                name = future_to_name[future]
                try:
                    results[name] = future.result(timeout=5)
                    status[name] = "[green]done[/green]"
                    if monitor:
                        monitor.complete_provider(name, success=True)
                except Exception as e:
                    error_msg = str(e)
                    hint_info = get_error_hint(name, error_msg)
                    hint_suffix = f" → {hint_info['hint']}" if hint_info else ""
                    log_status(f"{name} failed: {error_msg[:60]}{hint_suffix}", provider=name, status="ERROR")
                    results[name] = {"error": error_msg, "hint": hint_info["hint"] if hint_info else None}
                    status[name] = f"[red]error[/red]"
                    if monitor:
                        monitor.complete_provider(name, success=False, error_msg=error_msg)
                if publisher:
                    publisher.publish_result("stage1", name, results[name])
                if on_result:
                    on_result(name, results[name])
                if live_ctx:
                    live_ctx.update(_build_progress_table())
        except FuturesTimeoutError:
            # Cancel orphaned futures that are still running after timeout
            for future, name in future_to_name.items():
                if not future.done():
                    future.cancel()
                    log_status(f"{name} cancelled after timeout", provider=name, status="ERROR")
                    hint_info = get_error_hint(name, "timeout")
                    results[name] = {"error": "Timed out after stage1 budget", "hint": hint_info["hint"] if hint_info else None}
                    if monitor:
                        monitor.complete_provider(name, success=False, error_msg="Timed out after stage1 budget")
        finally:
            if live_ctx:
                live_ctx.__exit__(None, None, None)

    # Fill in any providers that timed out with helpful hints
    for name in providers:
        if name not in results:
            timeout_msg = f"Timed out after {STAGE1_TIMEOUT}s"
            hint_info = get_error_hint(name, "timeout")
            hint_suffix = f" → {hint_info['hint']}" if hint_info else ""
            log_status(f"{name} {timeout_msg}{hint_suffix}", provider=name, status="ERROR")
            results[name] = {"error": timeout_msg, "hint": hint_info["hint"] if hint_info else None}
            if monitor:
                monitor.complete_provider(name, success=False, error_msg=timeout_msg)
            if publisher:
                publisher.publish_result("stage1", name, results[name])
            if on_result:
                on_result(name, results[name])

    skipped = {
        "perplexity": {
            "skipped": "Perplexity is retired for Dogpile; API calls are disabled.",
            "replacement": "brave_questions",
            "hint": "Use Dogpile's concurrent Brave question lane for free web-backed research.",
        }
    }
    if with_perplexity:
        skipped["perplexity"]["requested"] = True
        skipped["perplexity"]["hint"] = "The deprecated flag intentionally does not call the paid Perplexity API."
    if not with_readarr:
        skipped["readarr"] = {
            "skipped": "Readarr/Usenet is disabled by default.",
            "hint": "Pass --with-readarr when local Readarr/ingest-book search is intentionally required.",
        }
    if not with_wayback:
        skipped["wayback"] = {
            "skipped": "Wayback archive lookup is disabled by default.",
            "hint": "Pass --with-wayback when historical snapshots are intentionally required.",
        }
    if not with_feeds:
        skipped["feeds"] = {
            "skipped": "Feed monitors are disabled by default.",
            "hint": "Pass --with-feeds to run configured consume-feed RSS monitors as a dry-run lane.",
        }

    for name, result in skipped.items():
        if name not in results:
            results[name] = result
            if publisher:
                publisher.publish_result("stage1", name, result)
            if monitor:
                monitor.skip_provider(name)

    return results


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


def _run_search(
    query: str,
    preset: Optional[str],
    interactive: bool,
    tailor: bool,
    use_github_skill: bool,
    auto_preset: bool,
    monitor,
    with_perplexity: bool = False,
    with_readarr: bool = False,
    with_wayback: bool = False,
    with_feeds: bool = False,
    feed_limit: int = 3,
    feed_pack: str = "security_code",
    html_report: bool = False,
    open_report: bool = False,
    report_file: Optional[Path] = None,
    publisher: Optional[PartialResultsPublisher] = None,
):
    """Internal search implementation."""
    # Pre-hook: Recall prior research on this topic to avoid redundant API calls
    if _HAS_MEMORY_INTEGRATION:
        try:
            prior = recall_prior_research(query)
            if prior:
                console.print("[dim]Found prior research on this topic in memory.[/dim]")
                console.print(f"[dim]{prior[:200]}...[/dim]" if len(prior) > 200 else f"[dim]{prior}[/dim]")
        except Exception as e:
            console.print(f"[dim]Memory recall skipped: {e}[/dim]")

    # 0. Handle preset selection
    active_preset = None
    preset_brave_query = None

    if REGISTRY_AVAILABLE:
        registry = get_registry()

        # Auto-detect preset if requested
        if auto_preset and not preset:
            suggested = registry.suggest_preset(query)
            if suggested != "general":
                preset = suggested
                console.print(f"[dim]Auto-detected preset: {preset}[/dim]")

        # Load preset if specified
        if preset:
            active_preset = registry.get_preset(preset)
            if active_preset:
                console.print(f"[bold magenta]Using preset:[/bold magenta] {preset} - {active_preset.description}")
                console.print(f"[dim]  Brave sites: {len(active_preset.brave_sites)} | API resources: {active_preset.api_resources}[/dim]")
                # Generate site-filtered Brave query
                if active_preset.brave_sites:
                    preset_brave_query = active_preset.get_brave_query(query)
            else:
                console.print(f"[yellow]Warning: Preset '{preset}' not found, using default search[/yellow]")

    # 1. Analyze Query (Ambiguity + Intent)
    query, is_code_related = analyze_query(query, interactive)
    if publisher:
        publisher.set_effective_query(query)

    console.print(f"[bold blue]Dogpiling on:[/bold blue] {query} (Code Related: {is_code_related})...")

    # 2. Tailor queries for each service (expert-level optimization)
    monitor.start_stage("tailoring")
    if tailor:
        tailored = tailor_queries_for_services(query, is_code_related)
        console.print("[dim]Tailored queries:[/dim]")
        for svc, q in tailored.items():
            console.print(f"  [cyan]{svc}:[/cyan] {q[:60]}...")
    else:
        # Use same query for all services
        tailored = {svc: query for svc in ["arxiv", "perplexity", "brave", "github", "youtube", "readarr", "feeds"]}

    # Override Brave query with preset-filtered query if active
    if preset_brave_query:
        tailored["brave"] = preset_brave_query
        console.print(f"  [magenta]brave (preset):[/magenta] {preset_brave_query[:80]}...")
    if publisher:
        publisher.set_tailored_queries(tailored)
    monitor.complete_stage("tailoring")

    stage2_lock = threading.Lock()
    stage2_futures = []
    stage2_results: Dict[str, Any] = {}

    def schedule_stage2(name: str, stage1_result: Any) -> None:
        stage_map = {
            "github": ("stage2_github", lambda: _run_github_stage2_bundle(stage1_result, query, is_code_related)),
            "arxiv": ("stage2_arxiv", lambda: _run_arxiv_stage2_bundle(stage1_result, query)),
            "youtube": ("stage2_youtube", lambda: _timed_stage2("youtube", run_stage2_youtube, stage1_result)),
            "brave": ("stage2_brave", lambda: _timed_stage2("brave", run_stage2_brave, stage1_result, query, search_codex)),
        }
        if name not in stage_map:
            return

        monitor_stage, runner = stage_map[name]
        monitor.start_stage(monitor_stage)
        future = stage2_executor.submit(runner)
        stage2_futures.append(future)

        def _store_stage2_result(done_future, provider_name=name, monitor_name=monitor_stage):
            try:
                result = done_future.result()
            except Exception as e:
                result = {"error": str(e)}
            with stage2_lock:
                stage2_results[provider_name] = result
            if publisher:
                publisher.publish_result("stage2", monitor_name, result)
            monitor.complete_stage(monitor_name)

        future.add_done_callback(_store_stage2_result)

    # Stage 1: Broad parallel searches
    monitor.start_stage("stage1")
    with ThreadPoolExecutor(max_workers=4) as stage2_executor:
        stage1_results = run_stage1_searches(
            tailored,
            query,
            use_github_skill,
            is_code_related,
            with_perplexity=with_perplexity,
            with_readarr=with_readarr,
            with_wayback=with_wayback,
            with_feeds=with_feeds,
            feed_limit=feed_limit,
            feed_pack=feed_pack,
            publisher=publisher,
            on_result=schedule_stage2,
            monitor=monitor,
        )
        monitor.complete_stage("stage1")

        for future in stage2_futures:
            try:
                future.result()
            except Exception:
                pass

    # Flush stage1 execution metadata to memory
    _flush_execution_records("stage1")

    # Show partial success status after Stage 1
    succeeded = [name for name, res in stage1_results.items()
                 if not (isinstance(res, dict) and ("error" in res or "skipped" in res))]
    failed = [name for name, res in stage1_results.items()
              if isinstance(res, dict) and "error" in res]

    if failed:
        console.print(f"\n[yellow]Stage 1: {len(succeeded)}/{len(stage1_results)} providers succeeded[/yellow]")
        for name in failed:
            res = stage1_results[name]
            err_msg = res.get("error", "Unknown")[:50]
            hint = res.get("hint", "")
            if hint:
                console.print(f"  [red]{name}:[/red] {err_msg} → [yellow]{hint}[/yellow]")
            else:
                console.print(f"  [red]{name}:[/red] {err_msg}")
        console.print("[dim]Continuing with partial results...[/dim]\n")

    brave_res = stage1_results["brave"]
    brave_questions_res = stage1_results.get("brave_questions", {})
    perp_res = stage1_results["perplexity"]
    github_res = stage1_results["github"]
    arxiv_res = stage1_results["arxiv"]
    youtube_res = stage1_results["youtube"]
    readarr_res = stage1_results["readarr"]
    wayback_res = stage1_results["wayback"]
    feeds_res = stage1_results["feeds"]
    codex_src_res = stage1_results["codex_knowledge"]

    github_stage2 = stage2_results.get("github", {})
    if not isinstance(github_stage2, dict) or "error" in github_stage2:
        github_stage2 = {}
    github_details = github_stage2.get("github_details", [])
    github_deep = github_stage2.get("github_deep", {})
    target_repo = github_stage2.get("target_repo")
    deep_code_res = github_stage2.get("deep_code_res", [])
    code_explanation = github_stage2.get("code_explanation")

    arxiv_stage2 = stage2_results.get("arxiv", {})
    if not isinstance(arxiv_stage2, dict) or "error" in arxiv_stage2:
        arxiv_stage2 = {}
    arxiv_details = arxiv_stage2.get("arxiv_details", [])
    arxiv_deep = arxiv_stage2.get("arxiv_deep", [])

    youtube_transcripts = stage2_results.get("youtube", [])
    if not isinstance(youtube_transcripts, list):
        youtube_transcripts = []
    brave_deep = stage2_results.get("brave", [])
    if not isinstance(brave_deep, list):
        brave_deep = []

    # Flush stage2 execution metadata to memory
    _flush_execution_records("stage2")

    monitor.start_stage("synthesis")
    auto_synthesis = _generate_auto_synthesis(query, stage1_results, stage2_results)
    if auto_synthesis.startswith("Error:"):
        stage2_results["synthesis"] = {"error": auto_synthesis}
        synthesis_payload = {"error": auto_synthesis}
    else:
        stage2_results["synthesis"] = {"ok": True, "text": auto_synthesis}
        synthesis_payload = {"text": auto_synthesis}
    if publisher:
        publisher.publish_result("synthesis", "evidence_synthesis", synthesis_payload)
    monitor.complete_stage("synthesis")

    # Generate report from collected results and the grounded synthesis.
    final_report = generate_report(
        query=query,
        wayback_res=wayback_res,
        codex_src_res=codex_src_res,
        perp_res=perp_res,
        readarr_res=readarr_res,
        github_res=github_res,
        github_details=github_details,
        github_deep=github_deep,
        target_repo=target_repo,
        deep_code_res=deep_code_res,
        brave_res=brave_res,
        brave_questions_res=brave_questions_res,
        feeds_res=feeds_res,
        brave_deep=brave_deep,
        arxiv_res=arxiv_res,
        arxiv_details=arxiv_details,
        arxiv_deep=arxiv_deep,
        youtube_res=youtube_res,
        youtube_transcripts=youtube_transcripts,
        synthesis=auto_synthesis,
        code_explanation=code_explanation,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
    )

    report_path = None
    if html_report or open_report or report_file:
        report_path = write_html_report(
            query=query,
            markdown_report=final_report,
            brave_res=brave_res,
            github_res=github_res,
            arxiv_res=arxiv_res,
            youtube_res=youtube_res,
            readarr_res=readarr_res,
            wayback_res=wayback_res,
            codex_src_res=codex_src_res,
            perp_res=perp_res,
            output_path=report_file,
            open_in_browser=open_report,
        )
        typer.echo(f"[dogpile] HTML report: {report_path}", err=True)
    if publisher:
        publisher.publish_report(final_report, report_path=report_path)

    # Print the report
    # When piped (non-TTY), output raw markdown for machine parsing.
    # Interactive TTY gets Rich-rendered markdown with colors/formatting.
    if console.is_terminal:
        console.print(Markdown(final_report))
    else:
        print(final_report)

    # Post-hook: Learn research findings to memory
    if _HAS_MEMORY_INTEGRATION:
        try:
            # Collect sources that were successfully searched
            sources_searched = []
            for name, res in [
                ("brave", brave_res), ("brave_questions", brave_questions_res), ("perplexity", perp_res),
                ("github", github_res), ("arxiv", arxiv_res),
                ("youtube", youtube_res), ("readarr", readarr_res),
                ("wayback", wayback_res), ("feeds", feeds_res), ("codex", codex_src_res),
            ]:
                if res and not (isinstance(res, dict) and ("error" in res or "skipped" in res)):
                    sources_searched.append(name)

            # Collect key URLs from brave results
            key_urls = []
            if isinstance(brave_res, dict):
                web_results = brave_res.get("web", {}).get("results", []) or brave_res.get("results", [])
                for item in web_results[:10]:
                    url = item.get("url")
                    if url:
                        key_urls.append(url)

            _learned = learn_research(
                query=query,
                sources_searched=sources_searched,
                findings=final_report[:2000] if final_report else None,
                synthesis=auto_synthesis if not auto_synthesis.startswith("Error:") else None,
                key_urls=key_urls,
            )
            if _learned:
                console.print(f"[dim]Research findings learned to memory ({len(_learned)} entries).[/dim]")
            else:
                console.print("[yellow dim]Memory learn returned 0 entries — check /memory service.[/yellow dim]")
        except Exception as e:
            console.print(f"[dim]Memory learn skipped: {e}[/dim]")


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
                    except Exception:
                        pass
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
