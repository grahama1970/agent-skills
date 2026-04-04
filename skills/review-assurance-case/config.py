"""Configuration for review-assurance-case skill.

Contains:
- Provider configurations (same registry as review-code)
- Review check definitions (47 checks across 7 categories)
- Severity levels and scoring weights
"""
from __future__ import annotations

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent

# ---------------------------------------------------------------------------
# Provider configurations (mirrors review-code/config.py)
# ---------------------------------------------------------------------------

PROVIDERS = {
    "github": {
        "cli": "copilot",
        "models": {
            "gpt-5": "gpt-5",
            "claude-sonnet-4": "claude-sonnet-4",
            "claude-sonnet-4.5": "claude-sonnet-4.5",
            "claude-haiku-4.5": "claude-haiku-4.5",
        },
        "default_model": "gpt-5",
        "env": {"COPILOT_ALLOW_ALL": "1"},
        "cost": "free",
        "supports_continue": True,
    },
    "anthropic": {
        "cli": "claude",
        "models": {
            "opus": "opus",
            "sonnet": "sonnet",
            "haiku": "haiku",
        },
        "default_model": "sonnet",
        "env": {},
        "cost": "paid",
        "supports_continue": True,
    },
    "openai": {
        "cli": "codex",
        "models": {
            "codex-5.3": "codex-5.3",
            "gpt-5.2-codex": "gpt-5.2-codex",
            "o3": "o3",
        },
        "default_model": "codex-5.3",
        "default_reasoning": "high",
        "env": {},
        "supports_reasoning": True,
        "supports_continue": False,
        "cost": "paid",
    },
    "google": {
        "cli": "gemini",
        "models": {
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-pro": "gemini-2.5-pro",
        },
        "default_model": "gemini-2.5-flash",
        "env": {},
        "supports_continue": False,
        "cost": "paid",
    },
}

DEFAULT_PROVIDER = "github"
DEFAULT_MODEL = PROVIDERS[DEFAULT_PROVIDER]["default_model"]

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# ---------------------------------------------------------------------------
# Review checks: 47 checks across 7 categories
# ---------------------------------------------------------------------------

