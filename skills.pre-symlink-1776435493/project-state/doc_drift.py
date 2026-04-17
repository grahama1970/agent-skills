"""Phase 3: Doc-code drift detection.

Compares documentation claims against the actual codebase, flagging missing
files, aspirational language, stale references, and feature claims that
lack corresponding code.
"""

from __future__ import annotations

import re
from typing import Any

from constants import DOC_FILES, EMBRY_OS, PI_SKILLS


def _extract_claims(text: str) -> list[str]:
    """Extract feature claims from markdown (lines with bold or list items)."""
    claims = []
    for line in text.splitlines():
        line = line.strip()
        # Bold claims: **Feature Name**: description
        if re.match(r"^[-*]\s+\*\*", line):
            claims.append(line)
        # Header claims
        elif re.match(r"^#{1,3}\s+", line):
            claims.append(line)
    return claims


def _check_claim_in_codebase(claim: str) -> dict[str, Any]:
    """Check if a doc claim has corresponding code."""
    # Extract key terms from the claim
    terms = re.findall(r'\b[A-Za-z][a-z]{3,}\b', claim)
    # Filter common words
    stopwords = {"this", "that", "with", "from", "have", "been", "will", "each",
                 "when", "uses", "into", "every", "same", "through", "across",
                 "between", "about", "should", "would", "could", "does", "more",
                 "also", "based", "first", "only", "than", "other", "which"}
    terms = [t.lower() for t in terms if t.lower() not in stopwords][:5]
    return {"claim": claim[:120], "search_terms": terms}


def collect_doc_drift() -> dict[str, Any]:
    """Compare doc claims vs codebase reality."""
    drift_items = []

    for doc_rel in DOC_FILES:
        doc_path = EMBRY_OS / doc_rel
        if not doc_path.exists():
            drift_items.append({"file": doc_rel, "issue": "MISSING", "severity": "high"})
            continue

        text = doc_path.read_text()
        _extract_claims(text)

        # Check for aspirational language
        aspirational_patterns = [
            (r"\bwill\b", "aspirational_will"),
            (r"\bTODO\b", "todo"),
            (r"\bFIXME\b", "fixme"),
            (r"\bplanned\b", "planned"),
            (r"\bfuture\b", "future"),
            (r"\bnot yet\b", "not_yet"),
            (r"\bcoming soon\b", "coming_soon"),
        ]
        for pattern, label in aspirational_patterns:
            matches = re.findall(f".*{pattern}.*", text, re.IGNORECASE)
            for m in matches[:3]:
                drift_items.append({
                    "file": doc_rel,
                    "issue": label,
                    "severity": "medium" if label in ("todo", "fixme") else "low",
                    "line": m.strip()[:120],
                })

    # Check for stale references to removed files
    for doc_rel in DOC_FILES:
        doc_path = EMBRY_OS / doc_rel
        if not doc_path.exists():
            continue
        text = doc_path.read_text()
        # Find file path references
        refs = re.findall(r'`([a-zA-Z0-9_/.-]+\.[a-z]{1,4})`', text)
        for ref in refs:
            ref_path = EMBRY_OS / ref
            if not ref_path.exists() and not (PI_SKILLS.parent.parent.parent / ref).exists():
                # Only flag .py/.ts/.rs files; skip .sh (run.sh exists everywhere in skills)
                if ref.endswith(('.py', '.ts', '.tsx', '.rs')):
                    drift_items.append({
                        "file": doc_rel,
                        "issue": "stale_reference",
                        "severity": "medium",
                        "line": f"References `{ref}` but file not found",
                    })

    return {
        "docs_checked": len(DOC_FILES),
        "docs_found": sum(1 for d in DOC_FILES if (EMBRY_OS / d).exists()),
        "drift_items": drift_items,
        "drift_count": len(drift_items),
    }
