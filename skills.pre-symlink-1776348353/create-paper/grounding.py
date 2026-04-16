"""
Paper Writer Skill - Grounding
RAG grounding context construction, claim verification, and grounded prompt generation.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()

from config import (
    ARXIV_SCRIPT,
    MEMORY_SCRIPT,
    PaperScope,
    ProjectAnalysis,
    RAGContext,
    LiteratureReview,
)


def extract_code_snippets(project_path: Path, max_snippets: int = 20) -> List[Dict[str, str]]:
    """Extract key code snippets from project for grounding.

    Focuses on:
    - Function/class definitions
    - Docstrings
    - Key implementation patterns

    Args:
        project_path: Path to project
        max_snippets: Maximum snippets to extract

    Returns:
        List of snippet dicts with file, content, type
    """
    snippets = []

    # Find Python files
    py_files = list(project_path.rglob("*.py"))[:30]  # Limit files

    for py_file in py_files:
        if "__pycache__" in str(py_file) or ".venv" in str(py_file):
            continue

        try:
            content = py_file.read_text()
            lines = content.split("\n")

            # Extract function and class definitions with docstrings
            i = 0
            while i < len(lines) and len(snippets) < max_snippets:
                line = lines[i]

                # Function definition
                if line.strip().startswith("def ") or line.strip().startswith("async def "):
                    snippet_lines = [line]
                    j = i + 1

                    # Get docstring if present
                    while j < len(lines) and j < i + 15:
                        snippet_lines.append(lines[j])
                        if '"""' in lines[j] and j > i + 1:
                            break
                        if "'''" in lines[j] and j > i + 1:
                            break
                        j += 1

                    snippets.append({
                        "file": str(py_file.relative_to(project_path)),
                        "content": "\n".join(snippet_lines[:15]),
                        "type": "function",
                    })

                # Class definition
                elif line.strip().startswith("class "):
                    snippet_lines = [line]
                    j = i + 1

                    # Get docstring and first few methods
                    while j < len(lines) and j < i + 20:
                        snippet_lines.append(lines[j])
                        if lines[j].strip().startswith("def ") and j > i + 5:
                            break
                        j += 1

                    snippets.append({
                        "file": str(py_file.relative_to(project_path)),
                        "content": "\n".join(snippet_lines[:20]),
                        "type": "class",
                    })

                i += 1

        except Exception:
            continue

    return snippets[:max_snippets]


def build_rag_context(
    project_path: Path,
    scope: PaperScope,
    analysis: ProjectAnalysis,
    review: LiteratureReview,
) -> RAGContext:
    """Build RAG context from all available sources.

    Collects and organizes grounding material:
    1. Code snippets from project
    2. Verified facts from analysis
    3. Paper excerpts from literature review
    4. Research findings from dogpile

    Args:
        project_path: Path to project
        scope: Paper scope definition
        analysis: Project analysis results
        review: Literature review results

    Returns:
        RAGContext with organized grounding material
    """
    typer.echo("Building RAG grounding context...")

    # 1. Extract code snippets
    code_snippets = extract_code_snippets(project_path)
    typer.echo(f"  Extracted {len(code_snippets)} code snippets")

    # 2. Build project facts from analysis
    project_facts = []

    # Features as facts
    for f in analysis.features[:10]:
        feature_name = f.get("feature", f.get("name", "Unknown"))
        loc = f.get("loc", f.get("lines", 0))
        if loc:
            project_facts.append(f"The project implements {feature_name} ({loc} lines of code)")
        else:
            project_facts.append(f"The project implements {feature_name}")

    # Architecture patterns as facts
    patterns = analysis.architecture.get("patterns", [])
    for p in patterns[:5]:
        project_facts.append(f"The project uses {p} architectural pattern")

    # Issues as facts (for discussion section)
    for issue in analysis.issues[:5]:
        issue_desc = issue.get("issue", issue.get("description", ""))
        if issue_desc:
            project_facts.append(f"Known limitation: {issue_desc}")

    typer.echo(f"  Compiled {len(project_facts)} project facts")

    # 3. Extract paper excerpts from literature review
    paper_excerpts = _extract_paper_excerpts(review, scope)
    typer.echo(f"  Extracted {len(paper_excerpts)} paper excerpts")

    # 4. Parse research facts from dogpile context
    research_facts = []
    if analysis.research_context:
        for line in analysis.research_context.split("\n"):
            line = line.strip()
            if line.startswith(("-", "*", "\u2022")) and len(line) > 20:
                research_facts.append(line[1:].strip())

    typer.echo(f"  Found {len(research_facts)} research facts")

    # 5. Define section constraints
    section_constraints = _build_section_constraints()

    return RAGContext(
        code_snippets=code_snippets,
        project_facts=project_facts,
        paper_excerpts=paper_excerpts,
        research_facts=research_facts,
        section_constraints=section_constraints,
    )


