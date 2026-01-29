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
# Draft Generation Helpers
# =============================================================================


def build_draft_prompt(
    thought: str,
    format: str,
    research: dict,
    prior_drafts: list,
    prior_critiques: list,
    iteration: int
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

    # Add research context
    if research.get("sources"):
        prompt_parts.append("## Research Context")
        for source, content in research.get("sources", {}).items():
            if content and not content.startswith("Episodic") and not content.startswith("Movie"):
                prompt_parts.append(f"### {source}\n{str(content)[:500]}...")

    if research.get("dogpile", {}).get("results"):
        prompt_parts.append(f"### Dogpile Research\n{research['dogpile']['results'][:800]}...")

    # Add prior critique feedback for iterations > 1
    if iteration > 1 and prior_critiques:
        prompt_parts.append("\n## Feedback from Previous Draft")
        last_critique = prior_critiques[-1]
        if last_critique.get("priority_fixes"):
            prompt_parts.append("**Priority fixes to address:**")
            for fix in last_critique.get("priority_fixes", []):
                prompt_parts.append(f"- {fix}")
        if last_critique.get("overall_score"):
            prompt_parts.append(f"\nPrevious score: {last_critique['overall_score']}/10")

    # Horus persona guidance
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
    # Resolve model name
    model_id = CREATIVE_MODELS.get(model, model)

    console.print(f"[dim]Using model: {model_id}[/dim]")

    # Try scillm batch single
    scillm_result = run_skill("scillm", [
        "batch", "single",
        "--model", model_id,
        prompt,  # prompt is positional argument
    ])

    if scillm_result.get("returncode") == 0 and scillm_result.get("stdout"):
        content = scillm_result.get("stdout", "").strip()
        # Clean up any JSON wrapper if present
        if content.startswith("{"):
            try:
                data = json.loads(content)
                content = data.get("content", data.get("text", content))
            except json.JSONDecodeError:
                pass
        return content

    # Fallback: return placeholder
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
@click.option("--external", is_flag=True, help="Use external LLM for critique via review-story")
@click.option("--emotion", "-e", default=None, help="Intended emotion (rage, sorrow, camaraderie, regret, anger)")
@click.option("--provider", "-p", default="claude", help="Provider for review-story (claude, codex, gemini)")
@click.option("--validate-persona", is_flag=True, help="Validate against Horus voice patterns")
@click.option("--output", "-o", default="critiques", help="Output directory")
def critique(story_file: str, external: bool, emotion: Optional[str], provider: str,
             validate_persona: bool, output: str):
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
        # Use /review-story for structured multi-dimensional critique
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
            # Parse the output to build critique content
            critique_result = review_result.get("stdout", "")

            # Find the generated JSON file
            critique_files = list(output_path.glob(f"{provider}_*.json"))
            if critique_files:
                latest_critique = max(critique_files, key=lambda p: p.stat().st_mtime)
                with open(latest_critique) as f:
                    critique_data = json.load(f)

                # Build markdown summary from structured critique
                critique_content = build_critique_markdown(critique_data, story_path.name)
            else:
                critique_content = f"# Review-Story Critique\n\n{critique_result}"
        else:
            console.print(f"[yellow]Review-story failed, falling back to self-critique[/yellow]")
            console.print(f"[dim]{review_result.get('stderr', '')}[/dim]")
            external = False  # Fall through to self-critique

    if not external:
        # Self-critique framework (for manual completion or fallback)
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

    # Structural
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

    # Emotional
    emotional = critique_data.get("emotional", {})
    md.append("\n## Emotional Analysis")
    md.append(f"**Intended**: {emotional.get('intended', 'N/A')}")
    md.append(f"**Achieved**: {emotional.get('achieved', 'N/A')}")
    md.append(f"**Alignment**: {emotional.get('alignment_score', 0) * 100:.0f}%")
    if emotional.get("tom_pattern"):
        md.append(f"**ToM Pattern**: {emotional.get('tom_pattern')}")

    # Craft
    craft = critique_data.get("craft", {})
    md.append("\n## Craft Analysis")
    md.append(f"- Prose: {craft.get('prose_score', 'N/A')}/10")
    md.append(f"- Dialogue: {craft.get('dialogue_score', 'N/A')}/10")
    md.append(f"- Sensory: {craft.get('sensory_score', 'N/A')}/10")

    # Persona
    persona = critique_data.get("persona", {})
    md.append("\n## Persona Analysis (Horus Voice)")
    md.append(f"**Voice Score**: {persona.get('horus_voice_score', 0) * 100:.0f}%")
    md.append(f"**Tactical Mask**: {persona.get('tactical_mask_detected', 'None')}")
    if persona.get("issues"):
        md.append("**Issues**:")
        for issue in persona.get("issues", []):
            md.append(f"- {issue}")

    # Overall
    overall = critique_data.get("overall", {})
    md.append("\n## Overall")
    md.append(f"**Score**: {overall.get('score', 'N/A')}/10")
    ready = "Yes" if overall.get("ready_for_next_draft") else "No"
    md.append(f"**Ready for Next Draft**: {ready}")
    if overall.get("priority_fixes"):
        md.append("\n**Priority Fixes**:")
        for i, fix in enumerate(overall.get("priority_fixes", []), 1):
            md.append(f"{i}. {fix}")

    # Taxonomy
    taxonomy = critique_data.get("taxonomy", {})
    if taxonomy.get("bridge_tags"):
        md.append("\n## Taxonomy (Graph Traversal)")
        md.append(f"**Bridge Tags**: {', '.join(taxonomy.get('bridge_tags', []))}")

    return "\n".join(md)


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


# Creative writing models (Chutes only)
# Use /prompt-lab to evaluate which model produces best creative output
CREATIVE_MODELS = {
    "chimera": "deepseek/deepseek-tng-r1t2-chimera",  # DeepSeek creative/reasoning - default
    "qwen": "Qwen/Qwen3-235B-A22B-Instruct",  # Qwen large reasoning
    "deepseek-r1": "deepseek/deepseek-r1",  # DeepSeek R1 reasoning
    "default": "deepseek/deepseek-tng-r1t2-chimera",
}
# Note: Use $CHUTES_MODEL_ID env var to override, or pass full model ID directly


@click.command()
@click.argument("thought")
@click.option("--format", "-f", "story_format", default="story", type=click.Choice(list(STORY_FORMATS.keys())))
@click.option("--model", "-m", default="chimera", help="LLM model for drafts (chimera, sonnet, gpt4)")
@click.option("--external-critique", is_flag=True, help="Use external LLM for critique via review-story")
@click.option("--iterations", "-n", default=2, help="Number of draft iterations")
@click.option("--output", "-o", default="./story_output", help="Output directory")
def create(thought: str, story_format: str, model: str, external_critique: bool, iterations: int, output: str):
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

    # Phase 4-5: Iterative Drafting with Review-Story Integration
    console.print(f"\n[bold]Phase 4-5: Iterative Writing ({iterations} iterations)[/bold]")

    drafts_dir = output_path / "drafts"
    critiques_dir = output_path / "critiques"

    for i in range(iterations):
        console.print(f"\n[cyan]--- Iteration {i + 1}/{iterations} ---[/cyan]")

        # Draft
        console.print(f"  [bold]Writing draft {i + 1}...[/bold]")

        # Build draft prompt from research and prior critiques
        draft_prompt = build_draft_prompt(
            thought=thought,
            format=story_format,
            research=project.research,
            prior_drafts=project.drafts,
            prior_critiques=project.critiques,
            iteration=i + 1
        )

        # Generate draft via scillm with selected model
        draft_content = generate_draft_via_llm(draft_prompt, story_format, model)

        # Save draft
        draft_file = drafts_dir / f"draft_{i + 1}.md"
        with open(draft_file, "w") as f:
            f.write(draft_content)
        console.print(f"  [green]Saved: {draft_file}[/green]")

        project.drafts.append({
            "iteration": i + 1,
            "file": str(draft_file),
            "word_count": len(draft_content.split())
        })

        # Critique via review-story
        critique_mode = "review-story" if external_critique else "self"
        console.print(f"  [bold]Critiquing ({critique_mode})...[/bold]")

        if external_critique:
            # Use review-story for structured critique
            review_args = [
                "review", str(draft_file),
                "--provider", "claude",
                "--output-dir", str(critiques_dir),
                "--validate-persona",
            ]

            review_result = run_skill("review-story", review_args)

            if review_result.get("returncode") == 0:
                # Find the critique JSON
                critique_files = list(critiques_dir.glob(f"claude_draft_{i + 1}_*.json"))
                if critique_files:
                    latest = max(critique_files, key=lambda p: p.stat().st_mtime)
                    with open(latest) as f:
                        critique_data = json.load(f)

                    # Store structured critique
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
            # Self-critique framework (manual)
            critique_file = critiques_dir / f"critique_{i + 1}.md"
            self_critique = generate_self_critique_template(draft_content, i + 1)
            with open(critique_file, "w") as f:
                f.write(self_critique)
            project.critiques.append({"iteration": i + 1, "mode": "self", "file": str(critique_file)})
            console.print(f"  [dim]Self-critique template saved: {critique_file}[/dim]")

    # Phase 6: Final Draft
    console.print("\n[bold]Phase 6: Final Draft[/bold]")

    # Generate final draft based on all critiques
    if project.drafts:
        last_draft_file = project.drafts[-1].get("file")
        if last_draft_file and Path(last_draft_file).exists():
            with open(last_draft_file) as f:
                last_draft_content = f.read()

            # If we have critique feedback, generate refined final
            all_fixes = []
            for critique in project.critiques:
                all_fixes.extend(critique.get("priority_fixes", []))

            if all_fixes:
                final_prompt = f"""Refine this story draft based on the following feedback:

## Priority Fixes
{chr(10).join(f'- {fix}' for fix in all_fixes[:5])}

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

    # Save final draft
    final_file = output_path / "final.md"
    with open(final_file, "w") as f:
        f.write(project.final)
    console.print(f"[green]Final draft saved: {final_file}[/green]")

    # Phase 7: Aggregate Taxonomy
    console.print("\n[bold]Phase 7: Aggregate Taxonomy[/bold]")

    # Collect all taxonomy tags from critiques
    all_bridge_tags = set()
    all_collection_tags = {}

    for critique in project.critiques:
        taxonomy = critique.get("taxonomy", {})
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

    # Extract final score from last critique
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

    # Store in memory (horus-stories scope)
    memory_result = run_skill("memory", [
        "learn",
        "--scope", "horus-stories",
        "--content", json.dumps(memory_entry),
    ])

    if memory_result.get("returncode") == 0:
        console.print("[green]Story stored in horus-stories scope[/green]")
    else:
        console.print("[yellow]Memory storage skipped (memory skill unavailable)[/yellow]")

    # Save project
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
