#!/usr/bin/env python3
"""
create-story Orchestrator for Horus Persona

Creative writing through deep research and iterative refinement:
Initial Thought → Research → Dogpile → Draft 1 → Critique → Draft 2 → Final

Philosophy: "Every story Horus tells comes from somewhere"
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.markdown import Markdown

console = Console()

SKILL_DIR = Path(__file__).parent
PI_SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/

STORY_FORMATS = {
    "story": "Short Story (prose narrative)",
    "screenplay": "Screenplay (Fountain format)",
    "podcast": "Podcast Script (with audio cues)",
    "novella": "Novella (chapters)",
    "flash": "Flash Fiction (<1000 words)",
}


@dataclass
class StoryProject:
    """Represents a story being created."""

    thought: str
    format: str = "story"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    research: dict = field(default_factory=dict)
    drafts: list = field(default_factory=list)
    critiques: list = field(default_factory=list)
    final: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def save(self, path: Path):
        """Save project state to JSON."""
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2, default=str)

    @classmethod
    def load(cls, path: Path) -> "StoryProject":
        """Load project state from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


def run_skill(skill_name: str, args: list[str], capture: bool = True) -> dict:
    """Run a skill from .pi/skills/ and return result."""
    skill_path = PI_SKILLS_DIR / skill_name / "run.sh"

    if not skill_path.exists():
        return {"error": f"Skill not found: {skill_name}", "path": str(skill_path)}

    cmd = ["bash", str(skill_path)] + args
    console.print(f"[dim]Running: {skill_name} {' '.join(args[:2])}...[/dim]")

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=600,  # 10 min for research
            cwd=str(PI_SKILLS_DIR / skill_name),
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Skill timed out", "skill": skill_name}
    except Exception as e:
        return {"error": str(e), "skill": skill_name}


# =============================================================================
# Phase 1: Initial Thought
# =============================================================================


def capture_initial_thought(thought: str, format: str) -> dict:
    """Capture and structure the initial creative thought."""
    console.print(
        Panel(
            f"[bold magenta]INITIAL THOUGHT[/bold magenta]\n\n"
            f'"{thought}"\n\n'
            f"[dim]Format: {STORY_FORMATS.get(format, format)}[/dim]"
        )
    )

    return {
        "thought": thought,
        "format": format,
        "captured_at": datetime.now().isoformat(),
    }


# =============================================================================
# Phase 2: Research
# =============================================================================


@click.command()
@click.argument("topic")
@click.option("--output", "-o", default="research", help="Output directory")
def research(topic: str, output: str):
    """Phase 2: Deep research from movies, books, memory, past sessions."""
    console.print(Panel(f"[bold blue]RESEARCH PHASE[/bold blue]\nTopic: {topic}"))

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "sources": {},
    }

    # 1. Memory recall - past stories and techniques
    with console.status("[bold green]Recalling from memory (horus-stories scope)..."):
        memory_result = run_skill(
            "memory",
            ["recall", "--q", topic, "--scope", "horus-stories", "--k", "5"],
        )
        if memory_result.get("returncode") == 0:
            results["sources"]["memory_stories"] = memory_result.get("stdout", "")
            console.print("[green]Found prior stories/techniques[/green]")
        else:
            console.print("[dim]No prior stories found[/dim]")

    # 2. Memory recall - general Horus knowledge
    with console.status("[bold green]Recalling general knowledge..."):
        memory_general = run_skill(
            "memory",
            ["recall", "--q", topic, "--scope", "horus-filmmaking", "--k", "3"],
        )
        if memory_general.get("returncode") == 0:
            results["sources"]["memory_general"] = memory_general.get("stdout", "")

    # 3. Episodic archive - past creative sessions
    with console.status("[bold green]Checking episodic archive..."):
        # Note: episodic-archiver recall would go here
        results["sources"]["episodic"] = "Episodic archive integration pending"

    # 4. Movie analysis (if ingest-movie available)
    with console.status("[bold green]Analyzing relevant films..."):
        # Note: ingest-movie integration would go here
        results["sources"]["movies"] = "Movie analysis integration pending"

    # 5. Book search via ingest-book
    with console.status("[bold green]Searching for relevant books..."):
        readarr_result = run_skill("ingest-book", ["search", topic])
        if readarr_result.get("returncode") == 0:
            results["sources"]["books"] = readarr_result.get("stdout", "")
            console.print("[green]Found book references[/green]")
        else:
            console.print("[dim]Readarr search unavailable[/dim]")

    # Save research results
    research_file = output_path / "research.json"
    with open(research_file, "w") as f:
        json.dump(results, f, indent=2)

    console.print(f"\n[bold green]Research saved to {research_file}[/bold green]")
    return results


