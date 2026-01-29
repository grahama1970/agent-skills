#!/usr/bin/env python3
"""
Taxonomy - Extract Federated Taxonomy tags from text.

LLM extracts candidates, deterministic validation filters to known vocabulary.
Prevents hallucinated tags by validating against allowed values.

Based on:
- TAXONOMY_STRATEGY_ASSESSMENT.md (Federated Taxonomy Model)
- HORUS_TAXONOMY_SPEC.md (Dimensions, Vocabularies, Bridge Attributes)
- horus_taxonomy_verifier.py (Cross-collection multihop implementation)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import click
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "click", "-q"])
    import click


# Bridge Attributes (Tier 0 - Conceptual Bridges)
# Works across: lore ↔ operational ↔ sparta (security)
BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}

# Collection-specific vocabularies
COLLECTION_VOCABULARIES = {
    "lore": {
        "function": {"Catalyst", "Subversion", "Preservation", "Revelation", "Confrontation"},
        "domain": {"Legion", "Imperium", "Chaos", "Primarch", "World"},
        "thematic_weight": {"Betrayal", "Tragedy", "Honor", "Despair"},
        "perspective": {"Frontline", "Political", "Psychological", "Cosmic"},
    },
    "operational": {
        "function": {"Fix", "Optimization", "Refactor", "Hardening", "Debug"},
        "domain": {"Middleware", "Frontend", "Database", "Deployment", "Infrastructure"},
        "thematic_weight": {"Critical", "Technical_Debt", "Security", "Performance"},
        "perspective": {"Architectural", "Operational", "Strategic", "Internal"},
    },
    "sparta": {
        "function": {"Attack", "Defend", "Detect", "Mitigate", "Exploit"},
        "domain": {"Network", "Endpoint", "Identity", "Cloud", "Application"},
        "thematic_weight": {"Critical", "High", "Medium", "Low"},
        "perspective": {"Offensive", "Defensive", "Compliance", "Risk"},
    },
}

# Keyword patterns for fast extraction (no LLM needed)
BRIDGE_KEYWORDS = {
    "Precision": [
        "optimiz", "efficien", "precis", "algorithm", "calculat", "method",
        "iron warriors", "perturabo", "siege craft", "mathematical"
    ],
    "Resilience": [
        "error handl", "fault tol", "robust", "redund", "recover", "resili",
        "siege of terra", "imperial fists", "dorn", "endur", "withstand",
        "harden", "isolate", "restore", "defense"
    ],
    "Fragility": [
        "brittle", "technical debt", "legacy", "fragile", "single point",
        "webway", "magnus", "shatter", "broken", "vulnerability", "weakness",
        "cve", "cwe", "exploit"
    ],
    "Corruption": [
        "bug", "corrupt", "memory leak", "silent fail", "race condition",
        "warp", "chaos", "davin", "taint", "possess", "compromise",
        "breach", "persist", "backdoor", "malware"
    ],
    "Loyalty": [
        "secur", "auth", "encrypt", "complian", "trust", "access control",
        "oaths of moment", "loken", "luna wolves", "loyalist",
        "authentication", "authorization", "nist", "detect", "monitor"
    ],
    "Stealth": [
        "hidden", "infiltrat", "decept", "evas", "undetect",
        "alpha legion", "alpharius", "subterfuge", "obfuscat",
        "anti-forensic", "rootkit"
    ],
}

# LLM prompt template
EXTRACTION_PROMPT = """Extract taxonomy tags from this text.

BRIDGE TAGS (Tier 0 - pick 0-3 most relevant):
Precision, Resilience, Fragility, Corruption, Loyalty, Stealth

COLLECTION: {collection}
COLLECTION TAGS (pick best match per dimension, or null):
{vocab}

TEXT:
{text}

