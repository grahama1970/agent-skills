"""Minimal module used by the persona-review-implement DAG example."""

from __future__ import annotations


def normalize_handoff_id(raw: str) -> str:
    candidate = raw.strip().replace(".", "-")
    if not candidate:
        raise ValueError("handoff_id must be non-empty")
    return candidate


def merge_paths(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part]
    return "/".join(cleaned)
