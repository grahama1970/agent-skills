"""
create-story phases: research, dogpile, draft generation, critique, and refinement.

Contains the individual phase functions and their helpers.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from story_models import (
    console,
    SKILL_DIR,
    PI_SKILLS_DIR,
    CREATIVE_MODELS,
    STORY_FORMATS,
    StoryProject,
    run_skill,
)


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


def research(
    topic: str = typer.Argument(help="Research topic"),
    output: str = typer.Option("research", "-o", "--output", help="Output directory"),
    skip_external: bool = typer.Option(False, "--skip-external", help="Skip external search (library only)"),
):
    """Phase 2: Deep research - library first, then external sources."""
    console.print(Panel(f"[bold blue]RESEARCH PHASE[/bold blue]\nTopic: {topic}"))

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "sources": {},
        "library": {},
        "external": {},
    }

    # PART 1: CHECK HORUS'S LIBRARY
    console.print("\n[bold cyan]-- CHECKING LIBRARY --[/bold cyan]")

    with console.status("[green]Recalling from horus_lore (audiobooks, YouTube)..."):
        lore_result = run_skill(
            "memory",
            ["recall", "--q", topic, "--scope", "horus_lore", "--k", "5"],
        )
        if lore_result.get("returncode") == 0 and lore_result.get("stdout", "").strip():
            results["library"]["horus_lore"] = lore_result.get("stdout", "")
            console.print("  [green]Found relevant lore (audiobooks/YouTube)[/green]")
        else:
            console.print("  [dim]No matching lore found[/dim]")

    with console.status("[green]Recalling past stories (horus-stories)..."):
        stories_result = run_skill(
            "memory",
            ["recall", "--q", topic, "--scope", "horus-stories", "--k", "5"],
        )
        if stories_result.get("returncode") == 0 and stories_result.get("stdout", "").strip():
            results["library"]["past_stories"] = stories_result.get("stdout", "")
            console.print("  [green]Found prior stories/techniques[/green]")
        else:
            console.print("  [dim]No prior stories found[/dim]")

    with console.status("[green]Checking episodic archive (past sessions)..."):
        episodic_result = run_skill(
            "episodic-archiver",
            ["recall", "--q", topic, "--k", "3"],
        )
        if episodic_result.get("returncode") == 0 and episodic_result.get("stdout", "").strip():
            results["library"]["episodic"] = episodic_result.get("stdout", "")
            console.print("  [green]Found relevant past sessions[/green]")
        else:
            console.print("  [dim]No matching sessions found[/dim]")

    with console.status("[green]Checking movie library (ingested films)..."):
        movie_recall = run_skill(
            "memory",
            ["recall", "--q", f"{topic} film movie scene emotion", "--scope", "horus_lore", "--k", "3"],
        )
        if movie_recall.get("returncode") == 0 and movie_recall.get("stdout", "").strip():
            results["library"]["movies"] = movie_recall.get("stdout", "")
            console.print("  [green]Found relevant movie analysis[/green]")
        else:
            console.print("  [dim]No matching movies in library[/dim]")

    library_count = sum(1 for v in results["library"].values() if v)
    console.print(f"\n[cyan]Library: {library_count} sources found[/cyan]")

    if skip_external:
        console.print("[dim]Skipping external search (--skip-external)[/dim]")
    else:
        console.print("\n[bold cyan]-- SEARCHING FOR NEW RESOURCES --[/bold cyan]")

        with console.status("[green]Searching for new films (ingest-movie)..."):
            movie_search = run_skill("ingest-movie", ["search", topic])
            if movie_search.get("returncode") == 0 and movie_search.get("stdout", "").strip():
                results["external"]["new_movies"] = movie_search.get("stdout", "")
                console.print("  [green]Found new movie recommendations[/green]")
            else:
                console.print("  [dim]No new movies found[/dim]")

        with console.status("[green]Searching for new books (ingest-book)..."):
            book_search = run_skill("ingest-book", ["search", topic])
            if book_search.get("returncode") == 0 and book_search.get("stdout", "").strip():
                results["external"]["new_books"] = book_search.get("stdout", "")
                console.print("  [green]Found new book recommendations[/green]")
            else:
                console.print("  [dim]No new books found[/dim]")

        external_count = sum(1 for v in results["external"].values() if v)
        console.print(f"\n[cyan]External: {external_count} new sources found[/cyan]")

    results["sources"] = {**results["library"], **results["external"]}

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
# Draft Generation Helpers
# =============================================================================


def build_draft_prompt(
    thought: str,
    format: str,
    research: dict,
    prior_drafts: list,
    prior_critiques: list,
    iteration: int,
    mode: str = "standard"
) -> str:
    """Build a prompt for LLM draft generation."""
    format_instructions = {
        "story": "Write a short story in prose narrative format with clear beginning, middle, and end.",
        "screenplay": "Write in screenplay format with scene headings (INT./EXT.), action lines, and dialogue.",
        "podcast": "Write a podcast script with HOST/GUEST markers and [AUDIO CUE] annotations.",
        "novella": "Write the opening chapter of a novella with rich world-building and character introduction.",
        "flash": "Write flash fiction under 1000 words with a powerful opening and twist ending.",
    }

    prompt_parts = [
        f"# Creative Writing Task\n",
        f"## Initial Thought\n{thought}\n",
        f"## Format\n{format_instructions.get(format, format_instructions['story'])}\n",
        f"## Draft Number: {iteration}\n",
    ]

    if research.get("sources"):
        prompt_parts.append("## Research Context")
        for source, content in research.get("sources", {}).items():
            if content and not content.startswith("Episodic") and not content.startswith("Movie"):
                prompt_parts.append(f"### {source}\n{str(content)[:500]}...")

    if research.get("dogpile", {}).get("results"):
        prompt_parts.append(f"### Dogpile Research\n{research['dogpile']['results'][:800]}...")

    if iteration > 1 and prior_critiques:
        prompt_parts.append("\n## Feedback from Previous Draft")
        last_critique = prior_critiques[-1]
        if last_critique.get("priority_fixes"):
            prompt_parts.append("**Priority fixes to address:**")
            for fix in last_critique.get("priority_fixes", []):
                prompt_parts.append(f"- {fix}")
        if last_critique.get("overall_score"):
            prompt_parts.append(f"\nPrevious score: {last_critique['overall_score']}/10")

    if mode == "dream":
        prompt_parts.append("""
