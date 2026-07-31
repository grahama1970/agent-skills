#!/usr/bin/env python3
"""Optional Context7 documentation lane for Dogpile.

Context7 is useful after the project agent has identified a concrete library,
framework, SDK, or DSL. It is not a broad discovery provider.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
CONTEXT7_DIR = SKILLS_DIR / "context7"

if str(CONTEXT7_DIR) not in sys.path:
    sys.path.insert(0, str(CONTEXT7_DIR))


def _load_context7_helpers():
    from context7 import _get_context, _search_libs  # type: ignore

    return _search_libs, _get_context


def search_context7_docs(
    query: str,
    *,
    library: str | None = None,
    tokens: int = 3000,
    limit: int = 3,
) -> dict[str, Any]:
    """Fetch current library documentation context from Context7.

    A library name or Context7 library ID is required so Dogpile does not turn
    Context7 into a vague web-search substitute.
    """

    selected = (library or "").strip()
    if not selected:
        return {
            "skipped": "Context7 is disabled until a library name or Context7 library ID is provided.",
            "hint": "Use --with-context7 --context7-library <library-or-/owner/repo> for code/API documentation questions.",
            "source_class": "library_documentation",
            "requires_api_key": True,
            "required_env": "CONTEXT7_API_KEY",
        }

    try:
        search_libs, get_context = _load_context7_helpers()
    except Exception as exc:
        return {
            "error": f"Context7 helper import failed: {exc}",
            "hint": "Check skills/context7/context7.py and its dependencies.",
            "source_class": "library_documentation",
            "requires_api_key": True,
            "required_env": "CONTEXT7_API_KEY",
        }

    search_result: dict[str, Any] | None = None
    selected_library_id = selected
    selected_title = selected

    try:
        if not selected.startswith("/"):
            search_result = search_libs(selected, query, limit=limit)
            if search_result.get("error"):
                error = str(search_result["error"])
                status = "skipped_missing_credentials" if "CONTEXT7_API_KEY" in error else "error"
                payload = {
                    "source_class": "library_documentation",
                    "requires_api_key": True,
                    "required_env": "CONTEXT7_API_KEY",
                    "library": selected,
                    "hint": "Set CONTEXT7_API_KEY before enabling the Context7 lane." if status.startswith("skipped") else None,
                }
                if status.startswith("skipped"):
                    payload["skipped"] = error
                    payload["skip_status"] = status
                else:
                    payload["error"] = error
                return payload
            results = search_result.get("results") or []
            if not results:
                return {
                    "skipped": f"Context7 found no library match for {selected!r}.",
                    "hint": "Pass an explicit Context7 library ID such as /facebook/react when search is ambiguous.",
                    "source_class": "library_documentation",
                    "requires_api_key": True,
                    "required_env": "CONTEXT7_API_KEY",
                    "library": selected,
                    "search": search_result,
                }
            first = results[0]
            selected_library_id = first.get("libraryId") or first.get("id") or selected
            selected_title = first.get("title") or first.get("name") or selected_library_id

        context = get_context(selected_library_id, query, tokens=tokens)
    except Exception as exc:
        error = str(exc)
        status = "skipped_missing_credentials" if "CONTEXT7_API_KEY" in error else "error"
        payload = {
            "hint": "Set CONTEXT7_API_KEY before enabling the Context7 lane." if status.startswith("skipped") else None,
            "source_class": "library_documentation",
            "requires_api_key": True,
            "required_env": "CONTEXT7_API_KEY",
            "library": selected,
            "selected_library_id": selected_library_id,
        }
        if status.startswith("skipped"):
            payload["skipped"] = error
            payload["skip_status"] = status
        else:
            payload["error"] = error
        return payload

    if isinstance(context, str) and context.startswith("Error:"):
        return {
            "error": context,
            "hint": "Context7 returned an API error; keep the lane degraded and use Brave/GitHub docs evidence.",
            "source_class": "library_documentation",
            "requires_api_key": True,
            "required_env": "CONTEXT7_API_KEY",
            "library": selected,
            "selected_library_id": selected_library_id,
            "selected_title": selected_title,
            "search": search_result,
        }

    return {
        "library": selected,
        "selected_library_id": selected_library_id,
        "selected_title": selected_title,
        "query": query,
        "tokens_requested": tokens,
        "context": context,
        "context_chars": len(context),
        "search": search_result,
        "source_class": "library_documentation",
        "requires_api_key": True,
        "required_env": "CONTEXT7_API_KEY",
        "content_verdict": "ok" if context.strip() else "empty",
    }
