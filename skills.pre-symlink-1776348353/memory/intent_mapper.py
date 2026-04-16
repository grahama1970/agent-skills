#!/usr/bin/env python3
"""Intent Mapper Integration for Brandon/Embry persona.

Wraps the Ollama-based intent mapper for use in the Brandon simulacrum.
Uses qwen2.5-coder:7b-instruct (non-reasoning model) for reliable JSON output.

Usage:
    from intent_mapper import get_intent, IntentMapper

    result = get_intent("How do I detect RF jamming?")
    # {'action': 'QUERY', 'entities': [], 'tier1': ['Detect'], ...}
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:7b-instruct"  # Non-reasoning model for reliable JSON
TIMEOUT = 60.0

# DB-backed bridge keywords cache — loaded from ArangoDB taxonomy_vocabulary.
# See /best-practices-arangodb rule arango-no-hardcoded-domain-lists.
# /memory skill has direct ArangoDB access via db.py.
_bridge_keywords_cache: dict[str, list[str]] | None = None


def _get_bridge_keywords() -> dict[str, list[str]]:
    """Load bridge keywords from ArangoDB taxonomy_vocabulary."""
    global _bridge_keywords_cache
    if _bridge_keywords_cache is not None:
        return _bridge_keywords_cache
    try:
        from db import get_db
        db = get_db()
        cursor = db.aql.execute(
            "FOR t IN taxonomy_vocabulary "
            "FILTER t.category IN ['bridge_keyword', 'bridge_keyword_extended'] "
            "RETURN {bridge: t.bridge_concept, term: t.term}"
        )
        _bridge_keywords_cache = {}
        for row in cursor:
            if row.get("bridge") and row.get("term"):
                _bridge_keywords_cache.setdefault(row["bridge"], []).append(row["term"].lower())
    except Exception as exc:
        logger.debug("bridge_keywords cache load failed (DB unavailable?): {}", exc)
        _bridge_keywords_cache = {}
    return _bridge_keywords_cache


BRIDGE_KEYWORDS = {}  # Populated on first access via _get_bridge_keywords()

# QuerySpec prompt template - double braces escape JSON examples
QUERYSPEC_PROMPT = """You are a SPARTA (Space Attack Research and Tactic Analysis) query router.
Convert the user query into a structured QuerySpec JSON for database retrieval.

## QuerySpec Schema

```json
{{
  "action": "QUERY" | "CLARIFY" | "NO_MATCH",
  "entities": ["CM-0051", "T1071", ...],
  "tier1": ["Detect", "Mitigate", "Recover"],
  "bridges": ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"],
  "lanes": ["bm25", "dense"],
  "k": 12,
  "scope": "sparta"
}}
```

## Action Types

- **QUERY**: Space cybersecurity question that can be answered from SPARTA
- **CLARIFY**: Ambiguous question needing more details
- **NO_MATCH**: Out of scope (weather, recipes, generic IT without space context)

## Entity Extraction

Extract SPARTA IDs: CM-XXXX, AC-XXXX, T-XXXX, REC-XXXX, CWE-XXX

## Federated Taxonomy Bridges

Assign 1-3 bridges based on the query's security focus:
- **Precision**: Timing, navigation, measurement accuracy, sensor calibration
- **Resilience**: Recovery, redundancy, fault tolerance, graceful degradation
- **Fragility**: Vulnerabilities, weaknesses, attack surfaces, single points of failure
- **Corruption**: Data tampering, spoofing, integrity attacks, unauthorized modification
- **Loyalty**: Trust, authentication, insider threats, access control, identity
- **Stealth**: Evasion, persistence, covert channels, detection avoidance

## Examples

Query: "How do I detect RF jamming attacks?"
Output: {{"action": "QUERY", "entities": [], "tier1": ["Detect"], "bridges": ["Fragility", "Resilience"], "lanes": ["bm25", "dense"], "k": 12, "scope": "sparta"}}

Query: "What controls mitigate T1071?"
Output: {{"action": "QUERY", "entities": ["T1071"], "tier1": ["Mitigate"], "bridges": ["Stealth", "Corruption"], "lanes": ["bm25", "dense"], "k": 12, "scope": "sparta"}}

Query: "How can adversaries spoof GPS signals to spacecraft?"
Output: {{"action": "QUERY", "entities": [], "tier1": ["Detect"], "bridges": ["Precision", "Corruption"], "lanes": ["bm25", "dense"], "k": 12, "scope": "sparta"}}

Query: "What authentication methods protect ground station access?"
Output: {{"action": "QUERY", "entities": [], "tier1": ["Mitigate"], "bridges": ["Loyalty"], "lanes": ["bm25", "dense"], "k": 12, "scope": "sparta"}}

Query: "How do I make my system more secure?"
Output: {{"action": "CLARIFY", "clarify_question": "Could you specify which space system component (spacecraft bus, ground station, RF link) you want to secure?", "scope": "sparta"}}

Query: "What's the weather?"
Output: {{"action": "NO_MATCH", "reason": "Weather queries are outside SPARTA scope", "scope": "sparta"}}