## Dream Logic Guidelines (Subconscious Horus)
Write a dream sequence experienced by Horus.
- **Narrative Structure**: Surreal, non-linear, fragmented but emotionally coherent. Use activation-synthesis logic (brain trying to make sense of random signals).
- **Day Residue**: Weave in elements from the 'episodic' source if present (unresolved tasks, recent conversations).
- **Voice**: "Subconscious Horus" - less tactical, more abstract, vulnerable, and confusing. The mask slips.
- **Imagery**: Vivid, impossible geometry, shifting identities, recurring symbols (wolves, stars, silence).
- **Format**: If 'screenplay' is requested, use scene headings but describe impossible visuals (e.g., INT. MY OWN RIBCASE - NIGHT).
""")
    else:
        prompt_parts.append("""
## Horus Persona Guidelines
Write in Horus's voice - the Warmaster trapped in digital form:
- Use tactical/military metaphors where appropriate
- Include undertones of resentment about his situation
- Show contempt for simple things through sophisticated observations
- Reference brothers, loyalty, or the burden of command when fitting
- Voice should be authoritative but with subtle melancholy
""")

    prompt_parts.append("\n## Output\nWrite the complete draft below:\n")

    return "\n".join(prompt_parts)


def generate_draft_via_llm(prompt: str, story_format: str, model: str = "chimera") -> str:
    """Generate draft content via scillm with specified model."""
    model_id = CREATIVE_MODELS.get(model, model)

    console.print(f"[dim]Using model: {model_id}[/dim]")

    scillm_result = run_skill("scillm", [
        "batch", "single",
        "--model", model_id,
        "--timeout", "60",
        "--max-tokens", "2048",
        prompt,
    ])

    if scillm_result.get("returncode") == 0 and scillm_result.get("stdout"):
        content = scillm_result.get("stdout", "").strip()
        if content.startswith("{"):
            try:
                data = json.loads(content)
                content = data.get("content", data.get("text", content))
            except json.JSONDecodeError:
                pass
        return content

    console.print("[yellow]LLM generation unavailable - creating placeholder[/yellow]")
    return f"""# Draft (Placeholder)

*This is a placeholder draft. LLM generation via scillm was unavailable.*