CHECKS = {
    # --- Category 1: Structural Integrity (Programmatic) ---
    "S-01": {
        "category": "structural",
        "title": "Every claim has at least one argument/strategy",
        "description": "A goal/claim with no decomposition is structurally incomplete.",
        "source": "GSN Community Standard, CAE Connection Rules",
        "type": "programmatic",
        "severity": SEVERITY_CRITICAL,
    },
    "S-02": {
        "category": "structural",
        "title": "Every strategy has at least one sub-goal or solution",
        "description": "A strategy that decomposes into nothing is a dead end.",
        "source": "GSN Community Standard",
        "type": "programmatic",
        "severity": SEVERITY_CRITICAL,
    },
    "S-03": {
        "category": "structural",
        "title": "Every argument chain terminates in evidence",
        "description": "Leaf nodes must be solutions (GSN) or evidence (CAE), not claims.",
        "source": "GSN, CAE, SACM",
        "type": "programmatic",
        "severity": SEVERITY_CRITICAL,
    },
    "S-04": {
        "category": "structural",
        "title": "No dangling nodes",
        "description": "Every node must be reachable from a top-level goal.",
        "source": "SACM completeness requirement",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "S-05": {
        "category": "structural",
        "title": "No cycles in argument graph",
        "description": "Argument decomposition must be a DAG. Cycles indicate circular reasoning.",
        "source": "GSN well-formedness, CAE circular argument fallacy",
        "type": "programmatic",
        "severity": SEVERITY_CRITICAL,
    },
    "S-06": {
        "category": "structural",
        "title": "Type-correct connections",
        "description": "Claims→arguments, evidence→arguments only. No type violations.",
        "source": "CAE Connection Rules (NPSA), GSN Community Standard",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "S-07": {
        "category": "structural",
        "title": "No undeveloped markers remain",
        "description": "Zero 'in development' or undeveloped nodes for a complete case.",
        "source": "GSN Community Standard",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "S-08": {
        "category": "structural",
        "title": "Every claim has a context node",
        "description": "Context frames interpretation. Claim without context is ambiguous.",
        "source": "GSN (context element), ISO 15026-2",
        "type": "programmatic",
        "severity": SEVERITY_MEDIUM,
    },
    "S-09": {
        "category": "structural",
        "title": "Choice junctions specify M-of-N logic",
        "description": "OR-decompositions must state how many paths are required.",
        "source": "GSN Choice Junction element",
        "type": "programmatic",
        "severity": SEVERITY_MEDIUM,
    },
    "S-10": {
        "category": "structural",
        "title": "Module boundaries have interface goals",
        "description": "Modular cases must declare boundary claims and requirements.",
        "source": "GSN Annex B (modular arguments)",
        "type": "programmatic",
        "severity": SEVERITY_LOW,
    },
    # --- Category 2: Logical Soundness (LLM) ---
    "L-01": {
        "category": "logical",
        "title": "Arguments are valid inference steps",
        "description": "Sub-claims + evidence must logically entail the parent claim.",
        "source": "CAE side-warrant requirement, GSN strategy semantics",
        "type": "llm",
        "severity": SEVERITY_CRITICAL,
    },
    "L-02": {
        "category": "logical",
        "title": "No relevance fallacies",
        "description": "No red herrings, improper authorities, wrong conclusions.",
        "source": "Defeater Taxonomy (Relevance Fallacies)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "L-03": {
        "category": "logical",
        "title": "No acceptability fallacies",
        "description": "No circular arguments, false dichotomy, faulty analogy, ambiguity.",
        "source": "Defeater Taxonomy (Acceptability Fallacies)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "L-04": {
        "category": "logical",
        "title": "No sufficiency fallacies",
        "description": "No pseudo-precision, hasty generalization, arguing from ignorance.",
        "source": "Defeater Taxonomy (Sufficiency Fallacies)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "L-05": {
        "category": "logical",
        "title": "Argument type is identifiable",
        "description": "Each argument should be Decomposition, Substitution, Concretion, Calculation, or Evidence Incorporation.",
        "source": "CAE Building Blocks",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "L-06": {
        "category": "logical",
        "title": "Deductive vs inductive reasoning distinguished",
        "description": "Claims of deductive certainty with inductive evidence are overstated.",
        "source": "CAE Blocks framework",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "L-07": {
        "category": "logical",
        "title": "Strategy describes argument, not activity",
        "description": "'Argument by testing all interfaces' is valid. 'We tested' is not an argument.",
        "source": "GSN Community Standard",
        "type": "llm",
        "severity": SEVERITY_LOW,
    },
    # --- Category 3: Evidence Sufficiency (Mixed) ---
    "E-01": {
        "category": "evidence",
        "title": "Evidence references concrete artifacts",
        "description": "Every evidence node must reference a specific document, test report, or data set.",
        "source": "ISO 26262, CMMC, DO-178C",
        "type": "mixed",
        "severity": SEVERITY_CRITICAL,
    },
    "E-02": {
        "category": "evidence",
        "title": "Evidence is in final form",
        "description": "No drafts, working papers, or unapproved documents.",
        "source": "CMMC Assessment Guide",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "E-03": {
        "category": "evidence",
        "title": "Evidence provenance recorded",
        "description": "Who produced it, when, under what process, with what tools.",
        "source": "ISO 26262, DO-178C (tool qualification)",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "E-04": {
        "category": "evidence",
        "title": "Evidence is relevant to claimed property",
        "description": "Content must address the actual property being claimed.",
        "source": "CAE (evidence relevance)",
        "type": "llm",
        "severity": SEVERITY_CRITICAL,
    },
    "E-05": {
        "category": "evidence",
        "title": "Evidence is reliable",
        "description": "External > internal. Direct > indirect. Qualified process > ad-hoc.",
        "source": "Audit evidence hierarchy, DO-178C independence",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "E-06": {
        "category": "evidence",
        "title": "Evidence quantity proportional to risk",
        "description": "Higher-criticality claims need more evidence. Single test report insufficient for catastrophic.",
        "source": "DO-178C (DAL), IEC 61508 (SIL), ISO 26262 (ASIL)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "E-07": {
        "category": "evidence",
        "title": "Evidence is not stale",
        "description": "Test results from previous version may not apply to current version.",
        "source": "ISO 26262 (configuration management)",
        "type": "mixed",
        "severity": SEVERITY_MEDIUM,
    },
    "E-08": {
        "category": "evidence",
        "title": "Independence requirements met where mandated",
        "description": "High-assurance verification evidence must be independent of development.",
        "source": "DO-178C, IEC 61508",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "E-09": {
        "category": "evidence",
        "title": "Testing covers realistic conditions",
        "description": "Idealized test conditions don't transfer to operational environment.",
        "source": "Defeater taxonomy (Testing/Validation Issues)",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "E-10": {
        "category": "evidence",
        "title": "ML/AI evidence addresses robustness and drift",
        "description": "ML components need training data coverage, robustness, and drift analysis.",
        "source": "Defeater taxonomy (ML/AI Concerns)",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    # --- Category 4: Completeness (Mixed) ---
    "C-01": {
        "category": "completeness",
        "title": "All threats/hazards have corresponding claims",
        "description": "Cross-reference hazard analysis against top-level goals.",
        "source": "ISO 26262 (HARA traceability), IEC 61508",
        "type": "mixed",
        "severity": SEVERITY_CRITICAL,
    },
    "C-02": {
        "category": "completeness",
        "title": "All requirements traced to claims and evidence",
        "description": "Bidirectional traceability: requirement→claim→evidence.",
        "source": "DO-178C, CMMC",
        "type": "programmatic",
        "severity": SEVERITY_CRITICAL,
    },
    "C-03": {
        "category": "completeness",
        "title": "Assumptions explicitly stated",
        "description": "Every assumption must be a declared element, not hidden in prose.",
        "source": "GSN (Assumption element), ISO 15026-2",
        "type": "mixed",
        "severity": SEVERITY_HIGH,
    },
    "C-04": {
        "category": "completeness",
        "title": "All assumptions justified or validated",
        "description": "Each assumption should be validated by evidence or accepted as residual risk.",
        "source": "GSN, Assurance 2.0",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "C-05": {
        "category": "completeness",
        "title": "Counter-arguments/defeaters identified and addressed",
        "description": "A case with zero defeaters is suspicious. Known defeaters must be refuted or accepted.",
        "source": "Assurance 2.0 (eliminative argumentation)",
        "type": "llm",
        "severity": SEVERITY_CRITICAL,
    },
    "C-06": {
        "category": "completeness",
        "title": "All defeaters closed",
        "description": "Open defeaters propagate 'unsupported' status upward.",
        "source": "Assurance 2.0 truth-value propagation",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "C-07": {
        "category": "completeness",
        "title": "Residual risks documented",
        "description": "Sustained defeaters must be recorded with acceptance justification.",
        "source": "Assurance 2.0",
        "type": "mixed",
        "severity": SEVERITY_HIGH,
    },
    "C-08": {
        "category": "completeness",
        "title": "Framework control coverage demonstrated",
        "description": "CMMC: every practice has evidence. DO-178C: all objectives addressed.",
        "source": "CMMC, DO-178C, ISO 26262",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "C-09": {
        "category": "completeness",
        "title": "No missing requirements",
        "description": "Requirements must be complete — missing, incorrect, ambiguous, outdated all flagged.",
        "source": "Defeater taxonomy (Requirements Engineering Defeaters)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "C-10": {
        "category": "completeness",
        "title": "Structural defeaters addressed",
        "description": "Single points of failure and dangerous interdependencies must be argued about.",
        "source": "Defeater taxonomy (Structural Defeaters)",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    # --- Category 5: Confidence Calibration (LLM) ---
    "CF-01": {
        "category": "confidence",
        "title": "Confidence levels stated explicitly",
        "description": "If 'high confidence' is claimed, the basis must be articulated.",
        "source": "Assurance 2.0 (four-component confidence model)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "CF-02": {
        "category": "confidence",
        "title": "Confidence accounts for all four components",
        "description": "Logical, probabilistic, defeaters, and residual risks all considered.",
        "source": "Assurance 2.0 confidence framework",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "CF-03": {
        "category": "confidence",
        "title": "No pseudo-precision",
        "description": "Precise numerical probabilities without statistical basis is a fallacy.",
        "source": "Defeater taxonomy (Pseudo-Precision)",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "CF-04": {
        "category": "confidence",
        "title": "Verification vs validation distinguished",
        "description": "Model verification confidence differs from real-world validation confidence.",
        "source": "CAE Blocks, DO-178C",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "CF-05": {
        "category": "confidence",
        "title": "Epistemic vs aleatoric uncertainty distinguished",
        "description": "Epistemic (reducible) should drive evidence gathering. Aleatoric (inherent) must be quantified.",
        "source": "Defeater taxonomy (Uncertainty Defeaters)",
        "type": "llm",
        "severity": SEVERITY_LOW,
    },
    "CF-06": {
        "category": "confidence",
        "title": "Ontological uncertainty acknowledged",
        "description": "A case claiming to address ALL risks without qualification is overconfident.",
        "source": "Defeater taxonomy (Ontological Uncertainties)",
        "type": "llm",
        "severity": SEVERITY_LOW,
    },
    # --- Category 6: Contextual Validity (LLM) ---
    "CX-01": {
        "category": "contextual",
        "title": "Operational context explicitly defined",
        "description": "Environment, mission profile, user population, constraints must be stated.",
        "source": "GSN (Context element), ISO 26262 (item definition)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "CX-02": {
        "category": "contextual",
        "title": "Evidence valid for stated context",
        "description": "Test evidence from one environment doesn't auto-transfer to another.",
        "source": "Defeater taxonomy (Contextual Defeaters)",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    "CX-03": {
        "category": "contextual",
        "title": "Human factors addressed",
        "description": "If human operators involved, human error modes must be part of argument.",
        "source": "Defeater taxonomy (Human Errors), IEC 61508",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "CX-04": {
        "category": "contextual",
        "title": "Configuration management traceable",
        "description": "Specific system version/configuration that case applies to must be stated.",
        "source": "Defeater taxonomy (Configuration Errors), ISO 26262, DO-178C",
        "type": "mixed",
        "severity": SEVERITY_HIGH,
    },
    "CX-05": {
        "category": "contextual",
        "title": "Environmental factors addressed",
        "description": "Temperature, radiation, EMI — whatever is relevant to the domain.",
        "source": "Defeater taxonomy (Environmental Factors), IEC 61508",
        "type": "llm",
        "severity": SEVERITY_MEDIUM,
    },
    "CX-06": {
        "category": "contextual",
        "title": "Adversarial threats addressed (security cases)",
        "description": "If deliberate attacks possible, must argue adversarial resilience.",
        "source": "Defeater taxonomy (Adversarial Defeaters), CMMC",
        "type": "llm",
        "severity": SEVERITY_HIGH,
    },
    # --- Category 7: Process Compliance (Programmatic) ---
    "P-01": {
        "category": "process",
        "title": "Assessment methods include examine, interview, AND test",
        "description": "Document review alone is insufficient for full assessment.",
        "source": "CMMC Assessment Process (CAP)",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "P-02": {
        "category": "process",
        "title": "All evidence artifacts approved/final",
        "description": "No drafts, working papers, or unapproved documents.",
        "source": "CMMC Assessment Guide",
        "type": "programmatic",
        "severity": SEVERITY_HIGH,
    },
    "P-03": {
        "category": "process",
        "title": "Tool qualification evidence exists",
        "description": "Automated tools used for verification must be qualified.",
        "source": "DO-178C (DO-330 tool qualification)",
        "type": "programmatic",
        "severity": SEVERITY_MEDIUM,
    },
    "P-04": {
        "category": "process",
        "title": "Review independence demonstrated",
        "description": "At appropriate assurance level, reviewer must be independent.",
        "source": "DO-178C (DAL A/B), IEC 61508 (SIL 3/4)",
        "type": "programmatic",
        "severity": SEVERITY_MEDIUM,
    },
    "P-05": {
        "category": "process",
        "title": "Problem reports closed or dispositioned",
        "description": "Open problem reports against evidence items weaken the case.",
        "source": "DO-178C (problem reporting), ISO 26262",
        "type": "programmatic",
        "severity": SEVERITY_MEDIUM,
    },
    "P-06": {
        "category": "process",
        "title": "Case maintained through lifecycle",
        "description": "Case produced at design time but not updated is stale.",
        "source": "ISO 26262, ISO 15026-2",
        "type": "programmatic",
        "severity": SEVERITY_MEDIUM,
    },
}

# Category weights for overall scoring
CATEGORY_WEIGHTS = {
    "structural": 0.20,
    "logical": 0.20,
    "evidence": 0.20,
    "completeness": 0.15,
    "confidence": 0.10,
    "contextual": 0.10,
    "process": 0.05,
}

# Verdict thresholds (weighted average of category scores)
VERDICT_ADEQUATE = 7.0      # >=7.0 → ADEQUATE
VERDICT_NEEDS_WORK = 4.0    # >=4.0 → NEEDS_WORK
# < 4.0 → INADEQUATE


def get_checks_by_category(category: str) -> dict:
    """Get all checks for a specific category."""
    return {k: v for k, v in CHECKS.items() if v["category"] == category}


def get_checks_by_type(check_type: str) -> dict:
    """Get all checks by type (programmatic, llm, mixed)."""
    return {k: v for k, v in CHECKS.items() if v["type"] == check_type}


def get_timeout(default: int = 30) -> int:
    """Get timeout from ASSURANCE_REVIEW_TIMEOUT env var."""
    try:
        return int(os.environ.get("ASSURANCE_REVIEW_TIMEOUT", default))
    except (TypeError, ValueError):
        return default
