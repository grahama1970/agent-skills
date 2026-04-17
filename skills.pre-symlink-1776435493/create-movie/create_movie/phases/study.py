"""
Pre-Phase: Study

Study filmmaking topics to acquire knowledge for future movie creation.
This is a PRE-PHASE that should be run before creating movies.
"""

from typing import Optional

from rich.console import Console

from ..skill_registry import run_skill

console = Console()

# Suggested filmmaking topics
FILMMAKING_TOPICS = [
    "cinematography lighting techniques three-point lighting",
    "camera framing composition rule of thirds",
    "film directing actors performance",
    "shot types close-up medium wide establishing",
    "film editing cuts transitions montage",
    "color grading mood atmosphere",
    "sound design foley ambient",
    "screenplay structure three act format",
    "visual storytelling show don't tell",
    "film history movements genres",
]


def list_topics():
    """List suggested filmmaking topics."""
    console.print("\n[bold]Suggested Filmmaking Topics:[/bold]")
    for i, t in enumerate(FILMMAKING_TOPICS, 1):
        console.print(f"  {i}. {t}")
    console.print("\n[dim]Usage: ./run.sh study 'cinematography lighting'[/dim]")


def study_topic(
    topic: str,
    scope: str = "horus-filmmaking",
    deep: bool = False,
) -> dict:
    """
    Study a filmmaking topic and store knowledge in memory.

    Args:
        topic: The topic to study
        scope: Memory scope for storage
        deep: If True, perform deep research with dogpile

    Returns:
        dict with study results
    """
    results = {
        "topic": topic,
        "scope": scope,
        "deep": deep,
        "existing_knowledge": None,
        "new_knowledge": None,
        "stored": False,
    }

    console.print(f"[dim]Studying: {topic}[/dim]")
    console.print(f"[dim]Will store in scope: {scope}[/dim]")

    # Step 1: Check what we already know
    console.print("\n[cyan]── Checking existing knowledge ──[/cyan]")
    existing = run_skill("memory", ["recall", "--q", topic, "--scope", scope, "--k", "3"])
    if existing.get("returncode") == 0 and existing.get("stdout", "").strip():
        results["existing_knowledge"] = existing.get("stdout", "")
        console.print("[green]Already have some knowledge on this topic:[/green]")
        console.print(existing.get("stdout", "")[:500])
        console.print()

    if deep:
        # Step 2: Deep research with dogpile
        console.print("\n[cyan]── Deep Research via /dogpile ──[/cyan]")
        dogpile_query = f"{topic} filmmaking tutorial guide techniques"
        with console.status(f"[green]Researching: {dogpile_query}..."):
            dogpile_result = run_skill("dogpile", ["search", dogpile_query])

        if dogpile_result.get("returncode") == 0:
            research_text = dogpile_result.get("stdout", "")
            results["new_knowledge"] = research_text
            console.print(f"[green]✓ Got {len(research_text)} chars of research[/green]")

            # Step 3: Store using /memory learn
            console.print("\n[cyan]── Storing to memory via /memory learn ──[/cyan]")

            learn_result = run_skill("memory", [
                "learn",
                "--problem", f"How to apply {topic} in filmmaking?",
                "--solution", research_text[:2000],  # Memory limits
                "--scope", scope,
            ])

            if learn_result.get("returncode") == 0:
                results["stored"] = True
                console.print("[green]✓ Knowledge stored in memory[/green]")
            else:
                console.print(f"[yellow]Memory learn: {learn_result.get('stderr', '')[:100]}[/yellow]")
        else:
            console.print(f"[yellow]Dogpile research failed: {dogpile_result.get('stderr', '')[:100]}[/yellow]")

    else:
        # Quick mode: just search YouTube and add to memory
        console.print("\n[cyan]── Quick Study via YouTube transcripts ──[/cyan]")
        with console.status("[green]Searching YouTube for tutorials..."):
            yt_result = run_skill("ingest-youtube", ["search", f"{topic} tutorial filmmaking"])

        if yt_result.get("returncode") == 0:
            console.print("[green]✓ Found tutorials. Use --deep for full research.[/green]")
        else:
            console.print("[dim]No YouTube tutorials found. Try --deep for web research.[/dim]")

    console.print(f"\n[bold green]Study complete. Knowledge stored in '{scope}' scope.[/bold green]")
    console.print("[dim]Horus can now recall this when creating movies.[/dim]")

    return results


def study_all_topics(scope: str = "horus-filmmaking") -> dict:
    """
    Study all suggested filmmaking topics (comprehensive learning session).

    Args:
        scope: Memory scope for storage

    Returns:
        dict with study results for all topics
    """
    results = {
        "scope": scope,
        "topics_studied": [],
        "topics_skipped": [],
        "total": len(FILMMAKING_TOPICS),
    }

    for i, topic in enumerate(FILMMAKING_TOPICS, 1):
        console.print(f"\n[bold]Topic {i}/{len(FILMMAKING_TOPICS)}: {topic}[/bold]")

        # Check if already known
        existing = run_skill("memory", ["recall", "--q", topic, "--scope", scope, "--k", "1"])
        if existing.get("returncode") == 0 and existing.get("stdout", "").strip():
            console.print("[dim]Already have knowledge on this topic, skipping...[/dim]")
            results["topics_skipped"].append(topic)
            continue

        # Quick study (not deep to save time)
        study_topic(topic=topic, scope=scope, deep=False)
        results["topics_studied"].append(topic)

    console.print(f"\n[bold green]All {len(FILMMAKING_TOPICS)} topics studied![/bold green]")
    console.print("[dim]Horus is now ready to create movies with filmmaking knowledge.[/dim]")

    return results
