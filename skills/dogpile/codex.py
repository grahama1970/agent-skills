#!/usr/bin/env python3
"""Codex (OpenAI) integration for Dogpile.

Provides high-reasoning analysis capabilities:
- search_codex: General reasoning/extraction
- search_codex_knowledge: Technical overview queries
- tailor_queries_for_services: Generate service-specific search queries
- analyze_query: Analyze query for ambiguity and code-related intent
"""
import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import typer

from dogpile.config import SKILLS_DIR
from dogpile.utils import log_status, with_semaphore, run_command


@with_semaphore("codex")
def search_codex(prompt: str, schema: Optional[Path] = None) -> str:
    """Use high-reasoning Codex for analysis with rate limiting protection.

    Codex uses OpenAI API which has rate limits. Use semaphore to prevent
    overwhelming the API with concurrent requests.

    Args:
        prompt: Analysis prompt
        schema: Optional JSON schema file for structured output

    Returns:
        Codex response text
    """
    log_status("Consulting Codex for high-reasoning analysis...")
    script = SKILLS_DIR / "codex" / "run.sh"

    if schema:
        cmd = ["bash", str(script), "extract", prompt, "--schema", str(schema)]
    else:
        cmd = ["bash", str(script), "reason", prompt]

    output = run_command(cmd)

    # Check for rate limit errors
    if "rate limit" in output.lower() or "429" in output:
        log_status("Codex rate limited, backing off 30s...", provider="codex", status="RATE_LIMITED")
        time.sleep(30)
        output = run_command(cmd)  # Retry once

    log_status("Codex analysis finished.")
    return output


def search_codex_knowledge(query: str) -> str:
    """Use Codex as a direct source of technical knowledge.

    Args:
        query: Topic to get technical overview for

    Returns:
        Technical overview text
    """
    log_status(f"Querying Codex Knowledge for '{query}'...", provider="codex", status="RUNNING")
    prompt = (
        f"Provide a high-reasoning technical overview and internal knowledge "
        f"about this topic: '{query}'. Focus on architectural patterns, "
        f"common pitfalls, and state-of-the-art approaches."
    )
    res = search_codex(prompt)
    log_status("Codex technical overview finished.", provider="codex", status="DONE")
    return res


def tailor_queries_for_services(query: str, is_code_related: bool) -> Dict[str, str]:
    """Generate service-specific queries tailored to each source's strengths.

    Uses Codex to analyze the query and generate optimal queries for:
    - arxiv: Academic/technical terms, paper-style queries
    - perplexity: Natural language explanatory questions
    - brave: Documentation, tutorials, error messages
    - github: Code terms, library names, function signatures
    - youtube: Tutorial-style, "how to" queries
    - readarr: Book/author focused queries

    Args:
        query: Original search query
        is_code_related: Whether query is code-related

    Returns:
        Dict of {service: tailored_query}
    """
    prompt = f"""You are an expert research assistant. Given this query:
"{query}"

Generate OPTIMIZED search queries for each service. Each service has different strengths:

1. **arxiv**: Academic papers. Use technical terms, mathematical concepts, formal names.
   - Good: "transformer attention mechanism neural networks"
   - Bad: "how do transformers work"

2. **perplexity**: AI synthesis. Use natural language questions for explanations.
   - Good: "What are the best practices for AI agent memory systems in 2025?"
   - Bad: "AI agent memory 2025"

3. **brave**: Web search. Use documentation-style queries, include "docs", version numbers.
   - Good: "LangChain memory module documentation 2025"
   - Bad: "memory systems"

4. **github**: Code search. Use library names, function names, code patterns.
   - Good: "langchain memory BaseMemory implementation python"
   - Bad: "how to use memory in AI"

5. **youtube**: Video tutorials. Use "tutorial", "how to build", demonstration phrases.
   - Good: "how to build AI agent with long term memory tutorial"
   - Bad: "AI memory systems"

6. **readarr**: Books/Usenet. Use title/author focused queries.
   - Good: "Designing Data-Intensive Applications"
   - Bad: "how databases work"

Return JSON with tailored queries for each service. Keep queries concise but specific.
Include current year (2025-2026) where relevant for recent results.

{{"arxiv": "...", "perplexity": "...", "brave": "...", "github": "...", "youtube": "...", "readarr": "..."}}"""

    schema_path = SKILLS_DIR / "codex" / "query_tailor_schema.json"

    # Create schema if it doesn't exist
    if not schema_path.exists():
        schema = {
            "type": "object",
            "properties": {
                "arxiv": {"type": "string", "description": "Academic paper search query"},
                "perplexity": {"type": "string", "description": "Natural language question"},
                "brave": {"type": "string", "description": "Web/documentation search query"},
                "github": {"type": "string", "description": "Code-focused search query"},
                "youtube": {"type": "string", "description": "Tutorial-style search query"},
                "readarr": {"type": "string", "description": "Book/Usenet search query"}
            },
            "required": ["arxiv", "perplexity", "brave", "github", "youtube", "readarr"],
            "additionalProperties": False
        }
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(schema, indent=2))

    log_status("Tailoring queries for each service...")
    result_text = search_codex(prompt, schema=schema_path)

    # Default to original query for all services
    default_queries = {
        "arxiv": query,
        "perplexity": query,
        "brave": query,
        "github": query,
        "youtube": query,
        "readarr": query,
    }

    if result_text.startswith("Error:"):
        log_status(f"Query tailoring failed: {result_text[:100]}")
        return default_queries

    try:
        start = result_text.find("{")
        end = result_text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(result_text[start:end+1])
            # Merge with defaults (in case some keys missing)
            return {**default_queries, **data}
    except json.JSONDecodeError as e:
        log_status(f"Query tailoring JSON decode failed: {e}")

    return default_queries


