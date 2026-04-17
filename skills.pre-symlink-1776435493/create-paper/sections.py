"""
Paper Writer Skill - Sections
Section content generation, stub fallbacks, interview scope, and persona prompt enhancement.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

from config import (
    ACADEMIC_PHRASES,
    HORUS_ACADEMIC_PHRASES,
    HORUS_PERSONA,
    INTERVIEW_SKILL,
    SCILLM_SCRIPT,
    AgentPersona,
    LiteratureReview,
    PaperScope,
    ProjectAnalysis,
    RAGContext,
)


def generate_section_content(
    section_key: str,
    section_title: str,
    scope: PaperScope,
    analysis: ProjectAnalysis,
    review: LiteratureReview,
    project_path: Path,
    use_llm: bool = True,
    rag_context: Optional[RAGContext] = None,
    persona: Optional[AgentPersona] = None,
    persona_strength: float = 1.0,
) -> str:
    """Generate content for a paper section using LLM or fallback to stub.

    Args:
        section_key: Section identifier (e.g., 'abstract', 'intro')
        section_title: Human-readable title
        scope: Paper scope from interview
        analysis: Project analysis results
        review: Literature review results
        project_path: Path to the project
        use_llm: If True, attempt LLM generation; if False or LLM fails, use stub
        rag_context: Optional RAG context for grounded generation
        persona: Optional agent persona for stylized writing
        persona_strength: Persona voice intensity (0.0=neutral, 1.0=full persona)

    Returns:
        Generated section content as string
    """
    if use_llm and SCILLM_SCRIPT.exists():
        try:
            # Build context for LLM - use grounded prompt if RAG enabled
            if rag_context:
                from grounding import generate_grounded_prompt
                context = generate_grounded_prompt(section_key, section_title, scope, rag_context)
            else:
                context = f"""Generate the {section_title} section for an academic paper.

Paper Type: {scope.paper_type}
Target Venue: {scope.target_venue}
Contributions: {', '.join(scope.contributions)}
Audience: {scope.audience}

Project: {project_path.name}
Features: {', '.join(f.get('feature', '') for f in analysis.features[:5]) if analysis.features else 'None'}
Architecture: {analysis.architecture}

Learned Knowledge:
{chr(10).join(e.get('output', '')[:500] for e in review.extractions if e.get('status') == 'success')}

Write a well-structured {section_title} section suitable for {scope.target_venue}.
Use academic writing style. Be concise but comprehensive.
"""

            # Apply persona to prompt if specified
            if persona:
                context = apply_persona_to_prompt(context, persona, section_key, persona_strength)

            # Use scillm batch command with temp JSONL file to avoid CLI arg mangling
            # Retry with exponential backoff to handle Chutes rate limiting
            import time as _time
            generated = ""
            for _attempt in range(3):
                with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
                    tf.write(json.dumps({"prompt": context[:6000]}) + "\n")
                    prompt_path = tf.name
                try:
                    result = subprocess.run(
                        [str(SCILLM_SCRIPT), "batch", "batch", "--input", prompt_path,
                         "--max-tokens", "2048", "--timeout", "90"],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                finally:
                    Path(prompt_path).unlink(missing_ok=True)
                # Parse batch JSONL output: {"index": 0, "content": "...", "ok": true}
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        try:
                            obj = json.loads(line)
                            if obj.get("ok") and obj.get("content"):
                                generated = obj["content"].strip()
                                break
                            elif obj.get("error") and "429" in str(obj["error"]):
                                logger.warning(f"Rate limited on {section_key}, waiting {5 * (2 ** _attempt)}s...")
                                _time.sleep(5 * (2 ** _attempt))
                        except json.JSONDecodeError:
                            continue
                if generated:
                    break
                if _attempt < 2:
                    _time.sleep(3 * (_attempt + 1))  # 3s, 6s between attempts
            if generated:

                # Verify grounding if RAG enabled
                if rag_context:
                    from grounding import verify_grounding
                    verification = verify_grounding(generated, section_key, rag_context)
                    if not verification["grounded"]:
                        logger.warning("Grounding issues found:")
                        for issue in verification["issues"][:3]:
                            logger.warning(f"  {issue}")
                    else:
                        typer.echo(f"    [RAG] Content grounded (confidence: {verification['confidence']:.0%})")

                return generated
            else:
                logger.warning(f"LLM generation returned empty for {section_key}, using stub")
                if result.returncode != 0 and result.stderr:
                    logger.debug(f"stderr: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning(f"LLM timed out for {section_key} after 120s, using stub")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"LLM not available for {section_key}: {e}")

    # Fallback to stub content
    return _generate_stub_content(section_key, section_title, scope, analysis, review, project_path)


def _generate_stub_content(
    section_key: str,
    section_title: str,
    scope: PaperScope,
    analysis: ProjectAnalysis,
    review: LiteratureReview,
    project_path: Path,
) -> str:
    """Generate stub content when LLM is not available.

    Args:
        section_key: Section identifier
        section_title: Human-readable title
        scope: Paper scope
        analysis: Project analysis
        review: Literature review
        project_path: Project path

    Returns:
        Stub content string
    """
    if section_key == "abstract":
        return f"""{scope.contributions[0] if scope.contributions else 'Paper abstract'}.
