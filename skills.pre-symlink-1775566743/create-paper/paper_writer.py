#!/usr/bin/env python3
"""
Paper Writer Skill - CLI Entry Point
Thin CLI layer that delegates to modular components.
"""
import os
import json
from pathlib import Path

import typer
from loguru import logger

# Local imports using absolute imports for script compatibility
from config import (
    ACADEMIC_PHRASES,
    COMMAND_DOMAINS,
    FIXTURE_GRAPH_SCRIPT,
    HORUS_ACADEMIC_PHRASES,
    HORUS_PERSONA,
    LATEX_TEMPLATES,
    SCILLM_SCRIPT,
    VENUE_POLICIES,
    WORKFLOW_RECOMMENDATIONS,
    get_template,
    list_templates,
)

app = typer.Typer(
    name="create-paper",
    help="AI-assisted academic paper writing with interview-driven workflow",
)

# Register quality/verification/compliance commands from cli_quality module
from cli_quality import register_commands as _register_quality_commands
_register_quality_commands(app)


# =============================================================================
# SHADOW-LEGO SELF-IMPROVEMENT COMMANDS
# =============================================================================


@app.command("shadow-report")
def shadow_report_cmd(
    hours: int = typer.Option(168, "--hours", "-h", help="Look-back window in hours (default: 7 days)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed breakdown"),
) -> None:
    """Show Shadow-LEGO quality tracking report for paper generation."""
    from shadow_quality import shadow_report, lessons_summary

    report = shadow_report(hours=hours)

    typer.echo(f"\n=== SHADOW-LEGO QUALITY REPORT (last {hours}h) ===\n")

    if report["total"] == 0:
        typer.echo("[INFO] No shadow data yet. Generate a paper to start tracking.")
        return

    rate = report["agreement_rate"]
    status = report["status"]
    status_icon = {"ready": "[OK]", "learning": "[~]", "early": "[!]", "no_data": "[-]"}[status]

    typer.echo(f"  Heuristic vs LLM critique agreement: {rate:.1%}")
    typer.echo(f"  Status: {status_icon} {status}")
    typer.echo(f"  Entries: {report['total']}")

    if verbose and report.get("by_section"):
        typer.echo(f"\n  Per-section agreement:")
        for section, section_rate in sorted(report["by_section"].items()):
            typer.echo(f"    {section}: {section_rate:.1%}")

    lessons = lessons_summary()
    if lessons["total"] > 0:
        typer.echo(f"\n  Lessons logged: {lessons['total']}")
        typer.echo(f"  By category: {lessons['by_category']}")
        if verbose and lessons["recent"]:
            typer.echo(f"\n  Recent lessons:")
            for l in lessons["recent"]:
                typer.echo(f"    [{l['category']}] {l['description']}")


# =============================================================================
# HELPER COMMANDS
# =============================================================================


@app.command()
def phrases(
    section: str = typer.Argument(..., help="Section name (abstract, intro, related, method, eval, discussion)"),
    aspect: str = typer.Option("", "--aspect", "-a", help="Specific aspect (e.g., problem, solution, motivation)"),
    persona: str = typer.Option("", "--persona", "-p", help="Persona for stylized phrases (e.g., 'horus')"),
) -> None:
    """Show academic phrase suggestions for a section."""
    if persona and persona.lower() == "horus":
        phrase_source = HORUS_ACADEMIC_PHRASES
        persona_name = "Horus Lupercal (authoritative)"
    else:
        phrase_source = ACADEMIC_PHRASES
        persona_name = "Standard academic"

    typer.echo(f"\n=== ACADEMIC PHRASES: {section} ({persona_name}) ===\n")

    if section not in phrase_source:
        logger.error(f"Unknown section: {section}")
        typer.echo(f"Available: {', '.join(phrase_source.keys())}")
        raise typer.Exit(1)

    section_phrases = phrase_source[section]

    if aspect:
        if aspect not in section_phrases:
            logger.error(f"Unknown aspect: {aspect}")
            typer.echo(f"Available for {section}: {', '.join(section_phrases.keys())}")
            raise typer.Exit(1)

        typer.echo(f"Aspect: {aspect}")
        typer.echo("-" * 40)
        for phrase in section_phrases[aspect]:
            typer.echo(f"  - {phrase}")
    else:
        for asp, phrases_list in section_phrases.items():
            typer.echo(f"{asp}:")
            for phrase in phrases_list:
                typer.echo(f"  - {phrase}")
            typer.echo()


