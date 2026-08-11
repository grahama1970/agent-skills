"""Provenance-safe documentation metadata for code-symbol records.

This module provides deterministic enrichment for `ingest-code` symbol records:
- source-docstring status and documentation-need classification;
- source-fact evidence packets used by optional summary generators;
- validation of current versus stale derived summaries;
- one canonical semantic input string for Memory retrieval.

Inputs:
- CodeSymbolRecord-like objects with source path, signature, code, calls,
  imports, parameters, hashes, and optional derived_summary metadata.

Outputs:
- JSON-serializable metadata and retrieval text. It never writes source files
  and never treats generated prose as developer-authored documentation.

Failure modes:
- Unsupported or malformed generated summaries are rejected by returning None.
- Missing source facts degrade to conservative status/reason fields.

Dependencies:
- Python standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SEMANTIC_INPUT_SCHEMA = "ingest-code.symbol_semantic_input.v1"
SUMMARY_EVIDENCE_SCHEMA = "ingest-code.symbol_summary_evidence.v1"
DERIVED_SUMMARY_SCHEMA = "ingest-code.derived_symbol_summary.v1"

DOCSTRING_STATUSES = {"present", "missing", "inherited", "generated_file", "not_applicable"}
DOCUMENTATION_NEEDS = {"required", "recommended", "optional", "exempt"}

GENERATED_PATH_MARKERS = (
    "generated",
    "__generated__",
    ".generated.",
    "vendor/",
    "dist/",
    "build/",
)
EXTERNAL_IO_CALL_MARKERS = (
    "open",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "httpx",
    "requests",
    "subprocess",
    "socket",
)
PERSISTENCE_CALL_MARKERS = (
    "commit",
    "upsert",
    "delete",
    "prune",
    "write",
    "replace",
    "store",
    "persist",
)
SECURITY_MARKERS = (
    "auth",
    "token",
    "secret",
    "password",
    "scope",
    "cwe",
    "permission",
    "credential",
)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _get(record: Any, name: str, default: Any = "") -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def source_docstring(record: Any) -> str:
    """Return exact authored source docstring text."""
    return str(_get(record, "source_docstring", "") or _get(record, "docstring", "") or "")


def _is_generated_file(path: str, code: str) -> bool:
    lowered_path = path.lower().replace("\\", "/")
    lowered_code = code[:800].lower()
    return any(marker in lowered_path for marker in GENERATED_PATH_MARKERS) or "generated file" in lowered_code


def source_docstring_status(record: Any) -> str:
    path = str(_get(record, "path", "") or _get(record, "normalized_path", "") or "")
    code = str(_get(record, "code", "") or "")
    if _is_generated_file(path, code):
        return "generated_file"
    kind = str(_get(record, "symbol_kind", "") or "").lower()
    if kind in {"module", "variable", "constant", "field"}:
        return "not_applicable"
    if source_docstring(record):
        return "present"
    return "missing"


def _indicators(record: Any) -> dict[str, bool]:
    code = str(_get(record, "code", "") or "")
    lowered_code = code.lower()
    calls = [item.lower() for item in _as_list(_get(record, "called_symbols", []))]
    imports = [item.lower() for item in _as_list(_get(record, "imports", []))]
    combined = " ".join([lowered_code, *calls, *imports])
    return {
        "returns": bool(re.search(r"\breturn\b", code)),
        "yields": bool(re.search(r"\byield\b", code)),
        "explicit_raises": bool(re.search(r"\braise\b", code)),
        "external_io": any(marker in combined for marker in EXTERNAL_IO_CALL_MARKERS),
        "persistence": any(marker in combined for marker in PERSISTENCE_CALL_MARKERS),
        "security": any(marker in combined for marker in SECURITY_MARKERS),
        "mutation": bool(re.search(r"(\.append|\.extend|\.update|\.pop|\.remove|\[[^\]]+\]\s*=)", code)),
    }


def documentation_need(record: Any) -> dict[str, Any]:
    """Classify documentation need deterministically from source facts."""
    status = source_docstring_status(record)
    if status in {"present", "generated_file", "not_applicable"}:
        need = "exempt" if status != "present" else "optional"
        return {
            "documentation_need": need,
            "documentation_need_reasons": [status],
            "source_docstring_status": status,
        }

    name = str(_get(record, "symbol_name", "") or "")
    kind = str(_get(record, "symbol_kind", "") or "")
    code = str(_get(record, "code", "") or "")
    calls = _as_list(_get(record, "called_symbols", []))
    line_count = max(0, len(code.splitlines()))
    indicators = _indicators(record)
    reasons: list[str] = []
    if not name.startswith("_"):
        reasons.append("public_api")
    if line_count > 20 or len(calls) > 4:
        reasons.append("complex_private_logic" if name.startswith("_") else "complex_logic")
    for reason in ("external_io", "persistence", "security", "explicit_raises", "mutation"):
        if indicators[reason]:
            reasons.append(reason)
    risky_indicators = (
        indicators["explicit_raises"]
        or indicators["external_io"]
        or indicators["persistence"]
        or indicators["security"]
        or indicators["mutation"]
    )
    if name.startswith("_") and line_count <= 3 and not risky_indicators:
        reasons.append("trivial_helper")

    if any(reason in reasons for reason in ("public_api", "external_io", "persistence", "security", "explicit_raises")):
        need = "required"
    elif "complex_private_logic" in reasons or "complex_logic" in reasons or "mutation" in reasons:
        need = "recommended"
    elif "trivial_helper" in reasons:
        need = "exempt"
    else:
        need = "optional"
    return {
        "documentation_need": need,
        "documentation_need_reasons": sorted(set(reasons or ["missing"])),
        "source_docstring_status": status,
    }


def summary_evidence(record: Any) -> dict[str, Any]:
    """Build a deterministic source-fact packet for optional summarization."""
    payload = {
        "schema": SUMMARY_EVIDENCE_SCHEMA,
        "symbol_id": str(_get(record, "symbol_id", "")),
        "symbol_version_id": str(_get(record, "symbol_version_id", "")),
        "repo": str(_get(record, "repo", "")),
        "branch": str(_get(record, "branch", "")),
        "path": str(_get(record, "path", "") or _get(record, "normalized_path", "")),
        "symbol_kind": str(_get(record, "symbol_kind", "")),
        "symbol_name": str(_get(record, "symbol_name", "")),
        "qualified_name": str(_get(record, "qualified_name", "")),
        "signature": str(_get(record, "signature", "")),
        "parameters": sorted(_as_list(_get(record, "parameters", []))),
        "imports": sorted(_as_list(_get(record, "imports", []))),
        "calls": sorted(_as_list(_get(record, "called_symbols", []))),
        "source_hash": str(_get(record, "content_hash", "") or _get(record, "effective_content_hash", "")),
        "source_docstring_sha256": sha256_payload(source_docstring(record)),
        "indicators": _indicators(record),
    }
    payload["evidence_sha256"] = sha256_payload(payload)
    return payload


def current_derived_summary(summary: Any, evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a current derived summary or None for stale/malformed summaries."""
    if not isinstance(summary, Mapping):
        return None
    text = str(summary.get("text") or "").strip()
    if not text:
        return None
    if summary.get("status") != "derived_unreviewed":
        return None
    if summary.get("source_symbol_version_id") != evidence.get("symbol_version_id"):
        return None
    if summary.get("source_content_hash") != evidence.get("source_hash"):
        return None
    if summary.get("summary_evidence_sha256") != evidence.get("evidence_sha256"):
        return None
    return {
        "schema": DERIVED_SUMMARY_SCHEMA,
        "text": text,
        "status": "derived_unreviewed",
        "source_symbol_version_id": summary["source_symbol_version_id"],
        "source_content_hash": summary["source_content_hash"],
        "summary_evidence_sha256": summary["summary_evidence_sha256"],
        "generator": str(summary.get("generator") or "unknown"),
        "model": str(summary.get("model") or "unavailable"),
        "prompt_sha256": str(summary.get("prompt_sha256") or ""),
        "created_at": str(summary.get("created_at") or ""),
        "limitations": _as_list(summary.get("limitations", [])),
    }