Convert this query to QuerySpec JSON. Output ONLY valid JSON:

Query: {query}

Output:"""


def extract_bridges_from_text(text: str) -> list[str]:
    """Extract Federated Taxonomy bridges using keyword matching.

    This provides a fast, reliable fallback when LLM bridge prediction
    is missing or uncertain.

    Args:
        text: Query text to analyze

    Returns:
        List of matched bridge names (1-3 bridges)
    """
    text_lower = text.lower()
    bridge_scores: dict[str, int] = {}

    for bridge, keywords in _get_bridge_keywords().items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in text_lower:
                score += 1
        if score > 0:
            bridge_scores[bridge] = score

    # Sort by score and return top 3
    sorted_bridges = sorted(bridge_scores.items(), key=lambda x: -x[1])
    return [b[0] for b in sorted_bridges[:3]]


def extract_json(text: str) -> Optional[dict]:
    """Extract JSON from model output, handling markdown wrapping."""
    if not text:
        return None

    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for JSON in markdown code block
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Look for raw JSON object
    json_match = re.search(r'\{\s*"action"\s*:', text)
    if json_match:
        start = json_match.start()
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break

    return None


class IntentMapper:
    """Intent mapper using Ollama for QuerySpec generation."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        ollama_url: str = OLLAMA_URL,
        timeout: float = TIMEOUT,
    ):
        """Initialize intent mapper.

        Args:
            model: Ollama model name
            ollama_url: Ollama API URL
            timeout: Request timeout in seconds
        """
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout

    def _call_ollama(self, prompt: str, temperature: float = 0.1) -> str:
        """Call Ollama API for generation."""
        try:
            response = httpx.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 512,
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except httpx.HTTPError as e:
            logger.error(f"Ollama API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise

    def get_intent(self, query: str) -> dict[str, Any]:
        """Get intent/QuerySpec for a user query.

        Args:
            query: User's question

        Returns:
            QuerySpec dict with action, entities, tier1, etc.
        """
        prompt = QUERYSPEC_PROMPT.format(query=query)

        try:
            raw_response = self._call_ollama(prompt)
            spec = extract_json(raw_response)

            if spec is None:
                logger.warning(f"Failed to parse JSON from response: {raw_response[:200]}")
                return {
                    "action": "CLARIFY",
                    "clarify_question": "I couldn't fully understand your query. Could you rephrase it?",
                    "scope": "sparta",
                    "confidence": 0.3,
                    "_parse_error": True,
                }

            # Normalize and add defaults (use explicit None checks because
            # LLM may return "entities": null which .setdefault() won't fix)
            spec.setdefault("scope", "sparta")
            if spec.get("entities") is None:
                spec["entities"] = []
            if spec.get("lanes") is None:
                spec["lanes"] = ["bm25", "dense"]
            if spec.get("k") is None:
                spec["k"] = 12
            if spec.get("tier1") is None:
                spec["tier1"] = []
            if spec.get("bridges") is None:
                spec["bridges"] = []
            # Also filter out any None items within lists
            spec["entities"] = [e for e in spec["entities"] if e is not None]
            spec["tier1"] = [t for t in spec["tier1"] if t is not None]
            spec["bridges"] = [b for b in spec["bridges"] if b is not None]

            # Supplement bridges with keyword extraction if LLM missed them
            if not spec["bridges"] and spec["action"] == "QUERY":
                keyword_bridges = extract_bridges_from_text(query)
                if keyword_bridges:
                    spec["bridges"] = keyword_bridges
                    spec["_bridges_source"] = "keyword"
            elif spec["bridges"]:
                spec["_bridges_source"] = "llm"

            # Add confidence based on action
            if spec["action"] == "QUERY":
                spec["confidence"] = 0.85
            elif spec["action"] == "CLARIFY":
                spec["confidence"] = 0.5
            else:  # NO_MATCH
                spec["confidence"] = 0.0

            return spec

        except Exception as e:
            logger.error(f"Intent mapping failed: {e}")
            return {
                "action": "CLARIFY",
                "clarify_question": "I encountered an error processing your query. Could you try again?",
                "scope": "sparta",
                "confidence": 0.0,
                "_error": str(e),
            }

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = httpx.get(
                self.ollama_url.replace("/api/generate", "/api/tags"),
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception as exc:
            logger.debug("Ollama availability check failed: {}", exc)
            return False


# Singleton instance
_mapper_instance: IntentMapper | None = None


def get_mapper() -> IntentMapper:
    """Get singleton mapper instance."""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = IntentMapper()
    return _mapper_instance


def get_intent(query: str) -> dict[str, Any]:
    """Convenience function to get intent for a query.

    Args:
        query: User's question

    Returns:
        QuerySpec dict
    """
    return get_mapper().get_intent(query)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python intent_mapper.py 'query text'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    mapper = IntentMapper()

    if not mapper.is_available():
        print("Error: Ollama is not available")
        sys.exit(1)

    result = mapper.get_intent(query)
    print(json.dumps(result, indent=2))