def _extract_paper_excerpts(
    review: LiteratureReview,
    scope: PaperScope,
) -> List[Dict[str, str]]:
    """Extract paper excerpts from literature review.

    Args:
        review: Literature review with extractions
        scope: Paper scope for topic context

    Returns:
        List of excerpt dicts
    """
    paper_excerpts = []
    for extraction in review.extractions:
        if extraction.get("status") != "success":
            continue

        paper_id = extraction.get("paper_id", "unknown")
        output = extraction.get("output", "")

        # Extract Q&A pairs as excerpts
        qa_pairs = []
        lines = output.split("\n")
        current_q = ""
        current_a = ""

        for line in lines:
            if line.strip().startswith(("Q:", "Question:")):
                if current_q and current_a:
                    qa_pairs.append({"q": current_q, "a": current_a})
                current_q = line.strip()
                current_a = ""
            elif line.strip().startswith(("A:", "Answer:")):
                current_a = line.strip()
            elif current_a:
                current_a += " " + line.strip()

        if current_q and current_a:
            qa_pairs.append({"q": current_q, "a": current_a})

        for qa in qa_pairs[:5]:  # Limit per paper
            paper_excerpts.append({
                "paper_id": paper_id,
                "excerpt": f"{qa['q']} {qa['a']}",
                "topic": scope.prior_work_areas[0] if scope.prior_work_areas else "general",
            })

    return paper_excerpts


def _build_section_constraints() -> Dict[str, List[str]]:
    """Build section-specific grounding constraints.

    Returns:
        Dict mapping section key to list of constraint strings
    """
    return {
        "abstract": [
            "Only mention features that exist in project_facts",
            "Quantitative claims must have source in code_snippets or project_facts",
            "Do not claim novelty without supporting paper_excerpts",
        ],
        "intro": [
            "Problem statement must be supported by research_facts or paper_excerpts",
            "Contribution claims must map to specific features in project_facts",
            "Related work comparisons must cite paper_excerpts",
        ],
        "related": [
            "Every cited claim must have source in paper_excerpts",
            "Do not summarize papers not in paper_excerpts",
            "Comparison must be factual, based on documented differences",
        ],
        "design": [
            "Architecture description must match code_snippets",
            "Design decisions must be evidenced by actual code patterns",
            "Do not describe features not in project_facts",
        ],
        "impl": [
            "Implementation details must match code_snippets",
            "Code examples must be real excerpts, not generated",
            "Line counts and metrics must match project_facts",
        ],
        "eval": [
            "Metrics must be derived from project_facts or code_snippets",
            "Comparisons must be based on documented paper_excerpts",
            "Do not fabricate benchmark results",
        ],
        "discussion": [
            "Limitations must come from analysis issues",
            "Future work should address documented issues",
            "Do not claim capabilities beyond project_facts",
        ],
    }


def verify_grounding(
    content: str,
    section_key: str,
    rag_context: RAGContext,
) -> Dict[str, Any]:
    """Verify that generated content is grounded in source material.

    Checks:
    1. Claims have supporting evidence
    2. No hallucinated features or metrics
    3. Citations match paper_excerpts

    Args:
        content: Generated section content
        section_key: Section identifier
        rag_context: RAG context with grounding material

    Returns:
        Verification report with issues and confidence score
    """
    report = {
        "grounded": True,
        "confidence": 1.0,
        "issues": [],
        "suggestions": [],
    }

    content_lower = content.lower()

    # Check for potentially ungrounded claims
    ungrounded_indicators = [
        ("achieves", "Performance claims should be backed by evaluation data"),
        ("novel", "Novelty claims should cite prior work showing gap"),
        ("first", "Priority claims are dangerous without thorough search"),
        ("unique", "Uniqueness claims need comprehensive comparison"),
        ("outperforms", "Performance comparison needs baseline data"),
        ("state-of-the-art", "SOTA claims require recent benchmarks"),
        ("significantly", "Significance claims need statistical support"),
    ]

    for indicator, warning in ungrounded_indicators:
        if indicator in content_lower:
            has_evidence = False

            for fact in rag_context.project_facts:
                if indicator in fact.lower():
                    has_evidence = True
                    break

            for excerpt in rag_context.paper_excerpts:
                if indicator in excerpt.get("excerpt", "").lower():
                    has_evidence = True
                    break

            if not has_evidence:
                report["issues"].append(f"Claim '{indicator}': {warning}")
                report["confidence"] -= 0.1

    # Check for fabricated metrics (numbers without sources)
    numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b', content)
    for num in numbers:
        try:
            val = float(num.rstrip('%'))
            if val > 10:  # Likely a metric
                found = False
                for fact in rag_context.project_facts:
                    if num in fact:
                        found = True
                        break
                for snippet in rag_context.code_snippets:
                    if num in snippet.get("content", ""):
                        found = True
                        break

                if not found:
                    report["suggestions"].append(
                        f"Metric '{num}' not found in sources - verify accuracy"
                    )
        except ValueError:
            continue

    # Section-specific checks
    constraints = rag_context.section_constraints.get(section_key, [])
    for constraint in constraints:
        report["suggestions"].append(f"Constraint: {constraint}")

    # Calculate final confidence
    report["confidence"] = max(0.0, min(1.0, report["confidence"]))
    report["grounded"] = len(report["issues"]) == 0 and report["confidence"] >= 0.7

    return report