@app.command()
def templates(
    show: str = typer.Option("", "--show", help="Show details for specific template"),
) -> None:
    """List available LaTeX templates."""
    if show:
        template = get_template(show)
        if show.lower() not in LATEX_TEMPLATES:
            logger.error(f"Unknown template: {show}")
            typer.echo(f"Available: {', '.join(list_templates())}")
            raise typer.Exit(1)

        typer.echo(f"\n=== TEMPLATE: {template['name']} ===\n")
        typer.echo(f"Document class:")
        typer.echo(f"  {template['documentclass']}")
        typer.echo(f"\nPackages:")
        for line in template['packages'].split('\n'):
            typer.echo(f"  {line}")
        typer.echo(f"\nBibliography style: {template['bib_style']}")
    else:
        typer.echo("\n=== AVAILABLE TEMPLATES ===\n")
        for key, template in LATEX_TEMPLATES.items():
            typer.echo(f"  {key:<10} - {template['name']}")
        typer.echo(f"\nUse --show <template> for details")


@app.command()
def disclosure(
    venue: str = typer.Argument(..., help="Target venue (arxiv, iclr, neurips, acl, aaai, cvpr)"),
    output: str = typer.Option("", "--output", "-o", help="Output file path"),
    show_policy: bool = typer.Option(False, "--policy", "-p", help="Show full venue policy"),
) -> None:
    """Generate LLM-use disclosure statement for target venue."""
    from compliance import generate_disclosure

    venue_key = venue.lower()

    if venue_key not in VENUE_POLICIES:
        logger.error(f"Unknown venue: {venue}")
        typer.echo(f"Available: {', '.join(VENUE_POLICIES.keys())}")
        raise typer.Exit(1)

    result = generate_disclosure(venue)

    typer.echo(f"\n=== LLM DISCLOSURE: {result['venue']} ===\n")

    if show_policy:
        typer.echo("Venue Policy Notes:")
        for note in result.get("policy_notes", []):
            typer.echo(f"  - {note}")
        typer.echo(f"\nDisclosure Location: {result['location']}")
        typer.echo()

    typer.echo("Generated Disclosure Statement:")
    typer.echo("-" * 50)
    typer.echo(result["text"])
    typer.echo("-" * 50)

    if output:
        output_path = Path(output)
        output_path.write_text(result["latex"])
        typer.echo(f"\n[OK] Saved to: {output_path}")

    typer.echo(f"\n[INFO] Add this to your {result['location']} section.")


# =============================================================================
# NAVIGATION COMMANDS
# =============================================================================


@app.command()
def domains(
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON for agents"),
) -> None:
    """List command domains for easier navigation."""
    if summary:
        typer.echo(json.dumps(COMMAND_DOMAINS, indent=2))
        return

    typer.echo("=== Paper Writer Command Domains ===\n")
    for domain, info in COMMAND_DOMAINS.items():
        typer.echo(f"[{domain}] {info['description']}")
        typer.echo(f"  Commands: {', '.join(info['commands'])}")
        typer.echo(f"  When: {info['when_to_use']}")
        typer.echo()


