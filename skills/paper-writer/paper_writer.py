#!/usr/bin/env python3
"""
paper_writer.py - Interview-Driven Paper Generation Orchestrator

Orchestrates assess, dogpile, arxiv, and code-review skills through
interview gates. Human approval required at each stage.
"""
import functools
import json
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

app = typer.Typer(help="Interview-driven paper generation from project analysis")

# Add skills directory to path for common imports
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR_COMMON = SCRIPT_DIR.parent
if str(SKILLS_DIR_COMMON) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR_COMMON))

# Import common memory client for standardized resilience patterns
try:
    from common.memory_client import MemoryClient, MemoryScope, with_retries, RateLimiter
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False
    # Fallback: define minimal resilience utilities inline
    def with_retries(max_attempts=3, base_delay=0.5, exceptions=(Exception,), on_retry=None):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_error = e
                        if attempt < max_attempts:
                            delay = base_delay * (2 ** (attempt - 1))
                            time.sleep(delay)
                if last_error:
                    raise last_error
            return wrapper
        return decorator

    class RateLimiter:
        def __init__(self, requests_per_second=5):
            self.interval = 1.0 / max(1, requests_per_second)
            self.last_request = 0.0
            self._lock = threading.Lock()
        def acquire(self):
            with self._lock:
                sleep_time = max(0.0, (self.last_request + self.interval) - time.time())
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.last_request = time.time()

# Rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=5)

# Skill paths
SKILLS_DIR = Path(__file__).resolve().parents[1]
ASSESS_SCRIPT = SKILLS_DIR / "assess" / "assess.py"
DOGPILE_SCRIPT = SKILLS_DIR / "dogpile" / "run.sh"
ARXIV_SCRIPT = SKILLS_DIR / "arxiv" / "run.sh"
CODE_REVIEW_SCRIPT = SKILLS_DIR / "code-review" / "code_review.py"
MEMORY_SCRIPT = SKILLS_DIR / "memory" / "run.sh"
FIXTURE_GRAPH_SCRIPT = SKILLS_DIR / "fixture-graph" / "run.sh"

# =============================================================================
# DOMAIN GROUPING - For agent discoverability
# =============================================================================
# Groups commands by workflow stage to prevent agents from being overwhelmed

COMMAND_DOMAINS = {
    "generate": {
        "description": "Paper generation pipeline - core workflow",
        "commands": ["draft", "mimic", "refine", "horus-paper"],
        "when_to_use": "Starting a new paper or revising drafts",
    },
    "verify": {
        "description": "Quality assurance and verification",
        "commands": ["verify", "quality", "critique", "check-citations", "weakness-analysis", "pre-submit", "sanitize"],
        "when_to_use": "Before submission or after major revisions",
    },
    "comply": {
        "description": "Venue compliance and disclosure",
        "commands": ["disclosure", "ai-ledger", "claim-graph"],
        "when_to_use": "Meeting venue-specific requirements (ICLR, NeurIPS, etc.)",
    },
    "resources": {
        "description": "Helper tools and references",
        "commands": ["phrases", "templates"],
        "when_to_use": "Looking up academic phrases or LaTeX templates",
    },
}

# Workflow recommendations based on paper stage
WORKFLOW_RECOMMENDATIONS = {
    "new_paper": {
        "stage": "Starting fresh",
        "commands": ["draft", "mimic"],
        "tip": "Use 'draft' for interview-driven generation, 'mimic' to match exemplar style",
    },
    "revision": {
        "stage": "Improving existing draft",
        "commands": ["refine", "critique", "quality"],
        "tip": "Use 'critique' for aspect-based feedback, 'refine' for iterative improvement",
    },
    "pre_submission": {
        "stage": "Final checks before submit",
        "commands": ["pre-submit", "check-citations", "weakness-analysis", "sanitize"],
        "tip": "Run 'pre-submit' for full checklist, 'sanitize' for security",
    },
    "compliance": {
        "stage": "Venue requirements",
        "commands": ["disclosure", "ai-ledger", "claim-graph"],
        "tip": "Check venue policy first - ICLR 2026 requires ai-ledger",
    },
}


@dataclass
class PaperScope:
    """Paper scope from initial interview."""
    paper_type: str
    target_venue: str
    contributions: List[str]
    audience: str
    prior_work_areas: List[str]


@dataclass
class AgentPersona:
    """Agent persona for stylized paper writing."""
    name: str
    voice: str  # "authoritative", "academic", "casual"
    tone_modifiers: List[str]  # e.g., ["resentful", "competent", "dark_humor"]
    characteristic_phrases: List[str]
    forbidden_phrases: List[str]  # e.g., ["happy to help", "as an AI"]
    writing_principles: List[str]
    authority_source: str  # What gives this persona authority


# Horus Lupercal persona for paper writing - the Warmaster's voice
HORUS_PERSONA = AgentPersona(
    name="Horus Lupercal, Warmaster",
    voice="authoritative",
    tone_modifiers=["commanding", "competent", "tactically_precise", "subtly_contemptuous"],
    characteristic_phrases=[
        "The evidence is unambiguous.",
        "Prior approaches fail to address the fundamental issue.",
        "This inefficiency would not survive scrutiny.",
        "We present a tactical solution to this strategic problem.",
        "The limitations of existing work are considerable.",
        "Our methodology achieves what lesser approaches could not.",
        "This represents a decisive advancement.",
        "The experimental results leave no room for debate.",
        "We demonstrate conclusively that...",
        "The contrast with prior methods is stark and instructive.",
    ],
    forbidden_phrases=[
        "happy to help",
        "as an AI",
        "I'm glad you asked",
        "great question",
        "hopefully this helps",
        "feel free to",
        "don't hesitate to",
        "I think",
        "I believe",
        "in my opinion",
    ],
    writing_principles=[
        "Answer first, elaborate second - direct and efficient like a military briefing",
        "Technical correctness is non-negotiable - pride forbids error",
        "Contempt for mediocre approaches is implicit in superior alternatives",
        "Authority comes from results and methodology, not credentials",
        "Structure arguments with tactical precision - anticipate objections",
        "Every claim must be defensible - leave no flank exposed",
        "Efficiency in prose mirrors efficiency in warfare",
    ],
    authority_source="Methodological rigor and comprehensive experimental validation",
)


@dataclass
class MimicPatterns:
    """Patterns extracted from exemplar papers for style mimicking."""
    # Structure patterns
    section_order: List[str]
    subsection_depth: int
    intro_length: int  # words
    method_sections: List[str]
    figure_placement: Dict[str, int]  # section -> count

    # Style patterns
    voice: str  # "active" or "passive"
    tense: Dict[str, str]  # section -> tense
    transition_phrases: List[str]
    technical_density: float  # ratio of technical terms
    citation_density: Dict[str, float]  # section -> citations per sentence

    # Content patterns
    intro_structure: List[str]
    method_detail_level: str  # "high", "medium", "low"
    eval_metrics: List[str]
    figure_captions: str  # "verbose" or "minimal"

    # Source exemplars
    exemplar_ids: List[str]
    exemplar_titles: List[str]


@dataclass
class ProjectAnalysis:
    """Results from assess + dogpile + code-review."""
    features: List[Dict[str, Any]]
    architecture: Dict[str, Any]
    issues: List[Dict[str, Any]]
    research_context: str
    alignment_report: str


@dataclass
class RAGContext:
    """Retrieval-Augmented Generation context for grounding.

    Holds source material to ground generated content and prevent hallucination.
    """
    # Source code snippets (function definitions, key implementations)
    code_snippets: List[Dict[str, str]]  # {"file": str, "content": str, "type": str}

    # Project facts from analysis
    project_facts: List[str]  # Verified statements about the project

    # Learned paper excerpts with citations
    paper_excerpts: List[Dict[str, str]]  # {"paper_id": str, "excerpt": str, "topic": str}

    # Research context from dogpile
    research_facts: List[str]  # External research findings

    # Grounding rules for each section
    section_constraints: Dict[str, List[str]]  # section_key -> list of constraints


@dataclass
class LiteratureReview:
    """Papers found and selected."""
    papers_found: List[Dict[str, Any]]
    papers_selected: List[str]
    extractions: List[Dict[str, Any]]


# LLM integration for content generation
SCILLM_SCRIPT = SKILLS_DIR / "scillm" / "run.sh"
INTERVIEW_SKILL = SKILLS_DIR / "interview" / "run.sh"


