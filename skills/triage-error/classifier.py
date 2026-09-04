"""Pure, dependency-free failure classifier (no typer/loguru).

Any skill in any environment can import this to canonicalize a raw error signal
without pulling triage-error's CLI dependencies. triage_error.py (the Typer CLI)
and every consumer skill share this one implementation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent / "failure_codes.json"


def load_catalog() -> list[dict[str, Any]]:
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8")).get("codes", [])
    except (OSError, json.JSONDecodeError):
        return []


def load_aliases() -> dict[str, str]:
    """Top-level aliases map: minted code -> canonical catalog code."""
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8")).get("aliases", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _canonical_layer(layer: str | None) -> str:
    """Return the failure-code-safe canonical layer name.

    Failure-code consumers (project-watchdog, shame, receipt validators) accept
    lowercase alphanumerics and underscores. Callers historically passed names
    such as ``project-watchdog``; minting that raw value produced a code the
    caller immediately rejected. Canonicalize once at the vocabulary owner.
    """
    raw = _normalize(layer or "unknown")
    canonical = "_".join(part for part in raw.replace("-", " ").split() if part)
    safe = "".join(ch for ch in canonical if ch.islower() or ch.isdigit() or ch == "_")
    safe = safe.strip("_")
    return safe or "unknown"


def _mint_code(text: str, layer: str | None) -> str:
    digest = hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()[:8]
    return f"{_canonical_layer(layer)}_unclassified_{digest}"


def _first_error_line(text: str) -> str:
    for line in str(text or "").splitlines():
        low = line.lower()
        if any(k in low for k in ("error", "fail", "reject", "not accepted", "timeout", "404", "denied")):
            return line.strip()[:300]
    return str(text or "").strip()[:300]


def _result_from_entry(entry: dict[str, Any], matched_tokens: list[str]) -> dict[str, Any]:
    return {
        "code": entry["code"],
        "layer": entry.get("layer"),
        "cause": entry.get("cause"),
        "next_command": entry.get("next_command"),
        "recoverable": entry.get("recoverable"),
        "not_this": entry.get("not_this", []),
        "ambiguous": False,
        "matched_tokens": matched_tokens,
    }


def _catalog_entry_for_code(catalog: list[dict[str, Any]], code: str, layer: str | None) -> dict[str, Any] | None:
    for entry in catalog:
        if entry.get("code") != code:
            continue
        if layer and entry.get("layer") and entry["layer"] != layer:
            continue
        return entry
    return None


def _explicit_failure_code(text: str) -> tuple[str, str] | None:
    """Return the authoritative code field from a JSON receipt, if present.

    Receipts can include an embedded catalog such as ``failure_codes``. Those
    catalog entries are documentation, not the active failure. Prefer typed
    top-level outcome fields before falling back to substring matching.
    """

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for field in ("active_failure_code", "failure_code", "code"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return field, value.strip()
    report = payload.get("report")
    if isinstance(report, dict):
        value = report.get("code")
        if isinstance(value, str) and value.strip():
            return "report.code", value.strip()
    return None


def classify(text: str, layer: str | None = None) -> dict[str, Any]:
    """Map raw error text to a canonical catalog code, or mint an ambiguous one."""
    catalog = load_catalog()
    explicit = _explicit_failure_code(text)
    if explicit:
        field, code = explicit
        entry = _catalog_entry_for_code(catalog, code, layer)
        if entry:
            return _result_from_entry(entry, [f"{field}:{code}"])

    norm = _normalize(text)
    for entry in catalog:
        if layer and entry.get("layer") and entry["layer"] != layer:
            continue
        tokens = [t.lower() for t in entry.get("match", []) if t]
        if any(tok in norm for tok in tokens):
            return _result_from_entry(entry, [tok for tok in tokens if tok in norm])
    minted = _mint_code(text, layer)
    # Functional aliasing: minting is deterministic over the normalized signal,
    # so a recurring signal re-mints the same code; the aliases map then
    # resolves it to its canonical entry instead of a second identity.
    canonical_code = load_aliases().get(minted)
    if canonical_code:
        entry = _catalog_entry_for_code(catalog, canonical_code, layer) or _catalog_entry_for_code(catalog, canonical_code, None)
        if entry:
            result = _result_from_entry(entry, [f"alias:{minted}"])
            result["aliased_from"] = minted
            return result
    return {
        "code": minted,
        "layer": layer,
        "cause": f"Unclassified error signal: {_first_error_line(text)}",
        "next_command": None,
        "recoverable": None,
        "not_this": [],
        "ambiguous": True,
        "matched_tokens": [],
    }