def analyze_query(query: str, interactive: bool) -> Tuple[str, bool]:
    """Analyze query for ambiguity and code-related intent.

    Args:
        query: Search query
        interactive: Whether to enable ambiguity check

    Returns:
        Tuple of (query, is_code_related)
        Exits if ambiguous and interactive.
    """
    if not interactive:
        return query, True

    # Skip ambiguity check for queries that are clearly detailed research queries
    # Only flag truly ambiguous single-word or vague queries
    word_count = len(query.split())
    if word_count >= 5:
        # Detailed queries with 5+ words are almost never ambiguous
        return query, True

    prompt = (
        f"Analyze this research query: '{query}'\n\n"
        "IMPORTANT: Only mark as ambiguous if the query is truly vague or has multiple unrelated meanings.\n"
        "Examples of AMBIGUOUS queries (is_ambiguous=true):\n"
        "- 'apple' (fruit vs company)\n"
        "- 'python' (snake vs language, but context usually makes clear)\n"
        "- 'fix it' (no context what 'it' is)\n\n"
        "Examples of NOT AMBIGUOUS queries (is_ambiguous=false):\n"
        "- 'AI agent memory systems 2025' (clear research topic)\n"
        "- 'python sort list' (clear programming question)\n"
        "- 'react hooks best practices' (clear topic)\n"
        "- Any multi-word technical query with clear intent\n\n"
        "Assess: is this query ambiguous? Does it relate to software/coding?"
    )

    schema_path = SKILLS_DIR / "codex" / "dogpile_schema.json"
    result_text = search_codex(prompt, schema=schema_path)

    if result_text.startswith("Error:"):
        log_status(f"Codex analysis failed: {result_text}")
        return query, True  # Fail open

    try:
        # Codex CLI output-schema might contain some wrap text if we didn't use --json
        # However, our run_codex wrapper returns the output.
        # Let's try to extract JSON from the output in case there's noise.
        start = result_text.find("{")
        end = result_text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(result_text[start:end+1])
        else:
            data = json.loads(result_text)

        # Check Ambiguity
        if data.get("is_ambiguous"):
            clarifications = data.get("clarifications", [])
            if clarifications:
                output = {
                    "status": "ambiguous",
                    "query": query,
                    "clarifications": clarifications,
                    "message": "The query is ambiguous. Please ask the user these clarifying questions."
                }
                # Print JSON to stdout for agentic handoff
                print(json.dumps(output, indent=2))
                raise typer.Exit(code=0)

        return query, data.get("is_code_related", True)

    except json.JSONDecodeError as e:
        log_status(f"JSON decode failed for Codex output: {e}")
    except typer.Exit:
        raise
    except Exception as e:
        log_status(f"Unexpected error in query analysis: {e}")

    return query, True