@app.command("list")
def list_commands(
    domain: str = typer.Option("", "--domain", "-d", help="Filter by domain"),
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON for agents"),
) -> None:
    """List commands, optionally filtered by domain."""
    if domain and domain not in COMMAND_DOMAINS:
        logger.error(f"Unknown domain: {domain}")
        typer.echo(f"Available: {', '.join(COMMAND_DOMAINS.keys())}")
        raise typer.Exit(1)

    if domain:
        info = COMMAND_DOMAINS[domain]
        commands = info["commands"]
        if summary:
            typer.echo(json.dumps({"domain": domain, "commands": commands}))
            return
        typer.echo(f"[{domain}] {info['description']}\n")
        for cmd in commands:
            typer.echo(f"  {cmd}")
    else:
        all_commands = []
        for d, info in COMMAND_DOMAINS.items():
            all_commands.extend(info["commands"])
        if summary:
            typer.echo(json.dumps({"all_commands": all_commands}))
            return
        typer.echo("All commands:")
        for cmd in sorted(set(all_commands)):
            typer.echo(f"  {cmd}")


@app.command()
def workflow(
    stage: str = typer.Option("", "--stage", "-s", help="Paper stage: new_paper, revision, pre_submission, compliance"),
    summary: bool = typer.Option(False, "--summary", help="Output JSON for agents"),
) -> None:
    """Show workflow recommendations based on paper stage."""
    if stage and stage not in WORKFLOW_RECOMMENDATIONS:
        logger.error(f"Unknown stage: {stage}")
        typer.echo(f"Available: {', '.join(WORKFLOW_RECOMMENDATIONS.keys())}")
        raise typer.Exit(1)

    if summary:
        if stage:
            typer.echo(json.dumps(WORKFLOW_RECOMMENDATIONS[stage], indent=2))
        else:
            typer.echo(json.dumps(WORKFLOW_RECOMMENDATIONS, indent=2))
        return

    if stage:
        rec = WORKFLOW_RECOMMENDATIONS[stage]
        typer.echo(f"=== {rec['stage']} ===\n")
        typer.echo(f"Recommended commands: {', '.join(rec['commands'])}")
        typer.echo(f"Tip: {rec['tip']}")
    else:
        typer.echo("=== Workflow Recommendations ===\n")
        for stage_name, rec in WORKFLOW_RECOMMENDATIONS.items():
            typer.echo(f"[{stage_name}] {rec['stage']}")
            typer.echo(f"  Commands: {', '.join(rec['commands'])}")
            typer.echo(f"  Tip: {rec['tip']}")
            typer.echo()


@app.command("figure-presets")
def figure_presets_cmd(
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON for agents"),
) -> None:
    """Show fixture-graph presets for paper figures."""
    presets = {
        "ieee_sizes": {
            "single": {"width": 3.5, "height": 2.5, "use": "Single-column figures"},
            "double": {"width": 7.16, "height": 3.0, "use": "Full-width figures"},
            "square": {"width": 3.5, "height": 3.5, "use": "Square figures"},
        },
        "colorblind_safe": ["viridis", "plasma", "cividis", "gray", "Blues", "Oranges"],
        "fixture_graph_cmd": str(FIXTURE_GRAPH_SCRIPT),
    }

    if summary:
        typer.echo(json.dumps(presets, indent=2))
        return

    typer.echo("=== Figure Presets for Papers ===\n")
    typer.echo("IEEE Figure Sizes:")
    for name, info in presets["ieee_sizes"].items():
        typer.echo(f"  {name}: {info['width']}\" x {info['height']}\" - {info['use']}")

    typer.echo("\nColorblind-Safe Colormaps:")
    typer.echo(f"  {', '.join(presets['colorblind_safe'])}")


# =============================================================================
# CORE PIPELINE COMMANDS
# =============================================================================


