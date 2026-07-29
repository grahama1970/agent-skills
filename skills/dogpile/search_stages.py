#!/usr/bin/env python3
"""Dogpile search stages: partial-result publishing and provider fan-out.

Extracted from cli.py (house rule: no Python file over 800 lines). Owns the
stage-1 broad parallel search, stage-2 deep-dive bundles, evidence digest, and
the ``PartialResultsPublisher`` that writes the durable partial-results file and
stderr event stream. The ``_run_search`` orchestrator in ``dogpile.search_engine``
composes these pieces.
"""
import json
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent

import typer
from rich.live import Live
from rich.table import Table

from dogpile.config import console
from dogpile.utils import log_status
from dogpile.error_hints import get_error_hint
from dogpile.security_research_packet import make_run_id, utc_now
from dogpile.codex import search_codex, search_codex_knowledge
from dogpile.brave import (
    build_brave_question_queries,
    search_brave,
    search_brave_questions,
)
from dogpile.arxiv_search import search_arxiv, run_stage2_arxiv
from dogpile.github_search import search_github, search_github_via_skill
from dogpile.github_deep import run_stage2_github
from dogpile.youtube_search import search_youtube
from dogpile.wayback import search_wayback
from dogpile.readarr import search_readarr
from dogpile.feeds import search_feeds

PARTIAL_RESULTS_PATH = _SCRIPT_DIR / "dogpile_partial_results.json"

# Memory integration (graceful degradation)
try:
    from dogpile.memory_integration import learn_execution_batch
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
        summary["source_bearing_evidence_count"] = sum(1 for item in web_results if item.get("url") or item.get("link"))
        summary["source_bearing"] = summary["source_bearing_evidence_count"] > 0
        if result.get("query"):
            summary["query"] = result["query"]
    elif name == "brave_questions" and isinstance(result, dict):
        summary["queries"] = len(result.get("queries", []) or [])
        summary["succeeded"] = result.get("succeeded", 0)
        summary["total"] = result.get("total", 0)
        count = 0
        for run in result.get("results", []) or []:
            run_result = run.get("result", {})
            if isinstance(run_result, dict):
                items = run_result.get("web", {}).get("results", []) or run_result.get("results", [])
                count += sum(1 for item in items if item.get("url") or item.get("link"))
        summary["source_bearing_evidence_count"] = count
        summary["source_bearing"] = count > 0
    elif name == "github" and isinstance(result, dict):
        summary["repos"] = len(result.get("repos", []) or [])
        summary["issues"] = len(result.get("issues", []) or [])
        summary["source_bearing_evidence_count"] = 0
        summary["source_bearing"] = False
    elif name == "arxiv" and isinstance(result, dict):
        summary["papers"] = len(result.get("items", []) or [])
        summary["source_bearing_evidence_count"] = sum(1 for item in result.get("items", []) or [] if item.get("id") or item.get("abs_url") or item.get("url"))
        summary["source_bearing"] = summary["source_bearing_evidence_count"] > 0
    elif name in {"youtube", "readarr"} and isinstance(result, list):
        summary["result_count"] = len(result)
        summary["source_bearing_evidence_count"] = sum(1 for item in result if isinstance(item, dict) and (item.get("id") or item.get("url")))
        summary["source_bearing"] = summary["source_bearing_evidence_count"] > 0
    elif name == "feeds" and isinstance(result, dict):
        summary["returncode"] = result.get("returncode")
        summary["limit"] = result.get("limit")
        stdout = str(result.get("stdout", ""))
        summary["output_chars"] = len(stdout)
        summary["source_bearing_evidence_count"] = 1 if stdout else 0
        summary["source_bearing"] = bool(stdout)
    elif name == "wayback" and isinstance(result, dict):
        summary["has_snapshot"] = bool(result.get("closest") or result.get("snapshots"))
    elif name == "codex_knowledge":
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        summary["excerpt"] = text[:180]
        summary["source_bearing_evidence_count"] = 0
        summary["source_bearing"] = False
        summary["model_synthesis_present"] = True
    elif name == "stage2_github" and isinstance(result, dict):
        summary["repos_examined"] = len(result.get("github_details", []) or [])
        summary["target_repo"] = result.get("target_repo")
        github_deep = result.get("github_deep", {}) or {}
        summary["code_matches"] = len(github_deep.get("code_matches", []) or [])
        has_receipt = bool(result.get("evaluation_receipt") or result.get("github_search_receipt"))
        summary["source_bearing_evidence_count"] = 1 if has_receipt and result.get("target_repo") else 0
        summary["source_bearing"] = summary["source_bearing_evidence_count"] > 0
    elif name == "stage2_arxiv" and isinstance(result, dict):
        summary["paper_details"] = len(result.get("arxiv_details", []) or [])
        summary["deep_extractions"] = len(result.get("arxiv_deep", []) or [])
    elif name == "stage2_youtube" and isinstance(result, list):
        summary["transcripts"] = len(result)
        summary["source_bearing_evidence_count"] = sum(1 for item in result if isinstance(item, dict) and (item.get("id") or item.get("url") or item.get("full_text")))
        summary["source_bearing"] = summary["source_bearing_evidence_count"] > 0
    elif name == "stage2_brave" and isinstance(result, list):
        summary["deep_extractions"] = len(result)
    elif name == "report" and isinstance(result, str):
        summary["chars"] = len(result)
        summary["lines"] = len(result.splitlines())
        summary["source_bearing_evidence_count"] = 0
        summary["source_bearing"] = False
    else:
        summary["type"] = type(result).__name__
    return summary


