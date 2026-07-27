#!/usr/bin/env python3
"""scillm integration for Dogpile.

Provides high-reasoning analysis capabilities:
- search_codex: General reasoning/extraction through /scillm
- search_codex_knowledge: Technical overview queries
- tailor_queries_for_services: Generate service-specific search queries
- analyze_query: Analyze query for ambiguity and code-related intent
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import typer
import httpx

from dogpile.config import SKILLS_DIR
from dogpile.utils import log_status, with_semaphore, capture_execution_metadata

SCILLM_URL = os.environ.get("SCILLM_URL", "http://localhost:4001")
SCILLM_API_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")
SCILLM_MODEL = os.environ.get("DOGPILE_SCILLM_MODEL", "gpt-5.5")


def _call_scillm(prompt: str, schema: Optional[Path] = None, timeout_s: float = 120.0) -> str:
    """Call Dogpile's single active LLM lane.

    Dogpile deliberately does not set max_tokens. scillm owns provider routing,
    model-specific token controls, and upstream fallback behavior.
    """
    effective_prompt = prompt
    payload: Dict[str, Any] = {
        "model": SCILLM_MODEL,
        "messages": [{"role": "user", "content": effective_prompt}],
    }
    if schema:
        try:
            schema_text = schema.read_text()
        except Exception:
            schema_text = ""
        payload["response_format"] = {"type": "json_object"}
        if schema_text:
            payload["messages"][0]["content"] = (
                f"{effective_prompt}\n\nReturn JSON matching this schema:\n{schema_text}"
            )

    try:
        response = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SCILLM_API_KEY}",
                "X-Caller-Skill": "dogpile",
            },
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500] if e.response is not None else ""
        return f"Error: scillm HTTP {e.response.status_code if e.response else 'unknown'}: {body}"
    except Exception as e:
        return f"Error: scillm request failed: {e}"

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return f"Error: scillm returned unexpected response shape: {str(data)[:500]}"
    if content is None:
        return "Error: scillm returned empty content"
    return str(content)


@with_semaphore("llm")
def search_codex(prompt: str, schema: Optional[Path] = None) -> str:
    """Use Dogpile's single /scillm lane for analysis.

    Args:
        prompt: Analysis prompt
        schema: Optional JSON schema file for structured output

    Returns:
        LLM response text (prefixed with Error: on failure)
    """
    log_status(f"Consulting /scillm model {SCILLM_MODEL}...")
    result = _call_scillm(prompt, schema=schema, timeout_s=120.0)

    if result.startswith("Error:"):
        log_status("scillm analysis failed", status="FAILED")
        return result

    log_status("scillm analysis finished")
    return result


def search_codex_fast(prompt: str, schema: Optional[Path] = None) -> str:
    """Use fast LLM for simple tasks (query tailoring, etc).

    Uses the same /scillm lane with a shorter timeout.

    Args:
        prompt: Analysis prompt
        schema: Optional JSON schema file

    Returns:
        LLM response text
    """
    log_status(f"Consulting /scillm model {SCILLM_MODEL} for fast task...")
    result = _call_scillm(prompt, schema=schema, timeout_s=60.0)

    if result.startswith("Error:"):
        return result

    log_status("Fast scillm task finished")
    return result


@capture_execution_metadata("codex_knowledge", stage="stage1")
def search_codex_knowledge(query: str) -> str:
    """Use high-reasoning LLM for technical knowledge.

    Uses /scillm for deep analysis.

    Args:
        query: Topic to get technical overview for

    Returns:
        Technical overview text
    """
    log_status(f"Querying LLM Knowledge for '{query}'...", provider="llm", status="RUNNING")
    prompt = (
        f"Provide a high-reasoning technical overview and internal knowledge "
        f"about this topic: '{query}'. Focus on architectural patterns, "
        f"common pitfalls, and state-of-the-art approaches."
    )

    # Keep the LLM lane inside Dogpile's Stage 1 wall-clock budget.
    result = _call_scillm(prompt, timeout_s=75.0)

    if result.startswith("Error:"):
        log_status("Knowledge query failed", provider="llm", status="FAILED")
        return result

    log_status("LLM knowledge finished via scillm", provider="llm", status="DONE")
    return result


def tailor_queries_for_services(query: str, is_code_related: bool) -> Dict[str, str]:
    """Generate service-specific queries tailored to each source's strengths.

    Uses /scillm to analyze the query and generate optimal queries for:
    - arxiv: Academic/technical terms, paper-style queries
    - brave_questions: Natural language explanatory questions formerly sent to Perplexity
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