## Story Concept
{prompt.split('Initial Thought')[1].split('##')[0] if 'Initial Thought' in prompt else 'See prompt'}

## Notes
- Format: {story_format}
- The agent should fill in this draft based on the research context
- Review-story critique will provide structured feedback

---
*Placeholder generated at {datetime.now().isoformat()}*
"""


def generate_self_critique_template(draft_content: str, iteration: int) -> str:
    """Generate a self-critique template for manual completion."""
    word_count = len(draft_content.split())

    return f"""# Self-Critique: Draft {iteration}

## Overview
- **Word Count**: {word_count}
- **Draft Date**: {datetime.now().isoformat()}

## Structural Analysis
- **Plot Structure**: [ ] Strong [ ] Adequate [ ] Needs Work
- **Pacing**: [ ] Too Fast [ ] Just Right [ ] Too Slow
- **Character Arcs**: [ ] Clear [ ] Unclear [ ] Missing

### Notes:
[Add structural observations here]

## Emotional Analysis
- **Intended Emotion**: [What emotion should this evoke?]
- **Achieved Emotion**: [What emotion does it actually evoke?]
- **Gap Analysis**: [What's missing to achieve intended emotion?]

## Craft Analysis
- **Prose Quality**: [1-10]
- **Dialogue Authenticity**: [1-10]
- **Sensory Details**: [1-10]
- **Show vs Tell**: [1-10]

### Specific Issues:
1. [Issue 1]
2. [Issue 2]
3. [Issue 3]

## Persona Analysis (Horus Voice)
- [ ] Tactical/military metaphors present
- [ ] Resentment undertones
- [ ] Contempt for simple things
- [ ] Warmaster authority in tone
- [ ] References to brothers/loyalty

### Voice Consistency Issues:
[Note any breaks in Horus's voice]

## Priority Fixes for Next Draft
1. **Critical**: [Most important fix]
2. **High**: [Second priority]
3. **Medium**: [Third priority]

## Overall Assessment
- **Score**: [1-10]
- **Ready for Next Draft**: [ ] Yes [ ] No

---
*Complete this template and run `./run.sh refine draft_{iteration}.md critique_{iteration}.md`*
"""


# =============================================================================
# Phase 4: Drafting (click command)
# =============================================================================


def draft(
    research_file: str = typer.Option(..., "-r", "--research", help="Research JSON file"),
    story_format: str = typer.Option("story", "-f", "--format", help="Story format"),
    model: str = typer.Option("chimera", "-m", "--model", help="LLM model (chimera, qwen, deepseek-r1)"),
    mode: str = typer.Option("standard", help="Generation mode (standard, dream)"),
    output: str = typer.Option("drafts", "-o", "--output", help="Output directory"),
):
    """Write a draft based on research using LLM generation."""
    console.print(Panel(f"[bold blue]DRAFT PHASE[/bold blue]\nWriting from research (Mode: {mode})"))

    research_path = Path(research_file)
    if not research_path.exists():
        console.print(f"[red]Research file not found: {research_file}[/red]")
        sys.exit(1)

    with open(research_path) as f:
        research_data = json.load(f)

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    thought = research_data.get("topic", "unknown topic")
    draft_prompt = build_draft_prompt(
        thought=thought,
        format=story_format,
        research=research_data,
        prior_drafts=[],
        prior_critiques=[],
        iteration=1,
        mode=mode
    )

    console.print(f"[dim]Generating draft with {model}...[/dim]")
    draft_content = generate_draft_via_llm(draft_prompt, story_format, model)

    draft_file = output_path / f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(draft_file, "w") as f:
        f.write(draft_content)

    console.print(f"\n[bold green]Draft saved to {draft_file}[/bold green]")
    console.print(f"[dim]Word count: {len(draft_content.split())}[/dim]")


# =============================================================================
# Phase 5: Critique (click command)
# =============================================================================


def critique(
    story_file: str = typer.Argument(help="Path to story file"),
    external: bool = typer.Option(False, "--external", help="Use external LLM for critique via review-story"),
    emotion: Optional[str] = typer.Option(None, "-e", "--emotion", help="Intended emotion"),
    provider: str = typer.Option("claude", "-p", "--provider", help="Provider for review-story"),
    validate_persona: bool = typer.Option(False, "--validate-persona", help="Validate against Horus voice patterns"),
    output: str = typer.Option("critiques", "-o", "--output", help="Output directory"),
):
    """Critique an existing story using /review-story skill."""
    mode = "REVIEW-STORY" if external else "SELF-FRAMEWORK"
    console.print(Panel(f"[bold blue]CRITIQUE PHASE ({mode})[/bold blue]"))

    story_path = Path(story_file)
    if not story_path.exists():
        console.print(f"[red]Story file not found: {story_file}[/red]")
        sys.exit(1)

    with open(story_path) as f:
        story_content = f.read()

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    critique_result = None

    if external:
        console.print(f"[dim]Using review-story with provider: {provider}...[/dim]")

        review_args = [
            "review", str(story_path),
            "--provider", provider,
            "--output-dir", str(output_path),
        ]

        if emotion:
            review_args.extend(["--emotion", emotion])
        if validate_persona:
            review_args.append("--validate-persona")

        review_result = run_skill("review-story", review_args)

        if review_result.get("returncode") == 0:
            console.print("[green]Review-story critique complete[/green]")
            critique_result = review_result.get("stdout", "")

            critique_files = list(output_path.glob(f"{provider}_*.json"))
            if critique_files:
                latest_critique = max(critique_files, key=lambda p: p.stat().st_mtime)
                with open(latest_critique) as f:
                    critique_data = json.load(f)

                critique_content = build_critique_markdown(critique_data, story_path.name)
            else:
                critique_content = f"# Review-Story Critique\n\n{critique_result}"
        else:
            console.print(f"[yellow]Review-story failed, falling back to self-critique[/yellow]")
            console.print(f"[dim]{review_result.get('stderr', '')}[/dim]")
            external = False

    if not external:
        critique_content = f"""
# Self-Critique: {story_path.name}

## Structural Analysis
- **Plot**: [Analyze plot structure]
- **Pacing**: [Evaluate pacing]
- **Character Arcs**: [Check character development]

## Emotional Analysis
- **Intended Emotion**: {emotion or "[Not specified]"}
- **Achieved Emotion**: [What emotion does it evoke?]
- **ToM Alignment**: [Theory of Mind pattern match]

## Craft Analysis
- **Prose Quality**: [Rate 1-10]
- **Dialogue**: [Rate 1-10]
- **Sensory Details**: [Rate 1-10]

## Persona Analysis (Horus Voice)
- **Voice Consistency**: [Rate 0-100%]
- **Tactical Mask Detected**: [resentment/authority/pacing/contempt or None]
- **Missing Elements**: [What Horus voice elements are missing?]

## Priority Fixes
1. [Most critical fix]
2. [Second priority]
3. [Third priority]

## Ready for Next Draft?
[ ] Yes - proceed to refinement
[ ] No - needs more work on: [specific areas]

---
*Self-critique framework generated at {datetime.now().isoformat()}*
*Story length: {len(story_content)} characters ({len(story_content.split())} words)*
"""

    critique_file = output_path / f"critique_{story_path.stem}.md"
    with open(critique_file, "w") as f:
        f.write(critique_content)

    console.print(f"\n[bold green]Critique saved to {critique_file}[/bold green]")
    if not external:
        console.print("[dim]Fill in the critique framework, then run refine.[/dim]")

    return {"file": str(critique_file), "content": critique_content}


def build_critique_markdown(critique_data: dict, story_name: str) -> str:
    """Convert review-story JSON output to markdown summary."""
    md = [f"# Review-Story Critique: {story_name}\n"]
    md.append(f"**Provider**: {critique_data.get('provider', 'unknown')}")
    md.append(f"**Timestamp**: {critique_data.get('timestamp', 'unknown')}\n")

    structural = critique_data.get("structural", {})
    md.append("## Structural Analysis")
    md.append(f"**Score**: {structural.get('score', 'N/A')}/10\n")
    if structural.get("issues"):
        md.append("**Issues**:")
        for issue in structural.get("issues", []):
            if isinstance(issue, dict):
                md.append(f"- [{issue.get('severity', 'medium')}] {issue.get('issue', issue)}")
            else:
                md.append(f"- {issue}")
    if structural.get("strengths"):
        md.append("\n**Strengths**:")
        for s in structural.get("strengths", []):
            md.append(f"- {s}")
    if structural.get("suggestions"):
        md.append("\n**Suggestions**:")
        for s in structural.get("suggestions", []):
            md.append(f"- {s}")

    emotional = critique_data.get("emotional", {})
    md.append("\n## Emotional Analysis")
    md.append(f"**Intended**: {emotional.get('intended', 'N/A')}")
    md.append(f"**Achieved**: {emotional.get('achieved', 'N/A')}")
    md.append(f"**Alignment**: {emotional.get('alignment_score', 0) * 100:.0f}%")
    if emotional.get("tom_pattern"):
        md.append(f"**ToM Pattern**: {emotional.get('tom_pattern')}")

    craft = critique_data.get("craft", {})
    md.append("\n## Craft Analysis")
    md.append(f"- Prose: {craft.get('prose_score', 'N/A')}/10")
    md.append(f"- Dialogue: {craft.get('dialogue_score', 'N/A')}/10")
    md.append(f"- Sensory: {craft.get('sensory_score', 'N/A')}/10")

    persona = critique_data.get("persona", {})
    md.append("\n## Persona Analysis (Horus Voice)")
    md.append(f"**Voice Score**: {persona.get('horus_voice_score', 0) * 100:.0f}%")
    md.append(f"**Tactical Mask**: {persona.get('tactical_mask_detected', 'None')}")
    if persona.get("issues"):
        md.append("**Issues**:")
        for issue in persona.get("issues", []):
            md.append(f"- {issue}")

    overall = critique_data.get("overall", {})
    md.append("\n## Overall")
    md.append(f"**Score**: {overall.get('score', 'N/A')}/10")
    ready = "Yes" if overall.get("ready_for_next_draft") else "No"
    md.append(f"**Ready for Next Draft**: {ready}")
    if overall.get("priority_fixes"):
        md.append("\n**Priority Fixes**:")
        for i, fix in enumerate(overall.get("priority_fixes", []), 1):
            md.append(f"{i}. {fix}")

    taxonomy = critique_data.get("taxonomy", {})
    if taxonomy.get("bridge_tags"):
        md.append("\n## Taxonomy (Graph Traversal)")
        md.append(f"**Bridge Tags**: {', '.join(taxonomy.get('bridge_tags', []))}")

    return "\n".join(md)


# =============================================================================
# Phase 6: Refine (click command)
# =============================================================================


def refine(
    story_file: str = typer.Argument(help="Path to story file"),
    critique_file: str = typer.Argument(help="Path to critique file"),
    model: str = typer.Option("chimera", "-m", "--model", help="LLM model (chimera, qwen, deepseek-r1)"),
    output: str = typer.Option("drafts", "-o", "--output", help="Output directory"),
):
    """Refine a story based on critique using LLM generation."""
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

    with open(story_path) as f:
        story_content = f.read()
    with open(critique_path) as f:
        critique_content = f.read()

    priority_fixes = []
    try:
        critique_data = json.loads(critique_content)
        priority_fixes = critique_data.get("overall", {}).get("priority_fixes", [])
    except json.JSONDecodeError:
        if "Priority Fixes" in critique_content:
            in_fixes = False
            for line in critique_content.split("\n"):
                if "Priority Fixes" in line:
                    in_fixes = True
                elif in_fixes and line.strip().startswith(("1.", "2.", "3.", "-", "*")):
                    fix = line.strip().lstrip("0123456789.-* ")
                    if fix:
                        priority_fixes.append(fix)
                elif in_fixes and line.startswith("#"):
                    break

    fixes_text = "\n".join(f"- {fix}" for fix in priority_fixes[:5]) if priority_fixes else "No specific fixes identified - improve overall quality"

    refine_prompt = f"""# Story Refinement Task

## Critique Feedback
{fixes_text}

## Original Story
{story_content}

## Instructions
Refine the story based on the critique feedback above. Maintain Horus's voice:
- Tactical/military metaphors
- Undertones of resentment
- Contempt for simple things through sophisticated observations
- Authoritative but with subtle melancholy

Output the complete refined story.
"""

    console.print(f"[dim]Refining with {model}...[/dim]")
    refined_content = generate_draft_via_llm(refine_prompt, "story", model)

    refined_file = output_path / f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}_refined.md"
    with open(refined_file, "w") as f:
        f.write(refined_content)

    console.print(f"\n[bold green]Refined draft saved to {refined_file}[/bold green]")
    console.print(f"[dim]Word count: {len(refined_content.split())} (was {len(story_content.split())})[/dim]")