class PartialResultsPublisher:
    """Persist partial Dogpile results and emit machine-readable progress events."""

    def __init__(
        self,
        requested_query: str,
        request_context: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Path] = None,
        run_id: Optional[str] = None,
    ):
        run_id = run_id or make_run_id(requested_query)
        self.output_dir = (output_dir or (_SCRIPT_DIR / "local" / "search-runs" / run_id)).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.output_dir / "dogpile_partial_results.json"
        request_context = request_context or {}
        self.state: Dict[str, Any] = {
            "run_id": run_id,
            "requested_query": requested_query,
            "effective_query": requested_query,
            "status": "starting",
            "started_at": utc_now(),
            "updated_at": time.time(),
            "output_dir": str(self.output_dir),
            "partial_results_path": str(self.path),
            "request_context": request_context,
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
                "request_context": request_context,
            }
        )

    def _write(self) -> None:
        self.state["updated_at"] = time.time()
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
        tmp_path.replace(self.path)
        if self.path != PARTIAL_RESULTS_PATH:
            latest = {
                "latest_run_id": self.state.get("run_id"),
                "partial_results_path": str(self.path),
                "updated_at": self.state["updated_at"],
            }
            PARTIAL_RESULTS_PATH.write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n")

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
        self.state["ended_at"] = utc_now()
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


def _format_request_context(request_context: Optional[Dict[str, Any]]) -> str:
    """Render persona/rationale/context request metadata for prompts and reports."""
    if not request_context:
        return ""
    labels = [
        ("persona", "Review persona"),
        ("rationale", "Rationale"),
        ("context", "Problem context"),
        ("context_file", "Context file"),
    ]
    lines = [f"{label}: {request_context[key]}" for key, label in labels if request_context.get(key)]
    return "\n".join(lines)


def _generate_auto_synthesis(
    query: str,
    stage1_results: Dict[str, Any],
    stage2_results: Dict[str, Any],
    request_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a concise synthesis from retrieved evidence, degrading cleanly."""
    digest = _collect_evidence_digest(query, stage1_results, stage2_results)
    context_block = _format_request_context(request_context)
    context_preface = f"Request context (shapes interpretation, not the search queries):\n{context_block}\n\n" if context_block else ""
    prompt = f"""Synthesize this Dogpile research evidence for the user query.

{context_preface}Rules:
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