@app.command()
def draft(
    project: str = typer.Option(..., "--project", help="Project path to analyze"),
    output: str = typer.Option("./paper_output", "--output", "-o", help="Output directory"),
    template: str = typer.Option("ieee", "--template", "-t", help="LaTeX template (ieee, acm, cvpr, arxiv, springer, darpa_baa)"),
    persona: str = typer.Option("", "--persona", "-p", help="Writing persona (horus, or path to persona.json)"),
    persona_strength: float = typer.Option(
        1.0,
        "--persona-strength", "-s",
        min=0.0,
        max=1.0,
        help="Persona voice intensity: 0.0=neutral academic, 0.5=balanced, 1.0=full persona"
    ),
    length: str = typer.Option(
        "paper",
        "--length", "-l",
        help="Document length: paper (5-10pg), extended (15-25pg), thesis (50-80pg), dissertation (100+pg)"
    ),
    use_mimic: bool = typer.Option(False, "--mimic", help="Use MIMIC patterns if available"),
    use_rag: bool = typer.Option(False, "--rag", help="Enable RAG grounding to prevent hallucination"),
) -> None:
    """
    Generate paper draft from project analysis (interactive).

    Runs 5-stage interview-driven workflow:
    1. Scope definition
    2. Project analysis
    3. Literature search
    4. Knowledge learning
    5. Draft generation
    """
    from analysis import analyze_project
    from draft import generate_draft_pipeline
    from mimic import load_mimic_patterns
    from research import learn_from_papers, search_literature
    from sections import interview_scope
    from utils import load_persona

    project_path = Path(project).resolve()
    output_dir = Path(output).resolve()

    if not project_path.exists():
        logger.error(f"Project not found: {project_path}")
        raise typer.Exit(1)

    # Load persona if specified
    agent_persona = None
    if persona:
        if persona.lower() == "horus":
            agent_persona = HORUS_PERSONA
            typer.echo(f"[PERSONA] Using {agent_persona.name} writing style")
        else:
            agent_persona = load_persona(Path(persona))
            if agent_persona:
                typer.echo(f"[PERSONA] Loaded {agent_persona.name}")
            else:
                logger.warning(f"Could not load persona from {persona}")

    # Load MIMIC patterns if requested
    mimic_patterns = None
    if use_mimic:
        mimic_patterns = load_mimic_patterns()
        if mimic_patterns:
            typer.echo(f"[MIMIC] Loaded patterns from: {', '.join(mimic_patterns.exemplar_ids[:2])}")
        else:
            logger.warning("No MIMIC patterns found. Run `mimic --select` first.")
            if not typer.confirm("Continue without MIMIC?"):
                raise typer.Exit(1)

    typer.echo(f"Starting paper draft for: {project_path.name}")

    # Stage 1: Scope
    scope = interview_scope()

    # Stage 2: Analysis
    analysis = analyze_project(project_path, scope)

    # Stage 3: Literature
    review = search_literature(scope, analysis)

    # Stage 4: Learning
    review = learn_from_papers(review, scope)

    # Stage 5: Draft generation (delegated to draft module)
    generate_draft_pipeline(
        project_path=project_path,
        scope=scope,
        analysis=analysis,
        review=review,
        output_dir=output_dir,
        mimic_patterns=mimic_patterns,
        use_rag=use_rag,
        template_name=template,
        persona=agent_persona,
        persona_strength=persona_strength,
    )

    typer.echo("\n[OK] Paper draft session complete")


