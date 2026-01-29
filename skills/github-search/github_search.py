#!/usr/bin/env python3
"""GitHub Search: Deep multi-strategy search for repositories and code.

This is the thin CLI entry point that delegates to modular components:
- config.py: Constants and paths
- utils.py: Common utilities
- repo_search.py: Repository search functions
- code_search.py: Code search functions
- readme_analyzer.py: README analysis and skill integrations

Features:
- Multi-strategy code search (basic, symbol, path-filtered)
- Repository analysis with README and metadata
- Full file content fetching
- Issue and PR search
- Agent-driven relevance evaluation

Reference: https://docs.github.com/en/search-github/github-code-search
"""
import json
import sys

try:
    import typer
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

from .config import get_console, DEFAULT_REPO_LIMIT, DEFAULT_CODE_LIMIT, DEFAULT_ISSUE_LIMIT
from .utils import check_gh_cli
from .repo_search import (
    search_repos,
    search_issues,
    fetch_file_content,
    deep_repo_analysis,
)
from .code_search import (
    search_code_basic,
    search_code_symbols,
    search_code_by_path,
    multi_strategy_code_search,
)
from .readme_analyzer import search_and_analyze

app = typer.Typer(help="GitHub Search - Deep multi-strategy search")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(DEFAULT_REPO_LIMIT, "--limit", "-n", help="Max repositories to return"),
    language: str = typer.Option(None, "--language", "-l", help="Filter by language"),
    deep: bool = typer.Option(False, "--deep", "-d", help="Deep analysis of top repo"),
    treesitter: bool = typer.Option(False, "--treesitter", "-t", help="Parse files with treesitter"),
    taxonomy: bool = typer.Option(False, "--taxonomy", help="Classify repos with taxonomy"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Search GitHub repositories and optionally analyze the top result."""
    console = get_console()

    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        console.print("Run: gh auth login")
        raise typer.Exit(1)

    if deep:
        result = search_and_analyze(
            query, limit, deep_search=True,
            use_treesitter=treesitter,
            use_taxonomy=taxonomy
        )
    else:
        result = search_repos(query, limit, language)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    # Display results
    if deep:
        console.print(f"\n[bold blue]GitHub Deep Search:[/bold blue] {query}\n")

        # Repos
        console.print("[bold]Repositories:[/bold]")
        for repo in result.get("repos", [])[:5]:
            stars = repo.get("stargazersCount", 0)
            lang = repo.get("language") or repo.get("primaryLanguage", {})
            lang_name = lang.get("name", lang) if isinstance(lang, dict) else (lang or "Unknown")
            console.print(f"  - [{repo['fullName']}]({repo['url']}) ({stars} stars, {lang_name})")
            if repo.get("description"):
                console.print(f"    {repo['description'][:80]}...")

        # Top repo analysis
        if result.get("top_repo_analysis"):
            analysis = result["top_repo_analysis"]
            console.print(f"\n[bold]Top Repo Analysis: {analysis['repo']}[/bold]")

            readme = analysis.get("readme", {})
            if readme.get("content"):
                console.print(f"  README: {len(readme['content'])} chars")

            langs = analysis.get("languages", {})
            if langs:
                total = sum(langs.values())
                top = sorted(langs.items(), key=lambda x: x[1], reverse=True)[:3]
                lang_str = ", ".join([f"{l[0]}: {l[1]*100/total:.1f}%" for l in top])
                console.print(f"  Languages: {lang_str}")

        # Code search
        if result.get("code_search"):
            cs = result["code_search"]
            console.print(f"\n[bold]Code Search Results:[/bold]")
            console.print(f"  Basic matches: {len(cs.get('basic_matches', []))}")
            console.print(f"  Symbol matches: {len(cs.get('symbol_matches', []))}")
            console.print(f"  Path matches: {len(cs.get('path_matches', []))}")
            console.print(f"  Files fetched: {len(cs.get('file_contents', []))}")
    else:
        console.print(f"\n[bold blue]GitHub Repos:[/bold blue] {query}\n")
        for repo in result.get("repos", []):
            stars = repo.get("stargazersCount", 0)
            console.print(f"  - {repo['fullName']} ({stars} stars)")


@app.command()
def repo(
    repository: str = typer.Argument(..., help="Repository (owner/repo)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Analyze a specific repository in depth."""
    console = get_console()

    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    result = deep_repo_analysis(repository)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"\n[bold blue]Repository Analysis:[/bold blue] {repository}\n")

    meta = result.get("metadata", {})
    if meta and not meta.get("error"):
        console.print(f"[bold]Description:[/bold] {meta.get('description', 'N/A')}")
        console.print(f"[bold]Stars:[/bold] {meta.get('stargazerCount', 0)}")
        console.print(f"[bold]Forks:[/bold] {meta.get('forkCount', 0)}")

        lang = meta.get("primaryLanguage", {})
        console.print(f"[bold]Language:[/bold] {lang.get('name', 'Unknown') if lang else 'Unknown'}")

        topics = meta.get("repositoryTopics", [])
        if topics:
            topic_names = [t.get("name", "") for t in topics]
            console.print(f"[bold]Topics:[/bold] {', '.join(topic_names)}")

    langs = result.get("languages", {})
    if langs:
        total = sum(langs.values())
        console.print("\n[bold]Language Breakdown:[/bold]")
        for lang, bytes_count in sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = bytes_count * 100 / total
            console.print(f"  {lang}: {pct:.1f}%")

    tree = result.get("tree", [])
    if tree:
        console.print("\n[bold]File Structure:[/bold]")
        for item in tree[:15]:
            icon = "[dir]" if item["type"] == "dir" else "[file]"
            console.print(f"  {icon} {item['name']}")


