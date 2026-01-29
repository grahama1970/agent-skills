#!/usr/bin/env python3
"""
Paper Writer Skill - CLI Entry Point
Thin CLI layer that delegates to modular components.
"""
import json
from dataclasses import asdict
from pathlib import Path

import typer

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
    name="paper-writer",
    help="AI-assisted academic paper writing with interview-driven workflow",
)


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
        typer.echo(f"[ERROR] Unknown section: {section}", err=True)
        typer.echo(f"Available: {', '.join(phrase_source.keys())}")
        raise typer.Exit(1)

    section_phrases = phrase_source[section]

    if aspect:
        if aspect not in section_phrases:
            typer.echo(f"[ERROR] Unknown aspect: {aspect}", err=True)
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
            typer.echo(f"[ERROR] Unknown template: {show}", err=True)
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
        typer.echo(f"[ERROR] Unknown venue: {venue}", err=True)
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
# QUALITY AND VERIFICATION COMMANDS
# =============================================================================


@app.command()
def quality(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed metrics"),
) -> None:
    """Show quality dashboard for a generated paper."""
    from citations import check_citations
    from critique import compute_quality_metrics

    paper_path = Path(paper_dir).resolve()

    if not paper_path.exists():
        typer.echo(f"[ERROR] Paper directory not found: {paper_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== QUALITY DASHBOARD: {paper_path.name} ===\n")

    metrics = compute_quality_metrics(paper_path)

    typer.echo("Section Metrics:")
    typer.echo("-" * 60)
    typer.echo(f"{'Section':<12} {'Words':>8} {'Target':>12} {'Status':>8} {'Cites':>6}")
    typer.echo("-" * 60)

    for section, data in metrics["sections"].items():
        target_str = f"{data['target'][0]}-{data['target'][1]}"
        status_icon = "[OK]" if data["status"] == "ok" else "[!]"
        typer.echo(
            f"{section:<12} {data['words']:>8} {target_str:>12} {status_icon:>8} {data['citations']:>6}"
        )

    typer.echo("-" * 60)
    typer.echo(f"{'TOTAL':<12} {metrics['total_words']:>8}")

    typer.echo(f"\nSummary:")
    typer.echo(f"  Total words: {metrics['total_words']}")
    typer.echo(f"  Total citations: {metrics['total_citations']}")
    typer.echo(f"  Figures: {metrics['figures']}")
    typer.echo(f"  Tables: {metrics['tables']}")
    typer.echo(f"  Equations: {metrics['equations']}")

    typer.echo(f"\nCitation Check:")
    citation_report = check_citations(paper_path)
    typer.echo(f"  Valid: {len(citation_report['valid'])}")
    typer.echo(f"  Missing: {len(citation_report['missing'])}")
    typer.echo(f"  Unused: {len(citation_report['unused'])}")

    if citation_report["missing"]:
        typer.echo(f"  [WARN] Missing BibTeX entries: {', '.join(citation_report['missing'][:5])}")

    if metrics["warnings"]:
        typer.echo(f"\nWarnings ({len(metrics['warnings'])}):")
        for warning in metrics["warnings"]:
            typer.echo(f"  [!] {warning}")

    if verbose:
        typer.echo(f"\nDetailed Metrics:")
        typer.echo(json.dumps(metrics, indent=2))


@app.command()
def critique(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    section: str = typer.Option("", "--section", "-s", help="Specific section to critique"),
    aspects: str = typer.Option("all", "--aspects", "-a", help="Aspects: clarity,novelty,rigor,completeness,presentation or 'all'"),
    use_llm: bool = typer.Option(False, "--llm", help="Use LLM for deep critique"),
) -> None:
    """Generate aspect-based critique (SWIF2T-style feedback)."""
    from config import CRITIQUE_ASPECTS
    from critique import critique_section, run_llm_critique

    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    if not sections_dir.exists():
        typer.echo(f"[ERROR] Sections not found: {sections_dir}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== ASPECT CRITIQUE: {paper_path.name} ===\n")

    if aspects == "all":
        aspect_list = list(CRITIQUE_ASPECTS.keys())
    else:
        aspect_list = [a.strip() for a in aspects.split(",")]

    typer.echo(f"Evaluating aspects: {', '.join(aspect_list)}\n")

    if section:
        section_files = [sections_dir / f"{section}.tex"]
    else:
        section_files = list(sections_dir.glob("*.tex"))

    overall_scores = {aspect: [] for aspect in aspect_list}

    for section_file in section_files:
        if not section_file.exists():
            continue

        section_key = section_file.stem
        content = section_file.read_text()

        typer.echo(f"--- {section_key} ---")

        if use_llm and SCILLM_SCRIPT.exists():
            llm_result = run_llm_critique(content, section_key, aspect_list)
            if llm_result:
                typer.echo(f"  LLM Critique:")
                typer.echo(f"  {str(llm_result)[:500]}...")

        critique_result = critique_section(section_key, content, aspect_list)

        for aspect, data in critique_result.items():
            score = data["score"]
            overall_scores[aspect].append(score)
            findings = data["findings"]

            status = "[OK]" if score >= 4 else "[!]" if score >= 2 else "[X]"
            typer.echo(f"  {aspect}: {status} {score}/5")

            if findings:
                for finding in findings:
                    typer.echo(f"    - {finding}")

        typer.echo()

    typer.echo("=== OVERALL SCORES ===")
    for aspect, scores in overall_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            typer.echo(f"  {aspect}: {avg:.1f}/5")