# =============================================================================
# Phase 3: Dogpile Context
# =============================================================================


def dogpile_context(topic: str, research_context: dict) -> dict:
    """Use /dogpile with gathered context for deeper research."""
    console.print(Panel("[bold blue]DOGPILE CONTEXT[/bold blue]\nDeep research with context"))

    # Build context-enriched query
    context_summary = []
    if research_context.get("sources", {}).get("memory_stories"):
        context_summary.append("past stories about similar themes")
    if research_context.get("sources", {}).get("books"):
        context_summary.append("relevant literature")

    enriched_query = f"{topic} narrative techniques storytelling"
    if context_summary:
        enriched_query += f" (building on: {', '.join(context_summary)})"

    with console.status("[bold green]Running dogpile research..."):
        dogpile_result = run_skill("dogpile", ["search", enriched_query])

    if dogpile_result.get("returncode") == 0:
        console.print("[green]Dogpile research complete[/green]")
        return {"query": enriched_query, "results": dogpile_result.get("stdout", "")}
    else:
        console.print(f"[yellow]Dogpile warning: {dogpile_result.get('stderr', '')}[/yellow]")
        return {"query": enriched_query, "error": dogpile_result.get("stderr", "")}


# =============================================================================
# Phase 4: Drafting
# =============================================================================


@click.command()
@click.option("--research", "-r", "research_file", required=True, help="Research JSON file")
@click.option("--format", "-f", "story_format", default="story", help="Story format")
@click.option("--output", "-o", default="drafts", help="Output directory")
def draft(research_file: str, story_format: str, output: str):
    """Write a draft based on research."""
    console.print(Panel("[bold blue]DRAFT PHASE[/bold blue]\nWriting from research"))

    research_path = Path(research_file)
    if not research_path.exists():
        console.print(f"[red]Research file not found: {research_file}[/red]")
        sys.exit(1)

    with open(research_path) as f:
        research_data = json.load(f)

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    # Draft template based on format
    draft_templates = {
        "story": "# {title}\n\n{content}",
        "screenplay": "FADE IN:\n\n{content}\n\nFADE OUT.",
        "podcast": "# {title}\n\n[INTRO MUSIC]\n\n{content}\n\n[OUTRO MUSIC]",
        "novella": "# {title}\n\n## Chapter 1\n\n{content}",
        "flash": "# {title}\n\n{content}\n\n---\n*{word_count} words*",
    }

    template = draft_templates.get(story_format, draft_templates["story"])

    # Placeholder for actual LLM generation
    draft_content = f"""
Based on research about: {research_data.get('topic', 'unknown topic')}

[Draft content would be generated here by the LLM based on:]
- Research context: {len(research_data.get('sources', {}))} sources
- Format: {STORY_FORMATS.get(story_format, story_format)}

This is a placeholder - the actual draft generation integrates with
the agent's creative capabilities.
"""

    draft_file = output_path / f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(draft_file, "w") as f:
        f.write(template.format(title="Untitled", content=draft_content, word_count="~500"))

    console.print(f"\n[bold green]Draft saved to {draft_file}[/bold green]")
    console.print("[dim]Edit this file or continue with critique phase.[/dim]")


