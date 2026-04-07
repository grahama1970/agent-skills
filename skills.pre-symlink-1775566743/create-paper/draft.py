"""
Paper Writer Skill - Draft Generation
Full draft generation pipeline orchestrator.
"""
import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from config import (
    SCILLM_SCRIPT,
    AgentPersona,
    LiteratureReview,
    MimicPatterns,
    PaperScope,
    ProjectAnalysis,
    RAGContext,
    get_template,
)

_TM_RUN = Path(__file__).parent.parent / "task-monitor" / "run.sh"


def _tm(args: list) -> bool:
    """Fire-and-forget task-monitor call."""
    if not _TM_RUN.exists():
        return False
    try:
        return subprocess.run(
            [str(_TM_RUN), *args],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        ).returncode == 0
    except Exception:
        return False


def generate_draft_pipeline(
    project_path: Path,
    scope: PaperScope,
    analysis: ProjectAnalysis,
    review: LiteratureReview,
    output_dir: Path,
    auto_approve: bool = False,
    mimic_patterns: Optional[MimicPatterns] = None,
    use_rag: bool = False,
    template_name: str = "ieee",
    persona: Optional[AgentPersona] = None,
    persona_strength: float = 1.0,
) -> None:
    """Stage 5: Generate LaTeX draft.

    Args:
        project_path: Path to the project being documented
        scope: Paper scope from interview
        analysis: Project analysis results
        review: Literature review results
        output_dir: Directory to write output
        auto_approve: If True, skip interactive prompts
        mimic_patterns: Optional MIMIC patterns for style transfer
        use_rag: If True, enable RAG grounding
        template_name: LaTeX template to use
        persona: Optional agent persona for stylized writing
        persona_strength: Persona voice intensity (0.0=neutral, 1.0=full persona)
    """
    import time as _time
    from figures import generate_figures
    from grounding import build_rag_context, generate_bibtex_from_arxiv
    from mimic import apply_style_transfer, validate_against_exemplars
    from sections import generate_section_content
    from shadow_quality import SectionQuality, log_lesson, log_section_shadow

    typer.echo("\n=== STAGE 5: DRAFT GENERATION ===\n")
    _tm(["start-session", "--project", "create-paper"])

    # Paper run ID for lesson tracking
    paper_id = f"{project_path.name}_{int(_time.time())}"
    typer.echo(f"[SHADOW] Paper run: {paper_id}")

    # Build RAG context if enabled
    rag_context = None
    if use_rag:
        rag_context = build_rag_context(project_path, scope, analysis, review)
        typer.echo(f"[RAG] Grounding enabled with {len(rag_context.project_facts)} facts, "
                   f"{len(rag_context.code_snippets)} snippets, {len(rag_context.paper_excerpts)} excerpts")
        log_lesson(paper_id, "generation", "success",
                   f"RAG context built: {len(rag_context.project_facts)} facts")

    if persona:
        typer.echo(f"[PERSONA] Writing in {persona.name} voice")

    output_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = output_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    # Generate structure
    structure = [
        ("abstract", "Abstract"),
        ("intro", "Introduction"),
        ("related", "Related Work"),
        ("design", "System Design"),
        ("impl", "Implementation"),
        ("eval", "Evaluation"),
        ("discussion", "Discussion"),
    ]

    typer.echo("\n--- PROPOSED STRUCTURE ---")
    for i, (key, title) in enumerate(structure, 1):
        typer.echo(f"{i}. {title}")

    if not auto_approve and not typer.confirm("\nApprove this structure?"):
        raise NotImplementedError("Custom paper structure not yet implemented")

    use_llm = SCILLM_SCRIPT.exists() and not auto_approve
    if use_llm:
        typer.echo("LLM available for content generation")
    else:
        typer.echo("[INFO] Using stub content (LLM not available or auto_approve=True)")

    if mimic_patterns:
        typer.echo(f"[MIMIC] Using style patterns from: {', '.join(mimic_patterns.exemplar_ids[:2])}")

    # Section word count targets (for quality tracking)
    section_targets = {
        "abstract": (150, 250), "intro": (800, 1500), "related": (600, 1200),
        "design": (800, 1500), "impl": (600, 1200), "eval": (800, 1500),
        "discussion": (400, 800),
    }

    # Generate each section with quality tracking
    section_qualities: List[SectionQuality] = []
    for key, title in structure:
        section_file = sections_dir / f"{key}.tex"
        typer.echo(f"  Generating: {title}...")
        t0 = _time.time()

        content = generate_section_content(
            section_key=key, section_title=title, scope=scope,
            analysis=analysis, review=review, project_path=project_path,
            use_llm=use_llm, rag_context=rag_context,
            persona=persona, persona_strength=persona_strength,
        )

        if mimic_patterns and use_llm:
            typer.echo(f"    Applying MIMIC style transfer...")
            content = apply_style_transfer(content, key, mimic_patterns)

        section_file.write_text(content)
        gen_time = _time.time() - t0

        # Track section quality
        wc = len(content.split())
        tgt = section_targets.get(key, (0, 99999))
        sq = SectionQuality(
            section_key=key, word_count=wc,
            target_min=tgt[0], target_max=tgt[1],
            within_target=tgt[0] <= wc <= tgt[1],
            citation_count=content.count("\\cite"),
            persona_name=persona.name if persona else "",
            persona_strength=persona_strength,
        )
        section_qualities.append(sq)

        # Log generation lesson
        source = "llm" if use_llm and wc > 50 else "stub"
        log_lesson(paper_id, "generation", "success" if sq.within_target else "warning",
                   f"{key}: {wc} words ({source}, {gen_time:.1f}s)" +
                   ("" if sq.within_target else f" [target: {tgt[0]}-{tgt[1]}]"),
                   section_key=key, metric_after=wc)

        typer.echo(f"  Generated: {section_file.name} ({wc} words, {gen_time:.1f}s)")

    _tm(["add-accomplishment", "--text", f"Generated {len(structure)} sections for {scope.contributions[0] if scope.contributions else 'paper'}"])

    # Generate figures
    figures_dir = output_dir / "figures"
    generated_figures = generate_figures(project_path, analysis, figures_dir)

    # Get template configuration
    template = get_template(template_name)
    typer.echo(f"Using template: {template['name']}")

    # Generate main tex file
    main_tex = output_dir / "draft.tex"
    title_text = scope.contributions[0] if scope.contributions else 'Paper Title'

    # Resolve author name: pen_name for real-person personas, name for AI/fictional
    author_name = "Author Name"
    if persona:
        if hasattr(persona, 'get_publication_name'):
            author_name = persona.get_publication_name()
        elif hasattr(persona, 'pen_name') and persona.pen_name:
            author_name = persona.pen_name
        else:
            author_name = persona.name
        # Append fictional affiliation if pen name is active
        pen_aff = getattr(persona, 'pen_affiliation', '')
        if pen_aff and author_name != persona.name:
            author_name = f"{author_name}\\\\{pen_aff}"

    main_content = _build_main_tex(template, title_text, author=author_name)
    main_tex.write_text(main_content)

    # Generate BibTeX
    refs_file = output_dir / "references.bib"
    arxiv_ids = _collect_arxiv_ids(review)
    generate_bibtex_from_arxiv(arxiv_ids[:20], refs_file)

    # Save metadata
    metadata = _build_metadata(
        scope, analysis, review, output_dir, template_name, template,
        persona, mimic_patterns, use_rag, rag_context,
    )
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # MIMIC validation if patterns were used
    if mimic_patterns and not auto_approve:
        _run_mimic_validation(output_dir, mimic_patterns)

    # Shadow-LEGO: Run heuristic critique and log section quality
    from critique import critique_section
    typer.echo("\n--- SHADOW QUALITY ASSESSMENT ---")
    for sq in section_qualities:
        section_file = sections_dir / f"{sq.section_key}.tex"
        if section_file.exists():
            content = section_file.read_text()
            heuristic = critique_section(sq.section_key, content)
            sq.heuristic_scores = {a: d["score"] for a, d in heuristic.items()}
            avg_score = sum(sq.heuristic_scores.values()) / max(len(sq.heuristic_scores), 1)
            log_section_shadow(paper_id, sq)
            typer.echo(f"  {sq.section_key}: avg={avg_score:.1f}/5 "
                       f"({'within' if sq.within_target else 'outside'} target)")

    # Final lessons summary
    on_target = sum(1 for sq in section_qualities if sq.within_target)
    total = len(section_qualities)
    total_words = sum(sq.word_count for sq in section_qualities)
    log_lesson(paper_id, "generation", "insight",
               f"Paper complete: {total_words} words, {on_target}/{total} sections within target, "
               f"template={template_name}, persona={persona.name if persona else 'none'}")

    # Add paper_id and shadow info to metadata
    metadata["paper_id"] = paper_id
    metadata["shadow_lego"] = {
        "sections_on_target": on_target,
        "sections_total": total,
        "total_words": total_words,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    typer.echo(f"\n[OK] Draft generated: {main_tex}")
    typer.echo(f"  Compile with: cd {output_dir} && pdflatex draft.tex")
    typer.echo(f"  [SHADOW] Run: create-paper shadow-report for quality trends")
    _tm(["end-session", "--notes", f"Draft complete: {scope.contributions[0] if scope.contributions else 'paper'}"])


def _build_main_tex(template: Dict[str, Any], title: str, author: str = "Author Name") -> str:
    """Build main .tex file content.

    Args:
        template: Template config dict
        title: Paper title
        author: Author name (uses persona pen_name if available)

    Returns:
        LaTeX content string
    """
    return f"""{template['documentclass']}
{template['packages']}

\\title{{{title}}}

{template['author_format'] % author}

\\begin{{document}}

\\maketitle

\\begin{{{template['abstract_env'][0]}}}
\\input{{sections/abstract}}
\\end{{{template['abstract_env'][1]}}}

\\section{{Introduction}}
\\input{{sections/intro}}

\\section{{Related Work}}
\\input{{sections/related}}

\\section{{System Design}}
\\input{{sections/design}}

\\begin{{figure}}[htbp]
\\centering
\\includegraphics[width=\\columnwidth]{{figures/architecture}}
\\caption{{System Architecture}}
\\label{{fig:architecture}}
\\end{{figure}}

\\section{{Implementation}}
\\input{{sections/impl}}

\\begin{{figure}}[htbp]
\\centering
\\includegraphics[width=\\columnwidth]{{figures/workflow}}
\\caption{{Paper Generation Workflow}}
\\label{{fig:workflow}}
\\end{{figure}}

\\section{{Evaluation}}
\\input{{sections/eval}}

\\section{{Discussion}}
\\input{{sections/discussion}}

\\bibliographystyle{{{template['bib_style']}}}
\\bibliography{{references}}

\\end{{document}}
"""


def _collect_arxiv_ids(review: LiteratureReview) -> List[str]:
    """Collect deduplicated arXiv IDs from review.

    Args:
        review: Literature review

    Returns:
        List of unique arXiv IDs
    """
    arxiv_ids = [p.get("id", "") for p in review.papers_found if p.get("id")]
    arxiv_ids.extend([pid for pid in review.papers_selected if pid not in arxiv_ids])

    seen = set()
    unique_ids = []
    for pid in arxiv_ids:
        if pid and pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    return unique_ids


def _build_metadata(
    scope: PaperScope,
    analysis: ProjectAnalysis,
    review: LiteratureReview,
    output_dir: Path,
    template_name: str,
    template: Dict[str, Any],
    persona: Optional[AgentPersona],
    mimic_patterns: Optional[MimicPatterns],
    use_rag: bool,
    rag_context: Optional[RAGContext],
) -> Dict[str, Any]:
    """Build paper metadata dict.

    Args:
        scope: Paper scope
        analysis: Project analysis
        review: Literature review
        output_dir: Output directory
        template_name: Template name string
        template: Template config dict
        persona: Optional persona
        mimic_patterns: Optional MIMIC patterns
        use_rag: Whether RAG was enabled
        rag_context: Optional RAG context

    Returns:
        Metadata dict
    """
    return {
        "scope": asdict(scope),
        "features_count": len(analysis.features),
        "papers_learned": len(review.extractions),
        "output_dir": str(output_dir),
        "template": template_name,
        "template_name": template["name"],
        "persona_enabled": persona is not None,
        "persona_name": persona.name if persona else None,
        "mimic_enabled": mimic_patterns is not None,
        "mimic_exemplars": mimic_patterns.exemplar_ids if mimic_patterns else [],
        "rag_enabled": use_rag,
        "rag_facts_count": len(rag_context.project_facts) if rag_context else 0,
        "rag_snippets_count": len(rag_context.code_snippets) if rag_context else 0,
        "rag_excerpts_count": len(rag_context.paper_excerpts) if rag_context else 0,
    }


def generate_horus_pipeline(
    project_path: Path,
    output_dir: Path,
    template_name: str = "arxiv",
    use_rag: bool = True,
    persona_strength: float = 0.7,
    scope_file: Optional[Path] = None,
    title_override: Optional[str] = None,
) -> None:
    """Generate a paper in Horus Lupercal's voice (auto-run mode).

    Args:
        project_path: Path to the project being documented
        output_dir: Directory to write output
        template_name: LaTeX template to use
        use_rag: If True, enable RAG grounding
        persona_strength: Persona voice intensity (0.0=neutral, 1.0=full Warmaster)
        scope_file: Optional JSON file with custom paper scope
        title_override: Optional paper title (overrides scope-derived title)
    """
    from analysis import analyze_project
    from figures import generate_figures
    from grounding import build_rag_context, generate_bibtex_from_arxiv
    from sections import generate_section_content
    from utils import sanitize_prompt_injection

    from config import ARXIV_SCRIPT, HORUS_PERSONA, SCILLM_SCRIPT, LiteratureReview, PaperScope

    typer.echo("\n=== PHASE 1: PROJECT ANALYSIS & DRAFT ===")
    _tm(["start-session", "--project", "create-paper"])

    # Load scope from file or use defaults
    if scope_file and scope_file.exists():
        import json as _json
        scope_data = _json.loads(scope_file.read_text())
        scope = PaperScope(
            paper_type=scope_data.get("paper_type", "system"),
            target_venue=scope_data.get("target_venue", "arXiv preprint"),
            contributions=scope_data.get("contributions", []),
            audience=scope_data.get("audience", "AI/ML researchers and practitioners"),
            prior_work_areas=scope_data.get("prior_work_areas", []),
        )
        paper_title = title_override or scope_data.get("title", scope.contributions[0] if scope.contributions else "Untitled")
        arxiv_ids = scope_data.get("arxiv_ids", [])
        typer.echo(f"  Loaded scope from {scope_file}")
    else:
        scope = PaperScope(
            paper_type="system",
            target_venue="arXiv preprint",
            contributions=[
                f"Novel architecture demonstrated in {project_path.name}",
                "Comprehensive evaluation and analysis",
                "Open-source implementation",
            ],
            audience="AI/ML researchers and practitioners",
            prior_work_areas=["agent-systems", "software-architecture"],
        )
        paper_title = title_override or scope.contributions[0]
        arxiv_ids = []

    typer.echo(f"  Title: {paper_title}")

    analysis = analyze_project(project_path, scope, auto_approve=True)

    # Attempt literature review if arxiv IDs provided or arxiv skill available
    review = LiteratureReview(papers_found=[], papers_selected=[], extractions=[])
    if arxiv_ids:
        typer.echo(f"\n=== PHASE 1b: LITERATURE ({len(arxiv_ids)} papers) ===")
        for aid in arxiv_ids:
            typer.echo(f"  Referencing: {aid}")
            review.papers_selected.append(aid)
            review.papers_found.append({"id": aid, "status": "pre-loaded"})

    rag_context = None
    if use_rag:
        rag_context = build_rag_context(project_path, scope, analysis, review)

    output_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = output_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    use_llm = SCILLM_SCRIPT.exists()
    structure = [
        ("abstract", "Abstract"), ("intro", "Introduction"),
        ("related", "Related Work"), ("design", "System Design"),
        ("impl", "Implementation"), ("eval", "Evaluation"),
        ("discussion", "Discussion"),
    ]

    for key, section_title in structure:
        content = generate_section_content(
            section_key=key, section_title=section_title, scope=scope,
            analysis=analysis, review=review, project_path=project_path,
            use_llm=use_llm, rag_context=rag_context,
            persona=HORUS_PERSONA, persona_strength=persona_strength,
        )
        (sections_dir / f"{key}.tex").write_text(content)

    _tm(["add-accomplishment", "--text", f"Generated {len(structure)} sections for {paper_title}"])

    figures_dir = output_dir / "figures"
    generate_figures(project_path, analysis, figures_dir)

    template = get_template(template_name)
    main_tex = output_dir / "draft.tex"
    main_content = _build_main_tex(template, paper_title, author=HORUS_PERSONA.name)
    main_tex.write_text(main_content)

    refs_file = output_dir / "references.bib"
    generate_bibtex_from_arxiv(arxiv_ids, refs_file)

    # Sanitize
    for tex_file in output_dir.rglob("*.tex"):
        content = tex_file.read_text()
        sanitized, warnings = sanitize_prompt_injection(content)
        if warnings:
            tex_file.write_text(sanitized)

    typer.echo(f"\n[OK] PAPER GENERATION COMPLETE")
    typer.echo(f"Output: {output_dir}")
    typer.echo(f"Compile with: cd {output_dir} && pdflatex draft.tex")
    _tm(["end-session", "--notes", f"Draft complete: {paper_title}"])


def _run_mimic_validation(output_dir: Path, mimic_patterns: MimicPatterns) -> None:
    """Run MIMIC validation on generated paper.

    Args:
        output_dir: Paper output directory
        mimic_patterns: MIMIC patterns to validate against
    """
    from mimic import validate_against_exemplars

    typer.echo("\n--- MIMIC VALIDATION ---")
    report = validate_against_exemplars(output_dir, mimic_patterns)

    for category in ["structure", "style", "content"]:
        if report[category]["issues"]:
            typer.echo(f"{category.title()} issues:")
            for issue in report[category]["issues"]:
                typer.echo(f"  [!] {issue}")

    if report["recommendations"]:
        typer.echo("\nRecommendations:")
        for rec in report["recommendations"]:
            typer.echo(f"  -> {rec}")

    if not any(report[c]["issues"] for c in ["structure", "style", "content"]):
        typer.echo("  [OK] Paper matches exemplar patterns!")
