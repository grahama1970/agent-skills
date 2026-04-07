#!/usr/bin/env python3
"""
create-story Orchestrator for Horus Persona

Thin assembler: imports from story_models and story_phases,
provides the create() workflow and CLI entry point.

Creative writing through deep research and iterative refinement:
Initial Thought -> Research -> Dogpile -> Draft 1 -> Critique -> Draft 2 -> Final
"""

import json
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Re-export everything from sub-modules
from story_models import (
    console,
    SKILL_DIR,
    PI_SKILLS_DIR,
    CREATIVE_MODELS,
    STORY_FORMATS,
    StoryProject,
    run_skill,
)

from story_phases import (
    capture_initial_thought,
    research,
    dogpile_context,
    build_draft_prompt,
    generate_draft_via_llm,
    generate_self_critique_template,
    draft,
    critique,
    build_critique_markdown,
    refine,
)

# Memory integration (graceful degradation)
_memory_recall_prior_stories = None
_memory_learn_story = None
try:
    from memory_integration import recall_prior_stories as _memory_recall_prior_stories
    from memory_integration import learn_story as _memory_learn_story
except ImportError:
    pass  # Memory integration optional


# =============================================================================
# Full Workflow: Create
# =============================================================================


def create(
    thought: str = typer.Argument(help="Initial creative thought/concept"),
    story_format: str = typer.Option("story", "-f", "--format", help="Story format: story, screenplay, podcast, novella, flash"),
    model: str = typer.Option("chimera", "-m", "--model", help="LLM model for drafts (chimera, qwen, deepseek-r1)"),
    mode: str = typer.Option("standard", help="Generation mode (standard, dream)"),
    external_critique: bool = typer.Option(False, "--external-critique", help="Use external LLM for critique via review-story"),
    iterations: int = typer.Option(2, "-n", "--iterations", help="Number of draft iterations"),
    output: str = typer.Option("./story_output", "-o", "--output", help="Output directory"),
):
    """Full orchestrated workflow: Research -> Dogpile -> Draft -> Critique -> Refine -> Final."""
    console.print(
        Panel(
            f"[bold magenta]CREATE STORY[/bold magenta]\n\n"
            f'"{thought}"\n\n'
            f"[dim]Format: {STORY_FORMATS[story_format]} | Mode: {mode} | Iterations: {iterations}[/dim]"
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

    # Memory pre-hook: recall prior stories for creative continuity
    if _memory_recall_prior_stories:
        try:
            prior_context = _memory_recall_prior_stories(thought, genre=story_format, k=5)
            if prior_context:
                project.metadata["prior_stories_context"] = prior_context
                console.print(f"[dim]Recalled prior story context ({len(prior_context)} chars)[/dim]")
        except Exception as e:
            console.print(f"[dim]Memory recall skipped: {e}[/dim]")

    # Phase 2: Research
    console.print("\n[bold]Phase 2: Research[/bold]")

    research_results = {
        "topic": thought,
        "timestamp": datetime.now().isoformat(),
        "library": {},
        "external": {},
        "sources": {},
    }

    console.print("\n[cyan]-- Checking Library --[/cyan]")

    with console.status("[green]Recalling from horus_lore (audiobooks, YouTube)..."):
        lore_result = run_skill("memory", ["recall", "--q", thought, "--scope", "horus_lore", "--k", "5"])
        if lore_result.get("returncode") == 0 and lore_result.get("stdout", "").strip():
            research_results["library"]["horus_lore"] = lore_result.get("stdout", "")
            console.print("  [green]Found relevant lore[/green]")

    with console.status("[green]Recalling past stories (horus-stories)..."):
        stories_result = run_skill("memory", ["recall", "--q", thought, "--scope", "horus-stories", "--k", "5"])
        if stories_result.get("returncode") == 0 and stories_result.get("stdout", "").strip():
            research_results["library"]["past_stories"] = stories_result.get("stdout", "")
            console.print("  [green]Found prior stories[/green]")

    with console.status("[green]Checking episodic archive..."):
        episodic_result = run_skill("episodic-archiver", ["recall", "--q", thought, "--k", "3"])
        if episodic_result.get("returncode") == 0 and episodic_result.get("stdout", "").strip():
            research_results["library"]["episodic"] = episodic_result.get("stdout", "")
            console.print("  [green]Found past sessions[/green]")

    with console.status("[green]Checking movie library..."):
        movie_recall = run_skill("memory", ["recall", "--q", f"{thought} film movie scene emotion", "--scope", "horus_lore", "--k", "3"])
        if movie_recall.get("returncode") == 0 and movie_recall.get("stdout", "").strip():
            research_results["library"]["movies"] = movie_recall.get("stdout", "")
            console.print("  [green]Found movie analysis[/green]")

    library_count = sum(1 for v in research_results["library"].values() if v)
    console.print(f"[cyan]Library: {library_count} sources found[/cyan]")

    console.print("\n[cyan]-- Searching for New Resources --[/cyan]")

    with console.status("[green]Searching for new films (ingest-movie)..."):
        movie_search = run_skill("ingest-movie", ["search", thought])
        if movie_search.get("returncode") == 0 and movie_search.get("stdout", "").strip():
            research_results["external"]["new_movies"] = movie_search.get("stdout", "")
            console.print("  [green]Found new movie recommendations[/green]")

    with console.status("[green]Searching for new books (ingest-book)..."):
        book_search = run_skill("ingest-book", ["search", thought])
        if book_search.get("returncode") == 0 and book_search.get("stdout", "").strip():
            research_results["external"]["new_books"] = book_search.get("stdout", "")
            console.print("  [green]Found new book recommendations[/green]")

    external_count = sum(1 for v in research_results["external"].values() if v)
    console.print(f"[cyan]External: {external_count} new sources found[/cyan]")

    research_results["sources"] = {**research_results["library"], **research_results["external"]}
    project.research = research_results

    # Phase 3: Dogpile
    console.print("\n[bold]Phase 3: Dogpile Context[/bold]")
    dogpile_results = dogpile_context(thought, research_results)
    project.research["dogpile"] = dogpile_results

    # Phase 4-5: Iterative Drafting
    console.print(f"\n[bold]Phase 4-5: Iterative Writing ({iterations} iterations)[/bold]")

    drafts_dir = output_path / "drafts"
    critiques_dir = output_path / "critiques"

    for i in range(iterations):
        console.print(f"\n[cyan]--- Iteration {i + 1}/{iterations} ---[/cyan]")

        console.print(f"  [bold]Writing draft {i + 1}...[/bold]")

        draft_prompt = build_draft_prompt(
            thought=thought,
            format=story_format,
            research=project.research,
            prior_drafts=project.drafts,
            prior_critiques=project.critiques,
            iteration=i + 1
        )

        draft_content = generate_draft_via_llm(draft_prompt, story_format, model)

        draft_file = drafts_dir / f"draft_{i + 1}.md"
        with open(draft_file, "w") as f:
            f.write(draft_content)
        console.print(f"  [green]Saved: {draft_file}[/green]")

        project.drafts.append({
            "iteration": i + 1,
            "file": str(draft_file),
            "word_count": len(draft_content.split())
        })

        critique_mode = "review-story" if external_critique else "self"
        console.print(f"  [bold]Critiquing ({critique_mode})...[/bold]")

        if external_critique:
            review_args = [
                "review", str(draft_file),
                "--provider", "claude",
                "--output-dir", str(critiques_dir),
                "--validate-persona",
            ]

            review_result = run_skill("review-story", review_args)

            if review_result.get("returncode") == 0:
                critique_files = list(critiques_dir.glob(f"claude_draft_{i + 1}_*.json"))
                if critique_files:
                    latest = max(critique_files, key=lambda p: p.stat().st_mtime)
                    with open(latest) as f:
                        critique_data = json.load(f)

                    project.critiques.append({
                        "iteration": i + 1,
                        "mode": "review-story",
                        "file": str(latest),
                        "overall_score": critique_data.get("overall", {}).get("score"),
                        "ready_for_next": critique_data.get("overall", {}).get("ready_for_next_draft"),
                        "priority_fixes": critique_data.get("overall", {}).get("priority_fixes", []),
                        "taxonomy": critique_data.get("taxonomy", {})
                    })
                    console.print(f"  [green]Score: {critique_data.get('overall', {}).get('score', 'N/A')}/10[/green]")
                else:
                    console.print("  [yellow]Critique file not found[/yellow]")
                    project.critiques.append({"iteration": i + 1, "mode": "review-story", "error": "file not found"})
            else:
                console.print(f"  [yellow]Review-story failed: {review_result.get('stderr', '')[:100]}[/yellow]")
                project.critiques.append({"iteration": i + 1, "mode": "review-story", "error": review_result.get("stderr", "")})
        else:
            critique_file = critiques_dir / f"critique_{i + 1}.md"
            self_critique = generate_self_critique_template(draft_content, i + 1)
            with open(critique_file, "w") as f:
                f.write(self_critique)
            project.critiques.append({"iteration": i + 1, "mode": "self", "file": str(critique_file)})
            console.print(f"  [dim]Self-critique template saved: {critique_file}[/dim]")

    # Phase 6: Final Draft
    console.print("\n[bold]Phase 6: Final Draft[/bold]")

    if project.drafts:
        last_draft_file = project.drafts[-1].get("file")
        if last_draft_file and Path(last_draft_file).exists():
            with open(last_draft_file) as f:
                last_draft_content = f.read()

            all_fixes = []
            for crit in project.critiques:
                all_fixes.extend(crit.get("priority_fixes", []))

            if all_fixes:
                fixes_list = '\n'.join(f'- {fix}' for fix in all_fixes[:5])
                final_prompt = f"""Refine this story draft based on the following feedback:

## Priority Fixes
{fixes_list}

## Current Draft
{last_draft_content}

## Instructions
Apply the fixes above while maintaining Horus's voice. Output the complete refined story.
"""
                project.final = generate_draft_via_llm(final_prompt, story_format, model)
            else:
                project.final = last_draft_content
        else:
            project.final = "[Final draft generation failed - no prior drafts found]"
    else:
        project.final = "[No drafts were generated]"

    final_file = output_path / "final.md"
    with open(final_file, "w") as f:
        f.write(project.final or "[Final draft unavailable]")
    console.print(f"[green]Final draft saved: {final_file}[/green]")

    # Phase 7: Aggregate Taxonomy
    console.print("\n[bold]Phase 7: Aggregate Taxonomy[/bold]")

    all_bridge_tags = set()
    all_collection_tags = {}

    for crit in project.critiques:
        taxonomy = crit.get("taxonomy", {})
        for tag in taxonomy.get("bridge_tags", []):
            all_bridge_tags.add(tag)
        for dim, val in taxonomy.get("collection_tags", {}).items():
            if dim not in all_collection_tags:
                all_collection_tags[dim] = set()
            if isinstance(val, list):
                all_collection_tags[dim].update(val)
            else:
                all_collection_tags[dim].add(val)

    project.metadata["taxonomy"] = {
        "bridge_tags": list(all_bridge_tags),
        "collection_tags": {k: list(v) for k, v in all_collection_tags.items()},
        "worth_remembering": len(all_bridge_tags) > 0
    }

    if all_bridge_tags:
        console.print(f"[green]Bridge tags: {', '.join(all_bridge_tags)}[/green]")

    # Phase 8: Store in Memory
    console.print("\n[bold]Phase 8: Store in Memory[/bold]")

    final_score = None
    if project.critiques:
        final_score = project.critiques[-1].get("overall_score")

    memory_entry = {
        "title": f"Story: {thought[:50]}...",
        "thought": thought,
        "format": story_format,
        "iterations": iterations,
        "final_score": final_score,
        "word_count": len(project.final.split()) if project.final else 0,
        "created_at": project.created_at,
        "taxonomy": project.metadata.get("taxonomy", {}),
        "learnings": [
            f"Format {story_format} with {iterations} iterations",
            f"Final score: {final_score}/10" if final_score else "No score available",
        ]
    }

    memory_result = run_skill("memory", [
        "learn",
        "--scope", "horus-stories",
        "--content", json.dumps(memory_entry),
    ])

    if memory_result.get("returncode") == 0:
        console.print("[green]Story stored in horus-stories scope[/green]")
    else:
        console.print("[yellow]Memory storage skipped (memory skill unavailable)[/yellow]")

    # Memory post-hook: learn story decisions via memory_integration
    if _memory_learn_story:
        try:
            learned_ids = _memory_learn_story(
                title=f"Story: {thought[:50]}",
                genre=story_format,
                themes=list(all_bridge_tags) if all_bridge_tags else [],
                characters=[],  # Extracted from drafts if available
                narrative_decisions=memory_entry.get("learnings", []),
                word_count=len(project.final.split()) if project.final else 0,
                final_score=final_score,
                format_type=story_format,
                iterations=iterations,
            )
            if learned_ids:
                console.print(f"[green]Learned {len(learned_ids)} entries to memory integration[/green]")
        except Exception as e:
            console.print(f"[dim]Memory integration learn skipped: {e}[/dim]")

    project.save(output_path / "project.json")

    # Summary
    summary_table = Table(title="Story Project Complete")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_row("Output", str(output_path))
    summary_table.add_row("Format", STORY_FORMATS[story_format])
    summary_table.add_row("Iterations", str(iterations))
    summary_table.add_row("Final Word Count", str(len(project.final.split()) if project.final else 0))
    summary_table.add_row("Final Score", f"{final_score}/10" if final_score else "N/A")
    summary_table.add_row("Bridge Tags", ", ".join(all_bridge_tags) if all_bridge_tags else "None")

    console.print(summary_table)

    console.print(
        Panel(
            f"[bold green]STORY COMPLETE[/bold green]\n\n"
            f"Final: {final_file}\n"
            f"Project: {output_path / 'project.json'}\n\n"
            f"[dim]Story stored in memory for future recall.[/dim]"
        )
    )


# =============================================================================
# CLI Entry Point
# =============================================================================


cli = typer.Typer(help="create-story: Creative writing orchestrator for Horus persona.")

cli.command("create")(create)
cli.command("research")(research)
cli.command("draft")(draft)
cli.command("critique")(critique)
cli.command("refine")(refine)


if __name__ == "__main__":
    cli()