# =============================================================================
# Phase 5: Critique
# =============================================================================


@click.command()
@click.argument("story_file")
@click.option("--external", is_flag=True, help="Use external LLM for critique")
@click.option("--output", "-o", default="critiques", help="Output directory")
def critique(story_file: str, external: bool, output: str):
    """Critique an existing story (self or external)."""
    mode = "EXTERNAL" if external else "SELF"
    console.print(Panel(f"[bold blue]CRITIQUE PHASE ({mode})[/bold blue]"))

    story_path = Path(story_file)
    if not story_path.exists():
        console.print(f"[red]Story file not found: {story_file}[/red]")
        sys.exit(1)

    with open(story_path) as f:
        story_content = f.read()

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    if external:
        # Use /codex or /scillm for external critique
        console.print("[dim]Using external LLM for objective critique...[/dim]")
        critique_prompt = f"Critique this story for: narrative flow, character consistency, thematic coherence, pacing. Story:\n\n{story_content[:2000]}..."

        codex_result = run_skill("codex", ["--prompt", critique_prompt])
        if codex_result.get("returncode") == 0:
            critique_content = codex_result.get("stdout", "External critique unavailable")
        else:
            critique_content = "External critique failed - falling back to self-critique framework"
    else:
        # Self-critique framework
        critique_content = f"""
# Self-Critique: {story_path.name}

## What Works
- [Analyze strengths]

## What Doesn't Work
- [Identify weaknesses]

## What's Missing
- [Note gaps]

## Specific Improvements
1. [Improvement 1]
2. [Improvement 2]
3. [Improvement 3]

## Next Draft Focus
- [Priority for revision]

---
*Self-critique generated at {datetime.now().isoformat()}*
*Story length: {len(story_content)} characters*
"""

    critique_file = output_path / f"critique_{story_path.stem}.md"
    with open(critique_file, "w") as f:
        f.write(critique_content)

    console.print(f"\n[bold green]Critique saved to {critique_file}[/bold green]")
    if not external:
        console.print("[dim]Fill in the critique framework, then run refine.[/dim]")


# =============================================================================
# Phase 6: Refine
# =============================================================================


@click.command()
@click.argument("story_file")
@click.argument("critique_file")
@click.option("--output", "-o", default="drafts", help="Output directory")
def refine(story_file: str, critique_file: str, output: str):
    """Refine a story based on critique."""
    console.print(Panel("[bold blue]REFINE PHASE[/bold blue]\nApplying critique"))

    story_path = Path(story_file)
    critique_path = Path(critique_file)

    if not story_path.exists():
        console.print(f"[red]Story file not found: {story_file}[/red]")
        sys.exit(1)
    if not critique_path.exists():
        console.print(f"[red]Critique file not found: {critique_file}[/red]")
        sys.exit(1)

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    # Placeholder - actual refinement would use LLM
    refined_file = output_path / f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}_refined.md"

    console.print(f"[dim]Refining based on critique...[/dim]")
    console.print(f"\n[bold green]Refined draft would be saved to {refined_file}[/bold green]")
    console.print("[dim]This phase integrates with agent's creative refinement capabilities.[/dim]")


# =============================================================================
# Full Workflow: Create
# =============================================================================


