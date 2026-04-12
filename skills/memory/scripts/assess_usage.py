#!/usr/bin/env python3
"""Assess external code for correct memory API usage patterns.

Detects common misuse patterns that cause silent failures, performance issues,
or data corruption. Run via: ./run.sh assess <file.py>

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
# Misuse patterns to detect
# =============================================================================

PATTERNS = [
    # data["results"] instead of data["items"] (CRITICAL)
    {
        "name": "wrong_key_results",
        "pattern": r'data\s*\[\s*["\']results["\']\s*\]|\.get\s*\(\s*["\']results["\']',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": 'data["results"] does not exist - the key is "items"',
        "fix": 'Use data["items"] or data.get("items", [])',
    },
    # TCP instead of Unix socket
    {
        "name": "tcp_instead_of_socket",
        "pattern": r'http://(?:localhost|127\.0\.0\.1):8601',
        "flags": re.MULTILINE,
        "severity": "warning",
        "message": "TCP connection to memory API - prefer Unix socket for lower latency",
        "fix": 'transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")',
    },
    # subprocess.run with memory/run.sh in loop
    {
        "name": "subprocess_loop",
        "pattern": r'subprocess\.(?:run|call|Popen).*(?:memory|run\.sh).*(?:recall|learn|store)',
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "error",
        "message": "subprocess.run in loop - 2s overhead per call, fork-bomb risk",
        "fix": "Use httpx client with connection pooling instead",
    },
    # for loop containing subprocess with memory
    {
        "name": "loop_subprocess",
        "pattern": r'for\s+\w+\s+in.*:\s*\n[^}]*subprocess.*(?:memory|run\.sh)',
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "error",
        "message": "subprocess inside loop - causes fork-bomb (learn-datalake incident)",
        "fix": "Use single httpx.Client with connection reuse for all calls",
    },
    # Direct ArangoDB import (forbidden outside memory project)
    {
        "name": "direct_arango_import",
        "pattern": r'from\s+arango\s+import|import\s+arango',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "Direct ArangoDB import - all AQL must be in memory project",
        "fix": "Use /recall, /list, /store endpoints via HTTP API",
    },
    # Raw AQL execution
    {
        "name": "raw_aql",
        "pattern": r'\.aql\.execute|AQL|FOR\s+doc\s+IN\s+\w+\s+FILTER',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "Raw AQL query outside memory project",
        "fix": "Move AQL to memory project, expose via HTTP endpoint",
    },
    # /learn endpoint (deprecated)
    {
        "name": "deprecated_learn",
        "pattern": r'/learn["\']|\.post\s*\(\s*["\'].*learn',
        "flags": re.MULTILINE,
        "severity": "warning",
        "message": "/learn is DEPRECATED - it always writes to lessons collection",
        "fix": 'Use /store with explicit collection: {"document": {...}, "collection": "my_coll"}',
    },
    # /store without tags for lessons
    {
        "name": "lessons_without_tags",
        "pattern": r'/store.*problem.*solution(?:(?!tags).)*\}',
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "warning",
        "message": "Lesson stored without tags - multi-hop traversal won't find it",
        "fix": 'Add "tags": ["Fragility", "extraction", ...] for graph discovery',
    },
    # from graph_memory import (bypass daemon)
    {
        "name": "direct_graph_memory_import",
        "pattern": r'from\s+graph_memory\s+import|import\s+graph_memory',
        "flags": re.MULTILINE,
        "severity": "error",
        "message": "Direct graph_memory import bypasses daemon - no BM25/embedding scoring",
        "fix": "Use HTTP client to memory daemon at /run/user/1000/embry/memory.sock",
    },
    # requests library instead of httpx
    {
        "name": "requests_library",
        "pattern": r'import\s+requests|from\s+requests\s+import',
        "flags": re.MULTILINE,
        "severity": "warning",
        "message": "requests library has 120s default timeout, no Unix socket support",
        "fix": "Use httpx with HTTPTransport(uds=...) for Unix socket support",
    },
    # Missing timeout on memory calls
    {
        "name": "missing_timeout",
        "pattern": r'client\.post\s*\(\s*["\']/?recall["\'](?:(?!timeout).)*\)',
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "warning",
        "message": "Memory API call without explicit timeout",
        "fix": "Add timeout=httpx.Timeout(10.0, connect=2.0) for recall calls",
    },
    # Building manual corpus with rapidfuzz
    {
        "name": "manual_corpus_rapidfuzz",
        "pattern": r'rapidfuzz|fuzz\.(?:partial_ratio|ratio)',
        "flags": re.MULTILINE,
        "severity": "warning",
        "message": "Manual fuzzy matching - the daemon already does BM25+cosine+graph",
        "fix": 'Just read data["confidence"] from /recall - scoring is already done',
    },
    # Reimplementing /recall with multiple /list calls
    {
        "name": "reimplementing_recall",
        "pattern": r'for\s+\w+\s+in\s+\[.*sparta.*\].*:.*\.post.*["\']/?list["\']',
        "flags": re.MULTILINE | re.DOTALL,
        "severity": "warning",
        "message": "Reimplementing /recall with /list loops - use unified View instead",
        "fix": 'Single /recall call with collections param: {"q": query, "collections": [...]}',
    },
]

# Positive patterns (good practices to confirm)
POSITIVE_PATTERNS = [
    {
        "name": "unix_socket",
        "pattern": r'HTTPTransport\s*\(\s*uds\s*=|memory\.sock',
        "message": "Uses Unix socket transport",
    },
    {
        "name": "correct_items_key",
        "pattern": r'data\s*\[\s*["\']items["\']\s*\]|\.get\s*\(\s*["\']items["\']',
        "message": 'Reads data["items"] (correct key)',
    },
    {
        "name": "http_client",
        "pattern": r'httpx\.Client|httpx\.AsyncClient',
        "message": "Uses httpx client (connection pooling)",
    },
    {
        "name": "store_endpoint",
        "pattern": r'/store["\']|\.post.*store',
        "message": "Uses /store endpoint (current API)",
    },
    {
        "name": "explicit_timeout",
        "pattern": r'timeout\s*=\s*(?:httpx\.Timeout|[\d.]+)',
        "message": "Sets explicit timeout",
    },
    {
        "name": "confidence_check",
        "pattern": r'["\']confidence["\']|data\.get\s*\(\s*["\']confidence',
        "message": "Checks confidence score",
    },
    {
        "name": "should_scan_check",
        "pattern": r'should_scan',
        "message": "Checks should_scan for hybrid search",
    },
]


def assess_file(file_path: str) -> dict:
    """Assess a file for memory API usage patterns.

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
    lines = [f"\n=== memory usage assessment: {result['file']} ===\n"]

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
    parser = argparse.ArgumentParser(description="Assess memory API usage patterns")
    parser.add_argument("file", help="Python file to assess")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = assess_file(args.file)

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
