#!/usr/bin/env python3
"""
Taxonomy - Extract Federated Taxonomy tags from text.

LLM extracts candidates, deterministic validation filters to known vocabulary.
Prevents hallucinated tags by validating against allowed values.

Usage:
    ./run.sh --text "Error handling code" --collection operational
    ./run.sh --file document.txt --collection lore
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"])
    import typer

# Known vocabularies - LLM output is filtered against these
BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}

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

# Keyword patterns for fallback extraction (no LLM needed)
BRIDGE_KEYWORDS = {
    "Precision": ["optimiz", "efficien", "precis", "algorithm", "calculat", "method"],
    "Resilience": ["error handl", "fault tol", "robust", "redund", "recover", "resili"],
    "Fragility": ["brittle", "technical debt", "legacy", "fragile", "single point"],
    "Corruption": ["bug", "corrupt", "memory leak", "silent fail", "race condition"],
    "Loyalty": ["secur", "auth", "encrypt", "complian", "trust", "access control"],
    "Stealth": ["hidden", "infiltrat", "decept", "evas", "undetect"],
}

PROMPT = """Extract taxonomy tags from this text.

ALLOWED BRIDGE TAGS (pick 0-3 most relevant):
Precision, Resilience, Fragility, Corruption, Loyalty, Stealth

COLLECTION: {collection}
ALLOWED COLLECTION TAGS:
{vocab}

TEXT:
{text}

Return JSON only:
{{"bridge_tags": [...], "collection_tags": {{"function": null, "domain": null}}, "confidence": 0.8}}"""


def extract_keywords(text: str) -> list:
    """Fast keyword-based extraction (no LLM)."""
    text_lower = text.lower()
    tags = []
    for tag, patterns in BRIDGE_KEYWORDS.items():
        if any(p in text_lower for p in patterns):
            tags.append(tag)
    return tags


def validate_tags(raw: dict, collection: str) -> dict:
    """Filter LLM output to known vocabulary."""
    bridge = [t for t in raw.get("bridge_tags", []) if t in BRIDGE_TAGS]

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


def extract_llm(text: str, collection: str) -> dict:
    """Use LLM to extract tags, then validate."""
    vocab_str = json.dumps(COLLECTION_VOCABULARIES.get(collection, {}), indent=2)
    prompt = PROMPT.format(text=text[:2000], collection=collection, vocab=vocab_str)

    # Try scillm batch.py
    skill_dirs = [
        Path.home() / ".claude" / "skills" / "scillm",
        Path.home() / ".pi" / "skills" / "scillm",
        Path(__file__).parent.parent / "scillm",
    ]

    batch_script = None
    for d in skill_dirs:
        if (d / "batch.py").exists():
            batch_script = d / "batch.py"
            break

    if not batch_script:
        # Fallback to keywords
        return {"bridge_tags": extract_keywords(text), "collection_tags": {}, "confidence": 0.3}

    try:
        result = subprocess.run(
            [sys.executable, str(batch_script), "--prompt", prompt, "--json", "--max-tokens", "256"],
            capture_output=True, text=True, timeout=30, cwd=str(batch_script.parent)
        )

        # Parse JSON from output
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    raw = json.loads(line)
                    return validate_tags(raw, collection)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"LLM failed: {e}", file=sys.stderr)

    # Fallback
    return {"bridge_tags": extract_keywords(text), "collection_tags": {}, "confidence": 0.3}


def main(
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text to analyze"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="File to read"),
    collection: str = typer.Option("operational", "--collection", "-c", help="lore/operational/sparta"),
    bridges_only: bool = typer.Option(False, "--bridges-only", "-b", help="Only output bridge tags"),
    fast: bool = typer.Option(False, "--fast", help="Use keyword extraction only (no LLM)"),
):
    """Extract taxonomy tags from text."""
    # Get text
    if file and file.exists():
        text = file.read_text()[:5000]
    elif not text:
        print('{"error": "No text provided"}')
        raise typer.Exit(1)

    # Extract
    if fast:
        result = {"bridge_tags": extract_keywords(text), "collection_tags": {}, "confidence": 0.3}
    else:
        result = extract_llm(text, collection)

    # Worth remembering if has meaningful tags
    result["worth_remembering"] = len(result["bridge_tags"]) > 0 or len(result["collection_tags"]) > 0

    # Output
    if bridges_only:
        print(",".join(result["bridge_tags"]))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    typer.run(main)
