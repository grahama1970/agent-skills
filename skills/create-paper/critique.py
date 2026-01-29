"""
Paper Writer Skill - Critique
Quality metrics, critique functions, and weakness analysis.
"""
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import typer

from config import (
    CRITIQUE_ASPECTS,
    SCILLM_SCRIPT,
)


def compute_quality_metrics(paper_dir: Path) -> Dict[str, Any]:
    """Compute quality metrics for a generated paper.

    Args:
        paper_dir: Path to paper directory

    Returns:
        Metrics dict with word counts, citation stats, etc.
    """
    metrics = {
        "sections": {},
        "total_words": 0,
        "total_citations": 0,
        "figures": 0,
        "tables": 0,
        "equations": 0,
        "warnings": [],
    }

    sections_dir = paper_dir / "sections"
    if not sections_dir.exists():
        metrics["warnings"].append("Sections directory not found")
        return metrics

    targets = {
        "abstract": (150, 250),
        "intro": (800, 1500),
        "related": (600, 1200),
        "design": (800, 1500),
        "impl": (600, 1200),
        "eval": (800, 1500),
        "discussion": (400, 800),
    }

    cite_pattern = re.compile(r'\\cite[tp]?\{[^}]+\}')
    figure_pattern = re.compile(r'\\begin\{figure')
    table_pattern = re.compile(r'\\begin\{table')
    equation_pattern = re.compile(r'\\begin\{equation|\\begin\{align|\$\$')

    for section_file in sections_dir.glob("*.tex"):
        section_key = section_file.stem
        content = section_file.read_text()
        words = len(content.split())

        citations = len(cite_pattern.findall(content))
        figures = len(figure_pattern.findall(content))
        tables = len(table_pattern.findall(content))
        equations = len(equation_pattern.findall(content))

        target = targets.get(section_key, (0, 99999))
        status = "ok"
        if words < target[0]:
            status = "short"
            metrics["warnings"].append(f"{section_key}: {words} words (min: {target[0]})")
        elif words > target[1]:
            status = "long"
            metrics["warnings"].append(f"{section_key}: {words} words (max: {target[1]})")

        metrics["sections"][section_key] = {
            "words": words,
            "target": target,
            "status": status,
            "citations": citations,
            "figures": figures,
            "tables": tables,
        }

        metrics["total_words"] += words
        metrics["total_citations"] += citations
        metrics["figures"] += figures
        metrics["tables"] += tables
        metrics["equations"] += equations

    return metrics


def critique_section(
    section_key: str,
    content: str,
    aspects: List[str] = None,
) -> Dict[str, Any]:
    """Generate aspect-based critique for a section.

    Args:
        section_key: Section identifier
        content: Section content
        aspects: List of aspects to critique (default: all)

    Returns:
        Critique report by aspect
    """
    if aspects is None:
        aspects = list(CRITIQUE_ASPECTS.keys())

    critique = {}

    for aspect in aspects:
        if aspect not in CRITIQUE_ASPECTS:
            continue

        aspect_info = CRITIQUE_ASPECTS[aspect]
        findings = []
        content_lower = content.lower()

        if aspect == "clarity":
            sentences = content.split(".")
            long_sentences = [s for s in sentences if len(s.split()) > 40]
            if long_sentences:
                findings.append(f"Found {len(long_sentences)} sentences over 40 words")

            acronyms = re.findall(r'\b[A-Z]{2,}\b', content)
            if len(set(acronyms)) > 5:
                findings.append(f"Many acronyms used ({len(set(acronyms))})")

        elif aspect == "novelty":
            if "novel" not in content_lower and "contribution" not in content_lower:
                if section_key == "intro":
                    findings.append("No explicit novelty/contribution statement found")

        elif aspect == "rigor":
            if section_key == "eval":
                if "baseline" not in content_lower and "compare" not in content_lower:
                    findings.append("No baseline comparison mentioned")
                if "%" not in content and "accuracy" not in content_lower:
                    findings.append("No quantitative metrics found")

        elif aspect == "completeness":
            word_count = len(content.split())
            if word_count < 100 and section_key not in ["abstract"]:
                findings.append(f"Section seems short ({word_count} words)")

        elif aspect == "presentation":
            if "\\begin{figure}" not in content and section_key in ["design", "eval"]:
                findings.append("No figures in this section")

        critique[aspect] = {
            "description": aspect_info["description"],
            "checklist": aspect_info["checklist"],
            "findings": findings,
            "score": max(0, 5 - len(findings)),
        }

    return critique


