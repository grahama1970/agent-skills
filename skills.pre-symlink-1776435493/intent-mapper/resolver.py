#!/usr/bin/env python3
"""Tier 0 deterministic action resolver for QuerySpec.

Maps natural language text to app_actions via BM25 recall + token overlap.
No LLM required — runs in <100ms.

Usage:
    python resolver.py resolve "approve this entry"
    python resolver.py resolve "approve this entry" --verbose --json
"""

import json
import re
from typing import Any

import httpx
import typer
from loguru import logger

app = typer.Typer()

MEMORY_URL = "http://localhost:8601"
TIMEOUT = 5.0


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _to_upper_snake(text: str) -> str:
    """Convert text to UPPER_SNAKE_CASE for direct action lookup."""
    text = re.sub(r"[^\w\s]", " ", text.upper())
    return re.sub(r"\s+", "_", text.strip())


def _tokenize(text: str) -> set[str]:
    """Tokenize normalized text into word set, dropping stopwords."""
    stops = {"the", "a", "an", "this", "that", "it", "to", "do", "can", "you",
             "me", "my", "i", "is", "are", "was", "were", "be", "been", "being",
             "have", "has", "had", "will", "would", "could", "should", "may",
             "might", "shall", "of", "in", "on", "at", "for", "with", "from",
             "by", "and", "or", "not", "no", "but", "if", "then", "so", "please"}
    words = _normalize(text).split()
    return {w for w in words if w not in stops and len(w) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _fetch_all_actions(app_filter: str = "") -> list[dict]:
    """Fetch all actions from app_actions collection."""
    try:
        resp = httpx.post(
            f"{MEMORY_URL}/list",
            json={"collection": "app_actions", "limit": 300},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        docs = data.get("documents", data.get("items", []))
        if app_filter:
            docs = [d for d in docs if d.get("scope", "") == app_filter or d.get("app", "") == app_filter]
        return docs
    except Exception as e:
        logger.error(f"Failed to fetch app_actions: {e}")
        return []


def _recall_actions(query: str, k: int = 5) -> list[dict]:
    """BM25 recall from app_actions collection."""
    try:
        resp = httpx.post(
            f"{MEMORY_URL}/recall",
            json={
                "q": query,
                "k": k,
                "collections": ["app_actions"],
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except Exception as e:
        logger.debug(f"BM25 recall failed: {e}")
        return []


def resolve_action(text: str, app: str = "datalake-explorer") -> dict[str, Any]:
    """Resolve NL text to an app_action.

    Three-layer cascade (first confident match wins):
    1. Exact action name match
    2. BM25 recall from ArangoDB
    3. Token overlap scoring against all actions

    Returns:
        {resolved, action, dom_selector, confidence, tier, method, candidates}
    """
    result: dict[str, Any] = {
        "resolved": False,
        "action": None,
        "dom_selector": None,
        "confidence": 0.0,
        "tier": "T0",
        "method": None,
        "candidates": [],
    }

    # === Layer 1: Exact action name match ===
    upper = _to_upper_snake(text)
    all_actions = _fetch_all_actions(app)
    if not all_actions:
        logger.warning("No actions fetched from app_actions — is memory daemon running?")
        return result

    action_map = {}
    for doc in all_actions:
        action_name = doc.get("action", "")
        if action_name:
            action_map[action_name] = doc

    if upper in action_map:
        doc = action_map[upper]
        result.update({
            "resolved": True,
            "action": upper,
            "dom_selector": f'[data-qs-action="{upper}"]',
            "confidence": 1.0,
            "method": "exact",
            "label": doc.get("label", ""),
        })
        return result

    # === Layer 2: BM25 recall ===
    recalled = _recall_actions(text, k=5)
    if recalled:
        top = recalled[0]
        score = top.get("_score", top.get("score", 0))
        # Normalize score — BM25 scores vary, but >5 is usually strong
        norm_score = min(1.0, score / 10.0) if score > 0 else 0.0
        action_name = top.get("action", "")
        label = top.get("label", top.get("problem", ""))

        candidates = []
        for item in recalled[:3]:
            a = item.get("action", "")
            s = item.get("_score", item.get("score", 0))
            candidates.append({
                "action": a,
                "dom_selector": f'[data-qs-action="{a}"]',
                "label": item.get("label", item.get("problem", "")),
                "score": round(min(1.0, s / 10.0) if s > 0 else 0, 3),
            })
        result["candidates"] = candidates

        if norm_score > 0.85 and action_name:
            result.update({
                "resolved": True,
                "action": action_name,
                "dom_selector": f'[data-qs-action="{action_name}"]',
                "confidence": round(norm_score, 3),
                "method": "bm25",
                "label": label,
            })
            return result
        elif norm_score > 0.65 and action_name:
            result.update({
                "resolved": True,
                "action": action_name,
                "dom_selector": f'[data-qs-action="{action_name}"]',
                "confidence": round(norm_score, 3),
                "method": "bm25",
                "label": label,
            })
            return result

    # === Layer 3: Token overlap scoring ===
    query_tokens = _tokenize(text)
    if not query_tokens:
        return result

    scored = []
    for doc in all_actions:
        action_name = doc.get("action", "")
        label = doc.get("label", "")
        desc = doc.get("description", "")
        problem = doc.get("problem", "")

        # Build target token set from all text fields
        target_text = f"{label} {desc} {problem} {action_name.replace('_', ' ')}"
        target_tokens = _tokenize(target_text)

        score = _jaccard(query_tokens, target_tokens)
        if score > 0:
            scored.append((score, action_name, label, doc))

    scored.sort(key=lambda x: -x[0])

    if scored:
        # Add top 3 as candidates
        for score, action_name, label, _doc in scored[:3]:
            result["candidates"].append({
                "action": action_name,
                "dom_selector": f'[data-qs-action="{action_name}"]',
                "label": label,
                "score": round(score, 3),
            })

        top_score, top_action, top_label, _ = scored[0]
        if top_score > 0.2 and top_action:
            result.update({
                "resolved": True,
                "action": top_action,
                "dom_selector": f'[data-qs-action="{top_action}"]',
                "confidence": round(top_score, 3),
                "method": "token_overlap",
                "label": top_label,
            })

    # Deduplicate candidates
    result["candidates"] = _dedup_candidates(result["candidates"])[:3]
    return result


@app.command("resolve")
def resolve_cmd(
    text: str = typer.Argument(..., help="Natural language command to resolve"),
    app_name: str = typer.Option("datalake-explorer", "--app", help="App scope filter"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Resolve a natural language command to a DOM action."""
    result = resolve_action(text, app=app_name)

    if output_json:
        print(json.dumps(result, indent=2))
        return

    if result["resolved"]:
        print(f"✓ Resolved: {result['action']}")
        print(f"  Selector: {result['dom_selector']}")
        print(f"  Confidence: {result['confidence']:.1%}")
        print(f"  Method: {result['method']}")
        if result.get("label"):
            print(f"  Label: {result['label']}")
    else:
        print("✗ Not resolved")
        if result["candidates"]:
            print("  Candidates:")
            for c in result["candidates"]:
                print(f"    - {c['action']} ({c['score']:.1%}) — {c.get('label', '')}")

    if verbose and result["candidates"]:
        print(f"\n  All candidates: {json.dumps(result['candidates'], indent=2)}")


def _dedup_candidates(candidates: list[dict]) -> list[dict]:
    """Deduplicate candidates by action, keeping highest score."""
    seen: dict[str, dict] = {}
    for c in candidates:
        action = c.get("action", "")
        if action not in seen or c.get("score", 0) > seen[action].get("score", 0):
            seen[action] = c
    return sorted(seen.values(), key=lambda x: -x.get("score", 0))


if __name__ == "__main__":
    app()