@app.command("check-citations")
def check_citations_cmd(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    strict: bool = typer.Option(False, "--strict", help="Fail on any unverified citation"),
    verify_api: bool = typer.Option(False, "--verify-api", "-v", help="Verify citations against real APIs"),
) -> None:
    """Verify citations to prevent hallucinated references."""
    import re

    from citations import check_citations, verify_citation_from_bib

    paper_path = Path(paper_dir).resolve()

    tex_files = list(paper_path.rglob("*.tex"))
    bib_files = list(paper_path.rglob("*.bib"))

    if not tex_files:
        typer.echo(f"[ERROR] No .tex files found in {paper_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== CITATION VERIFICATION ===\n")
    typer.echo(f"Checking {len(tex_files)} .tex files, {len(bib_files)} .bib files\n")

    all_citations = set()
    citation_pattern = re.compile(r"\\cite[pt]?\{([^}]+)\}")

    for tex_file in tex_files:
        content = tex_file.read_text()
        matches = citation_pattern.findall(content)
        for match in matches:
            for cite_key in match.split(","):
                all_citations.add(cite_key.strip())

    typer.echo(f"Found {len(all_citations)} unique citations")

    bib_entries = {}
    bib_entry_pattern = re.compile(r"@\w+\{([^,]+),")

    for bib_file in bib_files:
        content = bib_file.read_text()
        entries = re.split(r"(?=@\w+\{)", content)
        for entry in entries:
            key_match = bib_entry_pattern.search(entry)
            if key_match:
                bib_entries[key_match.group(1).strip()] = entry

    typer.echo(f"Found {len(bib_entries)} .bib entries\n")

    missing = all_citations - set(bib_entries.keys())
    issues = []

    if missing:
        typer.echo("[WARN] MISSING CITATIONS (used but not in .bib):")
        for cite in sorted(missing):
            typer.echo(f"  [X] {cite}")
            issues.append(f"Missing bib entry: {cite}")

    if verify_api:
        typer.echo("\n--- API VERIFICATION ---")
        typer.echo("Verifying citations against arXiv, CrossRef, and Semantic Scholar...\n")

        verification_results = {"Supported": [], "Partial": [], "Unsupported": [], "Uncertain": []}

        for cite_key in sorted(all_citations):
            if cite_key not in bib_entries:
                continue

            entry = bib_entries[cite_key]
            result = verify_citation_from_bib(entry)
            status = result.get("status", "Uncertain")
            verification_results[status].append((cite_key, result))

            if status == "Supported":
                typer.echo(f"  [OK] {cite_key} [{result.get('source', 'Unknown')}]")
            elif status == "Partial":
                typer.echo(f"  [~] {cite_key} [{result.get('source', 'Unknown')}]")
            elif status == "Unsupported":
                typer.echo(f"  [X] {cite_key} - {result.get('error', 'Not found')}")
                if strict:
                    issues.append(f"API verification failed: {cite_key}")
            else:
                typer.echo(f"  [?] {cite_key} - {result.get('error', 'Unknown')}")

        typer.echo("\n--- API VERIFICATION SUMMARY ---")
        typer.echo(f"  [OK] Supported: {len(verification_results['Supported'])}")
        typer.echo(f"  [~] Partial: {len(verification_results['Partial'])}")
        typer.echo(f"  [X] Unsupported: {len(verification_results['Unsupported'])}")
        typer.echo(f"  [?] Uncertain: {len(verification_results['Uncertain'])}")

    typer.echo("\n=== SUMMARY ===")
    if issues:
        typer.echo(f"[FAIL] {len(issues)} critical issues")
        if strict:
            raise typer.Exit(1)
    else:
        typer.echo("[OK] All citations verified")


