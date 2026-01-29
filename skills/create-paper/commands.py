"""
Paper Writer Skill - CLI Commands
Quality, verification, and compliance commands.
"""
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import List

import typer

from config import (
    ClaimEvidence,
    CRITIQUE_ASPECTS,
    SCILLM_SCRIPT,
    VENUE_POLICIES,
)


def register_commands(app: typer.Typer) -> None:
    """Register all verification and compliance commands on the app."""

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
        from citations import check_citations as check_cites, verify_citation_from_bib

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
            verification_results = {"Supported": [], "Partial": [], "Unsupported": [], "Uncertain": []}

            for cite_key in sorted(all_citations):
                if cite_key not in bib_entries:
                    continue

                entry = bib_entries[cite_key]
                result = verify_citation_from_bib(entry)
                status = result.get("status", "Uncertain")
                verification_results[status].append((cite_key, result))

                if status == "Supported":
                    typer.echo(f"  [OK] {cite_key}")
                elif status == "Unsupported":
                    typer.echo(f"  [X] {cite_key} - {result.get('error', 'Not found')}")
                    if strict:
                        issues.append(f"API verification failed: {cite_key}")

            typer.echo("\n--- API VERIFICATION SUMMARY ---")
            typer.echo(f"  [OK] Supported: {len(verification_results['Supported'])}")
            typer.echo(f"  [X] Unsupported: {len(verification_results['Unsupported'])}")

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
        paper_path = Path(paper_dir).resolve()
        sections_dir = paper_path / "sections"

        typer.echo(f"\n=== CLAIM-EVIDENCE GRAPH ===\n")

        if not sections_dir.exists():
            typer.echo(f"[ERROR] Sections not found: {sections_dir}", err=True)
            raise typer.Exit(1)

        claims: List[ClaimEvidence] = []
        claim_patterns = [
            r"we\s+(demonstrate|show|prove|achieve|present|introduce|propose)",
            r"our\s+(approach|method|system|framework)\s+(achieves|outperforms|improves)",
            r"this\s+(work|paper|approach)\s+(presents|introduces|demonstrates)",
            r"the\s+results\s+(show|demonstrate|indicate|confirm)",
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
