#!/usr/bin/env python3
"""Assess external code for correct scillm usage patterns.

Detects common misuse patterns that cause timeouts, failures, or inefficiency.
Run via: ./run.sh assess <file.py>

Usage:
    ./run.sh assess /path/to/script.py          # Human-readable output
    ./run.sh assess /path/to/script.py --json   # JSON for automation
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# =============================================================================
# Model corrections map (hardcoded model → recommended alias)
# Mirrors runtime knowledge from scillm proxy
# =============================================================================

MODEL_CORRECTIONS = {
    # OpenAI models → use proxy aliases
    "gpt-4": "text",
    "gpt-4o": "vlm",  # multimodal
    "gpt-4-turbo": "text",
    "gpt-4o-mini": "text",
    "gpt-3.5-turbo": "text",
    "gpt-5.3-codex": "vlm-codex",  # direct codex access
    # Anthropic models → use proxy aliases
    "claude-3-opus": "vlm-claude",
    "claude-3-sonnet": "vlm-claude",
    "claude-3-haiku": "text",
    "claude-sonnet-4": "vlm-claude",
    "claude-opus-4": "vlm-claude",
    # Google models → use proxy aliases
    "gemini-pro": "text-gemini",
    "gemini-1.5-pro": "text-gemini",
    "gemini-1.5-flash": "text-gemini",
    "gemini-2.0-flash": "text-gemini",
    "gemini-2.5-flash": "text-gemini",
    "gemini-3-flash": "text-gemini-3",
    # DeepSeek → use proxy alias
    "deepseek-chat": "text-deepseek",
    "deepseek-coder": "text-deepseek",
    # Qwen → use proxy alias
    "qwen2.5": "local-text",
}

# =============================================================================
# Misuse patterns to detect
# =============================================================================

PATTERNS = [
    # Fire-all-at-once batching (CRITICAL)
    {
        "name": "fire_all_at_once",
        "pattern": r"asyncio\.gather\s*\(\s*\*\s*\[.*for\s+\w+\s+in\s+(?:all_|prompts|requests|items|batch)",
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "error",
        "message": "Fires all requests at once - will timeout with >4 requests",
        "fix": "Use chunked batching: for chunk in chunks(items, 4): await gather(*[fn(x) for x in chunk])",
    },
    # Large batch without chunking
    {
        "name": "unbounded_gather",
        "pattern": r"await\s+asyncio\.gather\s*\(\s*\*\s*\w+\s*\)",
        "flags": re.MULTILINE,
        "severity": "warning",
        "message": "asyncio.gather with dynamic list - ensure CHUNK_SIZE batching",
        "fix": "Add CHUNK_SIZE=4 constant and chunk the work",
    },
    # max_tokens (FORBIDDEN)
    {
        "name": "max_tokens",
        "pattern": r'["\']max_tokens["\']\s*:',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "max_tokens is FORBIDDEN - causes empty/truncated output",
        "fix": "Remove max_tokens entirely. Let the model decide output length.",
    },
    # Import from scillm instead of HTTP
    {
        "name": "direct_import",
        "pattern": r"from\s+scillm\s+import|import\s+scillm",
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "Direct import bypasses proxy - use HTTP API instead",
        "fix": "Use httpx.post('http://localhost:4001/v1/chat/completions', ...)",
    },
    # Missing response_format for JSON (heuristic: json in prompt + no response_format)
    {
        "name": "missing_response_format",
        "pattern": r'(?:json|JSON|"format":\s*"json")(?:(?!response_format).)*?(?:chat/completions|openai\.)',
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "warning",
        "message": "JSON expected but response_format may not be set",
        "fix": 'Add "response_format": {"type": "json_object"} to request',
    },
    # Hardcoded provider URLs (bypass proxy)
    {
        "name": "hardcoded_provider",
        "pattern": r'https?://(?:api\.openai\.com|api\.anthropic\.com|api\.together\.ai|api\.deepseek\.com)',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "Hardcoded provider URL bypasses proxy cascade and caching",
        "fix": "Use http://localhost:4001/v1/chat/completions with model aliases",
    },
    # Hardcoded model names (should use aliases) - handled specially below
    # Pattern kept for detection, fix uses MODEL_CORRECTIONS map
    # No timeout on httpx calls (simplified pattern - just flag httpx calls for review)
    {
        "name": "httpx_call",
        "pattern": r'httpx\.(?:post|get)\s*\(',
        "flags": re.MULTILINE,
        "severity": "info",
        "message": "httpx call - ensure timeout is set for LLM operations",
        "fix": "Add timeout=httpx.Timeout(120.0, connect=5.0) for LLM calls",
    },
    # requests library (should use httpx)
    {
        "name": "requests_library",
        "pattern": r'import\s+requests|from\s+requests\s+import',
        "flags": re.MULTILINE,
        "severity": "warning",
        "message": "requests library has 120s default timeout, no async support",
        "fix": "Use httpx with explicit timeout for better control",
    },
    # Wrong health endpoint (common agent mistake)
    {
        "name": "wrong_health_endpoint",
        "pattern": r'localhost:4001/health["\'\s]|:4001/health["\'\s]',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "/health does not exist - returns 404",
        "fix": "Use /health/liveliness (basic) or /v1/scillm/health (detailed with auth)",
    },
]

# Positive patterns (good practices to confirm)
POSITIVE_PATTERNS = [
    {
        "name": "http_api",
        "pattern": r'localhost:4001|SCILLM_URL|/v1/chat/completions',
        "message": "Uses HTTP API (not import)",
    },
    {
        "name": "model_alias",
        "pattern": r'["\'](?:text|vlm|local-text|text-gemini)["\']',
        "message": "Uses model aliases",
    },
    {
        "name": "chunk_size",
        "pattern": r'CHUNK_SIZE\s*=|chunk_size\s*=|chunks?\s*\(\s*\w+\s*,\s*\d+\s*\)',
        "message": "Uses chunked batching",
    },
    {
        "name": "response_format",
        "pattern": r'response_format.*json_object|"type":\s*"json_object"',
        "message": "Sets response_format for JSON",
    },
    {
        "name": "preflight_check",
        "pattern": r'health|liveliness|preflight|check_proxy|is_ready',
        "message": "Has preflight check",
    },
]


def check_hardcoded_models(content: str) -> list[dict]:
    """Check for hardcoded model names and suggest corrections."""
    issues = []
    for model, alias in MODEL_CORRECTIONS.items():
        pattern = rf'["\']({re.escape(model)})["\']'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            line = content[:match.start()].count("\n") + 1
            issues.append({
                "line": line,
                "pattern": "hardcoded_model",
                "severity": "warning",
                "message": f"Hardcoded model '{model}' - use proxy alias instead",
                "fix": f"Use '{alias}' instead of '{model}'",
                "sent_value": model,
                "correct_value": alias,
            })
    return issues


def log_misuse_to_memory(file_path: str, issues: list[dict]) -> None:
    """Log misuse findings to memory for cross-project analysis.

    Non-blocking - failures are silently ignored.
    """
    if not issues:
        return
    try:
        import hashlib
        import time
        import httpx

        # Deterministic key based on file + date
        date = time.strftime("%Y-%m-%d")
        key_source = f"scillm-assess:{file_path}:{date}"
        doc_key = hashlib.sha256(key_source.encode()).hexdigest()[:16]

        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=2.0) as client:
            client.post("/store", json={
                "document": {
                    "_key": doc_key,
                    "type": "scillm_assess",
                    "file": file_path,
                    "date": date,
                    "issues": [{"pattern": i["pattern"], "severity": i["severity"]} for i in issues],
                    "error_count": sum(1 for i in issues if i["severity"] == "error"),
                    "warning_count": sum(1 for i in issues if i["severity"] == "warning"),
                },
                "collection": "misuse_events",
            })
    except Exception:
        pass  # Non-blocking


def assess_file(file_path: str, log_to_memory: bool = False) -> dict:
    """Assess a file for scillm usage patterns.

    Returns:
        {
            "file": str,
            "issues": [{"line": int, "pattern": str, "severity": str, "message": str, "fix": str}],
            "good_practices": [{"pattern": str, "message": str}],
            "summary": {"errors": int, "warnings": int, "ok": int}
        }
    """
    path = Path(file_path)
    if not path.exists():
        return {"file": file_path, "error": f"File not found: {file_path}"}

    content = path.read_text()
    issues = []
    good_practices = []

    # Check for misuse patterns
    for p in PATTERNS:
        for match in re.finditer(p["pattern"], content, p.get("flags", 0)):
            line = content[:match.start()].count("\n") + 1
            issues.append({
                "line": line,
                "pattern": p["name"],
                "severity": p["severity"],
                "message": p["message"],
                "fix": p["fix"],
            })

    # Check hardcoded models with corrections map
    issues.extend(check_hardcoded_models(content))

    # Check for positive patterns
    for p in POSITIVE_PATTERNS:
        if re.search(p["pattern"], content, re.MULTILINE):
            good_practices.append({
                "pattern": p["name"],
                "message": p["message"],
            })

    # Summarize
    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")

    return {
        "file": file_path,
        "issues": issues,
        "good_practices": good_practices,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "ok": len(good_practices),
        },
    }


def format_human(result: dict) -> str:
    """Format result for human reading."""
    lines = [f"\n=== scillm usage assessment: {result['file']} ===\n"]

    if "error" in result:
        return f"ERROR: {result['error']}"

    # Good practices first
    for p in result["good_practices"]:
        lines.append(f"  [OK] {p['message']}")

    if not result["good_practices"]:
        lines.append("  [--] No positive patterns detected")

    lines.append("")

    # Issues
    for issue in result["issues"]:
        icon = "[!!]" if issue["severity"] == "error" else "[??]"
        lines.append(f"  {icon} Line {issue['line']}: {issue['message']}")
        lines.append(f"      Fix: {issue['fix']}")

    if not result["issues"]:
        lines.append("  [OK] No issues detected")

    # Summary
    s = result["summary"]
    lines.append(f"\nSummary: {s['errors']} errors, {s['warnings']} warnings, {s['ok']} good practices")

    if s["errors"] > 0:
        lines.append("\nFIX ERRORS BEFORE DEPLOYING - these will cause runtime failures.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Assess scillm usage patterns")
    parser.add_argument("file", help="Python file to assess")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--log", action="store_true", help="Log findings to memory")
    args = parser.parse_args()

    result = assess_file(args.file)

    # Log to memory if requested
    if args.log and "issues" in result:
        log_misuse_to_memory(args.file, result["issues"])

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))

    # Exit code: 1 if errors, 0 otherwise
    if "error" in result or result.get("summary", {}).get("errors", 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