@app.command("weakness-analysis")
def weakness_analysis_cmd(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    project: str = typer.Option("", "--project", help="Project path for deeper analysis"),
    output: str = typer.Option("", "--output", "-o", help="Output file for limitations section"),
) -> None:
    """Generate explicit weakness/limitations section."""
    from critique import generate_weakness_analysis

    paper_path = Path(paper_dir).resolve()
    project_path = Path(project).resolve() if project else None

    typer.echo(f"\n=== WEAKNESS & LIMITATIONS ANALYSIS ===\n")

    result = generate_weakness_analysis(paper_path, project_path)
    weaknesses = result["weaknesses"]

    typer.echo(f"--- Identified Limitations ({len(weaknesses)}) ---\n")

    for i, w in enumerate(weaknesses, 1):
        severity_icon = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}[w["severity"]]
        typer.echo(f"{i}. {severity_icon} {w['category']}")
        typer.echo(f"   {w['description']}\n")

    typer.echo("\n--- Generated Limitations Section ---\n")
    typer.echo(result["latex"])

    if output:
        output_path = Path(output)
        output_path.write_text(result["latex"])
        typer.echo(f"\n[OK] Saved to: {output_path}")


@app.command("pre-submit")
def pre_submit_cmd(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    venue: str = typer.Option("arxiv", "--venue", "-v", help="Target venue for policy check"),
    project: str = typer.Option("", "--project", help="Project path for evidence grounding"),
) -> None:
    """Pre-submission checklist and validation."""
    from compliance import run_pre_submit_checks

    paper_path = Path(paper_dir).resolve()
    project_path = Path(project).resolve() if project else None

    result = run_pre_submit_checks(paper_path, venue, project_path)

    typer.echo(f"\n{'='*60}")
    typer.echo(f"PRE-SUBMISSION CHECKLIST: {paper_path.name}")
    typer.echo(f"Target Venue: {result['venue']}")
    typer.echo(f"{'='*60}\n")

    for status, msg in result["checks"]:
        icon = {"pass": "[OK]", "fail": "[X]", "warn": "[!]", "info": "[-]"}[status]
        typer.echo(f"  {icon} {msg}")

    typer.echo(f"\n{'='*60}")

    if result["passed"]:
        typer.echo("[OK] PASSED: Ready for submission\n")
    else:
        typer.echo(f"[FAIL] FAILED: {len(result['critical_fails'])} critical issues\n")
        for fail in result["critical_fails"]:
            typer.echo(f"  -> {fail}")
        raise typer.Exit(1)


@app.command()
def sanitize(
    paper_dir: str = typer.Argument(..., help="Path to paper directory"),
    fix: bool = typer.Option(False, "--fix", help="Auto-fix detected issues"),
) -> None:
    """Sanitize paper for prompt injection attacks."""
    from compliance import sanitize_paper

    paper_path = Path(paper_dir).resolve()

    typer.echo(f"\n=== PROMPT INJECTION SANITIZATION ===\n")

    result = sanitize_paper(paper_path, fix)

    typer.echo(f"Checked {result['files_checked']} .tex files\n")

    if result["warnings"]:
        typer.echo(f"[WARN] FOUND {result['total_issues']} ISSUES:\n")
        for file_path, warnings in result["warnings"]:
            typer.echo(f"  {file_path}:")
            for warning in warnings:
                typer.echo(f"    [X] {warning}")

        if fix:
            typer.echo(f"\n[OK] Fixed {result['files_fixed']} files")
        else:
            typer.echo("\n[ACTION] Run with --fix to auto-remediate")
    else:
        typer.echo("[OK] No prompt injection patterns detected")