@app.command()
def mimic(
    select: bool = typer.Option(False, "--select", help="Select exemplar papers to mimic"),
    analyze: bool = typer.Option(False, "--analyze", help="Analyze selected exemplars"),
    validate: str = typer.Option("", "--validate", help="Validate generated paper against patterns"),
    show: bool = typer.Option(False, "--show", help="Show current MIMIC patterns"),
    clear: bool = typer.Option(False, "--clear", help="Clear stored MIMIC patterns"),
) -> None:
    """
    Mimic the style of exemplar papers from prestigious sources.

    Workflow:
    1. ./run.sh mimic --select            # Choose 2-3 exemplar papers
    2. ./run.sh mimic --analyze           # Analyze and store patterns
    3. ./run.sh draft --project ./foo --mimic  # Generate using patterns
    4. ./run.sh mimic --validate ./paper_output  # Validate against patterns
    """
    from config import MIMIC_STATE_FILE
    from mimic import (
        analyze_exemplars,
        load_mimic_patterns,
        select_exemplar_papers,
        store_mimic_patterns,
        validate_against_exemplars,
    )

    if select:
        exemplars = select_exemplar_papers()
        if not exemplars:
            logger.error("No exemplars selected")
            raise typer.Exit(1)

        state = {"exemplars": exemplars}
        MIMIC_STATE_FILE.write_text(json.dumps(state, indent=2))
        typer.echo(f"\n[OK] Selected {len(exemplars)} exemplars. Run `mimic --analyze` to extract patterns.")

    elif analyze:
        if not MIMIC_STATE_FILE.exists():
            logger.error("No exemplars selected. Run `mimic --select` first.")
            raise typer.Exit(1)

        state = json.loads(MIMIC_STATE_FILE.read_text())
        exemplars = state.get("exemplars", [])
        if not exemplars:
            logger.error("No exemplars in state file.")
            raise typer.Exit(1)

        patterns = analyze_exemplars(exemplars)
        store_mimic_patterns(patterns)
        typer.echo("\n[OK] Patterns stored. Use `draft --mimic` to generate paper with these patterns.")

    elif validate:
        patterns = load_mimic_patterns()
        if not patterns:
            logger.error("No MIMIC patterns found.")
            raise typer.Exit(1)

        output_path = Path(validate)
        if not output_path.exists():
            logger.error(f"Paper directory not found: {output_path}")
            raise typer.Exit(1)

        report = validate_against_exemplars(output_path, patterns)

        all_ok = True
        for category in ["structure", "style", "content"]:
            if report[category]["issues"]:
                all_ok = False
                typer.echo(f"{category.title()} Issues:")
                for issue in report[category]["issues"]:
                    typer.echo(f"  [!] {issue}")

        if report["recommendations"]:
            typer.echo("\nRecommendations:")
            for rec in report["recommendations"]:
                typer.echo(f"  -> {rec}")

        if all_ok:
            typer.echo("[OK] Paper matches exemplar patterns!")

    elif show:
        patterns = load_mimic_patterns()
        if not patterns:
            typer.echo("[INFO] No MIMIC patterns stored. Run `mimic --select` and `mimic --analyze`.")
            raise typer.Exit(0)

        typer.echo("\n=== CURRENT MIMIC PATTERNS ===\n")
        typer.echo(f"Exemplars: {', '.join(patterns.exemplar_ids)}")
        typer.echo(f"Voice: {patterns.voice}")
        typer.echo(f"Technical density: {patterns.technical_density:.0%}")
        typer.echo(f"Intro target length: {patterns.intro_length} words")

    elif clear:
        if MIMIC_STATE_FILE.exists():
            MIMIC_STATE_FILE.unlink()
            typer.echo("[OK] MIMIC patterns cleared.")
        else:
            typer.echo("[INFO] No MIMIC patterns to clear.")

    else:
        typer.echo("Use --select, --analyze, --validate, --show, or --clear")


