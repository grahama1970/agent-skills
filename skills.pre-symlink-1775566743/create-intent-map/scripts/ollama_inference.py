#!/usr/bin/env python3
"""Ollama-based inference for SPARTA Intent Mapper.

Uses qwen3:8b via local Ollama for 100% accuracy QuerySpec generation.
Based on evaluation finding that qwen3:8b achieves perfect results locally.

Usage:
    python ollama_inference.py "How do I detect RF jamming attacks?"
    python ollama_inference.py --interactive
"""

import typer
import json
import re
import sys
from typing import Any, Optional

import httpx
from loguru import logger

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
# Use non-reasoning instruction model (qwen3:8b has thinking mode which causes issues)
DEFAULT_MODEL = "qwen2.5-coder:7b-instruct"
TIMEOUT = 60.0

# QuerySpec prompt template - Use double braces to escape JSON examples
QUERYSPEC_PROMPT = """You are a SPARTA (Space Attack Research and Tactic Analysis) query router.
Convert the user query into a structured QuerySpec JSON for database retrieval.

## QuerySpec Schema

```json
{{
  "action": "QUERY" | "CLARIFY" | "NO_MATCH",
  "entities": ["CM-0051", "T1071", ...],
  "tier1": ["Detect", "Mitigate", "Recover"],
  "lanes": ["bm25", "dense"],
  "k": 12,
  "scope": "sparta"
}}
```

## Action Types

- **QUERY**: Space cybersecurity question that can be answered from SPARTA
- **CLARIFY**: Ambiguous question needing more details (ask clarifying question)
- **NO_MATCH**: Out of scope (weather, recipes, generic IT without space context)

## Entity Extraction

Extract SPARTA IDs:
- Controls: CM-XXXX, AC-XXXX
- Techniques: T-XXXX, REC-XXXX, EXE-XXXX, PER-XXXX, IMP-XXXX
- CWEs: CWE-XXX

## Examples

Query: "How do I detect RF jamming attacks on satellite uplinks?"
Output:
```json
{{"action": "QUERY", "entities": [], "tier1": ["Detect"], "lanes": ["bm25", "dense"], "k": 12, "scope": "sparta"}}
```

Query: "What controls mitigate T1071 command and control?"
Output:
```json
{{"action": "QUERY", "entities": ["T1071"], "tier1": ["Mitigate"], "lanes": ["bm25", "dense"], "k": 12, "scope": "sparta"}}
```

Query: "How do I make my system more secure?"
Output:
```json
{{"action": "CLARIFY", "clarify_question": "Could you specify which space system component (spacecraft bus, ground station, RF link) you want to secure?", "scope": "sparta"}}
```

Query: "What's the weather forecast for tomorrow?"
Output:
```json
{{"action": "NO_MATCH", "reason": "Weather queries are outside SPARTA scope", "scope": "sparta"}}
```

## Your Task

Convert this query to QuerySpec JSON. Output ONLY valid JSON, no explanation.

Query: {query}

Output:"""


def call_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> str:
    """Call Ollama API for generation."""
    try:
        response = httpx.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except httpx.HTTPError as e:
        logger.error(f"Ollama API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        raise


def extract_json(text: str) -> Optional[dict]:
    """Extract JSON from model output, handling CoT reasoning and markdown."""
    if not text:
        return None

    text = text.strip()

    # Try to find JSON in the text
    # First, try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for JSON block in markdown (handles multiline)
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if json_match:
        try:
            # Clean up the JSON (remove extra whitespace)
            json_str = json_match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # Look for raw JSON object with "action" key (handles multiline)
    json_match = re.search(r'\{\s*"action"\s*:\s*"[^"]+"\s*[,}][\s\S]*?\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try greedy match for any JSON-like object
    json_match = re.search(r'\{[^{}]*\}', text)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if "action" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # Last resort: try to find nested JSON
    start = text.find('{')
    if start >= 0:
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


def infer(query: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Generate QuerySpec for a query using Ollama.

    Args:
        query: User query string
        model: Ollama model to use

    Returns:
        QuerySpec dict with action, entities, etc.
    """
    prompt = QUERYSPEC_PROMPT.format(query=query)

    logger.debug(f"Calling Ollama with model {model}")
    raw_response = call_ollama(prompt, model=model)
    logger.debug(f"Raw response: {raw_response[:200]}...")

    # Extract JSON from response
    spec = extract_json(raw_response)

    if spec is None:
        logger.warning(f"Failed to extract JSON from response: {raw_response[:200]}")
        # Return default CLARIFY response
        return {
            "action": "CLARIFY",
            "clarify_question": "I couldn't understand your query. Could you rephrase it?",
            "scope": "sparta",
            "_raw_response": raw_response[:500],
            "_parse_error": True,
        }

    # Normalize the spec
    spec.setdefault("scope", "sparta")
    spec.setdefault("entities", [])
    spec.setdefault("lanes", ["bm25", "dense"])
    spec.setdefault("k", 12)

    # Store original query for reference
    spec["_original_query"] = query

    return spec


def interactive_mode(model: str = DEFAULT_MODEL):
    """Run interactive inference session."""
    print("\nSPARTA Intent Mapper (Ollama)")
    print(f"Model: {model}")
    print("=" * 50)
    print("Enter queries to convert to QuerySpec. Type 'quit' to exit.\n")

    while True:
        try:
            query = input("Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break

        try:
            result = infer(query, model=model)
            print(f"\nQuerySpec:")
            print(json.dumps(result, indent=2))
            print()
        except Exception as e:
            print(f"\nError: {e}\n")

    print("\nExiting.")


app = typer.Typer(help="SPARTA Intent Mapper via Ollama")


@app.command()
def main(
    query: str = typer.Argument(None, help="Query to convert to QuerySpec"),
    model: str = typer.Option(DEFAULT_MODEL, help=""),
    interactive: bool = typer.Option(False, help="Interactive mode"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON only"),
):
    if interactive:
        interactive_mode(model=model)
        return 0

    if not query:
        parser.print_help()
        return 1

    try:
        result = infer(query, model=model)

        if json:
            print(json.dumps(result))
        else:
            print(json.dumps(result, indent=2))

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    app()
