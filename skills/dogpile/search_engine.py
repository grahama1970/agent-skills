#!/usr/bin/env python3
"""Dogpile search engine: the ``_run_search`` orchestrator.

Extracted from cli.py (house rule: no Python file over 800 lines). Composes the
stage helpers in ``dogpile.search_stages`` into the full pipeline the ``search``
command runs: preset selection, ambiguity/intent analysis, query tailoring,
stage-1 fan-out, stage-2 deep dives, synthesis, report assembly, and the
memory recall/learn hooks.

Re-exports ``PartialResultsPublisher`` so cli.py has a single engine import.
"""
import sys
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

# Add parent directory to path for package imports when imported as a script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import typer
from loguru import logger
from rich.markdown import Markdown

from dogpile.config import console, REGISTRY_AVAILABLE, get_registry
from dogpile.codex import search_codex, tailor_queries_for_services, analyze_query
from dogpile.brave import run_stage2_brave
from dogpile.youtube_search import run_stage2_youtube
from dogpile.synthesis import generate_report
from dogpile.html_report import write_html_report
from dogpile.search_stages import (
    PartialResultsPublisher,
    run_stage1_searches,
    _run_github_stage2_bundle,
    _run_arxiv_stage2_bundle,
    _timed_stage2,
    _flush_execution_records,
    _generate_auto_synthesis,
    _format_request_context,
)

# Memory integration (graceful degradation)
try:
    from dogpile.memory_integration import recall_prior_research, learn_research
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    _HAS_MEMORY_INTEGRATION = False


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
    request_context: Optional[Dict[str, Any]] = None,
    read_n: int = 1,
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
            "brave": ("stage2_brave", lambda: _timed_stage2("brave", run_stage2_brave, stage1_result, query, search_codex, read_n)),
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
            except Exception as e:
                # Per-future errors are already captured in _store_stage2_result;
                # this drain only surfaces anything that escaped that path.
                logger.warning("stage2 future drain saw uncaptured error: {}", e)

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
    auto_synthesis = _generate_auto_synthesis(query, stage1_results, stage2_results, request_context=request_context)
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

    # Prepend request-context metadata (persona/rationale/context) to the report.
    _context_block = _format_request_context(request_context)
    if _context_block:
        final_report = f"## Request Context\n\n{_context_block}\n\n{final_report}"

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