Return JSON only:
{{"bridge_tags": [...], "collection_tags": {{"function": "...", "domain": "..."}}, "confidence": 0.8}}"""


def extract_keywords(text: str) -> list[str]:
    """Fast keyword-based extraction (no LLM)."""
    text_lower = text.lower()
    tags = []
    for tag, patterns in BRIDGE_KEYWORDS.items():
        if any(p in text_lower for p in patterns):
            tags.append(tag)
    return tags


def validate_tags(raw: dict[str, Any], collection: str) -> dict[str, Any]:
    """Filter LLM output to known vocabulary - prevents hallucinated tags."""
    # Validate bridge tags
    bridge = [t for t in raw.get("bridge_tags", []) if t in BRIDGE_TAGS]

    # Validate collection tags
    vocab = COLLECTION_VOCABULARIES.get(collection, COLLECTION_VOCABULARIES["operational"])
    col_tags = {}
    for dim, allowed in vocab.items():
        val = raw.get("collection_tags", {}).get(dim)
        if val and val in allowed:
            col_tags[dim] = val

    return {
        "bridge_tags": bridge,
        "collection_tags": col_tags,
        "confidence": min(1.0, max(0.0, raw.get("confidence", 0.5))),
    }


def extract_llm(text: str, collection: str) -> dict[str, Any]:
    """Use LLM to extract tags, then validate against vocabulary."""
    vocab_str = json.dumps(COLLECTION_VOCABULARIES.get(collection, {}), indent=2)
    prompt = EXTRACTION_PROMPT.format(
        text=text[:3000],  # Truncate for LLM context
        collection=collection,
        vocab=vocab_str
    )

    # Look for scillm batch.py in common locations
    skill_dirs = [
        Path(__file__).parent.parent / "scillm",
        Path.home() / ".pi" / "skills" / "scillm",
        Path.home() / ".claude" / "skills" / "scillm",
    ]

    batch_script = None
    for d in skill_dirs:
        if (d / "batch.py").exists():
            batch_script = d / "batch.py"
            break

    if not batch_script:
        # Fallback to keywords only
        return {
            "bridge_tags": extract_keywords(text),
            "collection_tags": {},
            "confidence": 0.3,
            "method": "keywords_fallback"
        }

    try:
        result = subprocess.run(
            [
                sys.executable, str(batch_script),
                "--prompt", prompt,
                "--json",
                "--max-tokens", "256"
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(batch_script.parent)
        )

        # Parse JSON from output
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    raw = json.loads(line)
                    validated = validate_tags(raw, collection)
                    validated["method"] = "llm"
                    return validated
                except json.JSONDecodeError:
                    continue

    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        print(f"LLM extraction failed: {e}", file=sys.stderr)

    # Fallback to keywords
    return {
        "bridge_tags": extract_keywords(text),
        "collection_tags": {},
        "confidence": 0.3,
        "method": "keywords_fallback"
    }


def extract_taxonomy(
    text: str,
    collection: str = "operational",
    fast: bool = False
) -> dict[str, Any]:
    """
    Extract taxonomy tags from text.

    Args:
        text: Content to analyze
        collection: Target collection (lore, operational, sparta)
        fast: Use keyword extraction only (no LLM)

    Returns:
        dict with bridge_tags, collection_tags, confidence, worth_remembering
    """
    if fast or os.environ.get("TAXONOMY_FAST_MODE") == "1":
        result = {
            "bridge_tags": extract_keywords(text),
            "collection_tags": {},
            "confidence": 0.3,
            "method": "keywords"
        }
    else:
        result = extract_llm(text, collection)

    # Document is worth remembering if it has meaningful tags
    result["worth_remembering"] = (
        len(result["bridge_tags"]) > 0 or
        len(result.get("collection_tags", {})) > 0
    )

    return result


@click.group()
def cli():
    """Taxonomy - Extract Federated Taxonomy tags for multi-hop graph traversal."""
    pass


@cli.command()
@click.option("--text", "-t", help="Text to analyze")
@click.option("--file", "-f", type=click.Path(exists=True), help="File to read")
@click.option("--collection", "-c", default="operational",
              type=click.Choice(["lore", "operational", "sparta"]),
              help="Collection type")
@click.option("--bridges-only", "-b", is_flag=True, help="Only output bridge tags")
@click.option("--fast", is_flag=True, help="Use keyword extraction only (no LLM)")
def extract(text: Optional[str], file: Optional[str], collection: str,
            bridges_only: bool, fast: bool):
    """Extract taxonomy tags from text."""
    # Get text content
    if file:
        text = Path(file).read_text()[:5000]
    elif not text:
        click.echo('{"error": "No text provided"}', err=True)
        raise SystemExit(1)

    # Extract
    result = extract_taxonomy(text, collection, fast)

    # Output
    if bridges_only:
        click.echo(",".join(result["bridge_tags"]))
    else:
        click.echo(json.dumps(result, indent=2))


@cli.command()
@click.option("--tags", "-t", help="JSON string with tags to validate")
@click.option("--file", "-f", type=click.Path(exists=True), help="JSON file with tags")
@click.option("--collection", "-c", default="operational",
              type=click.Choice(["lore", "operational", "sparta"]),
              help="Collection type")
def validate(tags: Optional[str], file: Optional[str], collection: str):
    """Validate tags against known vocabulary."""
    if file:
        raw = json.loads(Path(file).read_text())
    elif tags:
        raw = json.loads(tags)
    else:
        click.echo('{"error": "No tags provided"}', err=True)
        raise SystemExit(1)

    result = validate_tags(raw, collection)
    click.echo(json.dumps(result, indent=2))


@cli.command()
def vocabulary():
    """Show all allowed vocabulary values."""
    output = {
        "bridge_tags": list(BRIDGE_TAGS),
        "collections": {}
    }
    for coll, vocab in COLLECTION_VOCABULARIES.items():
        output["collections"][coll] = {k: list(v) for k, v in vocab.items()}

    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    cli()