We present a {scope.paper_type} paper addressing this problem.
This paper demonstrates our approach on the {project_path.name} project.
"""
    elif section_key == "related":
        papers_desc = ", ".join(
            str(e.get("paper_id", "unknown")) for e in review.extractions[:3]
        ) if review.extractions else "N/A"
        return f"""We surveyed: {papers_desc}.
Our approach differs by focusing on {scope.contributions[0] if scope.contributions else 'our contribution'}.
"""
    elif section_key == "intro":
        return f"""[Introduction for {scope.paper_type} paper on {scope.contributions[0] if scope.contributions else 'the topic'}]

The main contributions of this work are:
{chr(10).join(f'- {c}' for c in scope.contributions) if scope.contributions else '- [Contribution]'}
"""
    elif section_key == "design":
        patterns = analysis.architecture.get('patterns', [])
        return f"""[System Design section]

Architecture patterns identified: {', '.join(patterns) if patterns else 'None documented'}
"""
    elif section_key == "eval":
        return f"""[Evaluation section]

Features evaluated: {len(analysis.features)}
Papers reviewed: {len(review.extractions)}
"""
    else:
        return f"""[Section content for {section_title} would be generated here based on analysis and learned knowledge.]
"""


def interview_scope(use_interview_skill: bool = True) -> PaperScope:
    """Stage 1: Interactive scope definition.

    Args:
        use_interview_skill: If True and available, use the /interview skill for better UX

    Returns:
        PaperScope from user interview
    """
    typer.echo("\n=== STAGE 1: SCOPE INTERVIEW ===\n")

    # Try to use interview skill for better UX
    if use_interview_skill and INTERVIEW_SKILL.exists():
        result = _interview_with_skill()
        if result is not None:
            return result

    # Fallback to basic typer prompts
    return _interview_with_typer()


def _interview_with_skill() -> Optional[PaperScope]:
    """Run interview using the interview skill.

    Returns:
        PaperScope or None if skill not available/failed
    """
    typer.echo("Using interactive interview form...")
    questions = {
        "title": "Paper Scope Definition",
        "context": "Define the scope for your academic paper",
        "questions": [
            {
                "id": "paper_type",
                "text": "What type of paper are you writing?",
                "type": "select",
                "options": [
                    "Research paper (novel contribution)",
                    "System paper (implementation/architecture)",
                    "Survey paper (literature review)",
                    "Experience report (lessons learned)",
                    "Demo paper (tool description)",
                ],
                "recommendation": "System paper (implementation/architecture)",
                "reason": "Most code-based papers describe implementations"
            },
            {
                "id": "target_venue",
                "text": "Target venue/conference (e.g., ICSE, FSE, arXiv)",
                "type": "text",
            },
            {
                "id": "audience",
                "text": "Who is the intended audience?",
                "type": "select",
                "options": [
                    "Software engineering researchers",
                    "AI/ML practitioners",
                    "Industry developers",
                    "Other (specify in contributions)",
                ],
                "recommendation": "Software engineering researchers",
            },
        ]
    }
    questions_file = Path(tempfile.gettempdir()) / "paper_scope_questions.json"
    questions_file.write_text(json.dumps(questions, indent=2))

    try:
        result = subprocess.run(
            [str(INTERVIEW_SKILL), "--mode", "auto", "--file", str(questions_file)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            responses = json.loads(result.stdout)
            if responses and responses.get("completed"):
                resp = responses.get("responses", {})
                paper_type_raw = resp.get("paper_type", {}).get("value", "system")
                type_map = {
                    "Research paper (novel contribution)": "research",
                    "System paper (implementation/architecture)": "system",
                    "Survey paper (literature review)": "survey",
                    "Experience report (lessons learned)": "experience",
                    "Demo paper (tool description)": "demo",
                }
                paper_type = type_map.get(paper_type_raw, "system")
                target_venue = resp.get("target_venue", {}).get("value", "arXiv")
                audience = resp.get("audience", {}).get("value", "Software engineering researchers")

                # Still need to get contributions via typer (multi-value input)
                contributions = _collect_contributions()
                prior_work_areas = _collect_prior_work_areas()

                return PaperScope(
                    paper_type=paper_type,
                    target_venue=target_venue,
                    contributions=contributions,
                    audience=audience,
                    prior_work_areas=prior_work_areas,
                )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.warning(f"Interview skill failed: {e}")

    return None


def _interview_with_typer() -> PaperScope:
    """Run interview using basic typer prompts.

    Returns:
        PaperScope from user input
    """
    typer.echo("Using command-line interview (install /interview skill for better UX)...")

    # Paper type
    typer.echo("What type of paper are you writing?")
    typer.echo("a) Research paper (novel contribution)")
    typer.echo("b) System paper (implementation/architecture)")
    typer.echo("c) Survey paper (literature review)")
    typer.echo("d) Experience report (lessons learned)")
    typer.echo("e) Demo paper (tool description)")
    paper_type_choice = typer.prompt("Select (a-e)", type=str).lower()

    type_map = {"a": "research", "b": "system", "c": "survey", "d": "experience", "e": "demo"}
    paper_type = type_map.get(paper_type_choice, "system")

    # Target venue
    target_venue = typer.prompt("Target venue/conference (e.g., ICSE, FSE, arXiv)")

    # Contributions
    contributions = _collect_contributions()

    # Audience
    typer.echo("\nWho is the intended audience?")
    typer.echo("a) Software engineering researchers")
    typer.echo("b) AI/ML practitioners")
    typer.echo("c) Industry developers")
    typer.echo("d) Specific domain (you'll specify)")
    audience_choice = typer.prompt("Select (a-d)", type=str).lower()

    audience_map = {
        "a": "Software engineering researchers",
        "b": "AI/ML practitioners",
        "c": "Industry developers",
        "d": typer.prompt("Specify domain"),
    }
    audience = audience_map.get(audience_choice, "Software engineering researchers")

    # Prior work areas
    prior_work_areas = _collect_prior_work_areas()

    scope = PaperScope(
        paper_type=paper_type,
        target_venue=target_venue,
        contributions=contributions,
        audience=audience,
        prior_work_areas=prior_work_areas,
    )

    # Confirmation gate
    typer.echo("\n--- SCOPE SUMMARY ---")
    typer.echo(f"Type: {scope.paper_type}")
    typer.echo(f"Venue: {scope.target_venue}")
    typer.echo(f"Contributions: {', '.join(scope.contributions)}")
    typer.echo(f"Audience: {scope.audience}")
    typer.echo(f"Prior work: {', '.join(scope.prior_work_areas)}")

    if not typer.confirm("\nProceed with this scope?"):
        typer.echo("Exiting. Re-run to define new scope.")
        raise typer.Exit(1)

    return scope


def _collect_contributions() -> List[str]:
    """Collect contribution claims from user.

    Returns:
        List of contribution strings
    """
    typer.echo("\nWhat are your main contribution claims? (one per line, 'done' when finished)")
    contributions = []
    while True:
        claim = typer.prompt(f"Contribution #{len(contributions)+1} (or 'done')")
        if claim.lower() == "done":
            if not contributions:
                logger.error("At least one contribution is required")
                continue
            break
        contributions.append(claim)
    return contributions


def _collect_prior_work_areas() -> List[str]:
    """Collect prior work areas from user.

    Returns:
        List of prior work area strings
    """
    typer.echo("\nPrior work areas to search (space-separated)?")
    typer.echo("Examples: agent-architectures, memory-systems, tool-use, formal-methods")
    areas_input = typer.prompt("Areas", default="agent-architectures memory-systems")
    return areas_input.split()


def apply_persona_to_prompt(
    base_prompt: str,
    persona: AgentPersona,
    section_key: str,
    strength: float = 1.0,
) -> str:
    """Enhance prompt with persona characteristics for stylized writing.

    Args:
        base_prompt: Original generation prompt
        persona: Agent persona to apply
        section_key: Section being generated
        strength: Persona intensity from 0.0 (neutral academic) to 1.0 (full persona).
                  - 0.0: Pure academic tone, no persona characteristics
                  - 0.3: Subtle hints of persona voice
                  - 0.5: Balanced blend of academic and persona
                  - 0.7: Strong persona presence
                  - 1.0: Full persona intensity (Warmaster mode)

    Returns:
        Enhanced prompt with persona guidance scaled by strength
    """
    # At strength 0, return base prompt unchanged (pure academic)
    if strength <= 0.0:
        return base_prompt

    # Clamp strength to valid range
    strength = min(1.0, max(0.0, strength))

    # Get persona-specific phrases for this section
    if persona.name.lower().startswith("horus"):
        phrase_source = HORUS_ACADEMIC_PHRASES
    else:
        phrase_source = ACADEMIC_PHRASES

    section_phrases = phrase_source.get(section_key, {})
    phrase_examples = []
    for aspect_phrases in section_phrases.values():
        phrase_examples.extend(aspect_phrases[:1])

    # Scale number of examples and modifiers by strength
    num_phrases = max(1, int(len(phrase_examples) * strength))
    num_modifiers = max(1, int(len(persona.tone_modifiers) * strength))
    num_principles = max(1, int(len(persona.writing_principles) * strength))

    # Scale intensity language based on strength
    if strength >= 0.9:
        intensity = "DOMINANT"
        instruction = "Write with FULL persona authority. The voice should be unmistakable."
    elif strength >= 0.7:
        intensity = "Strong"
        instruction = "Write with strong persona presence. The voice should be clearly evident."
    elif strength >= 0.5:
        intensity = "Moderate"
        instruction = "Balance academic neutrality with persona hints. Voice should be noticeable but not overwhelming."
    elif strength >= 0.3:
        intensity = "Subtle"
        instruction = "Write primarily in academic tone with subtle persona undertones. Voice should be a gentle undercurrent."
    else:
        intensity = "Minimal"
        instruction = "Write in neutral academic tone with very light persona flavor. Voice should be barely perceptible."

    persona_guidance = f"""