def generate_grounded_prompt(
    section_key: str,
    section_title: str,
    scope: PaperScope,
    rag_context: RAGContext,
) -> str:
    """Build a grounded prompt with source material for LLM generation.

    Args:
        section_key: Section identifier
        section_title: Human-readable title
        scope: Paper scope
        rag_context: RAG context with grounding material

    Returns:
        Grounded prompt string
    """
    relevant_facts = rag_context.project_facts[:8]
    relevant_excerpts = rag_context.paper_excerpts[:5]
    relevant_snippets = rag_context.code_snippets[:5]
    constraints = rag_context.section_constraints.get(section_key, [])

    facts_str = chr(10).join(f"- {fact}" for fact in relevant_facts)
    snippets_str = chr(10).join(f"[{s['file']}] {s['type']}: {s['content'][:200]}..." for s in relevant_snippets)
    excerpts_str = chr(10).join(f"[{e['paper_id']}] {e['excerpt'][:200]}..." for e in relevant_excerpts)
    constraints_str = chr(10).join(f"- {c}" for c in constraints)

    prompt = _load_prompt("create_paper_grounded_section_v1").format(
        section_title=section_title,
        paper_type=scope.paper_type,
        target_venue=scope.target_venue,
        relevant_facts=facts_str,
        relevant_snippets=snippets_str,
        relevant_excerpts=excerpts_str,
        constraints=constraints_str,
    )

    return prompt


def generate_bibtex_from_arxiv(
    paper_ids: List[str],
    output_path: Path,
) -> int:
    """Generate BibTeX entries from arxiv paper IDs.

    Args:
        paper_ids: List of arxiv paper IDs (e.g., ["2501.15355", "2502.67890"])
        output_path: Path to write the .bib file

    Returns:
        Number of BibTeX entries generated
    """
    if not paper_ids:
        output_path.write_text("% No arxiv papers referenced\n")
        return 0

    if not ARXIV_SCRIPT.exists():
        logger.warning("arxiv skill not available, creating stub references.bib")
        output_path.write_text("% arxiv skill not available - add references manually\n")
        return 0

    typer.echo(f"Generating BibTeX for {len(paper_ids)} arxiv papers...")
    bibtex_entries = []

    for paper_id in paper_ids:
        # Clean paper ID (remove version suffix if present)
        clean_id = paper_id.split("v")[0] if "v" in paper_id else paper_id

        try:
            result = subprocess.run(
                [str(ARXIV_SCRIPT), "get", "--id", clean_id],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        authors = item.get("authors", ["Unknown"])
                        author_str = " and ".join(authors[:5])
                        if len(authors) > 5:
                            author_str += " and others"

                        title = item.get("title", "Unknown Title").replace("\n", " ")
                        year = item.get("published", "2024")[:4]

                        first_author = authors[0].split()[-1].lower() if authors else "unknown"
                        cite_key = f"{first_author}{year}_{clean_id.replace('.', '_')}"

                        entry = f"""@article{{{cite_key},
  title = {{{{{title}}}}},
  author = {{{author_str}}},
  journal = {{arXiv preprint arXiv:{clean_id}}},
  year = {{{year}}},
  note = {{\\url{{https://arxiv.org/abs/{clean_id}}}}}
}}
"""
                        bibtex_entries.append(entry)
                        typer.echo(f"  Added: {cite_key}")
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse arxiv response for {clean_id}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout fetching {clean_id}")
        except Exception as e:
            logger.warning(f"Error fetching {clean_id}: {e}")

    # Write all entries to file
    if bibtex_entries:
        content = "% Auto-generated BibTeX from arxiv papers\n\n" + "\n".join(bibtex_entries)
    else:
        content = "% No arxiv papers could be fetched - add references manually\n"

    output_path.write_text(content)
    typer.echo(f"  Generated: {output_path.name} ({len(bibtex_entries)} entries)")
    return len(bibtex_entries)