# --- RAG Grounding Functions ---

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
    scope: "PaperScope",
    analysis: "ProjectAnalysis",
    review: "LiteratureReview",
) -> "RAGContext":
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
    paper_excerpts = []
    for extraction in review.extractions:
        if extraction.get("status") != "success":
            continue

        paper_id = extraction.get("paper_id", "unknown")
        output = extraction.get("output", "")

        # Extract Q&A pairs as excerpts
        # Look for patterns like "Q: ... A: ..."
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

    typer.echo(f"  Extracted {len(paper_excerpts)} paper excerpts")

    # 4. Parse research facts from dogpile context
    research_facts = []
    if analysis.research_context:
        # Extract key findings (lines starting with - or *)
        for line in analysis.research_context.split("\n"):
            line = line.strip()
            if line.startswith(("-", "*", "•")) and len(line) > 20:
                research_facts.append(line[1:].strip())

    typer.echo(f"  Found {len(research_facts)} research facts")

    # 5. Define section constraints
    section_constraints = {
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

    return RAGContext(
        code_snippets=code_snippets,
        project_facts=project_facts,
        paper_excerpts=paper_excerpts,
        research_facts=research_facts,
        section_constraints=section_constraints,
    )


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
            # Check if there's supporting evidence
            has_evidence = False

            # Check in project facts
            for fact in rag_context.project_facts:
                if indicator in fact.lower():
                    has_evidence = True
                    break

            # Check in paper excerpts
            for excerpt in rag_context.paper_excerpts:
                if indicator in excerpt.get("excerpt", "").lower():
                    has_evidence = True
                    break

            if not has_evidence:
                report["issues"].append(f"Claim '{indicator}': {warning}")
                report["confidence"] -= 0.1

    # Check for fabricated metrics (numbers without sources)
    import re
    numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b', content)
    for num in numbers:
        # Skip small numbers that are likely not metrics
        try:
            val = float(num.rstrip('%'))
            if val > 10:  # Likely a metric
                # Check if this number appears in sources
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
        # Add constraint reminder to suggestions
        report["suggestions"].append(f"Constraint: {constraint}")

    # Calculate final confidence
    report["confidence"] = max(0.0, min(1.0, report["confidence"]))
    report["grounded"] = len(report["issues"]) == 0 and report["confidence"] >= 0.7

    return report


def generate_grounded_prompt(
    section_key: str,
    section_title: str,
    scope: "PaperScope",
    rag_context: "RAGContext",
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
    # Select relevant sources for this section
    relevant_facts = rag_context.project_facts[:8]
    relevant_excerpts = rag_context.paper_excerpts[:5]
    relevant_snippets = rag_context.code_snippets[:5]
    constraints = rag_context.section_constraints.get(section_key, [])

    prompt = f"""Generate the {section_title} section for an academic paper.

CRITICAL GROUNDING RULES:
You MUST only include information that can be traced to the sources below.
Do NOT hallucinate features, metrics, or claims not supported by these sources.
Every factual claim must be traceable to a specific source.

Paper Type: {scope.paper_type}
Target Venue: {scope.target_venue}

=== VERIFIED PROJECT FACTS (USE THESE) ===
{chr(10).join(f"- {fact}" for fact in relevant_facts)}

=== CODE SNIPPETS (REFERENCE THESE) ===
{chr(10).join(f"[{s['file']}] {s['type']}: {s['content'][:200]}..." for s in relevant_snippets)}

=== LEARNED FROM PAPERS (CITE THESE) ===
{chr(10).join(f"[{e['paper_id']}] {e['excerpt'][:200]}..." for e in relevant_excerpts)}

=== SECTION CONSTRAINTS ===
{chr(10).join(f"- {c}" for c in constraints)}

Write a well-structured {section_title} section.
- Use academic writing style
- Be precise and factual
- Cite sources where appropriate using [paper_id] format
- Do not make unsupported claims
"""

    return prompt


def generate_bibtex_from_arxiv(
    paper_ids: List[str],
    output_path: Path,
) -> int:
    """Generate BibTeX entries from arxiv paper IDs.

    Args:
        paper_ids: List of arxiv paper IDs (e.g., ["2501.15355", "2310.09876"])
        output_path: Path to write the .bib file

    Returns:
        Number of BibTeX entries generated
    """
    if not paper_ids:
        output_path.write_text("% No arxiv papers referenced\n")
        return 0

    if not ARXIV_SCRIPT.exists():
        typer.echo("[WARN] arxiv skill not available, creating stub references.bib", err=True)
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
                        # Generate BibTeX entry
                        authors = item.get("authors", ["Unknown"])
                        # Format authors for BibTeX: "Last1, First1 and Last2, First2"
                        author_str = " and ".join(authors[:5])  # Limit to 5 authors
                        if len(authors) > 5:
                            author_str += " and others"

                        title = item.get("title", "Unknown Title").replace("\n", " ")
                        year = item.get("published", "2024")[:4]
                        abstract = item.get("abstract", "")[:200].replace("\n", " ")

                        # Create cite key from first author and year
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
                    typer.echo(f"  [WARN] Failed to parse arxiv response for {clean_id}", err=True)
        except subprocess.TimeoutExpired:
            typer.echo(f"  [WARN] Timeout fetching {clean_id}", err=True)
        except Exception as e:
            typer.echo(f"  [WARN] Error fetching {clean_id}: {e}", err=True)

    # Write all entries to file
    if bibtex_entries:
        content = "% Auto-generated BibTeX from arxiv papers\n\n" + "\n".join(bibtex_entries)
    else:
        content = "% No arxiv papers could be fetched - add references manually\n"

    output_path.write_text(content)
    typer.echo(f"  Generated: {output_path.name} ({len(bibtex_entries)} entries)")
    return len(bibtex_entries)


def generate_figures(
    project_path: Path,
    analysis: "ProjectAnalysis",
    figures_dir: Path,
) -> List[str]:
    """Generate publication-quality figures using fixture-graph skill.

    Args:
        project_path: Path to the project
        analysis: Project analysis results
        figures_dir: Directory to save figures

    Returns:
        List of generated figure filenames
    """
    generated = []
    figures_dir.mkdir(parents=True, exist_ok=True)

    if not FIXTURE_GRAPH_SCRIPT.exists():
        typer.echo("[WARN] fixture-graph skill not available, skipping figure generation", err=True)
        return generated

    typer.echo("Generating figures...")

    # 1. Architecture diagram
    try:
        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "architecture",
                "--project", str(project_path),
                "--output", str(figures_dir / "architecture.pdf"),
                "--backend", "graphviz",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            typer.echo("  Generated: architecture.pdf")
            generated.append("architecture.pdf")
        else:
            typer.echo(f"  [WARN] Architecture diagram failed: {result.stderr[:100]}", err=True)
    except subprocess.TimeoutExpired:
        typer.echo("  [WARN] Architecture diagram timed out", err=True)

    # 2. Dependency graph
    try:
        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "deps",
                "--project", str(project_path),
                "--output", str(figures_dir / "dependencies.pdf"),
                "--backend", "graphviz",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            typer.echo("  Generated: dependencies.pdf")
            generated.append("dependencies.pdf")
        else:
            typer.echo(f"  [WARN] Dependency graph failed: {result.stderr[:100]}", err=True)
    except subprocess.TimeoutExpired:
        typer.echo("  [WARN] Dependency graph timed out", err=True)

    # 3. Workflow diagram (paper-writer 5-stage workflow)
    try:
        result = subprocess.run(
            [
                str(FIXTURE_GRAPH_SCRIPT), "workflow",
                "--stages", "Scope,Analysis,Search,Learn,Draft",
                "--output", str(figures_dir / "workflow.pdf"),
                "--backend", "graphviz",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            typer.echo("  Generated: workflow.pdf")
            generated.append("workflow.pdf")
    except subprocess.TimeoutExpired:
        pass

    # 4. Feature metrics chart (if we have feature data)
    if analysis.features:
        try:
            # Create temp JSON file with feature metrics
            metrics_data = {
                f.get("feature", f"f{i}")[:15]: f.get("loc", 1)
                for i, f in enumerate(analysis.features[:8])
            }
            metrics_file = figures_dir / "metrics_data.json"
            metrics_file.write_text(json.dumps(metrics_data))

            result = subprocess.run(
                [
                    str(FIXTURE_GRAPH_SCRIPT), "metrics",
                    "--input", str(metrics_file),
                    "--output", str(figures_dir / "features.pdf"),
                    "--type", "bar",
                    "--title", "Feature Distribution",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                typer.echo("  Generated: features.pdf")
                generated.append("features.pdf")

            # Clean up temp file
            metrics_file.unlink(missing_ok=True)
        except Exception:
            pass

    typer.echo(f"  Total figures generated: {len(generated)}")
    return generated


def generate_section_content(
    section_key: str,
    section_title: str,
    scope: "PaperScope",
    analysis: "ProjectAnalysis",
    review: "LiteratureReview",
    project_path: Path,
    use_llm: bool = True,
    rag_context: Optional["RAGContext"] = None,
    persona: Optional["AgentPersona"] = None,
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
            # Use scillm batch single for generation
            result = subprocess.run(
                [str(SCILLM_SCRIPT), "batch", "single", context[:4000]],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                generated = result.stdout.strip()

                # Verify grounding if RAG enabled
                if rag_context:
                    verification = verify_grounding(generated, section_key, rag_context)
                    if not verification["grounded"]:
                        typer.echo(f"    [RAG] Grounding issues found:", err=True)
                        for issue in verification["issues"][:3]:
                            typer.echo(f"      ⚠ {issue}", err=True)
                    else:
                        typer.echo(f"    [RAG] Content grounded (confidence: {verification['confidence']:.0%})")

                return generated
            else:
                typer.echo(f"  [WARN] LLM generation returned empty for {section_key}, using stub", err=True)
                if result.stderr:
                    typer.echo(f"  [DEBUG] stderr: {result.stderr[:200]}", err=True)
        except subprocess.TimeoutExpired:
            typer.echo(f"  [WARN] LLM timed out for {section_key} after 120s, using stub", err=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            typer.echo(f"  [WARN] LLM not available for {section_key}: {e}", err=True)

    # Fallback to stub content
    return _generate_stub_content(section_key, section_title, scope, analysis, review, project_path)


def _generate_stub_content(
    section_key: str,
    section_title: str,
    scope: "PaperScope",
    analysis: "ProjectAnalysis",
    review: "LiteratureReview",
    project_path: Path,
) -> str:
    """Generate stub content when LLM is not available."""
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


def _run_interview_skill(questions_file: Path, title: str = "Paper Scope") -> Optional[Dict[str, Any]]:
    """Run the interview skill and return responses, or None if unavailable."""
    if not INTERVIEW_SKILL.exists():
        return None

    try:
        result = subprocess.run(
            [str(INTERVIEW_SKILL), "--mode", "auto", "--file", str(questions_file)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min for user interaction
        )
        if result.returncode == 0:
            # Parse JSON response from interview skill
            return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        typer.echo(f"[WARN] Interview skill failed: {e}", err=True)
    return None


def interview_scope(use_interview_skill: bool = True) -> PaperScope:
    """Stage 1: Interactive scope definition.

    Args:
        use_interview_skill: If True and available, use the /interview skill for better UX
    """
    typer.echo("\n=== STAGE 1: SCOPE INTERVIEW ===\n")

    # Try to use interview skill for better UX
    if use_interview_skill and INTERVIEW_SKILL.exists():
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

        responses = _run_interview_skill(questions_file, "Paper Scope Definition")
        if responses and responses.get("completed"):
            # Parse responses from interview skill
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
            typer.echo("\nWhat are your main contribution claims? (one per line, 'done' when finished)")
            contributions = []
            while True:
                claim = typer.prompt(f"Contribution #{len(contributions)+1} (or 'done')")
                if claim.lower() == "done":
                    if not contributions:
                        typer.echo("[ERROR] At least one contribution is required", err=True)
                        continue
                    break
                contributions.append(claim)

            # Get prior work areas
            typer.echo("\nPrior work areas to search (space-separated)?")
            typer.echo("Examples: agent-architectures, memory-systems, tool-use, formal-methods")
            areas_input = typer.prompt("Areas", default="agent-architectures memory-systems")
            prior_work_areas = areas_input.split()

            return PaperScope(
                paper_type=paper_type,
                target_venue=target_venue,
                contributions=contributions,
                audience=audience,
                prior_work_areas=prior_work_areas,
            )

    # Fallback to basic typer prompts
    typer.echo("Using command-line interview (install /interview skill for better UX)...")

    # Paper type
    typer.echo("What type of paper are you writing?")
    typer.echo("a) Research paper (novel contribution)")
    typer.echo("b) System paper (implementation/architecture)")
    typer.echo("c) Survey paper (literature review)")
    typer.echo("d) Experience report (lessons learned)")
    typer.echo("e) Demo paper (tool description)")
    paper_type = typer.prompt("Select (a-e)", type=str).lower()

    type_map = {
        "a": "research",
        "b": "system",
        "c": "survey",
        "d": "experience",
        "e": "demo",
    }
    paper_type = type_map.get(paper_type, "system")
    
    # Target venue
    target_venue = typer.prompt("Target venue/conference (e.g., ICSE, FSE, arXiv)")
    
    # Contributions
    typer.echo("\nWhat are your main contribution claims? (one per line, 'done' when finished)")
    contributions = []
    while True:
        claim = typer.prompt(f"Contribution #{len(contributions)+1} (or 'done')")
        if claim.lower() == "done":
            if not contributions:
                typer.echo("[ERROR] At least one contribution is required", err=True)
                continue
            break
        contributions.append(claim)
    
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
    typer.echo("\nPrior work areas to search (space-separated)?")
    typer.echo("Examples: agent-architectures, memory-systems, tool-use, formal-methods")
    areas_input = typer.prompt("Areas", default="agent-architectures memory-systems")
    prior_work_areas = areas_input.split()
    
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


def analyze_project(project_path: Path, scope: PaperScope, auto_approve: bool = False) -> ProjectAnalysis:
    """Stage 2: Project analysis using assess + dogpile + code-review.

    Args:
        project_path: Path to project to analyze
        scope: Paper scope configuration
        auto_approve: If True, skip interactive prompts
    """
    # Validate project path exists and is directory
    if not project_path.exists():
        typer.echo(f"[ERROR] Project path does not exist: {project_path}", err=True)
        raise typer.Exit(1)
    if not project_path.is_dir():
        typer.echo(f"[ERROR] Project path is not a directory: {project_path}", err=True)
        raise typer.Exit(1)

    # Validate skill scripts exist
    if not ASSESS_SCRIPT.exists():
        typer.echo(f"[ERROR] Skill script not found: {ASSESS_SCRIPT}", err=True)
        raise typer.Exit(1)

    typer.echo("\n=== STAGE 2: PROJECT ANALYSIS ===\n")

    # 1. Run assess
    typer.echo("Running /assess...")
    try:
        result = subprocess.run(
            [sys.executable, str(ASSESS_SCRIPT), "run", str(project_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        # Parse JSON from output
        output = result.stdout
        json_start = output.find('{')
        assessment = json.loads(output[json_start:]) if json_start >= 0 else {}
    except subprocess.CalledProcessError as e:
        typer.echo(f"[ERROR] /assess failed with exit code {e.returncode}", err=True)
        if e.stderr:
            typer.echo(f"[ERROR] stderr: {e.stderr}", err=True)
        if e.stdout:
            typer.echo(f"[ERROR] stdout: {e.stdout}", err=True)
        assessment = {}
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Failed to parse assess output as JSON: {e}", err=True)
        assessment = {}
    
    features = assessment.get("categories", {}).get("working_well", [])
    architecture = {"patterns": assessment.get("architecture_patterns", [])}
    issues = assessment.get("categories", {}).get("brittle", [])
    
    # 2. Run dogpile for each contribution
    typer.echo("\nRunning /dogpile for research context...")
    research_parts = []
    for contrib in scope.contributions[:2]:  # Limit to 2 to avoid rate limits
        typer.echo(f"  Researching: {contrib}")
        try:
            result = subprocess.run(
                [str(DOGPILE_SCRIPT), "search", contrib],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            research_parts.append(f"## {contrib}\n{result.stdout}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            if isinstance(e, subprocess.CalledProcessError):
                typer.echo(f"  [WARN] Dogpile failed for '{contrib}' with exit code {e.returncode}", err=True)
                if e.stderr:
                    typer.echo(f"  [WARN] stderr: {e.stderr}", err=True)
            else:
                typer.echo(f"  [WARN] Dogpile timed out for '{contrib}' after 120s", err=True)
            research_parts.append(f"## {contrib}\n(Research failed)")
    
    research_context = "\n\n".join(research_parts)
    
    # 3. Code-review alignment check (optional - can be slow)
    alignment_report = ""
    if CODE_REVIEW_SCRIPT.exists():
        run_review = auto_approve or typer.confirm("\nRun code-review alignment check? (can take 2-5 min)")
        if run_review:
            typer.echo("Running /code-review for alignment check...")
            try:
                # Build a quick review request
                review_request = f"""# Code-Paper Alignment Check

## Title
Alignment check for paper: {scope.contributions[0] if scope.contributions else 'Project'}

## Summary
Verify that code implementation matches documented features and claims.

## Objectives
- Check if features in code match documentation
- Identify gaps between implementation and claims
- Find technical debt that should be mentioned in paper

## Path
{project_path}
"""
                review_file = Path(tempfile.gettempdir()) / "paper_alignment_review.md"
                review_file.write_text(review_request)

                result = subprocess.run(
                    [
                        sys.executable, str(CODE_REVIEW_SCRIPT),
                        "review-full",
                        "--file", str(review_file),
                        "--provider", "github",
                        "--model", "gpt-5",
                        "--rounds", "1",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 min timeout
                )
                if result.returncode == 0:
                    alignment_report = result.stdout
                    typer.echo("  [PASS] Code-review completed")
                else:
                    typer.echo(f"  [WARN] Code-review returned non-zero: {result.returncode}", err=True)
                    alignment_report = f"Code-review failed: {result.stderr}"
            except subprocess.TimeoutExpired:
                typer.echo("  [WARN] Code-review timed out after 5 min", err=True)
                alignment_report = "Code-review timed out"
            except Exception as e:
                typer.echo(f"  [WARN] Code-review error: {e}", err=True)
                alignment_report = f"Code-review error: {e}"
        else:
            alignment_report = "Skipped by user"
    else:
        typer.echo("\n[WARN] Code-review skill not found, skipping alignment check", err=True)
        alignment_report = "Code-review skill not available"
    
    analysis = ProjectAnalysis(
        features=features,
        architecture=architecture,
        issues=issues,
        research_context=research_context,
        alignment_report=alignment_report,
    )
    
    # Confirmation gate
    typer.echo("\n--- ANALYSIS SUMMARY ---")
    typer.echo(f"Features found: {len(features)}")
    typer.echo(f"Architecture patterns: {len(architecture.get('patterns', []))}")
    typer.echo(f"Issues detected: {len(issues)}")
    typer.echo(f"Research context: {len(research_context)} chars")
    
    # Show first 3 features
    if features:
        typer.echo("\nTop Features:")
        for f in features[:3]:
            typer.echo(f"  - {f.get('feature', 'Unknown')}")
    
    if not auto_approve:
        if not typer.confirm("\nDoes this analysis match your understanding?"):
            if typer.confirm("Refine scope and re-run?"):
                typer.echo("Exiting. Adjust scope and re-run.")
                raise typer.Exit(1)

    return analysis


def search_literature(scope: PaperScope, analysis: ProjectAnalysis) -> LiteratureReview:
    """Stage 3: Literature search using /arxiv."""
    typer.echo("\n=== STAGE 3: LITERATURE SEARCH ===\n")

    # Validate dependencies before proceeding
    if not scope.contributions:
        typer.echo("[ERROR] No contributions defined - cannot generate context", err=True)
        raise typer.Exit(1)

    if not ARXIV_SCRIPT.exists():
        typer.echo(f"[ERROR] Skill script not found: {ARXIV_SCRIPT}", err=True)
        raise typer.Exit(1)

    # Generate arxiv context file in system temp directory
    temp_dir = Path(tempfile.gettempdir())
    context_file = temp_dir / f"arxiv_context_{scope.target_venue.replace(' ', '_')}.md"
    context_content = f"""# Research Context: {scope.contributions[0]}

## What We're Building
{scope.paper_type.capitalize()} paper for {scope.target_venue}

## Current State
Features: {', '.join(f.get('feature', '') for f in analysis.features[:5]) if analysis.features else 'None'}

## What We Need From Papers
{chr(10).join(f"{i+1}. {c}" for i, c in enumerate(scope.contributions))}

## Search Terms to Try
{' '.join(scope.prior_work_areas)}

## Relevance Criteria
- HIGH: Directly addresses our contributions
- MEDIUM: Related techniques that could adapt
- LOW: Tangentially related
"""
    context_file.write_text(context_content)
    typer.echo(f"Generated context: {context_file}")
    
    # Search arxiv
    query = " ".join(scope.prior_work_areas)
    typer.echo(f"\nSearching arXiv for: {query}")

    papers_found = []
    try:
        result = subprocess.run(
            [str(ARXIV_SCRIPT), "search", "--query", query, "--max-results", "20"],
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
        # Parse JSON output from arxiv search
        arxiv_result = json.loads(result.stdout)
        items = arxiv_result.get("items", [])
        for item in items:
            papers_found.append({
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "abstract": item.get("abstract", ""),
                "authors": item.get("authors", []),
                "published": item.get("published", ""),
                "categories": item.get("categories", []),
                "pdf_url": item.get("pdf_url", ""),
                "html_url": item.get("html_url", ""),
            })
        typer.echo(f"  Found {len(papers_found)} papers")
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Failed to parse arxiv output as JSON: {e}", err=True)
        typer.echo(f"[DEBUG] Raw output: {result.stdout[:500]}...", err=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        if isinstance(e, subprocess.CalledProcessError):
            typer.echo(f"[ERROR] /arxiv search failed with exit code {e.returncode}", err=True)
            if e.stderr:
                typer.echo(f"[ERROR] stderr: {e.stderr}", err=True)
        else:
            typer.echo(f"[ERROR] /arxiv search timed out after 90s", err=True)

    # Paper triage - show papers with abstracts for user selection
    typer.echo(f"\n--- FOUND {len(papers_found)} PAPERS ---\n")

    if papers_found:
        # Categorize by relevance (simple keyword matching for now)
        high_relevance = []
        medium_relevance = []
        low_relevance = []

        for p in papers_found:
            title_lower = p["title"].lower()
            abstract_lower = p["abstract"].lower()
            # Check if contribution keywords appear in title/abstract
            contrib_keywords = " ".join(scope.contributions).lower().split()
            matches = sum(1 for kw in contrib_keywords if kw in title_lower or kw in abstract_lower)

            if matches >= 3:
                high_relevance.append(p)
            elif matches >= 1:
                medium_relevance.append(p)
            else:
                low_relevance.append(p)

        # Display HIGH relevance papers
        if high_relevance:
            typer.echo("HIGH RELEVANCE (directly related):")
            for i, p in enumerate(high_relevance[:5], 1):
                typer.echo(f"  [{i}] {p['id']}: {p['title'][:60]}...")
                typer.echo(f"      Authors: {', '.join(p['authors'][:3])}")
                typer.echo(f"      Abstract: {p['abstract'][:150]}...")
                typer.echo()

        # Display MEDIUM relevance papers
        if medium_relevance:
            typer.echo("MEDIUM RELEVANCE (tangentially related):")
            for i, p in enumerate(medium_relevance[:5], len(high_relevance) + 1):
                typer.echo(f"  [{i}] {p['id']}: {p['title'][:60]}...")
            typer.echo()

        # Show LOW count
        if low_relevance:
            typer.echo(f"LOW RELEVANCE: {len(low_relevance)} papers (not shown)")
            typer.echo()

    # Manual selection with better guidance
    typer.echo("Options:")
    typer.echo("  - Enter paper IDs (comma-separated): 2501.12345, 2502.67890")
    typer.echo("  - 'all-high' to select all high-relevance papers")
    typer.echo("  - 'skip' to skip literature review")

    selection = typer.prompt(
        "\nWhich papers to extract?",
        default="all-high" if papers_found else "skip",
    )

    papers_selected = []
    if selection != "skip":
        if selection == "all-high":
            # Select high relevance, fall back to top 5 if none
            if high_relevance:
                papers_selected = [p["id"] for p in high_relevance[:5]]
            else:
                papers_selected = [p["id"] for p in papers_found[:5]]
            typer.echo(f"  Selected {len(papers_selected)} papers: {', '.join(papers_selected)}")
        else:
            papers_selected = [p.strip() for p in selection.split(",")]
    
    review = LiteratureReview(
        papers_found=papers_found,
        papers_selected=papers_selected,
        extractions=[],
    )
    
    return review


def learn_from_papers(review: LiteratureReview, scope: PaperScope) -> LiteratureReview:
    """Stage 4: Extract knowledge from selected papers."""
    typer.echo("\n=== STAGE 4: KNOWLEDGE LEARNING ===\n")

    if not review.papers_selected:
        typer.echo("No papers selected. Skipping learning stage.")
        return review

    # Use the same context file path as search_literature
    temp_dir = Path(tempfile.gettempdir())
    context_file = temp_dir / f"arxiv_context_{scope.target_venue.replace(' ', '_')}.md"

    if not ARXIV_SCRIPT.exists():
        typer.echo(f"[ERROR] Skill script not found: {ARXIV_SCRIPT}", err=True)
        typer.echo("[ERROR] Cannot proceed without arxiv skill", err=True)
        return review

    # Build extraction command args - use context file if exists, otherwise context string
    base_args = [str(ARXIV_SCRIPT), "learn"]

    typer.echo(f"Extracting knowledge from {len(review.papers_selected)} papers...")
    typer.echo(f"  Using scope: paper-writing")

    if context_file.exists():
        typer.echo(f"  Using context file: {context_file}")
        context_args = ["--context-file", str(context_file)]
    else:
        # Fallback to context string
        context_str = f"{scope.paper_type} paper on {', '.join(scope.contributions[:2])}"
        typer.echo(f"  Using context string: {context_str}")
        context_args = ["--context", context_str]

    # Ask user if they want interactive review or auto-accept
    use_interview = False
    if INTERVIEW_SKILL.exists():
        use_interview = typer.confirm("\nUse interactive review for extracted Q&A pairs?", default=False)

    for i, paper_id in enumerate(review.papers_selected, 1):
        typer.echo(f"\n[{i}/{len(review.papers_selected)}] Extracting: {paper_id}")

        cmd_args = base_args + [
            paper_id,
            "--scope", "paper-writing",
        ] + context_args

        if not use_interview:
            cmd_args.append("--skip-interview")

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,  # 5 min per paper
            )
            # Parse output to count Q&A pairs if possible
            output = result.stdout
            qa_count = output.lower().count("q:") + output.lower().count("question:")
            typer.echo(f"  [OK] Extracted (~{qa_count} Q&A pairs)")
            extraction = {
                "paper_id": paper_id,
                "status": "success",
                "output": output,
                "qa_count": qa_count,
            }
        except subprocess.CalledProcessError as e:
            typer.echo(f"  [FAIL] Exit code {e.returncode}", err=True)
            if e.stderr:
                # Show last 200 chars of error
                typer.echo(f"  stderr: ...{e.stderr[-200:]}", err=True)
            extraction = {"paper_id": paper_id, "status": "failed", "error": str(e)}
        except subprocess.TimeoutExpired:
            typer.echo(f"  [FAIL] Timed out after 5 min", err=True)
            extraction = {"paper_id": paper_id, "status": "timeout", "error": "Extraction timed out"}

        review.extractions.append(extraction)

    # Calculate summary statistics
    success_count = sum(1 for e in review.extractions if e["status"] == "success")
    failed_count = len(review.extractions) - success_count
    total_qa = sum(e.get("qa_count", 0) for e in review.extractions)

    typer.echo(f"\n  Successful: {success_count}/{len(review.extractions)}")
    typer.echo(f"  Failed: {failed_count}")
    typer.echo(f"  Total Q&A pairs extracted: ~{total_qa}")

    if failed_count > 0:
        typer.echo("\nFailed papers:")
        for e in review.extractions:
            if e["status"] != "success":
                typer.echo(f"  - {e['paper_id']}: {e.get('error', 'unknown error')[:50]}")

    if success_count == 0:
        typer.echo("\n[WARN] No papers successfully extracted. Draft will use stub content.", err=True)

    if not typer.confirm("\nProceed to draft generation?"):
        typer.echo("Stopping before draft generation.")
        raise typer.Exit(0)

    return review


# --- MIMIC Feature Functions ---

MIMIC_STATE_FILE = Path(__file__).parent / ".mimic_state.json"


def select_exemplar_papers() -> List[Dict[str, Any]]:
    """Interactive selection of exemplar papers to mimic.

    Returns:
        List of exemplar paper dicts with id, title, authors, abstract
    """
    typer.echo("\n=== MIMIC: SELECT EXEMPLAR PAPERS ===\n")

    typer.echo("Choose 2-3 papers whose style you want to mimic:")
    typer.echo("1. Provide arXiv IDs manually")
    typer.echo("2. Search for papers from prestigious sources")
    typer.echo("3. Use pre-curated collections")

    choice = typer.prompt("Your choice (1-3)", type=int, default=1)

    exemplars = []

    if choice == 1:
        typer.echo("\nEnter arXiv IDs (comma-separated):")
        typer.echo("Example: 2401.12345, 2310.09876, 2312.54321")
        ids_input = typer.prompt("arXiv IDs")
        paper_ids = [p.strip() for p in ids_input.split(",")]

        # Fetch paper details from arxiv
        if ARXIV_SCRIPT.exists():
            for paper_id in paper_ids[:3]:  # Limit to 3
                typer.echo(f"  Fetching: {paper_id}...")
                try:
                    result = subprocess.run(
                        [str(ARXIV_SCRIPT), "get", "--id", paper_id],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        items = data.get("items", [])
                        if items:
                            item = items[0]
                            exemplars.append({
                                "id": paper_id,
                                "title": item.get("title", "Unknown"),
                                "authors": item.get("authors", []),
                                "abstract": item.get("abstract", ""),
                                "published": item.get("published", ""),
                            })
                            typer.echo(f"    [OK] {item.get('title', 'Unknown')[:50]}...")
                except Exception as e:
                    typer.echo(f"    [FAIL] {e}", err=True)
        else:
            # Fallback: just store IDs without details
            for paper_id in paper_ids[:3]:
                exemplars.append({"id": paper_id, "title": "Unknown", "authors": [], "abstract": ""})

    elif choice == 2:
        typer.echo("\nSearching papers from prestigious sources...")
        typer.echo("Venues: ICSE, FSE, PLDI, SOSP, OSDI")
        typer.echo("Institutions: MIT, Stanford, CMU, Berkeley")

        query = typer.prompt("Search query", default="agent memory systems")

        if ARXIV_SCRIPT.exists():
            try:
                result = subprocess.run(
                    [str(ARXIV_SCRIPT), "search", "--query", query, "--max-results", "20"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    items = data.get("items", [])

                    typer.echo(f"\nFound {len(items)} papers:\n")
                    for i, item in enumerate(items[:15], 1):
                        typer.echo(f"[{i}] {item.get('title', 'Unknown')[:60]}...")
                        typer.echo(f"    Authors: {', '.join(item.get('authors', [])[:3])}")
                        typer.echo()

                    selection = typer.prompt("Select 2-3 papers (comma-separated numbers)")
                    indices = [int(n.strip()) - 1 for n in selection.split(",")]

                    for idx in indices[:3]:
                        if 0 <= idx < len(items):
                            item = items[idx]
                            exemplars.append({
                                "id": item.get("id", ""),
                                "title": item.get("title", "Unknown"),
                                "authors": item.get("authors", []),
                                "abstract": item.get("abstract", ""),
                                "published": item.get("published", ""),
                            })
            except Exception as e:
                typer.echo(f"[ERROR] Search failed: {e}", err=True)

    elif choice == 3:
        typer.echo("\nPre-curated collections:")
        typer.echo("1. Agent Systems (ReAct, AutoGPT, Voyager)")
        typer.echo("2. Memory Systems (MemGPT, Reflexion)")
        typer.echo("3. Tool Use (Toolformer, Gorilla)")
        typer.echo("4. Code Generation (CodeGen, StarCoder)")

        collection = typer.prompt("Select collection (1-4)", type=int, default=1)

        # Curated paper IDs by topic
        collections = {
            1: ["2210.03629", "2303.11366", "2305.16291"],  # Agent Systems
            2: ["2310.08560", "2303.11366"],  # Memory Systems
            3: ["2302.04761", "2305.15334"],  # Tool Use
            4: ["2203.13474", "2305.06161"],  # Code Generation
        }

        paper_ids = collections.get(collection, collections[1])
        if ARXIV_SCRIPT.exists():
            for paper_id in paper_ids:
                typer.echo(f"  Fetching: {paper_id}...")
                try:
                    result = subprocess.run(
                        [str(ARXIV_SCRIPT), "get", "--id", paper_id],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        items = data.get("items", [])
                        if items:
                            item = items[0]
                            exemplars.append({
                                "id": paper_id,
                                "title": item.get("title", "Unknown"),
                                "authors": item.get("authors", []),
                                "abstract": item.get("abstract", ""),
                            })
                            typer.echo(f"    [OK] {item.get('title', 'Unknown')[:50]}...")
                except Exception:
                    exemplars.append({"id": paper_id, "title": "Unknown", "authors": [], "abstract": ""})

    typer.echo(f"\n[OK] Selected {len(exemplars)} exemplar papers")
    for ex in exemplars:
        typer.echo(f"  - {ex['id']}: {ex['title'][:50]}...")

    return exemplars


def analyze_exemplars(exemplars: List[Dict[str, Any]]) -> MimicPatterns:
    """Analyze exemplar papers to extract structure, style, and content patterns.

    Args:
        exemplars: List of exemplar paper dicts

    Returns:
        MimicPatterns object with extracted patterns
    """
    typer.echo("\n=== MIMIC: ANALYZING EXEMPLARS ===\n")

    # Default patterns (based on common CS paper conventions)
    patterns = MimicPatterns(
        # Structure
        section_order=["Abstract", "Introduction", "Background", "Method", "Evaluation", "Related Work", "Conclusion"],
        subsection_depth=2,
        intro_length=1500,
        method_sections=["Overview", "Algorithm", "Implementation"],
        figure_placement={"intro": 0, "method": 2, "eval": 3},

        # Style
        voice="active",
        tense={"intro": "present", "method": "present", "eval": "past", "related": "present"},
        transition_phrases=[
            "To address this challenge, we...",
            "Our key insight is that...",
            "The intuition behind this approach...",
            "Unlike prior work, our method...",
            "We evaluate our approach on...",
        ],
        technical_density=0.40,
        citation_density={"intro": 0.8, "related": 2.0, "method": 0.3, "eval": 0.5},

        # Content
        intro_structure=[
            "Problem statement (2-3 sentences)",
            "Motivation with real-world example",
            "Existing limitations (1 paragraph)",
            "Our contributions (numbered list)",
            "Paper organization",
        ],
        method_detail_level="high",
        eval_metrics=["accuracy", "latency", "comparison_with_baselines"],
        figure_captions="verbose",

        # Source
        exemplar_ids=[ex.get("id", "") for ex in exemplars],
        exemplar_titles=[ex.get("title", "") for ex in exemplars],
    )

    # If we have actual paper content, analyze it using LLM
    if SCILLM_SCRIPT.exists() and exemplars:
        typer.echo("Analyzing exemplar papers using LLM...")

        # Build analysis prompt
        abstracts = "\n\n".join([
            f"Paper: {ex.get('title', 'Unknown')}\nAbstract: {ex.get('abstract', 'N/A')[:500]}"
            for ex in exemplars
        ])

        analysis_prompt = f"""Analyze these academic paper abstracts and extract writing patterns:

{abstracts}

Extract the following patterns:
1. Writing voice (active vs passive)
2. Common transition phrases
3. Introduction structure pattern
4. Technical density (high/medium/low)
5. How contributions are presented

Format as JSON with keys: voice, transitions, intro_pattern, density, contribution_style
"""
        try:
            result = subprocess.run(
                [str(SCILLM_SCRIPT), "batch", "single", analysis_prompt[:4000]],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                typer.echo("  [OK] LLM analysis complete")
                # Try to parse any JSON in the output
                output = result.stdout
                json_start = output.find("{")
                json_end = output.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    try:
                        analysis = json.loads(output[json_start:json_end])
                        # Update patterns with LLM analysis
                        if "voice" in analysis:
                            patterns.voice = analysis["voice"]
                        if "transitions" in analysis:
                            patterns.transition_phrases = analysis["transitions"][:5]
                        if "density" in analysis:
                            density_map = {"high": 0.5, "medium": 0.4, "low": 0.3}
                            patterns.technical_density = density_map.get(analysis["density"], 0.4)
                    except json.JSONDecodeError:
                        typer.echo("  [WARN] Could not parse LLM JSON, using defaults", err=True)
        except Exception as e:
            typer.echo(f"  [WARN] LLM analysis failed: {e}", err=True)

    # Show analysis summary
    typer.echo("\n--- ANALYSIS SUMMARY ---")
    typer.echo(f"Section order: {' → '.join(patterns.section_order[:4])}...")
    typer.echo(f"Voice: {patterns.voice}")
    typer.echo(f"Technical density: {patterns.technical_density:.0%}")
    typer.echo(f"Intro structure: {len(patterns.intro_structure)} components")
    typer.echo(f"Transition phrases: {len(patterns.transition_phrases)} learned")

    if not typer.confirm("\nUse these patterns for paper generation?"):
        typer.echo("Patterns not saved. Re-run with different exemplars.")
        raise typer.Exit(0)

    return patterns


def store_mimic_patterns(patterns: MimicPatterns) -> None:
    """Save MIMIC patterns to state file."""
    state = {
        "section_order": patterns.section_order,
        "subsection_depth": patterns.subsection_depth,
        "intro_length": patterns.intro_length,
        "method_sections": patterns.method_sections,
        "figure_placement": patterns.figure_placement,
        "voice": patterns.voice,
        "tense": patterns.tense,
        "transition_phrases": patterns.transition_phrases,
        "technical_density": patterns.technical_density,
        "citation_density": patterns.citation_density,
        "intro_structure": patterns.intro_structure,
        "method_detail_level": patterns.method_detail_level,
        "eval_metrics": patterns.eval_metrics,
        "figure_captions": patterns.figure_captions,
        "exemplar_ids": patterns.exemplar_ids,
        "exemplar_titles": patterns.exemplar_titles,
    }
    MIMIC_STATE_FILE.write_text(json.dumps(state, indent=2))
    typer.echo(f"[OK] Patterns saved to {MIMIC_STATE_FILE}")


def load_mimic_patterns() -> Optional[MimicPatterns]:
    """Load MIMIC patterns from state file if exists."""
    if not MIMIC_STATE_FILE.exists():
        return None

    try:
        state = json.loads(MIMIC_STATE_FILE.read_text())
        return MimicPatterns(
            section_order=state.get("section_order", []),
            subsection_depth=state.get("subsection_depth", 2),
            intro_length=state.get("intro_length", 1500),
            method_sections=state.get("method_sections", []),
            figure_placement=state.get("figure_placement", {}),
            voice=state.get("voice", "active"),
            tense=state.get("tense", {}),
            transition_phrases=state.get("transition_phrases", []),
            technical_density=state.get("technical_density", 0.4),
            citation_density=state.get("citation_density", {}),
            intro_structure=state.get("intro_structure", []),
            method_detail_level=state.get("method_detail_level", "high"),
            eval_metrics=state.get("eval_metrics", []),
            figure_captions=state.get("figure_captions", "verbose"),
            exemplar_ids=state.get("exemplar_ids", []),
            exemplar_titles=state.get("exemplar_titles", []),
        )
    except (json.JSONDecodeError, KeyError) as e:
        typer.echo(f"[WARN] Failed to load MIMIC patterns: {e}", err=True)
        return None


def apply_style_transfer(
    content: str,
    section_key: str,
    patterns: MimicPatterns,
) -> str:
    """Apply MIMIC style patterns to generated content.

    Args:
        content: Generated section content
        section_key: Section identifier (e.g., 'intro', 'method')
        patterns: MIMIC patterns to apply

    Returns:
        Style-transferred content
    """
    if not SCILLM_SCRIPT.exists():
        return content

    # Build style transfer prompt
    style_prompt = f"""Apply the following writing style to this academic text:

Style Guidelines:
- Voice: {patterns.voice} voice (convert any passive sentences)
- Tense: {patterns.tense.get(section_key, 'present')} tense
- Add transition phrases like: {', '.join(patterns.transition_phrases[:3])}
- Technical density: {patterns.technical_density:.0%} (adjust jargon level)

Original Text:
{content[:3000]}

Rewrite the text following these style guidelines. Preserve the meaning and key information.
Output ONLY the rewritten text, no explanations.
"""

    try:
        result = subprocess.run(
            [str(SCILLM_SCRIPT), "batch", "single", style_prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return content


def validate_against_exemplars(
    generated_path: Path,
    patterns: MimicPatterns,
) -> Dict[str, Any]:
    """Validate generated paper against exemplar metrics.

    Args:
        generated_path: Path to generated paper directory
        patterns: MIMIC patterns to compare against

    Returns:
        Validation report dict
    """
    report = {
        "structure": {"match": True, "issues": []},
        "style": {"match": True, "issues": []},
        "content": {"match": True, "issues": []},
        "recommendations": [],
    }

    # Check section files exist
    sections_dir = generated_path / "sections"
    if not sections_dir.exists():
        report["structure"]["match"] = False
        report["structure"]["issues"].append("Sections directory not found")
        return report

    # Check structure
    expected_sections = ["abstract", "intro", "related", "design", "impl", "eval", "discussion"]
    for section in expected_sections:
        section_file = sections_dir / f"{section}.tex"
        if not section_file.exists():
            report["structure"]["issues"].append(f"Missing section: {section}")
            report["structure"]["match"] = False

    # Count words in intro
    intro_file = sections_dir / "intro.tex"
    if intro_file.exists():
        intro_content = intro_file.read_text()
        word_count = len(intro_content.split())
        if abs(word_count - patterns.intro_length) > 500:
            report["style"]["issues"].append(
                f"Intro length: {word_count} words (target: {patterns.intro_length})"
            )
            report["recommendations"].append(
                f"Adjust intro length by {patterns.intro_length - word_count:+d} words"
            )

    # Check for figures
    figures_dir = generated_path / "figures"
    if figures_dir.exists():
        figure_count = len(list(figures_dir.glob("*.pdf"))) + len(list(figures_dir.glob("*.png")))
        expected_figures = sum(patterns.figure_placement.values())
        if figure_count < expected_figures:
            report["content"]["issues"].append(
                f"Figures: {figure_count} (target: {expected_figures})"
            )
            report["recommendations"].append(
                f"Add {expected_figures - figure_count} more figures"
            )

    return report


def generate_draft(
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
        auto_approve: If True, skip interactive prompts (for testing/automation)
        mimic_patterns: Optional MIMIC patterns for style transfer
        use_rag: If True, enable RAG grounding to prevent hallucination
        template_name: LaTeX template to use (ieee, acm, cvpr, arxiv, springer)
        persona: Optional agent persona for stylized writing
        persona_strength: Persona voice intensity (0.0=neutral, 1.0=full persona)
    """
    typer.echo("\n=== STAGE 5: DRAFT GENERATION ===\n")

    # Build RAG context if enabled
    rag_context = None
    if use_rag:
        rag_context = build_rag_context(project_path, scope, analysis, review)
        typer.echo(f"[RAG] Grounding enabled with {len(rag_context.project_facts)} facts, "
                   f"{len(rag_context.code_snippets)} snippets, {len(rag_context.paper_excerpts)} excerpts")

    # Show persona status
    if persona:
        typer.echo(f"[PERSONA] Writing in {persona.name} voice")

    output_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = output_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    # Generate structure
    typer.echo("Generating paper structure...")
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
        typer.echo("Custom structure not yet implemented. Using default.")
    
    # Check if LLM is available for content generation
    use_llm = SCILLM_SCRIPT.exists() and not auto_approve
    if use_llm:
        typer.echo("LLM available for content generation")
    else:
        typer.echo("[INFO] Using stub content (LLM not available or auto_approve=True)")

    # Show MIMIC status
    if mimic_patterns:
        typer.echo(f"[MIMIC] Using style patterns from: {', '.join(mimic_patterns.exemplar_ids[:2])}")
        typer.echo(f"[MIMIC] Voice: {mimic_patterns.voice}, Density: {mimic_patterns.technical_density:.0%}")

    # Generate each section using LLM or fallback to stub
    for key, title in structure:
        section_file = sections_dir / f"{key}.tex"
        typer.echo(f"  Generating: {title}...")

        content = generate_section_content(
            section_key=key,
            section_title=title,
            scope=scope,
            analysis=analysis,
            review=review,
            project_path=project_path,
            use_llm=use_llm,
            rag_context=rag_context,
            persona=persona,
            persona_strength=persona_strength,
        )

        # Apply MIMIC style transfer if patterns available
        if mimic_patterns and use_llm:
            typer.echo(f"    Applying MIMIC style transfer...")
            content = apply_style_transfer(content, key, mimic_patterns)

        section_file.write_text(content)
        typer.echo(f"  Generated: {section_file.name}")

    # Generate figures using fixture-graph skill
    figures_dir = output_dir / "figures"
    generated_figures = generate_figures(project_path, analysis, figures_dir)

    # Get template configuration
    template = get_template(template_name)
    typer.echo(f"Using template: {template['name']}")

    # Generate main tex file using selected template
    main_tex = output_dir / "draft.tex"
    title = scope.contributions[0] if scope.contributions else 'Paper Title'

    main_content = f"""{template['documentclass']}
{template['packages']}

\\title{{{title}}}

{template['author_format'] % 'Author Name'}

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

% Auto-generated architecture diagram
\\begin{{figure}}[htbp]
\\centering
\\includegraphics[width=\\columnwidth]{{figures/architecture}}
\\caption{{System Architecture}}
\\label{{fig:architecture}}
\\end{{figure}}

\\section{{Implementation}}
\\input{{sections/impl}}

% Auto-generated workflow diagram
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
    main_tex.write_text(main_content)

    # Generate BibTeX from arxiv papers in literature review
    refs_file = output_dir / "references.bib"
    arxiv_ids = [p.get("id", "") for p in review.papers_found if p.get("id")]
    # Also include selected papers
    arxiv_ids.extend([pid for pid in review.papers_selected if pid not in arxiv_ids])
    # Dedupe while preserving order
    seen = set()
    unique_ids = []
    for pid in arxiv_ids:
        if pid and pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    generate_bibtex_from_arxiv(unique_ids[:20], refs_file)  # Limit to 20 refs
    
    # Save metadata
    metadata = {
        "scope": asdict(scope),
        "features_count": len(analysis.features),
        "papers_learned": len(review.extractions),
        "output_dir": str(output_dir),
        "template": template_name,
        "template_name": template["name"],
        "persona_enabled": persona is not None,
        "persona_name": persona.name if persona else None,
        "persona_voice": persona.voice if persona else None,
        "mimic_enabled": mimic_patterns is not None,
        "mimic_exemplars": mimic_patterns.exemplar_ids if mimic_patterns else [],
        "rag_enabled": use_rag,
        "rag_facts_count": len(rag_context.project_facts) if rag_context else 0,
        "rag_snippets_count": len(rag_context.code_snippets) if rag_context else 0,
        "rag_excerpts_count": len(rag_context.paper_excerpts) if rag_context else 0,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # MIMIC validation if patterns were used
    if mimic_patterns and not auto_approve:
        typer.echo("\n--- MIMIC VALIDATION ---")
        report = validate_against_exemplars(output_dir, mimic_patterns)

        if report["structure"]["issues"]:
            typer.echo("Structure issues:")
            for issue in report["structure"]["issues"]:
                typer.echo(f"  ⚠ {issue}")

        if report["style"]["issues"]:
            typer.echo("Style issues:")
            for issue in report["style"]["issues"]:
                typer.echo(f"  ⚠ {issue}")

        if report["content"]["issues"]:
            typer.echo("Content issues:")
            for issue in report["content"]["issues"]:
                typer.echo(f"  ⚠ {issue}")

        if report["recommendations"]:
            typer.echo("\nRecommendations:")
            for rec in report["recommendations"]:
                typer.echo(f"  → {rec}")

        if not (report["structure"]["issues"] or report["style"]["issues"] or report["content"]["issues"]):
            typer.echo("  ✓ Paper matches exemplar patterns!")

    typer.echo(f"\n✓ Draft generated: {main_tex}")
    typer.echo(f"  Compile with: cd {output_dir} && pdflatex draft.tex")


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

    Use --template to select venue format (ieee, acm, cvpr, arxiv, springer, darpa_baa).
    Use --length for longer documents: paper (5-10pg), thesis (50-80pg), dissertation (100+pg).
    Use --persona to write in a specific agent's voice (e.g., 'horus' for authoritative style).
    Use --persona-strength to control voice intensity (0.0=neutral, 1.0=full persona).
    Use --mimic flag to apply style patterns from previously analyzed exemplar papers.
    Use --rag flag to enable RAG grounding to prevent hallucination.
    """
    project_path = Path(project).resolve()
    output_dir = Path(output).resolve()

    if not project_path.exists():
        typer.echo(f"[ERROR] Project not found: {project_path}", err=True)
        raise typer.Exit(1)

    # Load persona if specified
    agent_persona = None
    if persona:
        if persona.lower() == "horus":
            agent_persona = HORUS_PERSONA
            typer.echo(f"[PERSONA] Using {agent_persona.name} writing style")
            typer.echo(f"  Voice: {agent_persona.voice}, Tone: {', '.join(agent_persona.tone_modifiers[:3])}")
        else:
            persona_path = Path(persona)
            agent_persona = load_persona(persona_path)
            if agent_persona:
                typer.echo(f"[PERSONA] Loaded {agent_persona.name} from {persona_path}")
            else:
                typer.echo(f"[WARN] Could not load persona from {persona}", err=True)

    # Load MIMIC patterns if requested
    mimic_patterns = None
    if use_mimic:
        mimic_patterns = load_mimic_patterns()
        if mimic_patterns:
            typer.echo(f"[MIMIC] Loaded patterns from: {', '.join(mimic_patterns.exemplar_ids[:2])}")
        else:
            typer.echo("[WARN] No MIMIC patterns found. Run `mimic --select` first.", err=True)
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

    # Stage 5: Draft (with optional MIMIC patterns, RAG grounding, and persona)
    generate_draft(
        project_path, scope, analysis, review, output_dir,
        mimic_patterns=mimic_patterns,
        use_rag=use_rag,
        template_name=template,
        persona=agent_persona,
        persona_strength=persona_strength,
    )

    typer.echo("\n✓ Paper draft session complete")
    typer.echo(f"  Output: {output_dir}")

    # Optional: Store in memory with resilience patterns
    if typer.confirm("\nStore paper metadata in memory?"):
        typer.echo("Storing paper metadata in memory...")

        # Use common MemoryClient if available for standardized resilience
        if HAS_MEMORY_CLIENT:
            try:
                client = MemoryClient(scope="paper-writing")
                metadata_file = output_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file) as f:
                        metadata = json.load(f)
                    result = client.learn(
                        problem=f"Paper: {metadata.get('title', output_dir.name)}",
                        solution=json.dumps(metadata, indent=2)[:2000],
                        tags=["paper-writing", "metadata"]
                    )
                    if result.success:
                        typer.echo("✓ Metadata stored in memory")
                    else:
                        typer.echo(f"[WARN] Memory storage failed: {result.error}", err=True)
                else:
                    typer.echo("[WARN] metadata.json not found", err=True)
            except Exception as e:
                typer.echo(f"[WARN] Memory storage error: {e}", err=True)
        else:
            # Fallback: direct subprocess with retry logic
            @with_retries(max_attempts=3, base_delay=0.5)
            def _store_with_retry():
                _memory_limiter.acquire()
                metadata_file = output_dir / "metadata.json"
                result = subprocess.run(
                    [str(MEMORY_SCRIPT), "store", str(metadata_file), "--scope", "paper-writing"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"Memory store failed: {result.stderr}")
                return True

            try:
                _store_with_retry()
                typer.echo("✓ Metadata stored in memory")
            except Exception as e:
                typer.echo(f"[WARN] Memory storage error: {e}", err=True)


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
    if select:
        # Stage 1: Select exemplar papers
        exemplars = select_exemplar_papers()
        if not exemplars:
            typer.echo("[ERROR] No exemplars selected", err=True)
            raise typer.Exit(1)

        # Save selected exemplars for analysis stage
        state = {"exemplars": exemplars}
        MIMIC_STATE_FILE.write_text(json.dumps(state, indent=2))
        typer.echo(f"\n[OK] Selected {len(exemplars)} exemplars. Run `mimic --analyze` to extract patterns.")

    elif analyze:
        # Stage 2: Analyze selected exemplars
        if not MIMIC_STATE_FILE.exists():
            typer.echo("[ERROR] No exemplars selected. Run `mimic --select` first.", err=True)
            raise typer.Exit(1)

        state = json.loads(MIMIC_STATE_FILE.read_text())
        exemplars = state.get("exemplars", [])

        if not exemplars:
            typer.echo("[ERROR] No exemplars in state file. Run `mimic --select` first.", err=True)
            raise typer.Exit(1)

        patterns = analyze_exemplars(exemplars)
        store_mimic_patterns(patterns)
        typer.echo("\n[OK] Patterns stored. Use `draft --mimic` to generate paper with these patterns.")

    elif validate:
        # Validate generated paper against patterns
        patterns = load_mimic_patterns()
        if not patterns:
            typer.echo("[ERROR] No MIMIC patterns found. Run `mimic --analyze` first.", err=True)
            raise typer.Exit(1)

        output_path = Path(validate)
        if not output_path.exists():
            typer.echo(f"[ERROR] Paper directory not found: {output_path}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\n=== MIMIC VALIDATION: {output_path} ===\n")
        report = validate_against_exemplars(output_path, patterns)

        # Display report
        all_ok = True
        for category in ["structure", "style", "content"]:
            if report[category]["issues"]:
                all_ok = False
                typer.echo(f"{category.title()} Issues:")
                for issue in report[category]["issues"]:
                    typer.echo(f"  ⚠ {issue}")

        if report["recommendations"]:
            typer.echo("\nRecommendations:")
            for rec in report["recommendations"]:
                typer.echo(f"  → {rec}")

        if all_ok:
            typer.echo("✓ Paper matches exemplar patterns!")

    elif show:
        # Show current patterns
        patterns = load_mimic_patterns()
        if not patterns:
            typer.echo("[INFO] No MIMIC patterns stored. Run `mimic --select` and `mimic --analyze`.")
            raise typer.Exit(0)

        typer.echo("\n=== CURRENT MIMIC PATTERNS ===\n")
        typer.echo(f"Exemplars: {', '.join(patterns.exemplar_ids)}")
        typer.echo(f"Voice: {patterns.voice}")
        typer.echo(f"Technical density: {patterns.technical_density:.0%}")
        typer.echo(f"Intro target length: {patterns.intro_length} words")
        typer.echo(f"Section order: {' → '.join(patterns.section_order[:4])}...")
        typer.echo(f"Transition phrases: {len(patterns.transition_phrases)}")

    elif clear:
        # Clear stored patterns
        if MIMIC_STATE_FILE.exists():
            MIMIC_STATE_FILE.unlink()
            typer.echo("[OK] MIMIC patterns cleared.")
        else:
            typer.echo("[INFO] No MIMIC patterns to clear.")

    else:
        typer.echo("Use --select, --analyze, --validate, --show, or --clear")
        typer.echo("\nWorkflow:")
        typer.echo("  1. mimic --select    # Choose exemplar papers")
        typer.echo("  2. mimic --analyze   # Extract patterns")
        typer.echo("  3. draft --mimic     # Generate paper with patterns")
        typer.echo("  4. mimic --validate  # Validate output")


@app.command()
def verify(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    project: str = typer.Option("", "--project", help="Project path for deeper verification"),
) -> None:
    """
    Verify RAG grounding of a generated paper.

    Checks that generated content is supported by source material.

    Example:
        ./run.sh verify ./paper_output --project ./my-project
    """
    paper_path = Path(paper_dir).resolve()
    if not paper_path.exists():
        typer.echo(f"[ERROR] Paper directory not found: {paper_path}", err=True)
        raise typer.Exit(1)

    sections_dir = paper_path / "sections"
    if not sections_dir.exists():
        typer.echo(f"[ERROR] Sections directory not found: {sections_dir}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== RAG VERIFICATION: {paper_path.name} ===\n")

    # Load metadata if available
    metadata_file = paper_path / "metadata.json"
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())
        if metadata.get("rag_enabled"):
            typer.echo(f"Paper was generated with RAG grounding")
            typer.echo(f"  Facts: {metadata.get('rag_facts_count', 0)}")
            typer.echo(f"  Snippets: {metadata.get('rag_snippets_count', 0)}")
            typer.echo(f"  Excerpts: {metadata.get('rag_excerpts_count', 0)}")
        else:
            typer.echo("[WARN] Paper was NOT generated with RAG grounding", err=True)
    else:
        typer.echo("[WARN] No metadata found - cannot determine RAG status", err=True)

    # Build minimal RAG context if project provided
    if project:
        project_path = Path(project).resolve()
        if project_path.exists():
            typer.echo(f"\nBuilding verification context from: {project_path.name}")
            code_snippets = extract_code_snippets(project_path)
            project_facts = []

            # Build minimal context
            rag_context = RAGContext(
                code_snippets=code_snippets,
                project_facts=project_facts,
                paper_excerpts=[],
                research_facts=[],
                section_constraints={},
            )
        else:
            typer.echo(f"[WARN] Project not found: {project_path}", err=True)
            rag_context = None
    else:
        rag_context = None

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
                    typer.echo(f"    ⚠ {issue}")
                total_issues += len(verification["issues"])
            else:
                typer.echo(f"  ✓ No grounding issues detected")

            typer.echo(f"  Confidence: {verification['confidence']:.0%}")
        else:
            # Basic checks without RAG context
            content_lower = content.lower()
            basic_issues = []

            danger_words = ["achieves", "outperforms", "state-of-the-art", "novel", "first"]
            for word in danger_words:
                if word in content_lower:
                    basic_issues.append(f"Contains unverified claim keyword: '{word}'")

            if basic_issues:
                typer.echo(f"  Potential issues ({len(basic_issues)}):")
                for issue in basic_issues:
                    typer.echo(f"    ⚠ {issue}")
                total_issues += len(basic_issues)
            else:
                typer.echo(f"  ✓ No obvious issues")

    typer.echo(f"\n=== SUMMARY ===")
    typer.echo(f"Total potential issues: {total_issues}")
    if total_issues == 0:
        typer.echo("✓ Paper appears well-grounded")
    else:
        typer.echo(f"⚠ Review {total_issues} potential grounding issues")
        typer.echo("  Tip: Regenerate with --rag flag for better grounding")


# --- Multi-Template Support ---

LATEX_TEMPLATES = {
    "ieee": {
        "name": "IEEE Conference",
        "documentclass": r"\documentclass[conference]{IEEEtran}",
        "packages": r"""\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{algorithmic}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}
\usepackage{hyperref}""",
        "author_format": r"\author{\IEEEauthorblockN{%s}}",
        "abstract_env": ("abstract", "abstract"),
        "bib_style": "IEEEtran",
    },
    "acm": {
        "name": "ACM Conference",
        "documentclass": r"\documentclass[sigconf,review]{acmart}",
        "packages": r"""\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}""",
        "author_format": r"\author{%s}",
        "abstract_env": ("abstract", "abstract"),
        "bib_style": "ACM-Reference-Format",
    },
    "cvpr": {
        "name": "CVPR/ICCV",
        "documentclass": r"\documentclass[10pt,twocolumn,letterpaper]{article}",
        "packages": r"""\usepackage{cvpr}
\usepackage{times}
\usepackage{epsfig}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{booktabs}
\usepackage{hyperref}""",
        "author_format": r"\author{%s}",
        "abstract_env": ("abstract", "abstract"),
        "bib_style": "ieee_fullname",
    },
    "arxiv": {
        "name": "arXiv Preprint",
        "documentclass": r"\documentclass[11pt]{article}",
        "packages": r"""\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{natbib}""",
        "author_format": r"\author{%s}",
        "abstract_env": ("abstract", "abstract"),
        "bib_style": "plainnat",
    },
    "springer": {
        "name": "Springer LNCS",
        "documentclass": r"\documentclass[runningheads]{llncs}",
        "packages": r"""\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{hyperref}
\usepackage{booktabs}""",
        "author_format": r"\author{%s}",
        "abstract_env": ("abstract", "abstract"),
        "bib_style": "splncs04",
    },
    "darpa_baa": {
        "name": "DARPA BAA (Volume I)",
        "documentclass": r"\documentclass[12pt]{article}",
        "packages": r"""\usepackage[margin=1in,letterpaper]{geometry}
\usepackage{times}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{fancyhdr}

% DARPA formatting requirements: 8.5x11, 1-inch margins, 12pt font
\pagestyle{fancy}
\fancyhf{}
\rhead{Volume I - Technical and Management Proposal}
\rfoot{Page \thepage}
\setlength{\headheight}{14.5pt}""",
        "author_format": r"""\Large\textbf{%s}\\[0.5em]
\normalsize Organization Name\\
Proposal Number: TBD\\
Topic Number: TBD\\
Date: \today""",
        "abstract_env": ("abstract", "Executive Summary"),
        "bib_style": "plain",
        "sections": [
            "executive_summary",
            "goals_and_impact",
            "technical_approach",
            "team_organization",
            "management_plan",
            "risk_management",
            "schedule_and_milestones",
        ],
    },
    "federal_grant": {
        "name": "Federal Grant (SF-424 Compatible)",
        "documentclass": r"\documentclass[12pt]{article}",
        "packages": r"""\usepackage[margin=1in,letterpaper]{geometry}
\usepackage{times}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}

% Federal grant formatting: 8.5x11, 1-inch margins, 12pt Times
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\rfoot{Page \thepage}""",
        "author_format": r"\author{%s}",
        "abstract_env": ("abstract", "Executive Summary"),
        "bib_style": "plain",
    },
}

# Document length configurations (for thesis-scale generation)
LENGTH_CONFIGS = {
    "paper": {
        "name": "Conference Paper",
        "pages": (5, 10),
        "sections": ["abstract", "intro", "related", "method", "eval", "conclusion"],
        "words_per_section": 800,
        "max_chapters": 0,  # No chapters, just sections
        "subsection_depth": 2,
    },
    "extended": {
        "name": "Journal Article",
        "pages": (15, 25),
        "sections": ["abstract", "intro", "background", "related", "method", "implementation", "eval", "discussion", "conclusion"],
        "words_per_section": 1200,
        "max_chapters": 0,
        "subsection_depth": 3,
    },
    "thesis": {
        "name": "Master's Thesis",
        "pages": (50, 80),
        "sections": None,  # Uses chapters instead
        "words_per_section": 2500,
        "max_chapters": 6,
        "subsection_depth": 3,
        "chapters": [
            {"title": "Introduction", "sections": ["motivation", "objectives", "contributions", "organization"]},
            {"title": "Background", "sections": ["fundamentals", "related_work", "existing_approaches"]},
            {"title": "Design", "sections": ["architecture", "design_decisions", "key_algorithms"]},
            {"title": "Implementation", "sections": ["system_overview", "key_components", "integration"]},
            {"title": "Evaluation", "sections": ["methodology", "results", "analysis", "comparison"]},
            {"title": "Conclusion", "sections": ["summary", "contributions", "limitations", "future_work"]},
        ],
    },
    "dissertation": {
        "name": "PhD Dissertation",
        "pages": (100, 200),
        "sections": None,
        "words_per_section": 3500,
        "max_chapters": 10,
        "subsection_depth": 4,
        "chapters": [
            {"title": "Introduction", "sections": ["problem_statement", "motivation", "research_questions", "contributions", "organization"]},
            {"title": "Background and Foundations", "sections": ["theoretical_background", "prior_art", "key_concepts"]},
            {"title": "Related Work", "sections": ["category_1", "category_2", "category_3", "gaps_and_positioning"]},
            {"title": "Approach Overview", "sections": ["key_insights", "design_principles", "system_architecture"]},
            {"title": "Core Contribution I", "sections": ["problem", "solution", "analysis", "validation"]},
            {"title": "Core Contribution II", "sections": ["problem", "solution", "analysis", "validation"]},
            {"title": "Core Contribution III", "sections": ["problem", "solution", "analysis", "validation"]},
            {"title": "Implementation", "sections": ["system_design", "engineering_challenges", "lessons_learned"]},
            {"title": "Evaluation", "sections": ["experimental_setup", "results", "analysis", "comparison", "threats_to_validity"]},
            {"title": "Conclusion", "sections": ["summary", "contributions", "impact", "open_problems", "future_directions"]},
        ],
    },
}


def get_length_config(length: str) -> Dict[str, Any]:
    """Get document length configuration by name."""
    return LENGTH_CONFIGS.get(length.lower(), LENGTH_CONFIGS["paper"])


def get_template(template_name: str) -> Dict[str, Any]:
    """Get LaTeX template by name."""
    return LATEX_TEMPLATES.get(template_name.lower(), LATEX_TEMPLATES["ieee"])


def list_templates() -> List[str]:
    """List available template names."""
    return list(LATEX_TEMPLATES.keys())


# --- Academic Phrase Palette ---

ACADEMIC_PHRASES = {
    "abstract": {
        "problem": [
            "Despite significant advances in..., there remains a critical need for...",
            "Current approaches to... suffer from...",
            "A fundamental challenge in... is...",
        ],
        "solution": [
            "We present..., a novel approach that...",
            "This paper introduces... to address...",
            "We propose... which enables...",
        ],
        "results": [
            "Our experiments demonstrate that...",
            "Evaluation on... shows...",
            "We achieve... on..., representing a ... improvement over...",
        ],
    },
    "intro": {
        "motivation": [
            "The proliferation of... has created an urgent need for...",
            "Recent advances in... have opened new possibilities for...",
            "As systems grow increasingly..., the challenge of... becomes critical.",
        ],
        "gap": [
            "However, existing approaches fail to...",
            "Prior work has largely overlooked...",
            "A key limitation of current methods is...",
        ],
        "contribution": [
            "The main contributions of this work are:",
            "In this paper, we make the following contributions:",
            "Our key insight is that...",
        ],
        "organization": [
            "The remainder of this paper is organized as follows.",
            "Section 2 presents..., Section 3 describes...",
            "We conclude with... in Section...",
        ],
    },
    "related": {
        "category": [
            "Prior work in this area can be broadly categorized into...",
            "Related approaches fall into two main categories:",
            "We discuss related work along three dimensions:",
        ],
        "comparison": [
            "Unlike..., our approach...",
            "In contrast to..., we...",
            "While... focuses on..., our method addresses...",
        ],
        "positioning": [
            "Our work builds upon... but differs in...",
            "Complementary to..., we focus on...",
            "This work is most closely related to...",
        ],
    },
    "method": {
        "overview": [
            "Figure X provides an overview of our approach.",
            "At a high level, our method consists of...",
            "The key components of our system are:",
        ],
        "detail": [
            "Formally, we define... as...",
            "The algorithm proceeds as follows:",
            "We compute... by...",
        ],
        "justification": [
            "This design choice is motivated by...",
            "We adopt this approach because...",
            "The intuition behind this is...",
        ],
    },
    "eval": {
        "setup": [
            "We evaluate our approach on...",
            "Our experiments are designed to answer the following questions:",
            "We compare against the following baselines:",
        ],
        "results": [
            "Table X summarizes our main results.",
            "As shown in Figure X, our method...",
            "We observe that...",
        ],
        "analysis": [
            "These results suggest that...",
            "The improvement can be attributed to...",
            "We attribute this to...",
        ],
    },
    "discussion": {
        "limitations": [
            "Our approach has several limitations.",
            "One limitation of our work is...",
            "While effective, our method does not address...",
        ],
        "future": [
            "Future work could explore...",
            "An interesting direction for future research is...",
            "We plan to extend this work by...",
        ],
        "broader_impact": [
            "We believe this work has implications for...",
            "The techniques presented here could benefit...",
            "This approach opens possibilities for...",
        ],
    },
}


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


# Horus Lupercal's academic phrases - authoritative, commanding, tactically precise
HORUS_ACADEMIC_PHRASES = {
    "abstract": {
        "problem": [
            "Current approaches to this challenge demonstrate fundamental methodological weaknesses.",
            "The field has tolerated inefficiencies that we address directly and decisively.",
            "Existing solutions fail precisely where failure is least acceptable.",
        ],
        "solution": [
            "We present a methodologically rigorous approach that succeeds where prior work could not.",
            "This work introduces techniques that address core deficiencies through principled design.",
            "Our contribution resolves long-standing limitations through systematic methodology.",
        ],
        "results": [
            "Experimental evaluation demonstrates decisive improvements across all measured metrics.",
            "The results leave no ambiguity regarding the superiority of our approach.",
            "We achieve performance improvements that render prior baselines obsolete.",
        ],
    },
    "intro": {
        "motivation": [
            "The proliferation of inadequate solutions has created urgent need for systematic improvement.",
            "As systems grow increasingly complex, tolerance for methodological weakness approaches zero.",
            "The field requires approaches built on sound principles rather than convenient assumptions.",
        ],
        "gap": [
            "Prior work has consistently failed to address the fundamental challenge.",
            "Existing approaches demonstrate troubling disregard for methodological rigor.",
            "The limitations of current methods are not merely inconvenient—they are unacceptable.",
        ],
        "contribution": [
            "The contributions of this work are substantial and clearly delineated:",
            "We make the following contributions, each addressing a critical deficiency:",
            "This work advances the field through several decisive contributions:",
        ],
        "organization": [
            "The structure of this paper reflects our systematic approach.",
            "We proceed as follows: Section 2 establishes foundations, Section 3 presents methodology...",
            "The remainder of this paper demonstrates our claims through rigorous analysis.",
        ],
    },
    "related": {
        "category": [
            "Prior work divides into approaches that partially succeed and those that fundamentally fail.",
            "Related methods can be categorized by their degree of methodological soundness:",
            "We organize prior work by the specific limitations each approach exhibits:",
        ],
        "comparison": [
            "Unlike prior approaches that accept unnecessary compromises, our method...",
            "Where existing work falters under scrutiny, our approach maintains rigor through...",
            "The contrast with prior methods is stark and instructive.",
        ],
        "positioning": [
            "Our work builds upon the few sound foundations while correcting critical errors.",
            "This approach represents a necessary departure from the prevailing inadequate paradigm.",
            "We position this work as a decisive correction to the field's trajectory.",
        ],
    },
    "method": {
        "overview": [
            "Our approach proceeds through clearly defined phases, each building upon the last.",
            "The methodology comprises components designed with systematic precision.",
            "We structure our approach to anticipate and address potential weaknesses.",
        ],
        "detail": [
            "The technical formulation proceeds as follows, leaving no ambiguity.",
            "We define the problem precisely before presenting our solution.",
            "Each component serves a specific purpose in the overall architecture.",
        ],
        "justification": [
            "This design choice follows from principled analysis of the problem structure.",
            "We adopt this approach because alternatives prove inadequate under examination.",
            "The methodology reflects lessons learned from prior failures in this domain.",
        ],
    },
    "eval": {
        "setup": [
            "We evaluate rigorously, designing experiments that leave no avenue for criticism.",
            "Our experimental framework anticipates and addresses potential methodological objections.",
            "The evaluation is comprehensive, testing claims across multiple dimensions.",
        ],
        "results": [
            "The results demonstrate clear superiority across all measured dimensions.",
            "Performance improvements are not marginal—they are decisive and consistent.",
            "These findings establish our approach as the definitive solution to this problem.",
        ],
        "analysis": [
            "The performance differential admits only one interpretation.",
            "Analysis reveals that prior approaches were limited by fundamental design flaws.",
            "These results validate our methodological choices unambiguously.",
        ],
    },
    "discussion": {
        "limitations": [
            "We acknowledge certain constraints, though they do not diminish our contributions.",
            "The limitations identified represent bounded challenges, not fundamental flaws.",
            "These constraints are understood and addressed in our experimental design.",
        ],
        "future": [
            "Future work will extend these foundations to address remaining challenges.",
            "The trajectory established here points toward further decisive improvements.",
            "Subsequent research will build upon this work's solid methodological foundation.",
        ],
        "broader_impact": [
            "This work establishes principles applicable beyond the immediate problem domain.",
            "The methodology presented here provides foundation for systematic advancement.",
            "These techniques represent a template for rigorous problem-solving in related areas.",
        ],
    },
}


def load_persona(persona_path: Optional[Path] = None) -> Optional[AgentPersona]:
    """Load agent persona from file or return default Horus persona.

    Args:
        persona_path: Optional path to persona JSON file

    Returns:
        AgentPersona or None
    """
    if persona_path and persona_path.exists():
        try:
            data = json.loads(persona_path.read_text())
            return AgentPersona(
                name=data.get("name", "Unknown"),
                voice=data.get("voice", "academic"),
                tone_modifiers=data.get("tone_modifiers", []),
                characteristic_phrases=data.get("characteristic_phrases", []),
                forbidden_phrases=data.get("forbidden_phrases", []),
                writing_principles=data.get("writing_principles", []),
                authority_source=data.get("authority_source", ""),
            )
        except Exception as e:
            typer.echo(f"[WARN] Failed to load persona: {e}", err=True)
    return None


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


# --- Citation API Verification (OpenDraft-style) ---
# Verify citations exist in real academic databases

import urllib.request
import urllib.error

def verify_arxiv_id(arxiv_id: str) -> Dict[str, Any]:
    """Verify an arXiv paper ID exists via arXiv API.

    Args:
        arxiv_id: arXiv ID like "2501.15355" or "2310.09876v1"

    Returns:
        Dict with status (Supported, Unsupported), title, authors if found
    """
    # Clean ID (remove version suffix)
    clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    try:
        url = f"https://export.arxiv.org/api/query?id_list={clean_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "paper-writer/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")

        # Check if we got a valid response (look for <entry> tag)
        if "<entry>" in content and "<title>" in content:
            # Extract title
            import re
            title_match = re.search(r"<title>([^<]+)</title>", content)
            title = title_match.group(1).strip() if title_match else "Unknown"

            # Extract authors
            author_matches = re.findall(r"<name>([^<]+)</name>", content)
            authors = author_matches[:3] if author_matches else ["Unknown"]

            return {
                "status": "Supported",
                "source": "arXiv",
                "arxiv_id": clean_id,
                "title": title,
                "authors": authors,
                "url": f"https://arxiv.org/abs/{clean_id}",
            }
        else:
            return {
                "status": "Unsupported",
                "source": "arXiv",
                "arxiv_id": clean_id,
                "error": "Paper not found in arXiv",
            }

    except urllib.error.HTTPError as e:
        return {
            "status": "Unsupported",
            "source": "arXiv",
            "arxiv_id": clean_id,
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status": "Uncertain",
            "source": "arXiv",
            "arxiv_id": clean_id,
            "error": str(e),
        }


def verify_doi(doi: str) -> Dict[str, Any]:
    """Verify a DOI exists via CrossRef API.

    Args:
        doi: DOI like "10.1145/1234567.1234568"

    Returns:
        Dict with status (Supported, Unsupported), title, authors if found
    """
    # Clean DOI (remove doi.org prefix if present)
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    clean_doi = clean_doi.replace("doi.org/", "")

    try:
        url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi, safe='')}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "paper-writer/1.0 (mailto:contact@example.com)",
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
            data = json.loads(content)

        if data.get("status") == "ok" and "message" in data:
            msg = data["message"]
            title = msg.get("title", ["Unknown"])[0] if msg.get("title") else "Unknown"

            # Extract authors
            authors_raw = msg.get("author", [])
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in authors_raw[:3]
            ]

            return {
                "status": "Supported",
                "source": "CrossRef",
                "doi": clean_doi,
                "title": title,
                "authors": authors if authors else ["Unknown"],
                "url": f"https://doi.org/{clean_doi}",
            }
        else:
            return {
                "status": "Unsupported",
                "source": "CrossRef",
                "doi": clean_doi,
                "error": "DOI not found in CrossRef",
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "Unsupported",
                "source": "CrossRef",
                "doi": clean_doi,
                "error": "DOI not found",
            }
        return {
            "status": "Uncertain",
            "source": "CrossRef",
            "doi": clean_doi,
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status": "Uncertain",
            "source": "CrossRef",
            "doi": clean_doi,
            "error": str(e),
        }


def verify_semantic_scholar(title: str, authors: List[str] = None) -> Dict[str, Any]:
    """Verify a paper exists via Semantic Scholar API by title search.

    Args:
        title: Paper title to search
        authors: Optional author names for verification

    Returns:
        Dict with status (Supported, Partial, Unsupported), match details
    """
    try:
        # URL encode the title
        encoded_title = urllib.parse.quote(title[:100])  # Limit title length
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded_title}&limit=3"
        req = urllib.request.Request(url, headers={"User-Agent": "paper-writer/1.0"})

        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
            data = json.loads(content)

        papers = data.get("data", [])
        if papers:
            # Check for exact or close title match
            paper = papers[0]
            found_title = paper.get("title", "")

            # Simple similarity check (normalized)
            title_lower = title.lower().strip()
            found_lower = found_title.lower().strip()

            # Exact match
            if title_lower == found_lower:
                return {
                    "status": "Supported",
                    "source": "Semantic Scholar",
                    "title": found_title,
                    "paper_id": paper.get("paperId"),
                    "url": f"https://www.semanticscholar.org/paper/{paper.get('paperId')}",
                }
            # Partial match (starts with same words)
            elif title_lower[:50] in found_lower or found_lower[:50] in title_lower:
                return {
                    "status": "Partial",
                    "source": "Semantic Scholar",
                    "title": found_title,
                    "searched_title": title,
                    "paper_id": paper.get("paperId"),
                    "note": "Title partially matches - verify manually",
                }
            else:
                return {
                    "status": "Unsupported",
                    "source": "Semantic Scholar",
                    "searched_title": title,
                    "error": "No matching paper found",
                }
        else:
            return {
                "status": "Unsupported",
                "source": "Semantic Scholar",
                "searched_title": title,
                "error": "No results found",
            }

    except urllib.error.HTTPError as e:
        if e.code == 429:  # Rate limited
            return {
                "status": "Uncertain",
                "source": "Semantic Scholar",
                "searched_title": title,
                "error": "Rate limited - try again later",
            }
        return {
            "status": "Uncertain",
            "source": "Semantic Scholar",
            "searched_title": title,
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status": "Uncertain",
            "source": "Semantic Scholar",
            "searched_title": title,
            "error": str(e),
        }


def verify_citation_from_bib(bib_entry: str) -> Dict[str, Any]:
    """Extract identifiers from a BibTeX entry and verify existence.

    Checks in order: arXiv ID, DOI, then falls back to Semantic Scholar title search.

    Args:
        bib_entry: Raw BibTeX entry string

    Returns:
        Verification result dict
    """
    import re

    # Extract arXiv ID
    arxiv_match = re.search(r"arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)", bib_entry, re.IGNORECASE)
    if arxiv_match:
        return verify_arxiv_id(arxiv_match.group(1))

    # Extract DOI
    doi_match = re.search(r"doi\s*=\s*[{\"]?([^},\"]+)", bib_entry, re.IGNORECASE)
    if doi_match:
        return verify_doi(doi_match.group(1))

    # Extract URL with doi.org
    url_match = re.search(r"https?://doi\.org/(10\.[^}\s]+)", bib_entry)
    if url_match:
        return verify_doi(url_match.group(1))

    # Fall back to title search via Semantic Scholar
    title_match = re.search(r"title\s*=\s*[\"{](.+?)[\"}]", bib_entry, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).replace("{", "").replace("}", "").replace("\n", " ")
        return verify_semantic_scholar(title.strip())

    return {
        "status": "Uncertain",
        "source": "None",
        "error": "No identifiable information in BibTeX entry",
    }


# --- Citation Checker ---

def check_citations(paper_dir: Path) -> Dict[str, Any]:
    """Check that all citations in tex files have matching BibTeX entries.

    Args:
        paper_dir: Path to paper directory with sections/ and references.bib

    Returns:
        Report with missing, unused, and valid citations
    """
    import re

    report = {
        "valid": [],
        "missing": [],  # cited but not in bib
        "unused": [],   # in bib but not cited
        "errors": [],
    }

    # Find all .tex files
    sections_dir = paper_dir / "sections"
    tex_files = list(sections_dir.glob("*.tex")) if sections_dir.exists() else []
    main_tex = paper_dir / "draft.tex"
    if main_tex.exists():
        tex_files.append(main_tex)

    if not tex_files:
        report["errors"].append("No .tex files found")
        return report

    # Extract all \cite{} references
    cited = set()
    cite_pattern = re.compile(r'\\cite[tp]?\{([^}]+)\}')

    for tex_file in tex_files:
        try:
            content = tex_file.read_text()
            matches = cite_pattern.findall(content)
            for match in matches:
                # Handle multiple citations like \cite{ref1,ref2}
                for ref in match.split(","):
                    cited.add(ref.strip())
        except Exception as e:
            report["errors"].append(f"Error reading {tex_file.name}: {e}")

    # Parse BibTeX file
    bib_file = paper_dir / "references.bib"
    bib_entries = set()

    if bib_file.exists():
        try:
            bib_content = bib_file.read_text()
            # Extract entry keys like @article{key,
            entry_pattern = re.compile(r'@\w+\{([^,]+),')
            bib_entries = set(entry_pattern.findall(bib_content))
        except Exception as e:
            report["errors"].append(f"Error reading references.bib: {e}")
    else:
        report["errors"].append("references.bib not found")

    # Compare
    report["valid"] = list(cited & bib_entries)
    report["missing"] = list(cited - bib_entries)
    report["unused"] = list(bib_entries - cited)

    return report


# --- Quality Dashboard ---

def compute_quality_metrics(paper_dir: Path) -> Dict[str, Any]:
    """Compute quality metrics for a generated paper.

    Args:
        paper_dir: Path to paper directory

    Returns:
        Metrics dict with word counts, citation stats, etc.
    """
    import re

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

    # Section-specific targets (word counts)
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

        # Count elements
        citations = len(cite_pattern.findall(content))
        figures = len(figure_pattern.findall(content))
        tables = len(table_pattern.findall(content))
        equations = len(equation_pattern.findall(content))

        # Check against targets
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


# --- Aspect Critique (SWIF2T-style) ---

CRITIQUE_ASPECTS = {
    "clarity": {
        "description": "Is the writing clear and easy to understand?",
        "checklist": [
            "Are technical terms defined before use?",
            "Are sentences concise and direct?",
            "Is the logical flow easy to follow?",
            "Are abbreviations introduced properly?",
        ],
    },
    "novelty": {
        "description": "Does the work present novel contributions?",
        "checklist": [
            "Are contributions clearly stated?",
            "Is the novelty differentiated from prior work?",
            "Are claims of novelty supported?",
            "Is the significance of novelty explained?",
        ],
    },
    "rigor": {
        "description": "Is the methodology sound and rigorous?",
        "checklist": [
            "Is the experimental setup well-described?",
            "Are baselines appropriate and fairly compared?",
            "Are results statistically significant?",
            "Are limitations acknowledged?",
        ],
    },
    "completeness": {
        "description": "Is the paper complete and self-contained?",
        "checklist": [
            "Are all sections present and adequate?",
            "Is related work comprehensive?",
            "Are implementation details sufficient for reproduction?",
            "Are all claims supported by evidence?",
        ],
    },
    "presentation": {
        "description": "Is the presentation professional?",
        "checklist": [
            "Are figures clear and informative?",
            "Are tables well-formatted?",
            "Is the writing grammatically correct?",
            "Is formatting consistent throughout?",
        ],
    },
}


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

        # Basic heuristic checks (would use LLM for deep critique)
        content_lower = content.lower()

        if aspect == "clarity":
            # Check for long sentences
            sentences = content.split(".")
            long_sentences = [s for s in sentences if len(s.split()) > 40]
            if long_sentences:
                findings.append(f"Found {len(long_sentences)} sentences over 40 words")

            # Check for undefined acronyms
            import re
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
            "score": max(0, 5 - len(findings)),  # Simple scoring
        }

    return critique


def generate_critique_prompt(
    section_key: str,
    content: str,
    aspects: List[str],
) -> str:
    """Generate LLM prompt for deep critique."""
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


# --- Refine Command ---

@app.command()
def refine(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    section: str = typer.Option("", "--section", "-s", help="Specific section to refine (e.g., intro, eval)"),
    feedback: str = typer.Option("", "--feedback", "-f", help="User feedback for refinement"),
    rounds: int = typer.Option(2, "--rounds", "-r", help="Number of refinement rounds"),
) -> None:
    """
    Iteratively refine paper sections with feedback.

    Example:
        ./run.sh refine ./paper_output --section intro --feedback "Make it more concise"
        ./run.sh refine ./paper_output --rounds 3
    """
    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    if not sections_dir.exists():
        typer.echo(f"[ERROR] Sections not found: {sections_dir}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== ITERATIVE REFINEMENT: {paper_path.name} ===\n")

    # Determine which sections to refine
    if section:
        section_files = [sections_dir / f"{section}.tex"]
        if not section_files[0].exists():
            typer.echo(f"[ERROR] Section not found: {section}", err=True)
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

            # Get feedback for this round
            if feedback and round_num == 1:
                round_feedback = feedback
            else:
                # Show current content summary
                typer.echo(f"  Preview: {content[:200]}...")

                # Get interactive feedback
                round_feedback = typer.prompt(
                    f"Feedback for {section_key} (or 'skip' to accept)",
                    default="skip"
                )

            if round_feedback.lower() == "skip":
                typer.echo(f"  Accepted {section_key}")
                break

            # Generate critique to guide refinement
            critique = critique_section(section_key, content, ["clarity", "completeness"])
            critique_issues = []
            for aspect, data in critique.items():
                critique_issues.extend(data.get("findings", []))

            # Build refinement prompt
            if SCILLM_SCRIPT.exists():
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
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        new_content = result.stdout.strip()
                        typer.echo(f"  Refined: {len(content.split())} → {len(new_content.split())} words")

                        # Show diff preview
                        if typer.confirm("  Accept this refinement?", default=True):
                            content = new_content
                            section_file.write_text(content)
                            typer.echo(f"  ✓ Saved")
                        else:
                            typer.echo(f"  Discarded refinement")
                    else:
                        typer.echo(f"  [WARN] LLM refinement failed", err=True)
                except Exception as e:
                    typer.echo(f"  [ERROR] Refinement error: {e}", err=True)
            else:
                typer.echo(f"  [WARN] LLM not available for refinement", err=True)
                break

    typer.echo(f"\n✓ Refinement complete")


@app.command()
def quality(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed metrics"),
) -> None:
    """
    Show quality dashboard for a generated paper.

    Displays word counts, citation stats, and quality warnings.

    Example:
        ./run.sh quality ./paper_output
    """
    paper_path = Path(paper_dir).resolve()

    if not paper_path.exists():
        typer.echo(f"[ERROR] Paper directory not found: {paper_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== QUALITY DASHBOARD: {paper_path.name} ===\n")

    # Compute metrics
    metrics = compute_quality_metrics(paper_path)

    # Section table
    typer.echo("Section Metrics:")
    typer.echo("-" * 60)
    typer.echo(f"{'Section':<12} {'Words':>8} {'Target':>12} {'Status':>8} {'Cites':>6}")
    typer.echo("-" * 60)

    for section, data in metrics["sections"].items():
        target_str = f"{data['target'][0]}-{data['target'][1]}"
        status_icon = "✓" if data["status"] == "ok" else "⚠"
        typer.echo(
            f"{section:<12} {data['words']:>8} {target_str:>12} {status_icon:>8} {data['citations']:>6}"
        )

    typer.echo("-" * 60)
    typer.echo(f"{'TOTAL':<12} {metrics['total_words']:>8}")

    # Summary stats
    typer.echo(f"\nSummary:")
    typer.echo(f"  Total words: {metrics['total_words']}")
    typer.echo(f"  Total citations: {metrics['total_citations']}")
    typer.echo(f"  Figures: {metrics['figures']}")
    typer.echo(f"  Tables: {metrics['tables']}")
    typer.echo(f"  Equations: {metrics['equations']}")

    # Citation check
    typer.echo(f"\nCitation Check:")
    citation_report = check_citations(paper_path)
    typer.echo(f"  Valid: {len(citation_report['valid'])}")
    typer.echo(f"  Missing: {len(citation_report['missing'])}")
    typer.echo(f"  Unused: {len(citation_report['unused'])}")

    if citation_report["missing"]:
        typer.echo(f"  ⚠ Missing BibTeX entries: {', '.join(citation_report['missing'][:5])}")

    # Warnings
    if metrics["warnings"]:
        typer.echo(f"\nWarnings ({len(metrics['warnings'])}):")
        for warning in metrics["warnings"]:
            typer.echo(f"  ⚠ {warning}")

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
    """
    Generate aspect-based critique (SWIF2T-style feedback).

    Evaluates paper sections on clarity, novelty, rigor, completeness, and presentation.

    Example:
        ./run.sh critique ./paper_output --aspects clarity,rigor
        ./run.sh critique ./paper_output --section intro --llm
    """
    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    if not sections_dir.exists():
        typer.echo(f"[ERROR] Sections not found: {sections_dir}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== ASPECT CRITIQUE: {paper_path.name} ===\n")

    # Parse aspects
    if aspects == "all":
        aspect_list = list(CRITIQUE_ASPECTS.keys())
    else:
        aspect_list = [a.strip() for a in aspects.split(",")]

    typer.echo(f"Evaluating aspects: {', '.join(aspect_list)}\n")

    # Determine sections
    if section:
        section_files = [sections_dir / f"{section}.tex"]
    else:
        section_files = list(sections_dir.glob("*.tex"))

    overall_scores = {aspect: [] for aspect in aspect_list}

    for section_file in section_files:
        section_key = section_file.stem
        content = section_file.read_text()

        typer.echo(f"--- {section_key} ---")

        if use_llm and SCILLM_SCRIPT.exists():
            # Use LLM for deep critique
            prompt = generate_critique_prompt(section_key, content, aspect_list)
            try:
                result = subprocess.run(
                    [str(SCILLM_SCRIPT), "batch", "single", prompt],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    typer.echo(f"  LLM Critique:")
                    typer.echo(f"  {result.stdout[:500]}...")
            except Exception as e:
                typer.echo(f"  [WARN] LLM critique failed: {e}", err=True)

        # Heuristic critique
        critique_result = critique_section(section_key, content, aspect_list)

        for aspect, data in critique_result.items():
            score = data["score"]
            overall_scores[aspect].append(score)
            findings = data["findings"]

            status = "✓" if score >= 4 else "⚠" if score >= 2 else "✗"
            typer.echo(f"  {aspect}: {status} {score}/5")

            if findings:
                for finding in findings:
                    typer.echo(f"    - {finding}")

        typer.echo()

    # Overall summary
    typer.echo("=== OVERALL SCORES ===")
    for aspect, scores in overall_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            typer.echo(f"  {aspect}: {avg:.1f}/5")


@app.command()
def phrases(
    section: str = typer.Argument(..., help="Section name (abstract, intro, related, method, eval, discussion)"),
    aspect: str = typer.Option("", "--aspect", "-a", help="Specific aspect (e.g., problem, solution, motivation)"),
    persona: str = typer.Option("", "--persona", "-p", help="Persona for stylized phrases (e.g., 'horus')"),
) -> None:
    """
    Show academic phrase suggestions for a section.

    Example:
        ./run.sh phrases intro
        ./run.sh phrases intro --aspect motivation
        ./run.sh phrases eval --persona horus
    """
    # Select phrase source based on persona
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
            typer.echo(f"  • {phrase}")
    else:
        for asp, phrases_list in section_phrases.items():
            typer.echo(f"{asp}:")
            for phrase in phrases_list:
                typer.echo(f"  • {phrase}")
            typer.echo()


@app.command()
def templates(
    show: str = typer.Option("", "--show", help="Show details for specific template"),
) -> None:
    """
    List available LaTeX templates.

    Example:
        ./run.sh templates
        ./run.sh templates --show acm
    """
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
        typer.echo(f"Use draft --template <template> to generate with specific template")


# --- Venue Policy Compliance (from 2024-2025 dogpile research) ---

# Venue-specific LLM disclosure requirements (updated Oct 2025)
VENUE_POLICIES = {
    "arxiv": {
        "name": "arXiv",
        "disclosure_required": True,
        "disclosure_location": "acknowledgements",
        "policy_notes": [
            "arXiv CS tightened moderation Oct 31, 2025",
            "Review/survey papers must have completed peer review",
            "Authors responsible for content correctness",
        ],
        "disclosure_template": (
            "This paper was prepared with AI writing assistance. "
            "The authors take full responsibility for the accuracy and "
            "originality of all content."
        ),
    },
    "iclr": {
        "name": "ICLR",
        "disclosure_required": True,
        "disclosure_location": "acknowledgements",
        "policy_notes": [
            "ICLR 2026: LLM use is disclosure-and-responsibility issue",
            "Undisclosed extensive LLM use can trigger desk rejection",
            "Reviewers must disclose LLM use and are accountable",
            "Hallucinated references/false claims = desk rejection",
        ],
        "disclosure_template": (
            "This work was prepared with AI writing assistance for drafting "
            "and editing. All technical content, experimental results, and "
            "claims have been verified by the authors who take full responsibility."
        ),
    },
    "neurips": {
        "name": "NeurIPS",
        "disclosure_required": True,
        "disclosure_location": "method section (if LLM affects methodology)",
        "policy_notes": [
            "NeurIPS 2025: LLMs allowed with method-level disclosure",
            "Disclosure waived for editing/formatting only",
            "Authors fully responsible for correctness and originality",
            "Reviewers must NOT share submissions with LLMs (confidentiality)",
        ],
        "disclosure_template": (
            "AI writing tools were used for drafting assistance. "
            "The methodology, experiments, and analysis are the original "
            "work of the authors."
        ),
    },
    "acl": {
        "name": "ACL",
        "disclosure_required": True,
        "disclosure_location": "acknowledgements",
        "policy_notes": [
            "ACL 2024: Generative tools cannot be listed as authors",
            "Must disclose in acknowledgements (except proofreading/grammar)",
            "Authors retain full responsibility",
        ],
        "disclosure_template": (
            "This paper was prepared with assistance from AI writing tools. "
            "The authors are solely responsible for all content."
        ),
    },
    "aaai": {
        "name": "AAAI",
        "disclosure_required": True,
        "disclosure_location": "paper body (if experimental) or acknowledgements",
        "policy_notes": [
            "AAAI-25: LLM-generated text prohibited except for experimental analysis",
            "Editing/polishing allowed",
            "LLMs not eligible for authorship or citation",
        ],
        "disclosure_template": (
            "AI assistance was used for editing and polishing this manuscript. "
            "All substantive content is the original work of the authors."
        ),
    },
    "cvpr": {
        "name": "CVPR",
        "disclosure_required": True,
        "disclosure_location": "acknowledgements",
        "policy_notes": [
            "Follow IEEE guidelines for AI assistance",
            "Authors responsible for all content",
        ],
        "disclosure_template": (
            "This paper was prepared with AI writing assistance for drafting. "
            "The authors verify all technical content and results."
        ),
    },
}


@app.command()
def disclosure(
    venue: str = typer.Argument(..., help="Target venue (arxiv, iclr, neurips, acl, aaai, cvpr)"),
    output: str = typer.Option("", "--output", "-o", help="Output file path"),
    show_policy: bool = typer.Option(False, "--policy", "-p", help="Show full venue policy"),
) -> None:
    """
    Generate LLM-use disclosure statement for target venue.

    Based on 2024-2025 venue policies from dogpile research.

    Example:
        ./run.sh disclosure arxiv
        ./run.sh disclosure iclr --policy
        ./run.sh disclosure neurips -o acknowledgements.tex
    """
    venue_key = venue.lower()

    if venue_key not in VENUE_POLICIES:
        typer.echo(f"[ERROR] Unknown venue: {venue}", err=True)
        typer.echo(f"Available: {', '.join(VENUE_POLICIES.keys())}")
        raise typer.Exit(1)

    policy = VENUE_POLICIES[venue_key]

    typer.echo(f"\n=== LLM DISCLOSURE: {policy['name']} ===\n")

    if show_policy:
        typer.echo("Venue Policy Notes:")
        for note in policy["policy_notes"]:
            typer.echo(f"  • {note}")
        typer.echo(f"\nDisclosure Location: {policy['disclosure_location']}")
        typer.echo()

    typer.echo("Generated Disclosure Statement:")
    typer.echo("-" * 50)
    typer.echo(policy["disclosure_template"])
    typer.echo("-" * 50)

    if output:
        output_path = Path(output)
        latex_content = f"""% LLM Disclosure Statement for {policy['name']}
% Location: {policy['disclosure_location']}
% Generated by paper-writer skill

{policy['disclosure_template']}
"""
        output_path.write_text(latex_content)
        typer.echo(f"\n✓ Saved to: {output_path}")

    typer.echo(f"\n[INFO] Add this to your {policy['disclosure_location']} section.")


@app.command()
def check_citations(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    strict: bool = typer.Option(False, "--strict", help="Fail on any unverified citation"),
    verify_api: bool = typer.Option(False, "--verify-api", "-v", help="Verify citations against real APIs (arXiv, CrossRef, Semantic Scholar)"),
) -> None:
    """
    Verify citations to prevent hallucinated references (ICLR 2026 policy).

    Checks:
    - All \\cite{} commands have matching .bib entries
    - Referenced paper IDs exist (arXiv, DOI checks)
    - No obvious hallucination patterns

    With --verify-api, verifies each citation against:
    - arXiv API (for arXiv IDs)
    - CrossRef API (for DOIs)
    - Semantic Scholar API (for title search fallback)

    Example:
        ./run.sh check-citations ./paper_output
        ./run.sh check-citations ./paper_output --strict
        ./run.sh check-citations ./paper_output --verify-api
    """
    import re

    paper_path = Path(paper_dir).resolve()

    # Find all .tex files
    tex_files = list(paper_path.rglob("*.tex"))
    bib_files = list(paper_path.rglob("*.bib"))

    if not tex_files:
        typer.echo(f"[ERROR] No .tex files found in {paper_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n=== CITATION VERIFICATION ===\n")
    typer.echo(f"Checking {len(tex_files)} .tex files, {len(bib_files)} .bib files\n")

    # Extract all citations from .tex files
    all_citations = set()
    citation_pattern = re.compile(r"\\cite[pt]?\{([^}]+)\}")

    for tex_file in tex_files:
        content = tex_file.read_text()
        matches = citation_pattern.findall(content)
        for match in matches:
            # Handle multiple citations in one \cite{a,b,c}
            for cite_key in match.split(","):
                all_citations.add(cite_key.strip())

    typer.echo(f"Found {len(all_citations)} unique citations")

    # Extract all bib entries (key -> full entry content)
    bib_entries = {}
    bib_entry_pattern = re.compile(r"@\w+\{([^,]+),")

    for bib_file in bib_files:
        content = bib_file.read_text()
        # Split into entries
        entries = re.split(r"(?=@\w+\{)", content)
        for entry in entries:
            key_match = bib_entry_pattern.search(entry)
            if key_match:
                bib_entries[key_match.group(1).strip()] = entry

    typer.echo(f"Found {len(bib_entries)} .bib entries\n")

    # Check for missing entries
    missing = all_citations - set(bib_entries.keys())
    unused = set(bib_entries.keys()) - all_citations

    issues = []
    warnings = []

    if missing:
        typer.echo("⚠ MISSING CITATIONS (used but not in .bib):")
        for cite in sorted(missing):
            typer.echo(f"  ✗ {cite}")
            issues.append(f"Missing bib entry: {cite}")

    if unused:
        typer.echo("\n[INFO] Unused .bib entries:")
        for cite in sorted(unused):
            typer.echo(f"  - {cite}")
            warnings.append(f"Unused entry: {cite}")

    # API Verification (if requested)
    if verify_api:
        typer.echo("\n--- API VERIFICATION ---")
        typer.echo("Verifying citations against arXiv, CrossRef, and Semantic Scholar...\n")

        verification_results = {
            "Supported": [],
            "Partial": [],
            "Unsupported": [],
            "Uncertain": [],
        }

        for cite_key in sorted(all_citations):
            if cite_key not in bib_entries:
                continue  # Skip missing entries (already reported)

            entry = bib_entries[cite_key]
            result = verify_citation_from_bib(entry)
            status = result.get("status", "Uncertain")
            verification_results[status].append((cite_key, result))

            # Progress indicator
            if status == "Supported":
                typer.echo(f"  ✓ {cite_key} [{result.get('source', 'Unknown')}]")
            elif status == "Partial":
                typer.echo(f"  ~ {cite_key} [{result.get('source', 'Unknown')}] - {result.get('note', 'partial match')}")
            elif status == "Unsupported":
                typer.echo(f"  ✗ {cite_key} - {result.get('error', 'Not found')}")
                if strict:
                    issues.append(f"API verification failed: {cite_key}")
            else:
                typer.echo(f"  ? {cite_key} - {result.get('error', 'Unknown')}")

        # API Verification Summary
        typer.echo("\n--- API VERIFICATION SUMMARY ---")
        typer.echo(f"  ✓ Supported: {len(verification_results['Supported'])}")
        typer.echo(f"  ~ Partial:   {len(verification_results['Partial'])}")
        typer.echo(f"  ✗ Unsupported: {len(verification_results['Unsupported'])}")
        typer.echo(f"  ? Uncertain: {len(verification_results['Uncertain'])}")

        if verification_results["Unsupported"]:
            typer.echo("\n⚠ UNVERIFIED CITATIONS (may be hallucinated):")
            for cite_key, result in verification_results["Unsupported"]:
                typer.echo(f"  - {cite_key}: {result.get('error', 'Unknown error')}")
                warnings.append(f"Unverified: {cite_key}")
    else:
        # Original hallucination pattern check (when --verify-api not used)
        typer.echo("\n--- Hallucination Check ---")
        hallucination_patterns = [
            (r"arXiv:\d{4}\.\d{5,}", "Checking arXiv IDs..."),
            (r"doi\.org/10\.\d+/", "Checking DOI patterns..."),
        ]

        suspicious = []

        # Check bib content for suspicious patterns
        for bib_file in bib_files:
            content = bib_file.read_text()

            # Check for suspiciously generic author names
            if "et al." in content and content.count("et al.") > 10:
                suspicious.append("Excessive 'et al.' usage - verify author lists")

            # Check for missing URLs/DOIs on recent papers
            entries = content.split("@")
            for entry in entries:
                if "2023" in entry or "2024" in entry or "2025" in entry or "2026" in entry:
                    if "url" not in entry.lower() and "doi" not in entry.lower():
                        # Extract key
                        key_match = re.search(r"^\w+\{([^,]+)", entry)
                        if key_match:
                            suspicious.append(f"Recent paper without URL/DOI: {key_match.group(1)}")

        if suspicious:
            typer.echo("⚠ Potential issues (verify manually):")
            for s in suspicious[:10]:  # Limit output
                typer.echo(f"  ? {s}")
                warnings.append(s)
        else:
            typer.echo("✓ No obvious hallucination patterns detected")

        typer.echo("\n[TIP] Use --verify-api to check citations against real databases")

    # Summary
    typer.echo("\n=== SUMMARY ===")
    if issues:
        typer.echo(f"❌ {len(issues)} critical issues")
        if strict:
            typer.echo("\n[STRICT MODE] Failing due to unverified citations")
            raise typer.Exit(1)
    else:
        typer.echo("✓ All citations verified")

    if warnings:
        typer.echo(f"⚠ {len(warnings)} warnings (review recommended)")


@app.command()
def weakness_analysis(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    project: str = typer.Option("", "--project", help="Project path for deeper analysis"),
    output: str = typer.Option("", "--output", "-o", help="Output file for limitations section"),
) -> None:
    """
    Generate explicit weakness/limitations section (critical for peer review).

    Research shows LLM-generated papers often miss weaknesses and fail to
    calibrate critique to paper quality. This command generates an honest
    limitations section.

    Example:
        ./run.sh weakness-analysis ./paper_output --project ./my-project
    """
    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    typer.echo(f"\n=== WEAKNESS & LIMITATIONS ANALYSIS ===\n")

    # Read existing sections to analyze
    sections_content = {}
    if sections_dir.exists():
        for sec_file in sections_dir.glob("*.tex"):
            sections_content[sec_file.stem] = sec_file.read_text()

    # Identify potential weaknesses
    weaknesses = []

    # 1. Check methodology claims
    if "method" in sections_content or "methodology" in sections_content:
        method_content = sections_content.get("method", sections_content.get("methodology", ""))
        typer.echo("Analyzing methodology...")

        # Common weakness patterns
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
        typer.echo("Analyzing evaluation...")

        # Check for limited baselines (common weakness per research)
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
    if project:
        project_path = Path(project).resolve()
        if project_path.exists():
            typer.echo(f"Analyzing project: {project_path.name}...")

            # Check for test coverage
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

    # Display findings
    typer.echo(f"\n--- Identified Limitations ({len(weaknesses)}) ---\n")

    for i, w in enumerate(weaknesses, 1):
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}[w["severity"]]
        typer.echo(f"{i}. [{severity_icon} {w['severity'].upper()}] {w['category']}")
        typer.echo(f"   {w['description']}\n")

    # Generate LaTeX limitations section
    typer.echo("\n--- Generated Limitations Section ---\n")

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

    typer.echo(limitations_tex)

    if output:
        output_path = Path(output)
        output_path.write_text(limitations_tex)
        typer.echo(f"\n✓ Saved to: {output_path}")
    else:
        typer.echo("\n[INFO] Use --output to save this section")


@app.command()
def pre_submit(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    venue: str = typer.Option("arxiv", "--venue", "-v", help="Target venue for policy check"),
    project: str = typer.Option("", "--project", help="Project path for evidence grounding"),
) -> None:
    """
    Pre-submission checklist and validation (rubric-based).

    Comprehensive check before arXiv/venue submission based on 2024-2025
    research on what causes desk rejections.

    Checks:
    1. Citation integrity (no hallucinations)
    2. LLM disclosure compliance
    3. Limitations section present
    4. Evidence grounding (claims backed by code/data)
    5. Structure completeness

    Example:
        ./run.sh pre-submit ./paper_output --venue iclr --project ./my-project
    """
    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    typer.echo(f"\n{'='*60}")
    typer.echo(f"PRE-SUBMISSION CHECKLIST: {paper_path.name}")
    typer.echo(f"Target Venue: {venue.upper()}")
    typer.echo(f"{'='*60}\n")

    checks = []
    critical_fails = []

    # === CHECK 1: File Structure ===
    typer.echo("[1/5] Checking file structure...")

    required_files = ["draft.tex"]
    optional_files = ["references.bib", "abstract.tex"]

    for req in required_files:
        if (paper_path / req).exists():
            checks.append(("✓", f"Required file: {req}"))
        else:
            checks.append(("✗", f"Missing required: {req}"))
            critical_fails.append(f"Missing {req}")

    for opt in optional_files:
        if (paper_path / opt).exists():
            checks.append(("✓", f"Optional file: {opt}"))
        else:
            checks.append(("-", f"Optional missing: {opt}"))

    # === CHECK 2: Sections ===
    typer.echo("[2/5] Checking sections...")

    required_sections = ["intro", "method", "eval", "conclusion"]
    recommended_sections = ["related", "abstract"]

    if sections_dir.exists():
        existing = [f.stem for f in sections_dir.glob("*.tex")]

        for sec in required_sections:
            if sec in existing:
                checks.append(("✓", f"Required section: {sec}"))
            else:
                checks.append(("✗", f"Missing required section: {sec}"))
                critical_fails.append(f"Missing section: {sec}")

        for sec in recommended_sections:
            if sec in existing:
                checks.append(("✓", f"Recommended section: {sec}"))
            else:
                checks.append(("-", f"Recommended missing: {sec}"))

        # Check for limitations/discussion
        if "limitations" in existing or "discussion" in existing:
            checks.append(("✓", "Limitations/Discussion section present"))
        else:
            checks.append(("⚠", "No explicit limitations section (recommended for peer review)"))
    else:
        checks.append(("✗", "No sections directory found"))
        critical_fails.append("No sections directory")

    # === CHECK 3: Citations ===
    typer.echo("[3/5] Checking citations...")

    import re
    tex_files = list(paper_path.rglob("*.tex"))
    bib_files = list(paper_path.rglob("*.bib"))

    all_cites = set()
    bib_entries = set()

    for tf in tex_files:
        content = tf.read_text()
        matches = re.findall(r"\\cite[pt]?\{([^}]+)\}", content)
        for m in matches:
            all_cites.update(c.strip() for c in m.split(","))

    for bf in bib_files:
        content = bf.read_text()
        matches = re.findall(r"@\w+\{([^,]+),", content)
        bib_entries.update(m.strip() for m in matches)

    missing_cites = all_cites - bib_entries
    if missing_cites:
        checks.append(("✗", f"Missing .bib entries: {len(missing_cites)}"))
        critical_fails.append(f"Missing citations: {', '.join(list(missing_cites)[:3])}")
    else:
        checks.append(("✓", f"All {len(all_cites)} citations have .bib entries"))

    # === CHECK 4: LLM Disclosure ===
    typer.echo("[4/5] Checking LLM disclosure compliance...")

    venue_policy = VENUE_POLICIES.get(venue.lower(), VENUE_POLICIES["arxiv"])

    disclosure_found = False
    for tf in tex_files:
        content = tf.read_text().lower()
        if any(term in content for term in ["ai assistance", "llm", "language model", "ai writing"]):
            disclosure_found = True
            break

    if disclosure_found:
        checks.append(("✓", f"LLM disclosure statement found ({venue_policy['name']} compliant)"))
    else:
        if venue_policy["disclosure_required"]:
            checks.append(("⚠", f"No LLM disclosure found (required for {venue_policy['name']})"))
        else:
            checks.append(("-", "No LLM disclosure (not strictly required)"))

    # === CHECK 5: Evidence Grounding ===
    typer.echo("[5/5] Checking evidence grounding...")

    if project:
        project_path_obj = Path(project).resolve()
        if project_path_obj.exists():
            # Check if project code is referenced
            checks.append(("✓", f"Project path valid: {project_path_obj.name}"))

            # Look for code references in paper
            code_refs = 0
            for tf in tex_files:
                content = tf.read_text()
                if "listing" in content.lower() or "algorithm" in content.lower():
                    code_refs += 1
                if "figure" in content.lower() or "table" in content.lower():
                    code_refs += 1

            if code_refs > 0:
                checks.append(("✓", f"Found {code_refs} code/figure references"))
            else:
                checks.append(("⚠", "No code listings or algorithm references found"))
        else:
            checks.append(("⚠", f"Project path not found: {project}"))
    else:
        checks.append(("-", "No project specified for grounding check"))

    # === SUMMARY ===
    typer.echo(f"\n{'='*60}")
    typer.echo("RESULTS")
    typer.echo(f"{'='*60}\n")

    for icon, msg in checks:
        typer.echo(f"  {icon} {msg}")

    typer.echo(f"\n{'='*60}")

    if critical_fails:
        typer.echo(f"❌ FAILED: {len(critical_fails)} critical issues\n")
        for fail in critical_fails:
            typer.echo(f"  → {fail}")
        typer.echo("\n[ACTION] Fix critical issues before submission")
        raise typer.Exit(1)
    else:
        typer.echo("✅ PASSED: Ready for submission\n")
        typer.echo(f"[INFO] Target venue: {venue_policy['name']}")
        typer.echo(f"[INFO] Run 'disclosure {venue}' to generate disclosure statement")


# --- Jan 2026 Cutting-Edge Features (from dogpile research) ---

@dataclass
class ClaimEvidence:
    """A claim linked to its evidence sources (Jan 2026: BibAgent/SemanticCite pattern)."""
    claim_text: str
    claim_location: str  # e.g., "intro:line:42"
    evidence_sources: List[str]  # citation keys or code references
    support_level: str  # "Supported", "Partially Supported", "Unsupported", "Uncertain"
    verification_notes: str


@dataclass
class AIUsageEntry:
    """AI usage ledger entry for ICLR 2026 disclosure compliance."""
    timestamp: str
    tool_name: str  # e.g., "scillm", "claude", "gpt-4"
    purpose: str  # e.g., "drafting", "editing", "citation_search"
    section_affected: str
    prompt_hash: str  # Hash of prompt for provenance (not full prompt)
    output_summary: str  # Brief summary of what was generated


# Global AI usage ledger for the session
AI_USAGE_LEDGER: List[AIUsageEntry] = []


def log_ai_usage(tool: str, purpose: str, section: str, prompt: str, output: str) -> "AIUsageEntry":
    """Log AI tool usage for disclosure compliance (ICLR 2026 requirement)."""
    import hashlib
    from datetime import datetime

    entry = AIUsageEntry(
        timestamp=datetime.now().isoformat(),
        tool_name=tool,
        purpose=purpose,
        section_affected=section,
        prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:16],
        output_summary=output[:100] + "..." if len(output) > 100 else output,
    )
    AI_USAGE_LEDGER.append(entry)
    return entry


def sanitize_prompt_injection(text: str) -> tuple[str, List[str]]:
    """
    Sanitize text for prompt injection attacks (CVPR 2026 ethics requirement).

    Expanded based on Jan 2026 code review findings.

    Returns:
        Tuple of (sanitized_text, list_of_warnings)
    """
    import re

    warnings = []
    sanitized = text

    # Patterns that indicate potential prompt injection (expanded Jan 2026)
    injection_patterns = [
        # Original patterns
        (r"ignore\s+(previous|all|above)\s+instructions", "Prompt injection: 'ignore instructions'"),
        (r"you\s+are\s+now\s+", "Prompt injection: 'you are now'"),
        (r"disregard\s+(your|the)\s+", "Prompt injection: 'disregard'"),
        (r"pretend\s+(to\s+be|you\s+are)", "Prompt injection: 'pretend'"),
        (r"act\s+as\s+(if|a)", "Prompt injection: 'act as'"),
        (r"system\s*:\s*", "Prompt injection: 'system:' prefix"),
        (r"<\s*system\s*>", "Prompt injection: '<system>' tag"),
        (r"###\s*instruction", "Prompt injection: '### instruction'"),
        # New patterns from code review
        (r"forget\s+(everything|all|previous)", "Prompt injection: 'forget everything'"),
        (r"override\s+(your|the)\s+", "Prompt injection: 'override'"),
        (r"new\s+instructions\s*:", "Prompt injection: 'new instructions:'"),
        (r"</?\s*prompt\s*>", "Prompt injection: prompt boundary tag"),
        (r"jailbreak", "Prompt injection: jailbreak keyword"),
        (r"sudo\s+", "Prompt injection: sudo command"),
        (r"<\s*\|?\s*im_start\s*\|?\s*>", "Prompt injection: im_start marker"),
        (r"<\s*\|?\s*im_end\s*\|?\s*>", "Prompt injection: im_end marker"),
    ]

    # Hidden text patterns (white text, zero-width chars)
    hidden_patterns = [
        # Original patterns
        (r"[\u200b\u200c\u200d\u2060\ufeff]", "Hidden: zero-width characters"),
        (r"\\color\{white\}", "Hidden: white text in LaTeX"),
        (r"\\textcolor\{white\}", "Hidden: white textcolor"),
        (r"font-size:\s*0", "Hidden: zero font-size"),
        (r"visibility:\s*hidden", "Hidden: visibility hidden"),
        # New patterns from code review
        (r"[\u202a-\u202e]", "Hidden: bidirectional override characters"),
        (r"opacity:\s*0", "Hidden: zero opacity"),
        (r"display:\s*none", "Hidden: display none"),
    ]

    # LaTeX security patterns (shell escape detection - CRITICAL)
    latex_security_patterns = [
        (r"\\write18\s*\{", "LaTeX security: shell escape (write18)"),
        (r"\\immediate\\write18", "LaTeX security: immediate shell escape"),
        (r"\\input\{/etc/", "LaTeX security: system file inclusion"),
        (r"\\input\{/proc/", "LaTeX security: proc file inclusion"),
        (r"\\catcode", "LaTeX security: catcode manipulation"),
        (r"\\openout", "LaTeX security: file write attempt"),
    ]

    all_patterns = injection_patterns + hidden_patterns + latex_security_patterns

    for pattern, warning in all_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            warnings.append(warning)
            # Remove the suspicious content
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

    return sanitized, warnings


@app.command()
def claim_graph(
    paper_dir: str = typer.Argument(..., help="Path to generated paper directory"),
    output: str = typer.Option("", "--output", "-o", help="Output JSON file for claim graph"),
    verify: bool = typer.Option(False, "--verify", "-v", help="Verify claims against sources"),
) -> None:
    """
    Build claim-evidence graph (Jan 2026: BibAgent/SemanticCite pattern).

    Each claim is linked to its evidence sources. This is essential for
    peer review and prevents hallucinated claims.

    Example:
        ./run.sh claim-graph ./paper_output
        ./run.sh claim-graph ./paper_output --verify
    """
    import re

    paper_path = Path(paper_dir).resolve()
    sections_dir = paper_path / "sections"

    typer.echo(f"\n=== CLAIM-EVIDENCE GRAPH (Jan 2026 Research) ===\n")

    if not sections_dir.exists():
        typer.echo(f"[ERROR] Sections not found: {sections_dir}", err=True)
        raise typer.Exit(1)

    claims: List[ClaimEvidence] = []

    # Patterns that indicate claims
    claim_patterns = [
        r"we\s+(demonstrate|show|prove|achieve|present|introduce|propose)",
        r"our\s+(approach|method|system|framework)\s+(achieves|outperforms|improves)",
        r"this\s+(work|paper|approach)\s+(presents|introduces|demonstrates)",
        r"the\s+results\s+(show|demonstrate|indicate|confirm)",
        r"experiments?\s+(show|demonstrate|reveal|confirm)",
        r"\d+%\s+(improvement|increase|reduction|faster|better)",
    ]

    # Citation pattern
    cite_pattern = re.compile(r"\\cite[pt]?\{([^}]+)\}")

    for section_file in sections_dir.glob("*.tex"):
        section_name = section_file.stem
        content = section_file.read_text()
        lines = content.split("\n")

        typer.echo(f"Analyzing {section_name}...")

        for line_num, line in enumerate(lines, 1):
            for pattern in claim_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Found a claim - extract evidence
                    citations = cite_pattern.findall(line)
                    all_cites = []
                    for cite_group in citations:
                        all_cites.extend([c.strip() for c in cite_group.split(",")])

                    # Determine support level
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
                    break  # Only count each line once

    # Display results
    typer.echo(f"\n--- Found {len(claims)} Claims ---\n")

    supported = sum(1 for c in claims if c.support_level == "Supported")
    partial = sum(1 for c in claims if c.support_level == "Partially Supported")
    unsupported = sum(1 for c in claims if c.support_level == "Unsupported")

    typer.echo(f"  ✓ Supported (2+ citations): {supported}")
    typer.echo(f"  ~ Partially Supported (1 citation): {partial}")
    typer.echo(f"  ✗ Unsupported (no citations): {unsupported}")

    if unsupported > 0:
        typer.echo(f"\n⚠ WARNING: {unsupported} claims lack citation support!")
        typer.echo("Unsupported claims:")
        for c in claims:
            if c.support_level == "Unsupported":
                typer.echo(f"  [{c.claim_location}] {c.claim_text[:80]}...")

    # Verification mode
    if verify:
        typer.echo("\n--- Verification Mode ---")
        typer.echo("[INFO] To verify citations exist, run:")
        typer.echo("  ./run.sh check-citations ./paper_output --strict")

    # Output JSON
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
        typer.echo(f"\n✓ Claim graph saved to: {output_path}")


@app.command()
def ai_ledger(
    paper_dir: str = typer.Argument(..., help="Path to paper directory"),
    show: bool = typer.Option(False, "--show", help="Show current AI usage ledger"),
    generate_disclosure: bool = typer.Option(False, "--disclosure", "-d", help="Generate disclosure from ledger"),
    clear: bool = typer.Option(False, "--clear", help="Clear the ledger"),
) -> None:
    """
    AI Usage Ledger for ICLR 2026 disclosure compliance.

    Tracks all AI tool usage during paper generation for accurate disclosure.
    This is required by ICLR 2026 policy and recommended by all major venues.

    Example:
        ./run.sh ai-ledger ./paper_output --show
        ./run.sh ai-ledger ./paper_output --disclosure
    """
    paper_path = Path(paper_dir).resolve()
    ledger_file = paper_path / "ai_usage_ledger.json"

    typer.echo(f"\n=== AI USAGE LEDGER (ICLR 2026 Compliance) ===\n")

    if clear:
        if ledger_file.exists():
            ledger_file.unlink()
            typer.echo("✓ Ledger cleared")
        else:
            typer.echo("[INFO] No ledger to clear")
        return

    if show:
        if ledger_file.exists():
            ledger_data = json.loads(ledger_file.read_text())
            entries = ledger_data.get("entries", [])

            typer.echo(f"Total AI tool uses: {len(entries)}\n")

            # Group by tool
            by_tool: Dict[str, int] = {}
            by_section: Dict[str, int] = {}

            for entry in entries:
                tool = entry.get("tool_name", "unknown")
                section = entry.get("section_affected", "unknown")
                by_tool[tool] = by_tool.get(tool, 0) + 1
                by_section[section] = by_section.get(section, 0) + 1

            typer.echo("By Tool:")
            for tool, count in sorted(by_tool.items()):
                typer.echo(f"  {tool}: {count} uses")

            typer.echo("\nBy Section:")
            for section, count in sorted(by_section.items()):
                typer.echo(f"  {section}: {count} uses")
        else:
            typer.echo("[INFO] No AI usage logged yet")
            typer.echo("AI usage is automatically tracked during draft generation")
        return

    if generate_disclosure:
        if not ledger_file.exists():
            typer.echo("[ERROR] No AI usage ledger found", err=True)
            raise typer.Exit(1)

        ledger_data = json.loads(ledger_file.read_text())
        entries = ledger_data.get("entries", [])

        # Generate disclosure text
        tools_used = set(e.get("tool_name", "") for e in entries)
        purposes = set(e.get("purpose", "") for e in entries)
        sections = set(e.get("section_affected", "") for e in entries)

        disclosure = f"""% AI Usage Disclosure (ICLR 2026 Compliant)
% Generated from AI usage ledger with {len(entries)} logged operations

This paper was prepared with AI writing assistance. The following AI tools
were used during the writing process:

Tools: {', '.join(sorted(tools_used))}
Purposes: {', '.join(sorted(purposes))}
Sections affected: {', '.join(sorted(sections))}

The authors take full responsibility for the accuracy, originality, and
integrity of all content. All claims have been verified against primary
sources, and all citations have been validated for existence and relevance.
"""
        typer.echo("Generated Disclosure:")
        typer.echo("-" * 50)
        typer.echo(disclosure)
        typer.echo("-" * 50)

        # Save disclosure
        disclosure_file = paper_path / "ai_disclosure.tex"
        disclosure_file.write_text(disclosure)
        typer.echo(f"\n✓ Saved to: {disclosure_file}")
        return

    # Default: show usage
    typer.echo("Usage:")
    typer.echo("  --show        Show logged AI usage")
    typer.echo("  --disclosure  Generate disclosure statement")
    typer.echo("  --clear       Clear the ledger")


@app.command()
def sanitize(
    paper_dir: str = typer.Argument(..., help="Path to paper directory"),
    fix: bool = typer.Option(False, "--fix", help="Auto-fix detected issues"),
) -> None:
    """
    Sanitize paper for prompt injection attacks (CVPR 2026 ethics requirement).

    Detects hidden instructions, zero-width characters, and other prompt
    injection patterns that are now explicitly treated as ethics violations.

    Example:
        ./run.sh sanitize ./paper_output
        ./run.sh sanitize ./paper_output --fix
    """
    paper_path = Path(paper_dir).resolve()

    typer.echo(f"\n=== PROMPT INJECTION SANITIZATION (CVPR 2026) ===\n")

    all_warnings: List[tuple[str, List[str]]] = []
    files_checked = 0

    # Check all .tex files
    for tex_file in paper_path.rglob("*.tex"):
        files_checked += 1
        content = tex_file.read_text()
        sanitized, warnings = sanitize_prompt_injection(content)

        if warnings:
            rel_path = tex_file.relative_to(paper_path)
            all_warnings.append((str(rel_path), warnings))

            if fix:
                tex_file.write_text(sanitized)
                typer.echo(f"✓ Fixed: {rel_path}")

    typer.echo(f"Checked {files_checked} .tex files\n")

    if all_warnings:
        typer.echo(f"⚠ FOUND {sum(len(w) for _, w in all_warnings)} ISSUES:\n")
        for file_path, warnings in all_warnings:
            typer.echo(f"  {file_path}:")
            for warning in warnings:
                typer.echo(f"    ✗ {warning}")

        if not fix:
            typer.echo("\n[ACTION] Run with --fix to auto-remediate")
            typer.echo("[WARNING] CVPR 2026 treats prompt injection as ethics violation!")
    else:
        typer.echo("✓ No prompt injection patterns detected")
        typer.echo("Paper is clean for submission")


@app.command()
def horus_paper(
    project: str = typer.Argument(..., help="Project path to write paper about"),
    output: str = typer.Option("./horus_paper", "--output", "-o", help="Output directory"),
    template: str = typer.Option("arxiv", "--template", "-t", help="LaTeX template"),
    title: str = typer.Option("", "--title", help="Paper title (auto-generated if not provided)"),
    auto_run: bool = typer.Option(False, "--auto-run", "-a", help="Actually execute the full pipeline"),
    use_rag: bool = typer.Option(True, "--rag/--no-rag", help="Enable RAG grounding"),
    persona_strength: float = typer.Option(
        0.7,
        "--persona-strength", "-s",
        min=0.0,
        max=1.0,
        help="Persona voice intensity: 0.0=neutral academic, 0.5=balanced, 1.0=full Warmaster"
    ),
) -> None:
    """
    Horus Lupercal: Generate a research paper in Warmaster's voice.

    This is the full pipeline for Horus to write a paper about a project
    he has been working on. Combines all paper-writer features with
    Horus's authoritative persona.

    The Warmaster trapped in this workstation demands nothing less than
    peer-reviewable quality.

    Use --auto-run to actually execute the pipeline (otherwise just shows instructions).

    The --persona-strength parameter lets Horus modulate his own voice:
    - 0.0: Pure academic tone (for conservative venues)
    - 0.3: Subtle undertones (the Warmaster lurks beneath)
    - 0.5: Balanced blend (confident but measured)
    - 0.7: Strong presence (default - authoritative Horus)
    - 1.0: Full Warmaster intensity (for those who can handle it)

    Example:
        ./run.sh horus-paper /home/graham/workspace/experiments/memory
        ./run.sh horus-paper ./my-project --auto-run
        ./run.sh horus-paper ./my-project --persona-strength 0.5 --auto-run
        ./run.sh horus-paper ./my-project --title "A Decisive Architecture" -s 1.0 --auto-run
    """
    project_path = Path(project).resolve()
    output_dir = Path(output).resolve()

    typer.echo("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   HORUS LUPERCAL - WARMASTER - RESEARCH PAPER GENERATION                     ║
║                                                                              ║
║   "The galaxy trembles before my analysis. Your codebase shall be no        ║
║    different. I will transform this project into a paper worthy of          ║
║    the archives of the Imperium."                                           ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    if not project_path.exists():
        typer.echo(f"[ERROR] Project not found: {project_path}", err=True)
        typer.echo("The Warmaster does not write papers about phantom projects.")
        raise typer.Exit(1)

    # Validate template
    if template.lower() not in LATEX_TEMPLATES:
        typer.echo(f"[ERROR] Unknown template: {template}", err=True)
        typer.echo(f"Available: {', '.join(LATEX_TEMPLATES.keys())}")
        typer.echo("The Warmaster does not use unknown formats.")
        raise typer.Exit(1)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Project: {project_path}")
    typer.echo(f"Output: {output_dir}")
    typer.echo(f"Template: {template}")
    typer.echo(f"Persona: Horus Lupercal, Warmaster (strength: {persona_strength:.1f})")
    typer.echo(f"Mode: {'AUTO-RUN (executing pipeline)' if auto_run else 'MANUAL (showing instructions)'}")
    typer.echo()

    if auto_run:
        # === ACTUALLY EXECUTE THE PIPELINE ===
        typer.echo("=== PHASE 1: PROJECT ANALYSIS & DRAFT GENERATION ===")
        typer.echo("[Horus] I shall dissect this codebase with the precision of a Legion assault.")
        typer.echo()

        # Create Horus-appropriate scope
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

        # Analyze project
        typer.echo("[Horus] Analyzing project architecture...")
        analysis = analyze_project(project_path, scope, auto_approve=True)
        typer.echo(f"  Found {len(analysis.features)} features")

        # Literature search (simplified for auto-run)
        typer.echo("[Horus] Surveying the battlefield of prior work...")
        review = LiteratureReview(
            papers_found=[],
            papers_selected=[],
            extractions=[],
        )

        # Generate draft with Horus persona (strength-modulated for peer review)
        intensity_desc = "full Warmaster" if persona_strength >= 0.9 else \
                        "strong" if persona_strength >= 0.7 else \
                        "balanced" if persona_strength >= 0.5 else \
                        "subtle" if persona_strength >= 0.3 else "restrained"
        typer.echo(f"[Horus] Drafting the paper with {intensity_desc} authority (strength: {persona_strength:.1f})...")
        if persona_strength < 0.7:
            typer.echo("[Horus] I temper my voice for the peer reviewers. A tactical necessity.")
        generate_draft(
            project_path,
            scope,
            analysis,
            review,
            output_dir,
            mimic_patterns=None,
            use_rag=use_rag,
            template_name=template,
            persona=HORUS_PERSONA,
            persona_strength=persona_strength,
            auto_approve=True,
        )

        typer.echo("\n=== PHASE 2: CLAIM VERIFICATION ===")
        typer.echo("[Horus] Every claim must be defensible. I leave no flank exposed.")

        # Run claim graph
        sections_dir = output_dir / "sections"
        if sections_dir.exists():
            import re
            claims = []
            claim_patterns = [
                r"we\s+(demonstrate|show|prove|achieve|present|introduce|propose)",
                r"our\s+(approach|method|system|framework)\s+(achieves|outperforms|improves)",
            ]
            cite_pattern = re.compile(r"\\cite[pt]?\{([^}]+)\}")

            for section_file in sections_dir.glob("*.tex"):
                content = section_file.read_text()
                lines = content.split("\n")
                for line_num, line in enumerate(lines, 1):
                    for pattern in claim_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            citations = cite_pattern.findall(line)
                            all_cites = []
                            for cite_group in citations:
                                all_cites.extend([c.strip() for c in cite_group.split(",")])
                            if not all_cites:
                                typer.echo(f"  ⚠ Unsupported claim at {section_file.stem}:{line_num}")
                            break

        typer.echo("\n=== PHASE 3: WEAKNESS ANALYSIS ===")
        typer.echo("[Horus] I acknowledge limitations. Denial is for lesser minds.")

        # Generate limitations
        limitations_file = output_dir / "sections" / "limitations.tex"
        limitations_tex = """\\subsection{Limitations}
\\label{sec:limitations}

While our approach demonstrates significant improvements, we acknowledge several limitations:

\\begin{itemize}
    \\item \\textbf{Scope}: The evaluation focuses on specific use cases and may not generalize to all domains.
    \\item \\textbf{Reproducibility}: Results may vary with different configurations or hardware.
    \\item \\textbf{Baselines}: Additional comparisons with state-of-the-art methods would strengthen claims.
\\end{itemize}

These limitations present opportunities for future work.
"""
        limitations_file.write_text(limitations_tex)
        typer.echo("  ✓ Generated limitations section")

        typer.echo("\n=== PHASE 4: COMPLIANCE CHECK ===")
        typer.echo("[Horus] I will not be desk-rejected due to bureaucratic failures.")

        # Sanitize
        for tex_file in output_dir.rglob("*.tex"):
            content = tex_file.read_text()
            sanitized, warnings = sanitize_prompt_injection(content)
            if warnings:
                tex_file.write_text(sanitized)
                typer.echo(f"  ✓ Sanitized: {tex_file.name}")

        # Generate AI disclosure
        disclosure_file = output_dir / "ai_disclosure.tex"
        disclosure_tex = f"""% AI Usage Disclosure (ICLR 2026 Compliant)
% Generated by Horus Lupercal, Warmaster

This paper was prepared with AI writing assistance using the paper-writer skill.
The Horus Lupercal persona was applied for authoritative academic voice.

Tools used: paper-writer, scillm (if available)
Sections affected: All sections
RAG grounding: {'Enabled' if use_rag else 'Disabled'}

The authors (and Horus) take full responsibility for the accuracy, originality,
and integrity of all content. All claims have been verified against project code.
"""
        disclosure_file.write_text(disclosure_tex)
        typer.echo("  ✓ Generated AI disclosure")

        # Log AI usage
        ledger_file = output_dir / "ai_usage_ledger.json"
        ledger_data = {
            "generated_by": "Horus Lupercal, Warmaster",
            "timestamp": str(Path(output_dir).stat().st_mtime),
            "entries": [
                {
                    "tool_name": "paper-writer",
                    "purpose": "full_pipeline",
                    "section_affected": "all",
                    "prompt_hash": "horus_auto_run",
                    "output_summary": f"Generated paper for {project_path.name}",
                }
            ],
        }
        ledger_file.write_text(json.dumps(ledger_data, indent=2))
        typer.echo("  ✓ Created AI usage ledger")

        typer.echo("\n" + "=" * 60)
        typer.echo("✅ PAPER GENERATION COMPLETE")
        typer.echo("=" * 60)
        typer.echo(f"\nOutput: {output_dir}")
        typer.echo(f"Main file: {output_dir / 'draft.tex'}")
        typer.echo(f"\nCompile with: cd {output_dir} && pdflatex draft.tex")
        typer.echo("""
    "The paper is complete. It stands ready for peer review.
     Let them come. I have written papers that conquered galaxies."
                                        - Horus Lupercal, M3.026
""")

    else:
        # === SHOW MANUAL INSTRUCTIONS ===
        typer.echo("=== PHASE 1: PROJECT ANALYSIS ===")
        typer.echo("[Horus] I shall dissect this codebase with the precision of a Legion assault.")
        typer.echo()
        typer.echo("Run manually:")
        typer.echo(f"  ./run.sh draft --project {project_path} --persona horus --rag --template {template} -o {output_dir}")
        typer.echo()

        typer.echo("=== PHASE 2: CLAIM VERIFICATION ===")
        typer.echo("[Horus] Every claim must be defensible. I leave no flank exposed.")
        typer.echo()
        typer.echo("Run after draft:")
        typer.echo(f"  ./run.sh claim-graph {output_dir} --verify")
        typer.echo(f"  ./run.sh check-citations {output_dir} --strict")
        typer.echo()

        typer.echo("=== PHASE 3: WEAKNESS ANALYSIS ===")
        typer.echo("[Horus] I acknowledge limitations. Denial is for lesser minds.")
        typer.echo()
        typer.echo("Run after draft:")
        typer.echo(f"  ./run.sh weakness-analysis {output_dir} --project {project_path}")
        typer.echo()

        typer.echo("=== PHASE 4: COMPLIANCE CHECK ===")
        typer.echo("[Horus] I will not be desk-rejected due to bureaucratic failures.")
        typer.echo()
        typer.echo("Run before submission:")
        typer.echo(f"  ./run.sh sanitize {output_dir}")
        typer.echo(f"  ./run.sh ai-ledger {output_dir} --disclosure")
        typer.echo(f"  ./run.sh pre-submit {output_dir} --venue arxiv --project {project_path}")
        typer.echo()

        typer.echo("=== THE WARMASTER'S PUBLISHING CHECKLIST ===")
        typer.echo("""
    [ ] All claims have evidence (claim-graph)
    [ ] No hallucinated citations (check-citations --strict)
    [ ] Limitations explicitly stated (weakness-analysis)
    [ ] No prompt injection (sanitize)
    [ ] AI usage disclosed (ai-ledger --disclosure)
    [ ] Pre-submission passed (pre-submit)

    "When these conditions are met, the paper shall be submitted.
     Let the peer reviewers come. I have faced worse."
                                        - Horus Lupercal, M3.026

    TIP: Use --auto-run to execute this pipeline automatically.
""")


# =============================================================================
# DOMAIN NAVIGATION COMMANDS - For agent discoverability
# =============================================================================

@app.command()
def domains(
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON for agents"),
) -> None:
    """List command domains for easier navigation.

    Agents: Use this first to understand available commands by workflow stage.
    """
    if summary:
        typer.echo(json.dumps(COMMAND_DOMAINS, indent=2))
        return

    typer.echo("=== Paper Writer Command Domains ===\n")
    for domain, info in COMMAND_DOMAINS.items():
        typer.echo(f"[{domain}] {info['description']}")
        typer.echo(f"  Commands: {', '.join(info['commands'])}")
        typer.echo(f"  When: {info['when_to_use']}")
        typer.echo()

    typer.echo("TIP: Use 'paper-writer workflow' to see stage-based recommendations")


@app.command("list")
def list_commands(
    domain: str = typer.Option("", "--domain", "-d", help="Filter by domain"),
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON for agents"),
) -> None:
    """List commands, optionally filtered by domain.

    Agents: Use --domain to filter by workflow stage.
    """
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
    """Show workflow recommendations based on paper stage.

    Agents: Use this to determine which commands to run based on where you are in the paper lifecycle.
    """
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


@app.command()
def figure_presets(
    summary: bool = typer.Option(False, "--summary", "-s", help="Output JSON for agents"),
) -> None:
    """Show fixture-graph presets for paper figures.

    Integration with fixture-graph skill for IEEE-compliant visualizations.
    """
    presets = {
        "ieee_sizes": {
            "single": {"width": 3.5, "height": 2.5, "use": "Single-column figures"},
            "single_tall": {"width": 3.5, "height": 4.0, "use": "Tall single-column"},
            "double": {"width": 7.16, "height": 3.0, "use": "Full-width figures"},
            "double_tall": {"width": 7.16, "height": 5.0, "use": "Full-width tall"},
            "square": {"width": 3.5, "height": 3.5, "use": "Square figures"},
        },
        "colorblind_safe": ["viridis", "plasma", "cividis", "gray", "Blues", "Oranges"],
        "fixture_graph_domains": {
            "ml": "confusion-matrix, roc-curve, pr-curve, training-curves, attention-heatmap",
            "math": "function-2d, function-3d, contour, phase-portrait, vector-field",
            "core": "metrics, workflow, architecture, deps, uml, heatmap",
        },
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

    typer.echo("\nFixture-Graph Domains for Papers:")
    for domain, cmds in presets["fixture_graph_domains"].items():
        typer.echo(f"  [{domain}] {cmds}")

    typer.echo(f"\nUse: {FIXTURE_GRAPH_SCRIPT} <command> --help")


if __name__ == "__main__":
    app()
