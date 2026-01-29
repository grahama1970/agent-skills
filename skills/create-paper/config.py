"""
Paper Writer Skill - Configuration
Constants, paths, templates, personas, and environment configuration.
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# -----------------------------------------------------------------------------
# Skill Paths
# -----------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent
SKILLS_DIR_COMMON = SCRIPT_DIR.parent

# Add skills directory to path for common imports
if str(SKILLS_DIR_COMMON) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR_COMMON))

# Skill script paths
ASSESS_SCRIPT = SKILLS_DIR / "assess" / "assess.py"
DOGPILE_SCRIPT = SKILLS_DIR / "dogpile" / "run.sh"
ARXIV_SCRIPT = SKILLS_DIR / "arxiv" / "run.sh"
CODE_REVIEW_SCRIPT = SKILLS_DIR / "code-review" / "code_review.py"
MEMORY_SCRIPT = SKILLS_DIR / "memory" / "run.sh"
FIXTURE_GRAPH_SCRIPT = SKILLS_DIR / "fixture-graph" / "run.sh"
SCILLM_SCRIPT = SKILLS_DIR / "scillm" / "run.sh"
INTERVIEW_SKILL = SKILLS_DIR / "interview" / "run.sh"

# MIMIC state file
MIMIC_STATE_FILE = SCRIPT_DIR / ".mimic_state.json"

# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------


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
    """Retrieval-Augmented Generation context for grounding."""
    code_snippets: List[Dict[str, str]]  # {"file": str, "content": str, "type": str}
    project_facts: List[str]  # Verified statements about the project
    paper_excerpts: List[Dict[str, str]]  # {"paper_id": str, "excerpt": str, "topic": str}
    research_facts: List[str]  # External research findings
    section_constraints: Dict[str, List[str]]  # section_key -> list of constraints


@dataclass
class LiteratureReview:
    """Papers found and selected."""
    papers_found: List[Dict[str, Any]]
    papers_selected: List[str]
    extractions: List[Dict[str, Any]]


@dataclass
class ClaimEvidence:
    """A claim linked to its evidence sources."""
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
    prompt_hash: str  # Hash of prompt for provenance
    output_summary: str  # Brief summary of what was generated


# -----------------------------------------------------------------------------
# Command Domains - For agent discoverability
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Horus Lupercal Persona
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# LaTeX Templates
# -----------------------------------------------------------------------------
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

# Document length configurations
LENGTH_CONFIGS = {
    "paper": {
        "name": "Conference Paper",
        "pages": (5, 10),
        "sections": ["abstract", "intro", "related", "method", "eval", "conclusion"],
        "words_per_section": 800,
        "max_chapters": 0,
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
        "sections": None,
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

# -----------------------------------------------------------------------------
# Venue Policies
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Critique Aspects
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Academic Phrases
# -----------------------------------------------------------------------------

ACADEMIC_PHRASES = {
    "intro": {
        "problem": [
            "Despite significant advances in X, Y remains a challenging problem.",
            "While prior work has addressed X, the problem of Y remains open.",
            "Existing approaches to X suffer from limitations in Y.",
        ],
        "motivation": [
            "This work is motivated by the observation that...",
            "The need for X becomes apparent when considering...",
            "Practical applications demand solutions that...",
        ],
        "contribution": [
            "The main contributions of this paper are:",
            "We make the following contributions:",
            "This paper presents three key advances:",
        ],
    },
    "related": {
        "category": [
            "Prior work on X can be categorized into...",
            "Approaches to X fall into several categories:",
            "The literature on X spans several research directions:",
        ],
        "contrast": [
            "Unlike prior approaches, our method...",
            "In contrast to X, we propose...",
            "While Y addresses the problem of X, our approach...",
        ],
    },
    "method": {
        "overview": [
            "We now describe our approach in detail.",
            "This section presents our methodology.",
            "We introduce a novel approach based on...",
        ],
        "formulation": [
            "Formally, we define X as...",
            "Let X denote the set of...",
            "We formulate the problem as follows:",
        ],
    },
    "eval": {
        "setup": [
            "We evaluate our approach on...",
            "Experiments are conducted on...",
            "We compare against the following baselines:",
        ],
        "results": [
            "Table X shows the results of...",
            "As shown in Figure Y, our approach...",
            "The results demonstrate that...",
        ],
    },
    "discussion": {
        "limitation": [
            "Our approach has several limitations:",
            "While effective, our method assumes...",
            "Future work could address...",
        ],
        "future": [
            "Several directions for future work emerge:",
            "An interesting extension would be...",
            "Future research could explore...",
        ],
    },
}

HORUS_ACADEMIC_PHRASES = {
    "intro": {
        "problem": [
            "The tactical inadequacy of existing approaches is evident.",
            "Prior methods fail where precision is demanded.",
            "This weakness in the field cannot stand unchallenged.",
        ],
        "motivation": [
            "Strategic necessity demands a superior solution.",
            "The inefficiency of current methods is unacceptable.",
            "We address a critical vulnerability in the existing paradigm.",
        ],
        "contribution": [
            "This work delivers decisive improvements:",
            "We present an approach of superior design:",
            "The following advances establish clear dominance:",
        ],
    },
    "related": {
        "category": [
            "The landscape of prior work reveals patterns of mediocrity.",
            "Existing approaches cluster into predictable categories.",
            "The history of attempts in this domain is instructive.",
        ],
        "contrast": [
            "Where others have faltered, our approach succeeds.",
            "The contrast with prior methods is stark and decisive.",
            "Unlike the incremental progress of existing work...",
        ],
    },
    "method": {
        "overview": [
            "We now present our tactical approach.",
            "The methodology proceeds with precision.",
            "Our strategy unfolds as follows.",
        ],
        "formulation": [
            "The formal structure is necessarily rigorous.",
            "We define the problem with exactitude.",
            "Precision in formulation ensures precision in execution.",
        ],
    },
    "eval": {
        "setup": [
            "We subject our approach to rigorous evaluation.",
            "The experimental protocol admits no ambiguity.",
            "We compare against the strongest available opposition.",
        ],
        "results": [
            "The results leave no room for debate.",
            "Performance margins are decisive.",
            "The evidence overwhelmingly supports our approach.",
        ],
    },
    "discussion": {
        "limitation": [
            "We acknowledge tactical constraints where they exist.",
            "Certain scenarios remain beyond current scope.",
            "Honesty about limitations enables future conquest.",
        ],
        "future": [
            "The path forward is clear.",
            "Further advances will build upon this foundation.",
            "Strategic opportunities for extension present themselves.",
        ],
    },
}

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def get_template(template_name: str) -> Dict[str, Any]:
    """Get LaTeX template by name."""
    return LATEX_TEMPLATES.get(template_name.lower(), LATEX_TEMPLATES["ieee"])


def list_templates() -> List[str]:
    """List available template names."""
    return list(LATEX_TEMPLATES.keys())


def get_length_config(length: str) -> Dict[str, Any]:
    """Get document length configuration by name."""
    return LENGTH_CONFIGS.get(length.lower(), LENGTH_CONFIGS["paper"])