@click.command()
@click.argument("thought")
@click.option("--format", "-f", "story_format", default="story", type=click.Choice(list(STORY_FORMATS.keys())))
@click.option("--external-critique", is_flag=True, help="Use external LLM for critique")
@click.option("--iterations", "-n", default=2, help="Number of draft iterations")
@click.option("--output", "-o", default="./story_output", help="Output directory")
def create(thought: str, story_format: str, external_critique: bool, iterations: int, output: str):
    """Full orchestrated workflow: Research → Dogpile → Draft → Critique → Refine → Final."""
    console.print(
        Panel(
            f"[bold magenta]CREATE STORY[/bold magenta]\n\n"
            f'"{thought}"\n\n'
            f"[dim]Format: {STORY_FORMATS[story_format]} | Iterations: {iterations}[/dim]"
        )
    )

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "research").mkdir(exist_ok=True)
    (output_path / "drafts").mkdir(exist_ok=True)
    (output_path / "critiques").mkdir(exist_ok=True)

    project = StoryProject(thought=thought, format=story_format)

    # Phase 1: Initial Thought
    console.print("\n[bold]Phase 1: Initial Thought[/bold]")
    initial = capture_initial_thought(thought, story_format)
    project.metadata["initial_thought"] = initial

    # Phase 2: Research
    console.print("\n[bold]Phase 2: Research[/bold]")
    console.print("[dim]Gathering context from movies, books, memory, past sessions...[/dim]")

    research_results = {
        "topic": thought,
        "timestamp": datetime.now().isoformat(),
        "sources": {},
    }

    # Memory recall
    with console.status("[green]Checking memory (horus-stories)..."):
        mem_result = run_skill("memory", ["recall", "--q", thought, "--scope", "horus-stories"])
        if mem_result.get("returncode") == 0:
            research_results["sources"]["memory"] = mem_result.get("stdout", "")
            console.print("  [green]Found prior stories[/green]")

    project.research = research_results

    # Phase 3: Dogpile
    console.print("\n[bold]Phase 3: Dogpile Context[/bold]")
    dogpile_results = dogpile_context(thought, research_results)
    project.research["dogpile"] = dogpile_results

    # Phase 4-5: Iterative Drafting
    console.print(f"\n[bold]Phase 4-5: Iterative Writing ({iterations} iterations)[/bold]")

    for i in range(iterations):
        console.print(f"\n[cyan]--- Iteration {i + 1}/{iterations} ---[/cyan]")

        # Draft
        console.print(f"  Writing draft {i + 1}...")
        draft_content = f"[Draft {i + 1} placeholder - LLM generates based on research and prior critiques]"
        project.drafts.append({"iteration": i + 1, "content": draft_content})

        # Critique
        critique_mode = "external" if external_critique else "self"
        console.print(f"  Critiquing ({critique_mode})...")
        critique_content = f"[Critique {i + 1} placeholder - {'External LLM' if external_critique else 'Self'} analysis]"
        project.critiques.append({"iteration": i + 1, "mode": critique_mode, "content": critique_content})

    # Phase 6: Final
    console.print("\n[bold]Phase 6: Final Draft[/bold]")
    project.final = "[Final story placeholder - polished based on all critiques]"

    # Phase 7: Store in Memory
    console.print("\n[bold]Phase 7: Store in Memory[/bold]")
    memory_entry = {
        "thought": thought,
        "format": story_format,
        "iterations": iterations,
        "created_at": project.created_at,
    }
    console.print(f"[dim]Would store in horus-stories scope: {json.dumps(memory_entry, indent=2)}[/dim]")

    # Save project
    project.save(output_path / "project.json")

    console.print(
        Panel(
            f"[bold green]STORY PROJECT INITIALIZED[/bold green]\n\n"
            f"Output: {output_path}\n"
            f"Format: {STORY_FORMATS[story_format]}\n"
            f"Iterations: {iterations}\n\n"
            f"[dim]This is the orchestrator skeleton. Full LLM integration "
            f"happens when called by the agent.[/dim]"
        )
    )


# =============================================================================
# CLI Entry Point
# =============================================================================


@click.group()
def cli():
    """create-story: Creative writing orchestrator for Horus persona."""
    pass


cli.add_command(create)
cli.add_command(research)
cli.add_command(draft)
cli.add_command(critique)
cli.add_command(refine)


if __name__ == "__main__":
    cli()
