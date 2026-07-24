"""CWE pattern scanning for /ingest-code.

Contains regex-based CWE detection patterns and the single-file scanner.
Used by the main ingest_code.py scan pipeline for Phase 2 (CWE scanning).
"""

import re
import tokenize
from pathlib import Path
from typing import Any


# CWE pattern rules: {cwe_id: (name, category, [regex_patterns])}
CWE_PATTERNS: dict[str, tuple[str, str, list[str]]] = {
    "CWE-78": ("OS Command Injection", "InputValidation", [
        r"subprocess\.\w+\(.*shell\s*=\s*True", r"os\.system\(", r"os\.popen\(",
    ]),
    "CWE-79": ("Cross-site Scripting (XSS)", "InputValidation", [
        r"\.innerHTML\s*=", r"document\.write\(", r"\bMarkup\b.*\buser",
    ]),
    "CWE-89": ("SQL Injection", "InputValidation", [
        r"f['\"].*(?:SELECT|INSERT|UPDATE|DELETE|DROP).*\{", r"\.format\(.*(?:SELECT|INSERT)",
        r"execute\(\s*f['\"]",
    ]),
    "CWE-94": ("Code Injection", "InputValidation", [
        r"\beval\(", r"\bexec\((?!utor)", r"compile\(.*['\"]exec['\"]",
    ]),
    "CWE-259": ("Hard-coded Password", "Authentication", [
        r"(?:password|passwd|pwd|secret)\s*=\s*['\"][^'\"]{4,}['\"]",
    ]),
    "CWE-295": ("Improper Certificate Validation", "Cryptography", [
        r"verify\s*=\s*False", r"CERT_NONE", r"check_hostname\s*=\s*False",
    ]),
    "CWE-327": ("Broken Crypto Algorithm", "Cryptography", [
        r"(?:hashlib\.)?md5\(.*(?:password|secret|token|key)",
        r"(?:hashlib\.)?sha1\(.*(?:password|secret|token|key)",
        r"\bDES\b(?!C|K|IGN)", r"\bRC4\b",
    ]),
    "CWE-502": ("Deserialization of Untrusted Data", "InputValidation", [
        r"pickle\.loads?\(", r"yaml\.(?:unsafe_)?load\(",
        r"marshal\.loads?\(", r"shelve\.open\(",
    ]),
    "CWE-676": ("Use of Potentially Dangerous Function", "MemorySafety", [
        r"\bgets\(", r"\bstrcpy\(", r"\bsprintf\(",
    ]),
    "CWE-798": ("Hard-coded Credentials", "Authentication", [
        r"(?:api_key|apikey|token|auth)\s*=\s*['\"][A-Za-z0-9_\-]{10,}['\"]",
    ]),
}


def _read_cwe_source_text(filepath: Path) -> str:
    """Read source text using Python's declared encoding when applicable."""
    if filepath.suffix == ".py":
        with tokenize.open(filepath) as source:
            return source.read()
    return filepath.read_text(errors="ignore")


def scan_file_cwe(filepath: Path, taxonomy_module: Any, validate: bool = False) -> dict:
    """Scan a single file for CWE mappings using regex pattern rules.

    Uses compiled regex patterns (~1ms per file). Taxonomy module provides
    bridge_tags for context enrichment.
    """
    try:
        content = _read_cwe_source_text(filepath)[:15000]
    except Exception as e:
        return {"error": str(e), "cwe_mappings": []}

    cwe_mappings = []
    for cwe_id, (name, category, patterns) in CWE_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                cwe_mappings.append({
                    "cwe_id": cwe_id,
                    "name": name,
                    "category": category,
                    "matches": len(matches),
                    "pattern": pattern,
                })
                break  # One match per CWE is enough

    # Get bridge tags from taxonomy for context
    bridge_tags = []
    if taxonomy_module:
        try:
            result = taxonomy_module.extract_taxonomy(content, collection="sparta", fast=True)
            bridge_tags = result.get("bridge_tags", [])
        except Exception:
            pass

    return {
        "file": str(filepath),
        "cwe_mappings": cwe_mappings,
        "bridge_tags": bridge_tags,
        "worth_remembering": len(cwe_mappings) > 0,
    }