=== WRITING VOICE: {persona.name} (Strength: {strength:.1f} - {intensity}) ===

Voice Style: {persona.voice}
Tone: {', '.join(persona.tone_modifiers[:num_modifiers])}

{instruction}

WRITING PRINCIPLES (apply at {intensity.lower()} intensity):
{chr(10).join(f'- {p}' for p in persona.writing_principles[:num_principles])}

CHARACTERISTIC PHRASING (use {'frequently' if strength >= 0.7 else 'occasionally' if strength >= 0.4 else 'sparingly'}):
{chr(10).join(f'- "{p}"' for p in phrase_examples[:num_phrases])}

FORBIDDEN PHRASES (NEVER use these regardless of strength):
{chr(10).join(f'- "{p}"' for p in persona.forbidden_phrases)}

Write with authority derived from: {persona.authority_source}

CRITICAL: Maintain academic rigor while writing in this distinctive voice.
The persona adds authority and precision, not informality.
Every claim must be defensible. Every argument must be structured.
"""

    return base_prompt + "\n" + persona_guidance


def get_phrases(section_key: str, aspect: str = "", persona: str = "") -> List[str]:
    """Get academic phrases for a section and optional aspect.

    Args:
        section_key: Section name (intro, eval, etc.)
        aspect: Optional aspect (motivation, results, etc.)
        persona: Optional persona name for stylized phrases

    Returns:
        List of phrase templates
    """
    # Use persona-specific phrases if available
    if persona and persona.lower() == "horus":
        phrase_source = HORUS_ACADEMIC_PHRASES
    else:
        phrase_source = ACADEMIC_PHRASES

    section_phrases = phrase_source.get(section_key, {})
    if aspect:
        return section_phrases.get(aspect, [])
    # Return all phrases for section
    all_phrases = []
    for phrases in section_phrases.values():
        all_phrases.extend(phrases)
    return all_phrases
