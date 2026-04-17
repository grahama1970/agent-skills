"""Strategy pool definitions and evidence collectors per category.

Each question category has predefined strategies. /assistant selects from
these, and /recommend-skill-chain generates specific skill chains.

Inputs: Category string, question text.
Outputs: Strategy definitions with skill chains.
Failures: Unknown category falls back to "general" pool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyDef:
    """Static definition of a verification strategy."""

    name: str
    skills: list[str]
    description: str
    default_turns: int = 3


# Strategy pools by category
STRATEGY_POOL: dict[str, list[StrategyDef]] = {
    "compliance": [
        StrategyDef(
            name="qra_citation",
            skills=["/memory recall", "/review-conversation"],
            description="Check QRA citations and compliance references",
        ),
        StrategyDef(
            name="taxonomy_bridge",
            skills=["/memory recall", "/taxonomy"],
            description="Verify via taxonomy bridge attributes",
        ),
        StrategyDef(
            name="memory_trace",
            skills=["/memory recall", "/review-conversation"],
            description="Multi-hop graph traversal for compliance evidence",
            default_turns=4,
        ),
    ],
    "code": [
        StrategyDef(
            name="code_trace",
            skills=["/treesitter", "/analytics"],
            description="AST analysis and code path tracing",
        ),
        StrategyDef(
            name="test_verify",
            skills=["/test", "/analytics"],
            description="Run tests and verify assertions",
        ),
        StrategyDef(
            name="treesitter_ast",
            skills=["/treesitter", "/review-design"],
            description="Deep AST inspection for structural claims",
        ),
    ],
    "analytics": [
        StrategyDef(
            name="pandas_profile",
            skills=["/analytics", "/create-figure"],
            description="Data profiling with pandas and visualization",
        ),
        StrategyDef(
            name="viz_render",
            skills=["/create-figure", "/review-design"],
            description="Render visualization and verify correctness",
        ),
        StrategyDef(
            name="aggregation",
            skills=["/analytics", "/memory recall"],
            description="Aggregate metrics from memory and compute stats",
        ),
    ],
    "pipeline": [
        StrategyDef(
            name="step_trace",
            skills=["/review-pdf", "/analytics"],
            description="Trace pipeline step outputs and verify integrity",
        ),
        StrategyDef(
            name="profile_check",
            skills=["/review-pdf", "/extractor-quality-check"],
            description="Check extraction profiles against gold standards",
        ),
        StrategyDef(
            name="convergence",
            skills=["/extractor-quality-check", "/analytics"],
            description="Analyze convergence trends and quality trajectory",
        ),
    ],
    "general": [
        StrategyDef(
            name="memory_search",
            skills=["/memory recall"],
            description="Search memory for evidence",
        ),
        StrategyDef(
            name="conversation_review",
            skills=["/review-conversation"],
            description="Review conversation history for evidence",
        ),
    ],
}

# Composed skills available in v4 orchestrator
COMPOSED_SKILLS: list[str] = [
    "/memory recall",
    "/memory clarify",
    "/extract-entities",
    "/assistant classify",
    "/lean4-prove",
    "/dogpile",
    "/edge-verifier",
    "/cmmc-assessor",
    "/create-gsn-diagram",
    "/export-oscal",
    "/create-figure",
    "/taxonomy",
]


def get_strategies_for_category(category: str) -> list[StrategyDef]:
    """Get strategy pool for a category, with general fallback."""
    return STRATEGY_POOL.get(category, STRATEGY_POOL["general"])


def auto_categorize(claim_text: str) -> str:
    """Simple keyword-based categorization of claims.

    For production use, /assistant would do this classification.
    This is a fast heuristic fallback.
    """
    text = claim_text.lower()

    compliance_kw = {
        "compliance", "do-178", "mil-std", "requirement", "qra", "certification", "safety",
        "sparta", "countermeasure", "nist", "disa", "stig", "threat", "attack", "f-36", "f36",
        "d3fend", "cwe", "att&ck", "att_ck", "mitre", "arp4761", "arp4754", "fadec", "avionics",
        "firmware", "gps", "navigation", "vulnerability", "defense", "cmmc", "itar",
        "supply chain", "c4isr", "dai-a", "dal-b", "mc/dc", "do-178c",
        "spoofing", "jamming", "radar", "satellite", "spacecraft", "cyber", "encryption",
        "authentication", "access control", "secure boot", "telemetry", "payload",
        "ground station", "command and control", "sv-", "cm0", "esa-", "iso 27",
        "space system", "mission assurance", "resilience", "hardening", "mitigation",
        "exploit", "adversary", "intrusion", "denial of service", "interception",
        "manipulation", "injection", "tampering", "reconnaissance", "exfiltration",
        "security", "t1", "ir-", "sc-", "sa-", "si-", "au-", "ca-", "ac-",
        "framework", "mitigat", "protect", "capabilities",
    }
    code_kw = {"code", "function", "class", "import", "test", "bug", "error", "exception"}
    analytics_kw = {"metric", "score", "average", "trend", "degrad", "improv", "count", "how many"}
    pipeline_kw = {"pipeline", "extract", "table_fidelity", "section", "step", "s0", "s1", "profile"}

    # Check compliance FIRST — SPARTA/defense keywords must win over
    # partial matches like "count" in "countermeasure" hitting analytics.
    for kw in compliance_kw:
        if kw in text:
            return "compliance"
    for kw in pipeline_kw:
        if kw in text:
            return "pipeline"
    for kw in analytics_kw:
        if kw in text:
            return "analytics"
    for kw in code_kw:
        if kw in text:
            return "code"
    return "general"


def strategy_complexity(claim_text: str) -> int:
    """Suggest number of concurrent strategies based on question complexity.

    Returns:
        1 for simple, 2 for analytical, 3 for multi-domain.
    """
    text = claim_text.lower()
    # Multi-domain indicators
    if any(w in text for w in ("and", "compare", "versus", "relationship")):
        return 3
    # Analytical indicators
    if any(w in text for w in ("trend", "degrad", "why", "how")):
        return 2
    return 1
