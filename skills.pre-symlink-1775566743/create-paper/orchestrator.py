"""
Paper Writer Skill - create-paper
AI-assisted academic paper writing with interview-driven workflow.

Modules:
    config       - Constants, paths, dataclasses, templates, venue policies
    utils        - Resilience patterns, AI usage logging, sanitization
    analysis     - Project analysis (assess, dogpile, code-review)
    research     - Literature search and knowledge learning
    grounding    - RAG grounding context, claim verification, grounded prompts
    figures      - Figure generation using fixture-graph
    sections     - Section content generation, interview scope, persona prompts
    mimic        - Style pattern extraction and mimicking from exemplars
    citations    - Citation verification (arXiv, DOI, Semantic Scholar)
    critique     - Quality metrics, aspect critique, weakness analysis
    compliance   - Disclosure generation, pre-submit checks, sanitization
    draft        - Draft generation pipeline orchestrator
    cli_quality  - Quality/verification/compliance CLI commands
    rag          - Lightweight RAG helpers (simple build/verify)
    paper_writer - CLI entry point
"""

# Dataclasses
from config import (
    AgentPersona,
    AIUsageEntry,
    ClaimEvidence,
    LiteratureReview,
    MimicPatterns,
    PaperScope,
    ProjectAnalysis,
    RAGContext,
)

# Core functions
from analysis import analyze_project
from citations import (
    check_citations,
    verify_arxiv_id,
    verify_citation_from_bib,
    verify_doi,
    verify_semantic_scholar,
)
from compliance import (
    generate_ai_ledger_disclosure,
    generate_disclosure,
    run_pre_submit_checks,
    sanitize_paper,
)
from critique import (
    compute_quality_metrics,
    critique_section,
    generate_weakness_analysis,
)
from draft import generate_draft_pipeline, generate_horus_pipeline
from figures import generate_figures
from grounding import (
    build_rag_context,
    extract_code_snippets,
    generate_bibtex_from_arxiv,
    generate_grounded_prompt,
    verify_grounding,
)
from mimic import (
    analyze_exemplars,
    apply_mimic_guidance,
    apply_style_transfer,
    extract_style_patterns,
    load_mimic_patterns,
    load_mimic_state,
    select_exemplar_papers,
    store_mimic_patterns,
    validate_against_exemplars,
)
from research import (
    fetch_paper_details,
    learn_from_papers,
    search_arxiv_papers,
    search_literature,
)
from sections import (
    apply_persona_to_prompt,
    generate_section_content,
    get_phrases,
    interview_scope,
)
from utils import (
    RateLimiter,
    get_ai_usage_ledger,
    get_memory_limiter,
    load_persona,
    log_ai_usage,
    sanitize_prompt_injection,
    with_retries,
)

__all__ = [
    # Dataclasses
    "AgentPersona",
    "AIUsageEntry",
    "ClaimEvidence",
    "LiteratureReview",
    "MimicPatterns",
    "PaperScope",
    "ProjectAnalysis",
    "RAGContext",
    # Analysis
    "analyze_project",
    # Citations
    "check_citations",
    "verify_arxiv_id",
    "verify_citation_from_bib",
    "verify_doi",
    "verify_semantic_scholar",
    # Compliance
    "generate_ai_ledger_disclosure",
    "generate_disclosure",
    "run_pre_submit_checks",
    "sanitize_paper",
    # Critique
    "compute_quality_metrics",
    "critique_section",
    "generate_weakness_analysis",
    # Draft
    "generate_draft_pipeline",
    "generate_horus_pipeline",
    # Figures
    "generate_figures",
    # Grounding
    "build_rag_context",
    "extract_code_snippets",
    "generate_bibtex_from_arxiv",
    "generate_grounded_prompt",
    "verify_grounding",
    # MIMIC
    "analyze_exemplars",
    "apply_mimic_guidance",
    "apply_style_transfer",
    "extract_style_patterns",
    "load_mimic_patterns",
    "load_mimic_state",
    "select_exemplar_papers",
    "store_mimic_patterns",
    "validate_against_exemplars",
    # Research
    "fetch_paper_details",
    "learn_from_papers",
    "search_arxiv_papers",
    "search_literature",
    # Sections
    "apply_persona_to_prompt",
    "generate_section_content",
    "get_phrases",
    "interview_scope",
    # Utils
    "RateLimiter",
    "get_ai_usage_ledger",
    "get_memory_limiter",
    "load_persona",
    "log_ai_usage",
    "sanitize_prompt_injection",
    "with_retries",
]