@app.command()
def verify(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    project: str = typer.Option("", "--project", help="Project path for deeper verification"),
) -> None:
    """
    Verify RAG grounding of a generated paper.

    Checks that generated content is supported by source material.
    """
    from config import RAGContext
    from grounding import extract_code_snippets, verify_grounding

    paper_path = Path(paper_dir).resolve()
    if not paper_path.exists():
        logger.error(f"Paper directory not found: {paper_path}")
        raise typer.Exit(1)

    sections_dir = paper_path / "sections"
    if not sections_dir.exists():
        logger.error(f"Sections directory not found: {sections_dir}")
        raise typer.Exit(1)

    typer.echo(f"\n=== RAG VERIFICATION: {paper_path.name} ===\n")

    # Load metadata if available
    metadata_file = paper_path / "metadata.json"
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())
        if metadata.get("rag_enabled"):
            typer.echo("Paper was generated with RAG grounding")
        else:
            logger.warning("Paper was NOT generated with RAG grounding")

    # Build minimal RAG context if project provided
    rag_context = None
    if project:
        project_path = Path(project).resolve()
        if project_path.exists():
            typer.echo(f"\nBuilding verification context from: {project_path.name}")
            code_snippets = extract_code_snippets(project_path)
            rag_context = RAGContext(
                code_snippets=code_snippets,
                project_facts=[],
                paper_excerpts=[],
                research_facts=[],
                section_constraints={},
            )

    # Verify each section
    total_issues = 0
    for section_file in sections_dir.glob("*.tex"):
        section_key = section_file.stem
        content = section_file.read_text()

        typer.echo(f"\nSection: {section_key}")
        typer.echo(f"  Length: {len(content.split())} words")

        if rag_context:
            verification = verify_grounding(content, section_key, rag_context)
            if verification["issues"]:
                typer.echo(f"  Issues ({len(verification['issues'])}):")
                for issue in verification["issues"]:
                    typer.echo(f"    [!] {issue}")
                total_issues += len(verification["issues"])
            else:
                typer.echo("  [OK] No grounding issues detected")
            typer.echo(f"  Confidence: {verification['confidence']:.0%}")
        else:
            content_lower = content.lower()
            basic_issues = []
            for word in ["achieves", "outperforms", "state-of-the-art", "novel", "first"]:
                if word in content_lower:
                    basic_issues.append(f"Contains unverified claim keyword: '{word}'")
            if basic_issues:
                for issue in basic_issues:
                    typer.echo(f"    [!] {issue}")
                total_issues += len(basic_issues)
            else:
                typer.echo("  [OK] No obvious issues")

    typer.echo(f"\n=== SUMMARY ===")
    typer.echo(f"Total potential issues: {total_issues}")
    if total_issues == 0:
        typer.echo("[OK] Paper appears well-grounded")
    else:
        typer.echo(f"[!] Review {total_issues} potential grounding issues")


