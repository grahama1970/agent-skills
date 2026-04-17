"""
Phase 1: Research

Research techniques and tools for movie creation - library first, then external.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..skill_registry import run_skill

console = Console()


def research_topic(topic: str, output_path: Optional[Path] = None, skip_external: bool = False) -> dict:
    """
    Research techniques and tools - library first, then external.

    Args:
        topic: The research topic
        output_path: Optional path to save results
        skip_external: If True, skip external search (library only)

    Returns:
        dict with research results
    """
    results = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "library": {},   # What Horus already has
        "external": {},  # New resources found
        "sources": {},   # Combined
    }

    # =========================================================================
    # PART 1: CHECK HORUS'S LIBRARY (what he already has)
    # =========================================================================
    console.print("\n[cyan]── Checking Library ──[/cyan]")

    # 1a. horus-filmmaking scope - past filmmaking knowledge, techniques
    with console.status("[green]Recalling filmmaking knowledge (horus-filmmaking)..."):
        filmmaking_result = run_skill(
            "memory", ["recall", "--q", topic, "--scope", "horus-filmmaking", "--k", "5"]
        )
        if filmmaking_result.get("returncode") == 0 and filmmaking_result.get("stdout", "").strip():
            results["library"]["filmmaking"] = filmmaking_result.get("stdout", "")
            console.print("  [green]✓ Found filmmaking knowledge[/green]")

    # 1b. horus_lore scope - YouTube transcripts may have film analysis
    with console.status("[green]Recalling lore/analysis (horus_lore)..."):
        lore_result = run_skill(
            "memory", ["recall", "--q", f"{topic} cinematography visual style", "--scope", "horus_lore", "--k", "3"]
        )
        if lore_result.get("returncode") == 0 and lore_result.get("stdout", "").strip():
            results["library"]["lore"] = lore_result.get("stdout", "")
            console.print("  [green]✓ Found relevant lore/analysis[/green]")

    # 1c. Ingested movies with emotion tags
    with console.status("[green]Checking movie library (ingested films)..."):
        movie_result = run_skill(
            "memory", ["recall", "--q", f"{topic} movie film scene emotion pacing", "--scope", "horus_lore", "--k", "5"]
        )
        if movie_result.get("returncode") == 0 and movie_result.get("stdout", "").strip():
            results["library"]["movies"] = movie_result.get("stdout", "")
            console.print("  [green]✓ Found relevant ingested movies[/green]")

    # 1d. Episodic archive - past filmmaking sessions
    with console.status("[green]Checking episodic archive..."):
        episodic_result = run_skill(
            "episodic-archiver", ["recall", "--q", f"{topic} filmmaking video", "--k", "3"]
        )
        if episodic_result.get("returncode") == 0 and episodic_result.get("stdout", "").strip():
            results["library"]["episodic"] = episodic_result.get("stdout", "")
            console.print("  [green]✓ Found past filmmaking sessions[/green]")

    library_count = sum(1 for v in results["library"].values() if v)
    console.print(f"[cyan]Library: {library_count} sources found[/cyan]")

    # =========================================================================
    # PART 1b: CONSUMED CONTENT (what Horus has absorbed)
    # =========================================================================
    console.print("\n[cyan]── Searching Consumed Content ──[/cyan]")

    # Books Horus has read
    with console.status("[green]Searching book library (consume-book)..."):
        book_result = run_skill(
            "consume-book", ["search", topic, "--context", "500"]
        )
        if book_result.get("returncode") == 0 and book_result.get("stdout", "").strip():
            results["library"]["books_consumed"] = book_result["stdout"][:2000]
            console.print("  [green]✓ Found relevant book passages[/green]")

    # Movies Horus has watched (subtitle/scene search)
    with console.status("[green]Searching watched movies (consume-movie)..."):
        movie_consumed = run_skill(
            "consume-movie", ["search", topic, "--context", "10"]
        )
        if movie_consumed.get("returncode") == 0 and movie_consumed.get("stdout", "").strip():
            results["library"]["movies_consumed"] = movie_consumed["stdout"][:2000]
            console.print("  [green]✓ Found relevant movie scenes[/green]")

    # YouTube videos Horus has watched (transcript search)
    with console.status("[green]Searching watched YouTube (consume-youtube)..."):
        yt_consumed = run_skill(
            "consume-youtube", ["search", f"{topic} filmmaking technique"]
        )
        if yt_consumed.get("returncode") == 0 and yt_consumed.get("stdout", "").strip():
            results["library"]["youtube_consumed"] = yt_consumed["stdout"][:2000]
            console.print("  [green]✓ Found relevant YouTube segments[/green]")

    # Past project analysis (code structure of similar tools)
    with console.status("[green]Analyzing past project tools (treesitter)..."):
        tools_dir = Path(__file__).parent.parent.parent  # create-movie root
        tree_result = run_skill(
            "treesitter", ["scan", str(tools_dir / "core"), "--json"]
        )
        if tree_result.get("returncode") == 0 and tree_result.get("stdout", "").strip():
            results["library"]["code_structure"] = tree_result["stdout"][:2000]
            console.print("  [green]✓ Analyzed codebase structure[/green]")

    consumed_count = sum(1 for k, v in results["library"].items()
                         if v and k.endswith("_consumed"))
    console.print(f"[cyan]Consumed content: {consumed_count} sources found[/cyan]")

    if skip_external:
        console.print("[dim]Skipping external search (--skip-external)[/dim]")
    else:
        # =========================================================================
        # PART 2: SEARCH FOR NEW RESOURCES (external)
        # =========================================================================
        console.print("\n[cyan]── Searching for New Resources ──[/cyan]")

        # 2a. Search for new movies to watch for inspiration
        with console.status("[green]Searching for films to watch (ingest-movie)..."):
            movie_search = run_skill("ingest-movie", ["search", topic])
            if movie_search.get("returncode") == 0 and movie_search.get("stdout", "").strip():
                results["external"]["new_movies"] = movie_search.get("stdout", "")
                console.print("  [green]✓ Found movies to watch for inspiration[/green]")

        # 2b. Search YouTube for tutorials/techniques
        with console.status("[green]Searching YouTube for tutorials (ingest-youtube)..."):
            yt_search = run_skill("ingest-youtube", ["search", f"{topic} tutorial filmmaking technique"])
            if yt_search.get("returncode") == 0 and yt_search.get("stdout", "").strip():
                results["external"]["youtube"] = yt_search.get("stdout", "")
                console.print("  [green]✓ Found YouTube tutorials[/green]")

        external_count = sum(1 for v in results["external"].values() if v)
        console.print(f"[cyan]External: {external_count} new sources found[/cyan]")

        # =========================================================================
        # PART 3: DEEP EXTERNAL RESEARCH (web)
        # =========================================================================
        console.print("\n[cyan]── Deep Web Research ──[/cyan]")

        # 3a. Research with dogpile
        with console.status("[green]Running dogpile research..."):
            dogpile_query = f"{topic} filmmaking techniques cinematography tutorial"
            dogpile_result = run_skill("dogpile", ["search", dogpile_query])
            if dogpile_result.get("returncode") == 0 and dogpile_result.get("stdout", "").strip():
                results["external"]["dogpile"] = dogpile_result.get("stdout", "")
                console.print("  [green]✓ Dogpile research complete[/green]")
            else:
                console.print(f"  [yellow]Dogpile warning: {dogpile_result.get('stderr', '')[:100]}[/yellow]")

    # Merge into flat sources dict for backwards compatibility
    results["sources"] = {**results["library"], **results["external"]}

    # Save results if output path provided
    if output_path:
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        console.print(f"\n[bold green]Research saved to {output_path}[/bold green]")

    return results
