#!/usr/bin/env python3
"""CLI for Brave-discovered, executable GitHub repository evaluation."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

import typer

from candidate_search import discover_and_rank_repositories
from config import (
    DEFAULT_BRAVE_CANDIDATES,
    DEFAULT_CLONE_TIMEOUT,
    DEFAULT_EVALUATION_TOP,
    DEFAULT_MAX_REPO_SIZE_MB,
    DEFAULT_MIN_STARS,
    DEFAULT_RUN_MEMORY_MB,
    DEFAULT_RUN_TIMEOUT,
    get_console,
)
from repo_evaluator import evaluate_ranked_repositories
from utils import check_gh_cli


def main(
    query: str = typer.Argument(..., help="Requested implementation or code behavior"),
    criteria: str = typer.Option("", "--criteria", "-c", help="Additional free-text ranking criteria"),
    min_stars: int = typer.Option(DEFAULT_MIN_STARS, "--min-stars", help="Minimum GitHub stars"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Required primary language"),
    updated_after: Optional[str] = typer.Option(None, "--updated-after", help="Require update date >= YYYY-MM-DD"),
    license_name: Optional[str] = typer.Option(None, "--license", help="Required SPDX license identifier"),
    candidates: int = typer.Option(DEFAULT_BRAVE_CANDIDATES, "--candidates", help="Brave results to inspect (1-20)"),
    top: int = typer.Option(DEFAULT_EVALUATION_TOP, "--top", help="Top repositories to clone and execute (1-5)"),
    max_size_mb: int = typer.Option(DEFAULT_MAX_REPO_SIZE_MB, "--max-size-mb", help="Reject larger repositories"),
    include_archived: bool = typer.Option(False, "--include-archived", help="Allow archived repositories"),
    include_forks: bool = typer.Option(False, "--include-forks", help="Allow fork repositories"),
    entrypoint: Optional[str] = typer.Option(None, "--entrypoint", help="Override detected command; parsed without a shell"),
    run_timeout: int = typer.Option(DEFAULT_RUN_TIMEOUT, "--run-timeout", help="Entry-point timeout in seconds"),
    clone_timeout: int = typer.Option(DEFAULT_CLONE_TIMEOUT, "--clone-timeout", help="Clone timeout in seconds"),
    memory_mb: int = typer.Option(DEFAULT_RUN_MEMORY_MB, "--memory-mb", help="Entry-point memory limit"),
    sandbox: str = typer.Option("auto", "--sandbox", help="Execution mode: auto, strict, or host"),
    allow_network: bool = typer.Option(False, "--allow-network", help="Permit network access during untrusted execution"),
    keep_workspace: bool = typer.Option(True, "--keep-workspace/--cleanup", help="Retain clones under /tmp"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Rank Brave results, clone the leaders, run them, then evaluate relevant code."""
    console = get_console()
    if sandbox not in {"auto", "strict", "host"}:
        raise typer.BadParameter("sandbox must be one of: auto, strict, host", param_hint="--sandbox")
    if updated_after:
        try:
            date.fromisoformat(updated_after)
        except ValueError as exc:
            raise typer.BadParameter("use YYYY-MM-DD", param_hint="--updated-after") from exc
    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        console.print("Run: gh auth login")
        raise typer.Exit(1)

    discovery = discover_and_rank_repositories(
        query,
        criteria,
        count=max(1, min(candidates, 20)),
        min_stars=max(0, min_stars),
        language=language,
        updated_after=updated_after,
        license_name=license_name,
        include_archived=include_archived,
        include_forks=include_forks,
        max_size_mb=max(0, max_size_mb),
    )
    ranked = discovery.get("ranked", [])
    if discovery.get("error") or not ranked:
        result = {"query": query, "criteria": criteria, "discovery": discovery, "evaluation": None}
        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[red]Repository discovery failed:[/red] {discovery.get('error') or 'No repositories met the filters'}")
            if discovery.get("rejected"):
                console.print(f"Rejected candidates: {len(discovery['rejected'])}")
        raise typer.Exit(1)

    evaluation = evaluate_ranked_repositories(
        ranked,
        query,
        top=max(1, min(top, 5)),
        entrypoint_override=entrypoint,
        run_timeout=max(1, run_timeout),
        memory_mb=max(256, memory_mb),
        clone_timeout=max(10, clone_timeout),
        sandbox=sandbox,
        allow_network=allow_network,
        keep_workspace=keep_workspace,
    )
    result = {
        "query": query,
        "criteria": criteria,
        "discovery": discovery,
        "evaluation": evaluation,
    }
    if json_output:
        print(json.dumps(result, indent=2, default=str))
        if evaluation.get("evaluated_count", 0) == 0:
            raise typer.Exit(2)
        return

    console.print(f"\n[bold blue]Ranked repositories for:[/bold blue] {query}\n")
    for index, candidate in enumerate(ranked[:10], start=1):
        console.print(
            f"{index}. [bold]{candidate['repo']}[/bold] "
            f"score={candidate['score']:.3f}, stars={candidate.get('stars', 0)}, "
            f"language={candidate.get('language') or 'unknown'}"
        )
    console.print("\n[bold]Execution and code evaluation:[/bold]")
    for item in evaluation.get("results", []):
        status = item.get("status")
        console.print(f"\n[bold]{item.get('repo')}[/bold] — {status}")
        if item.get("entrypoint"):
            console.print(f"  Entry point: {item['entrypoint'].get('source')} -> {item['entrypoint'].get('command')}")
        if item.get("run"):
            run = item["run"]
            console.print(f"  Run: {run.get('status')} via {run.get('sandbox')} ({run.get('duration_seconds', 0)}s)")
            if run.get("warning"):
                console.print(f"  [yellow]{run['warning']}[/yellow]")
        if item.get("assessment"):
            assessment = item["assessment"]
            console.print(f"  Assessment: {assessment['recommendation']} ({assessment['score']:.3f})")
            for path in item.get("code_search", {}).get("matched_files", [])[:5]:
                console.print(f"    - {path}")
    console.print(f"\nWorkspace: {evaluation.get('workspace')}")
    if not allow_network:
        console.print("Network access was disabled where the available sandbox supported it.")
    if evaluation.get("evaluated_count", 0) == 0:
        raise typer.Exit(2)


if __name__ == "__main__":
    typer.run(main)