def generate_critique_prompt(
    section_key: str,
    content: str,
    aspects: List[str],
) -> str:
    """Generate LLM prompt for deep critique.

    Args:
        section_key: Section identifier
        content: Section content
        aspects: Aspects to critique

    Returns:
        LLM prompt string
    """
    aspects_text = "\n".join([
        f"- {aspect}: {CRITIQUE_ASPECTS[aspect]['description']}"
        for aspect in aspects if aspect in CRITIQUE_ASPECTS
    ])

    return f"""You are an expert academic reviewer. Critique this {section_key} section.

ASPECTS TO EVALUATE:
{aspects_text}

SECTION CONTENT:
{content[:3000]}

For each aspect, provide:
1. Score (1-5)
2. Specific issues found
3. Concrete suggestions for improvement

Format as JSON with structure:
{{
  "aspect_name": {{
    "score": N,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1", "suggestion2"]
  }}
}}
"""


def generate_weakness_analysis(
    paper_dir: Path,
    project_path: Path = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Generate explicit weakness/limitations analysis.

    Args:
        paper_dir: Path to paper directory
        project_path: Optional project path for deeper analysis

    Returns:
        Dict with weaknesses list and LaTeX content
    """
    sections_dir = paper_dir / "sections"
    sections_content = {}

    if sections_dir.exists():
        for sec_file in sections_dir.glob("*.tex"):
            sections_content[sec_file.stem] = sec_file.read_text()

    weaknesses = []

    # 1. Check methodology claims
    if "method" in sections_content or "methodology" in sections_content:
        method_content = sections_content.get("method", sections_content.get("methodology", ""))

        if "assume" in method_content.lower():
            weaknesses.append({
                "category": "Assumptions",
                "description": "The methodology makes assumptions that may not hold in all scenarios",
                "severity": "medium",
            })

        if "simplif" in method_content.lower():
            weaknesses.append({
                "category": "Simplifications",
                "description": "Simplifications were made that may limit generalizability",
                "severity": "medium",
            })

    # 2. Check evaluation scope
    if "eval" in sections_content or "evaluation" in sections_content:
        eval_content = sections_content.get("eval", sections_content.get("evaluation", ""))

        baseline_mentions = eval_content.lower().count("baseline")
        if baseline_mentions < 3:
            weaknesses.append({
                "category": "Limited Baselines",
                "description": "Evaluation compares against limited baselines (research suggests 3-4 minimum)",
                "severity": "high",
            })

    # 3. Check for scope limitations
    if "intro" in sections_content:
        intro_content = sections_content["intro"]

        if "scope" not in intro_content.lower() and "limit" not in intro_content.lower():
            weaknesses.append({
                "category": "Scope",
                "description": "The scope and applicability boundaries are not explicitly stated",
                "severity": "medium",
            })

    # 4. Analyze project if provided
    if project_path and project_path.exists():
        test_files = list(project_path.rglob("test_*.py")) + list(project_path.rglob("*_test.py"))
        py_files = [f for f in project_path.rglob("*.py") if "test" not in f.name]

        if len(test_files) < len(py_files) * 0.3:
            weaknesses.append({
                "category": "Validation",
                "description": f"Limited test coverage ({len(test_files)} tests for {len(py_files)} modules)",
                "severity": "medium",
            })

    # 5. Standard academic limitations
    standard_limitations = [
        {
            "category": "Reproducibility",
            "description": "Results may vary with different random seeds or hardware configurations",
            "severity": "low",
        },
        {
            "category": "Generalization",
            "description": "Performance on domains outside the evaluation set is not guaranteed",
            "severity": "medium",
        },
    ]
    weaknesses.extend(standard_limitations)

    # Generate LaTeX
    limitations_tex = """\\subsection{Limitations}
\\label{sec:limitations}

While our approach demonstrates significant improvements, we acknowledge several limitations:

\\begin{itemize}
"""
    for w in weaknesses:
        limitations_tex += f"    \\item \\textbf{{{w['category']}}}: {w['description']}\n"

    limitations_tex += """\\end{itemize}

These limitations present opportunities for future work and should be considered when applying our approach to new domains.
"""

    return {
        "weaknesses": weaknesses,
        "latex": limitations_tex,
    }


def run_llm_critique(
    content: str,
    section_key: str,
    aspects: List[str],
) -> Dict[str, Any]:
    """Run LLM-based deep critique.

    Args:
        content: Section content
        section_key: Section identifier
        aspects: Aspects to critique

    Returns:
        LLM critique result or empty dict
    """
    if not SCILLM_SCRIPT.exists():
        return {}

    prompt = generate_critique_prompt(section_key, content, aspects)

    try:
        result = subprocess.run(
            [str(SCILLM_SCRIPT), "batch", "single", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # Try to parse as JSON
            try:
                import json
                return json.loads(result.stdout)
            except Exception:
                return {"raw": result.stdout[:500]}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return {}
