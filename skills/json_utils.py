#!/usr/bin/env python3
"""Shared JSON helpers for skills (self-contained)."""

import json
import sys
from typing import Any, Dict, List, Optional


def clean_json_string(text: str) -> str:
    """Return a valid JSON string literal from arbitrary text."""
    return json.dumps(text)


def recall_payload(q: str, scope: str = "", k: int = 5, threshold: float = 0.3) -> Dict[str, Any]:
    return {"q": q, "scope": scope, "k": k, "threshold": threshold}


def learn_payload(problem: str, solution: str, scope: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"problem": problem, "solution": solution}
    if scope:
        payload["scope"] = scope
    if tags:
        payload["tags"] = tags
    return payload


def emit(obj: Any) -> None:
    json.dump(obj, sys.stdout)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: json_utils.py <command> ...")
    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "clean":
        if not args:
            raise SystemExit("clean requires a string")
        emit(clean_json_string(args[0]))
        return

    if cmd == "recall":
        if not args:
            raise SystemExit("recall requires at least a query")
        q = args[0]
        scope = args[1] if len(args) > 1 else ""
        k = int(args[2]) if len(args) > 2 else 5
        threshold = float(args[3]) if len(args) > 3 else 0.3
        emit(recall_payload(q, scope, k, threshold))
        return

    if cmd == "learn":
        if len(args) < 2:
            raise SystemExit("learn requires problem and solution")
        problem = args[0]
        solution = args[1]
        scope = args[2] if len(args) > 2 else ""
        tags = args[3].split(",") if len(args) > 3 and args[3] else None
        emit(learn_payload(problem, solution, scope, tags))
        return

    raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
