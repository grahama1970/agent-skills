#!/usr/bin/env python3
"""Brandon Bailey Simulacrum - Scope Enforcement.

Handles out-of-scope queries gracefully with helpful guidance.
SPARTA has specific domain boundaries - this module enforces them.

Usage:
    from scope_enforcement import handle_out_of_scope, is_in_scope

    if not is_in_scope(intent_action):
        response = handle_out_of_scope(query, intent_action)
"""

from typing import Any

# SPARTA's domain scope - what Brandon can definitively answer
SPARTA_SCOPE = """
**SPARTA covers space system cybersecurity threats and countermeasures:**

- Spacecraft bus and payload security
- Ground station vulnerabilities
- RF/communication link threats (uplink, downlink, crosslink)
- Command and telemetry security
- Orbital mechanics exploitation
- Space vehicle software security
- Mission control system security

**NOT in scope:**

- General IT CVEs (unless space-system specific)
- Non-space embedded systems
- Theoretical attacks without SPARTA technique mapping
- Vendor-specific vulnerabilities not in SPARTA
- Classified or export-controlled information
"""

# Keywords that might indicate a query could be reformulated
REFORMULATION_HINTS = {
    "cve": "For CVE mappings, ask about specific CWE categories in SPARTA (e.g., 'What CWEs apply to uplink command injection?')",
    "ransomware": "For malware threats, ask about SPARTA persistence or execution techniques",
    "phishing": "For social engineering, ask about ground station access control weaknesses",
    "password": "For authentication issues, ask about SPARTA access control techniques",
    "firewall": "For network security, ask about ground segment network isolation controls",
    "encryption": "For cryptographic questions, ask about SPARTA communication link protection",
    "patch": "For vulnerability management, ask about SPARTA software update security controls",
    "audit": "For logging/monitoring, ask about SPARTA detection and monitoring techniques",
    "iot": "For IoT-like devices, ask about SPARTA payload or sensor security",
    "cloud": "For cloud security, ask about ground segment infrastructure protection",
}


def is_in_scope(intent_action: str) -> bool:
    """Check if the intent mapper determined the query is in scope.

    Args:
        intent_action: Action from intent mapper (QUERY, CLARIFY, NO_MATCH)

    Returns:
        True if query is in SPARTA scope, False otherwise
    """
    return intent_action != "NO_MATCH"


def suggest_reformulation(query: str) -> str | None:
    """Suggest a SPARTA-relevant reformulation if possible.

    Args:
        query: The user's original query

    Returns:
        A suggestion string, or None if no relevant reformulation found
    """
    query_lower = query.lower()

    for keyword, suggestion in REFORMULATION_HINTS.items():
        if keyword in query_lower:
            return suggestion

    return None


def handle_out_of_scope(query: str, intent_action: str) -> dict[str, Any]:
    """Generate appropriate response for out-of-scope queries.

    Args:
        query: The user's original query
        intent_action: Action from intent mapper

    Returns:
        Dict with response, in_scope flag, and optional suggestion
    """
    if intent_action != "NO_MATCH":
        return {"in_scope": True}

    suggestion = suggest_reformulation(query)

    response_parts = [
        "That question falls outside SPARTA's scope.",
        "",
        SPARTA_SCOPE,
    ]

    if suggestion:
        response_parts.extend([
            "",
            "**Suggestion:**",
            suggestion,
        ])

    response_parts.extend([
        "",
        "If you believe this IS a space cybersecurity question, try rephrasing "
        "with specific SPARTA terminology (technique names, control IDs, or "
        "space system components).",
    ])

    return {
        "response": "\n".join(response_parts),
        "in_scope": False,
        "suggestion": suggestion,
        "original_query": query,
    }


def get_scope_examples() -> list[dict[str, str]]:
    """Get example queries showing in-scope vs out-of-scope.

    Returns:
        List of example dicts with 'query', 'in_scope', and 'explanation'
    """
    return [
        {
            "query": "How do I detect RF jamming attacks on satellite uplinks?",
            "in_scope": True,
            "explanation": "RF threats to space communication links are core SPARTA domain",
        },
        {
            "query": "What controls protect against command injection in uplink?",
            "in_scope": True,
            "explanation": "Uplink command security is directly covered by SPARTA",
        },
        {
            "query": "What is CVE-2024-1234?",
            "in_scope": False,
            "explanation": "Generic CVE lookup is not SPARTA's purpose",
        },
        {
            "query": "How do I configure a firewall?",
            "in_scope": False,
            "explanation": "General IT configuration is out of scope",
        },
        {
            "query": "What are the SPARTA techniques for ground station compromise?",
            "in_scope": True,
            "explanation": "Ground segment threats are core SPARTA domain",
        },
        {
            "query": "What's the weather in Houston?",
            "in_scope": False,
            "explanation": "Completely unrelated to space cybersecurity",
        },
    ]


def format_scope_help() -> str:
    """Format help text explaining SPARTA's scope.

    Returns:
        Formatted help text for users
    """
    examples = get_scope_examples()

    in_scope = [e for e in examples if e["in_scope"]]
    out_scope = [e for e in examples if not e["in_scope"]]

    lines = [
        "# Understanding SPARTA Scope",
        "",
        SPARTA_SCOPE,
        "",
        "## Example Questions I Can Answer:",
        "",
    ]

    for ex in in_scope[:3]:
        lines.append(f'- "{ex["query"]}"')

    lines.extend([
        "",
        "## Example Questions Outside My Scope:",
        "",
    ])

    for ex in out_scope[:3]:
        lines.append(f'- "{ex["query"]}"')

    lines.extend([
        "",
        "For questions outside SPARTA's scope, consider:",
        "- NIST Cybersecurity Framework for general security",
        "- MITRE ATT&CK for adversary techniques",
        "- NVD for CVE lookups",
        "- Consulting The Aerospace Corporation for novel space threats",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    # Quick self-test
    print("Testing scope enforcement...")

    # Test out-of-scope handling
    result = handle_out_of_scope("What is the weather in Paris?", "NO_MATCH")
    assert result["in_scope"] is False, "Weather query should be out of scope"
    assert result["suggestion"] is None, "No suggestion for weather query"

    # Test reformulation suggestion
    result = handle_out_of_scope("How do I protect against ransomware?", "NO_MATCH")
    assert result["in_scope"] is False
    assert result["suggestion"] is not None, "Should suggest SPARTA alternative"
    assert "persistence" in result["suggestion"].lower()

    # Test in-scope passthrough
    result = handle_out_of_scope("RF jamming detection", "QUERY")
    assert result["in_scope"] is True

    print("All tests passed!")
    print("\n" + "=" * 60)
    print("Scope Help:")
    print("=" * 60)
    print(format_scope_help())