@app.command()
def refine(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    section: str = typer.Option("", "--section", "-s", help="Specific section to refine"),
    feedback: str = typer.Option("", "--feedback", "-f", help="User feedback for refinement"),
    rounds: int = typer.Option(2, "--rounds", "-r", help="Number of refinement rounds"),
) -> None:
    """
    Iteratively refine paper sections with feedback.

    Example:
        ./run.sh refine ./paper_output --section intro --feedback "Make it more concise"
    """
    from critique import critique_section

    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    if not sections_dir.exists():
        logger.error(f"Sections not found: {sections_dir}")
        raise typer.Exit(1)

    typer.echo(f"\n=== ITERATIVE REFINEMENT: {paper_path.name} ===\n")

    if section:
        section_files = [sections_dir / f"{section}.tex"]
        if not section_files[0].exists():
            logger.error(f"Section not found: {section}")
            raise typer.Exit(1)
    else:
        section_files = list(sections_dir.glob("*.tex"))

    for section_file in section_files:
        section_key = section_file.stem
        content = section_file.read_text()

        typer.echo(f"\n--- Refining: {section_key} ---")
        typer.echo(f"Current length: {len(content.split())} words")

        for round_num in range(1, rounds + 1):
            typer.echo(f"\n[Round {round_num}/{rounds}]")

            if feedback and round_num == 1:
                round_feedback = feedback
            else:
                typer.echo(f"  Preview: {content[:200]}...")
                round_feedback = typer.prompt(
                    f"Feedback for {section_key} (or 'skip' to accept)",
                    default="skip"
                )

            if round_feedback.lower() == "skip":
                typer.echo(f"  Accepted {section_key}")
                break

            critique_result = critique_section(section_key, content, ["clarity", "completeness"])
            critique_issues = []
            for aspect, data in critique_result.items():
                critique_issues.extend(data.get("findings", []))

            if SCILLM_SCRIPT.exists():
                import subprocess
                refine_prompt = f"""Refine this academic paper section based on feedback.

SECTION: {section_key}
USER FEEDBACK: {round_feedback}
AUTOMATED CRITIQUE: {', '.join(critique_issues) if critique_issues else 'None'}

CURRENT CONTENT:
{content[:3500]}

INSTRUCTIONS:
1. Address the user feedback directly
2. Fix any issues from the automated critique
3. Maintain academic tone and style
4. Keep approximately the same length unless asked to expand/shorten

Output ONLY the refined section content, no explanations.
"""
                try:
                    result = subprocess.run(
                        [str(SCILLM_SCRIPT), "batch", "single", refine_prompt],
                        capture_output=True, text=True, timeout=120,
                        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        new_content = result.stdout.strip()
                        typer.echo(f"  Refined: {len(content.split())} -> {len(new_content.split())} words")
                        if typer.confirm("  Accept this refinement?", default=True):
                            content = new_content
                            section_file.write_text(content)
                            typer.echo("  [OK] Saved")
                        else:
                            typer.echo("  Discarded refinement")
                except Exception as e:
                    logger.error(f"Refinement error: {e}")
            else:
                logger.warning("LLM not available for refinement")
                break

    typer.echo(f"\n[OK] Refinement complete")


@app.command("horus-paper")
def horus_paper(
    project: str = typer.Argument(..., help="Project path to write paper about"),
    output: str = typer.Option("./horus_paper", "--output", "-o", help="Output directory"),
    template: str = typer.Option("arxiv", "--template", "-t", help="LaTeX template"),
    auto_run: bool = typer.Option(False, "--auto-run", "-a", help="Execute the full pipeline"),
    use_rag: bool = typer.Option(True, "--rag/--no-rag", help="Enable RAG grounding"),
    scope_file: str = typer.Option("", "--scope-file", help="JSON file with custom paper scope"),
    title: str = typer.Option("", "--title", help="Paper title (overrides scope)"),
    persona_strength: float = typer.Option(
        0.7,
        "--persona-strength", "-s",
        min=0.0,
        max=1.0,
        help="Persona voice intensity: 0.0=neutral academic, 1.0=full Warmaster"
    ),
) -> None:
    """
    Horus Lupercal: Generate a research paper in Warmaster's voice.

    Use --auto-run to actually execute the pipeline (otherwise just shows instructions).
    Use --scope-file to provide a JSON file with custom paper scope.
    """
    project_path = Path(project).resolve()
    output_dir = Path(output).resolve()

    if not project_path.exists():
        logger.error(f"Project not found: {project_path}")
        raise typer.Exit(1)

    typer.echo(f"\nHORUS LUPERCAL - WARMASTER - RESEARCH PAPER GENERATION\n")
    typer.echo(f"Project: {project_path}")
    typer.echo(f"Output: {output_dir}")
    typer.echo(f"Template: {template}")
    typer.echo(f"Persona strength: {persona_strength:.1f}")
    if scope_file:
        typer.echo(f"Scope: {scope_file}")
    if title:
        typer.echo(f"Title: {title}")

    if auto_run:
        from draft import generate_horus_pipeline

        generate_horus_pipeline(
            project_path=project_path,
            output_dir=output_dir,
            template_name=template,
            use_rag=use_rag,
            persona_strength=persona_strength,
            scope_file=Path(scope_file) if scope_file else None,
            title_override=title or None,
        )

    else:
        typer.echo("\n=== MANUAL INSTRUCTIONS ===")
        typer.echo(f"  ./run.sh draft --project {project_path} --persona horus --rag --template {template} -o {output_dir}")
        typer.echo(f"  ./run.sh claim-graph {output_dir} --verify")
        typer.echo(f"  ./run.sh check-citations {output_dir} --strict")
        typer.echo(f"  ./run.sh weakness-analysis {output_dir} --project {project_path}")
        typer.echo(f"  ./run.sh sanitize {output_dir}")
        typer.echo(f"  ./run.sh pre-submit {output_dir} --venue arxiv --project {project_path}")
        typer.echo("\nTIP: Use --auto-run to execute this pipeline automatically.")


if __name__ == "__main__":
    app()