def make_derived_summary(
    *,
    text: str,
    evidence: Mapping[str, Any],
    generator: str,
    model: str,
    prompt: str,
    created_at: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Create a provenance-bearing unreviewed derived summary artifact."""
    return {
        "schema": DERIVED_SUMMARY_SCHEMA,
        "text": text.strip(),
        "status": "derived_unreviewed",
        "source_symbol_version_id": evidence.get("symbol_version_id", ""),
        "source_content_hash": evidence.get("source_hash", ""),
        "summary_evidence_sha256": evidence.get("evidence_sha256", ""),
        "generator": generator,
        "model": model,
        "prompt_sha256": sha256_payload(prompt),
        "created_at": created_at,
        "limitations": list(limitations or []),
    }


def _implementation_excerpt_without_docstring(record: Any, docstring: str) -> str:
    code = str(_get(record, "code", "") or "")
    if not docstring:
        return code[:1200]
    escaped = re.escape(docstring)
    without_doc = re.sub(rf"(['\"]{{3}}){escaped}\1", "", code, count=1, flags=re.DOTALL).strip()
    return without_doc[:1200]


def semantic_input(record: Any, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return canonical retrieval text with purpose represented once."""
    evidence = dict(evidence or summary_evidence(record))
    authored = source_docstring(record)
    derived = current_derived_summary(_get(record, "derived_summary", None), evidence)
    purpose_source = "authored" if authored else ("derived" if derived else "none")
    purpose_text = authored or (derived["text"] if derived else "")

    sections = [
        f"Repository: {str(_get(record, 'repo', ''))}",
        f"Path: {str(_get(record, 'path', '') or _get(record, 'normalized_path', ''))}",
        f"Kind: {str(_get(record, 'symbol_kind', ''))}",
        f"Qualified name: {str(_get(record, 'qualified_name', ''))}",
    ]
    if purpose_text:
        sections.append(f"Purpose ({purpose_source}): {purpose_text}")
    signature = str(_get(record, "signature", "") or "")
    if signature:
        sections.append(f"Signature: {signature}")
    parameters = _as_list(_get(record, "parameters", []))
    if parameters:
        sections.append(f"Parameters: {', '.join(parameters[:20])}")
    calls = _as_list(_get(record, "called_symbols", []))
    if calls:
        sections.append(f"Calls: {', '.join(calls[:20])}")
    imports = _as_list(_get(record, "imports", []))
    if imports:
        sections.append(f"Imports: {', '.join(imports[:20])}")
    excerpt = _implementation_excerpt_without_docstring(record, authored)
    if excerpt:
        sections.append(f"Implementation excerpt:\n{excerpt}")
    text = "\n".join(sections)
    return {
        "schema": SEMANTIC_INPUT_SCHEMA,
        "text": text,
        "text_sha256": sha256_payload(text),
        "purpose_source": purpose_source,
        "derived_summary_current": derived is not None,
        "derived_summary": derived,
    }