2. **brave_questions**: Natural-language web research questions. These replace the retired Perplexity lane.
   - Good: "What are the best practices for AI agent memory systems in 2025?"
   - Bad: "AI agent memory 2025"

3. **brave**: Web search. Use documentation-style keyword queries, include "docs" or version numbers where useful.
   HARD LIMITS: Brave query must be <= 400 characters AND <= 50 words.
   Do NOT return a full natural-language paragraph for Brave.
   - Good: "LangChain memory module documentation 2025"
   - Good: "SPARTA control mapping assessor workflow evidence traceability docs"
   - Bad: "memory systems"
   - Bad: full question sentences with multiple clauses

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
The Brave query must fit Brave's hard limits and should read like a compressed search engine query, not prose.
Include current year (2025-2026) where relevant for recent results.

{{"arxiv": "...", "brave_questions": "...", "perplexity": "...", "brave": "...", "github": "...", "youtube": "...", "readarr": "..."}}"""

    schema_path = SKILLS_DIR / "codex" / "query_tailor_schema.json"

    # Create schema if it doesn't exist
    if not schema_path.exists():
        schema = {
            "type": "object",
            "properties": {
                "arxiv": {"type": "string", "description": "Academic paper search query"},
                "brave_questions": {"type": "string", "description": "Natural language Brave question"},
                "perplexity": {"type": "string", "description": "Deprecated alias for brave_questions"},
                "brave": {"type": "string", "description": "Web/documentation search query"},
                "github": {"type": "string", "description": "Code-focused search query"},
                "youtube": {"type": "string", "description": "Tutorial-style search query"},
                "readarr": {"type": "string", "description": "Book/Usenet search query"}
            },
            "required": ["arxiv", "brave_questions", "brave", "github", "youtube", "readarr"],
            "additionalProperties": False
        }
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(schema, indent=2))

    log_status("Tailoring queries for each service...")
    # Use fast chain for query tailoring (simple task)
    result_text = search_codex_fast(prompt, schema=schema_path)

    # Default to original query for all services
    default_queries = {
        "arxiv": query,
        "brave_questions": query,
        "perplexity": query,
        "brave": query,
        "github": query,
        "youtube": query,
        "readarr": query,
    }

    if result_text is None:
        log_status("Query tailoring returned None (search_codex_fast)")
        return default_queries

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


_CODE_KEYWORDS: Set[str] = {
    # Languages
    "python", "javascript", "typescript", "rust", "go", "golang", "java", "kotlin",
    "swift", "ruby", "php", "c++", "cpp", "csharp", "scala", "elixir", "haskell",
    "lua", "perl", "bash", "shell", "sql", "html", "css",
    # Concepts
    "api", "algorithm", "function", "class", "method", "module", "package", "library",
    "framework", "sdk", "cli", "deploy", "compile", "runtime", "debug", "refactor",
    "middleware", "endpoint", "webhook", "microservice", "monorepo",
    # Tools & package managers
    "npm", "pip", "cargo", "maven", "gradle", "docker", "kubernetes", "terraform",
    "ansible", "webpack", "vite", "eslint", "pytest", "jest", "git", "github",
    # AI/ML code patterns
    "llm", "embedding", "rag", "transformer", "tokenizer", "pytorch", "tensorflow",
    "langchain", "llamaindex", "huggingface", "finetune", "lora", "qlora",
}

_CODE_PATTERNS = [
    re.compile(r"[A-Z][a-z]+[A-Z]"),          # CamelCase
    re.compile(r"[a-z]+_[a-z]+"),              # snake_case
    re.compile(r"\.\w{1,4}$"),                 # File extensions (e.g. .py, .ts, .rs)
    re.compile(r"github\.com/"),               # GitHub URLs
    re.compile(r"\w+\(\)"),                    # Function call syntax
    re.compile(r"[a-z]+\.[a-z]+\.[a-z]+"),    # Dotted module paths (e.g. os.path.join)
]


def _is_code_related_heuristic(query: str) -> bool:
    """Determine if a query is code-related using keyword and pattern matching.

    Pure string matching — zero LLM cost.

    Args:
        query: Search query

    Returns:
        True if the query appears code-related.
    """
    query_lower = query.lower()
    words = set(query_lower.split())

    # Check keyword overlap
    if words & _CODE_KEYWORDS:
        return True

    # Check regex patterns against original query
    for pattern in _CODE_PATTERNS:
        if pattern.search(query):
            return True

    return False


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
        # Detailed queries with 5+ words are almost never ambiguous,
        # but still check whether the topic is code-related
        return query, _is_code_related_heuristic(query)

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