@app.command()
def code(
    query: str = typer.Argument(..., help="Search query"),
    repository: str = typer.Option(None, "--repo", "-r", help="Specific repository"),
    symbol: str = typer.Option(None, "--symbol", "-s", help="Search for symbol definition"),
    path: str = typer.Option(None, "--path", "-p", help="Search in specific path"),
    language: str = typer.Option(None, "--language", "-l", help="Filter by language"),
    limit: int = typer.Option(DEFAULT_CODE_LIMIT, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Search code with advanced qualifiers (symbol:, path:, language:)."""
    console = get_console()

    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    results = []

    if symbol and repository:
        # Symbol search
        results = search_code_symbols(repository, [symbol], language)
    elif path and repository:
        # Path-filtered search
        results = search_code_by_path(repository, query, [path], language)
    elif repository:
        # Multi-strategy search in repo
        search_result = multi_strategy_code_search(repository, query, language, fetch_files=False)
        results = search_result.get("basic_matches", []) + search_result.get("symbol_matches", [])
    else:
        # Global code search
        results = search_code_basic(query, None, language, limit)

    if json_output:
        print(json.dumps(results, indent=2, default=str))
        return

    console.print(f"\n[bold blue]Code Search:[/bold blue] {query}\n")

    if not results:
        console.print("No results found.")
        return

    for item in results[:limit]:
        repo_name = item.get("repository", {}).get("fullName", "unknown")
        file_path = item.get("path", "unknown")
        url = item.get("url", "#")

        console.print(f"[bold]{repo_name}[/bold] - {file_path}")
        console.print(f"  {url}")

        # Show text matches
        for tm in item.get("textMatches", [])[:2]:
            fragment = tm.get("fragment", "")[:100]
            if fragment:
                console.print(f"  > {fragment}...")
        console.print()


@app.command()
def issues(
    query: str = typer.Argument(..., help="Search query"),
    repository: str = typer.Option(None, "--repo", "-r", help="Specific repository"),
    state: str = typer.Option(None, "--state", "-s", help="Filter by state (open, closed)"),
    limit: int = typer.Option(DEFAULT_ISSUE_LIMIT, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Search GitHub issues and discussions."""
    console = get_console()

    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    result = search_issues(query, limit, state, repository)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"\n[bold blue]Issues Search:[/bold blue] {query}\n")

    for issue in result.get("issues", []):
        repo_name = issue.get("repository", {}).get("nameWithOwner", "unknown")
        title = issue.get("title", "No title")
        issue_state = issue.get("state", "unknown")
        url = issue.get("url", "#")

        state_color = "green" if issue_state == "OPEN" else "red"
        console.print(f"[{state_color}][{issue_state}][/{state_color}] {repo_name}")
        console.print(f"  {title}")
        console.print(f"  {url}\n")


@app.command(name="file")
def get_file(
    repository: str = typer.Argument(..., help="Repository (owner/repo)"),
    path: str = typer.Argument(..., help="File path"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Fetch full file content from a repository."""
    console = get_console()

    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    result = fetch_file_content(repository, path)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return

    console.print(f"\n[bold blue]File:[/bold blue] {repository}/{path}\n")
    console.print(f"Size: {result.get('size', 0)} bytes")
    if result.get("truncated"):
        console.print("[yellow]Content truncated[/yellow]")
    console.print("\n" + result.get("content", ""))


@app.command()
def check():
    """Check if gh CLI is installed and authenticated."""
    from .utils import run_command

    console = get_console()

    if check_gh_cli():
        console.print("[green]gh CLI is installed and authenticated[/green]")

        # Show current user
        output = run_command(["gh", "api", "user", "--jq", ".login"])
        if not output.startswith("Error:"):
            console.print(f"Logged in as: {output}")
    else:
        console.print("[red]gh CLI is not installed or not authenticated[/red]")
        console.print("Install: https://cli.github.com/")
        console.print("Auth: gh auth login")
        raise typer.Exit(1)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