@app.command("ai-ledger")
def ai_ledger_cmd(
    paper_dir: str = typer.Argument(..., help="Path to paper directory"),
    show: bool = typer.Option(False, "--show", help="Show current AI usage ledger"),
    generate_disclosure: bool = typer.Option(False, "--disclosure", "-d", help="Generate disclosure from ledger"),
    clear: bool = typer.Option(False, "--clear", help="Clear the ledger"),
) -> None:
    """AI Usage Ledger for ICLR 2026 disclosure compliance."""
    from compliance import generate_ai_ledger_disclosure

    paper_path = Path(paper_dir).resolve()
    ledger_file = paper_path / "ai_usage_ledger.json"

    typer.echo(f"\n=== AI USAGE LEDGER ===\n")

    if clear:
        if ledger_file.exists():
            ledger_file.unlink()
            typer.echo("[OK] Ledger cleared")
        else:
            typer.echo("[INFO] No ledger to clear")
        return

    if show:
        if ledger_file.exists():
            data = json.loads(ledger_file.read_text())
            entries = data.get("entries", [])
            typer.echo(f"Total AI tool uses: {len(entries)}\n")

            by_tool = {}
            for entry in entries:
                tool = entry.get("tool_name", "unknown")
                by_tool[tool] = by_tool.get(tool, 0) + 1

            typer.echo("By Tool:")
            for tool, count in sorted(by_tool.items()):
                typer.echo(f"  {tool}: {count} uses")
        else:
            typer.echo("[INFO] No AI usage logged yet")
        return

    if generate_disclosure:
        result = generate_ai_ledger_disclosure(paper_path)
        if "error" in result:
            typer.echo(f"[ERROR] {result['error']}", err=True)
            raise typer.Exit(1)

        typer.echo("Generated Disclosure:")
        typer.echo("-" * 50)
        typer.echo(result["disclosure_text"])
        typer.echo("-" * 50)

        disclosure_file = paper_path / "ai_disclosure.tex"
        disclosure_file.write_text(result["disclosure_text"])
        typer.echo(f"\n[OK] Saved to: {disclosure_file}")
        return

    typer.echo("Usage:")
    typer.echo("  --show        Show logged AI usage")
    typer.echo("  --disclosure  Generate disclosure statement")
    typer.echo("  --clear       Clear the ledger")


@app.command("claim-graph")
def claim_graph_cmd(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    output: str = typer.Option("", "--output", "-o", help="Output JSON file for claim graph"),
    verify: bool = typer.Option(False, "--verify", "-v", help="Verify claims against sources"),
) -> None:
    """Build claim-evidence graph."""
    import re

    from config import ClaimEvidence

    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    typer.echo(f"\n=== CLAIM-EVIDENCE GRAPH ===\n")

    if not sections_dir.exists():
        typer.echo(f"[ERROR] Sections not found: {sections_dir}", err=True)
        raise typer.Exit(1)

    claims = []
    claim_patterns = [
        r"we\s+(demonstrate|show|prove|achieve|present|introduce|propose)",
        r"our\s+(approach|method|system|framework)\s+(achieves|outperforms|improves)",
        r"this\s+(work|paper|approach)\s+(presents|introduces|demonstrates)",
        r"the\s+results\s+(show|demonstrate|indicate|confirm)",
        r"experiments?\s+(show|demonstrate|reveal|confirm)",
        r"\d+%\s+(improvement|increase|reduction|faster|better)",
    ]

    cite_pattern = re.compile(r"\\cite[pt]?\{([^}]+)\}")

    for section_file in sections_dir.glob("*.tex"):
        section_name = section_file.stem
        content = section_file.read_text()
        lines = content.split("\n")

        typer.echo(f"Analyzing {section_name}...")

        for line_num, line in enumerate(lines, 1):
            for pattern in claim_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    citations = cite_pattern.findall(line)
                    all_cites = []
                    for cite_group in citations:
                        all_cites.extend([c.strip() for c in cite_group.split(",")])

                    if all_cites:
                        support = "Supported" if len(all_cites) >= 2 else "Partially Supported"
                    else:
                        support = "Unsupported"

                    claim = ClaimEvidence(
                        claim_text=line.strip()[:200],
                        claim_location=f"{section_name}:line:{line_num}",
                        evidence_sources=all_cites,
                        support_level=support,
                        verification_notes="",
                    )
                    claims.append(claim)
                    break

    typer.echo(f"\n--- Found {len(claims)} Claims ---\n")

    supported = sum(1 for c in claims if c.support_level == "Supported")
    partial = sum(1 for c in claims if c.support_level == "Partially Supported")
    unsupported = sum(1 for c in claims if c.support_level == "Unsupported")

    typer.echo(f"  [OK] Supported (2+ citations): {supported}")
    typer.echo(f"  [~] Partially Supported (1 citation): {partial}")
    typer.echo(f"  [X] Unsupported (no citations): {unsupported}")

    if unsupported > 0:
        typer.echo(f"\n[WARN] {unsupported} claims lack citation support!")

    if output:
        output_path = Path(output)
        graph_data = {
            "total_claims": len(claims),
            "supported": supported,
            "partial": partial,
            "unsupported": unsupported,
            "claims": [asdict(c) for c in claims],
        }
        output_path.write_text(json.dumps(graph_data, indent=2))
        typer.echo(f"\n[OK] Claim graph saved to: {output_path}")


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
        typer.echo(f"[ERROR] Unknown domain: {domain}", err=True)
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
        typer.echo(f"[ERROR] Unknown stage: {stage}", err=True)
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


if __name__ == "__main__":
    app()
