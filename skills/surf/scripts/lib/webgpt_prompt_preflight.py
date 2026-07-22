#!/usr/bin/env python3
"""Detect local-path-heavy WebGPT prompts before browser submit (#34)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "surf.webgpt_prompt_preflight.v1"
SAFE_DEFAULT = "provide_concatenated_text_or_small_zip"
_PATH_TOKEN_RE = re.compile(r"(?:(?:^|\s)|`)((?:~|/|\./|\.\./)[^\s`]+)")
_SKILL_SHORTHAND = re.compile(r"^/(ask|surf|code-runner|scillm|browser-oracle)(?:\s|$)")


def extract_path_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".,;:)>")
        if token.startswith("~") and "/" not in token[1:]:
            continue
        if token.startswith("/") and "/" not in token[1:]:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _resolve_path_token(token: str) -> Path | None:
    try:
        path = Path(token).expanduser()
    except Exception:
        return None
    if not path.is_absolute():
        try:
            path = path.resolve(strict=False)
        except Exception:
            return None
    return path


def _sanitize_path_display(token: str) -> str:
    cleaned = "".join(ch if ch.isprintable() and ord(ch) >= 32 else "?" for ch in token)
    return cleaned[:200]


def _normalize_prompt_text(text: str) -> str:
    return "".join(ch if ch.isprintable() and ord(ch) >= 32 else " " for ch in text)


def validate_prompt_text(text: str, warn_only: bool = False) -> dict:
    text = _normalize_prompt_text(text)
    rows: list[dict] = []
    for token in extract_path_tokens(text):
        path = _resolve_path_token(token)
        exists = bool(path and path.exists())
        rows.append(
            {
                "path": _sanitize_path_display(token),
                "exists_locally": exists,
            }
        )
    has_unresolvable = bool(rows and any(not r["exists_locally"] for r in rows))
    if has_unresolvable and warn_only:
        status = "warn"
    elif rows:
        status = "fail"
    else:
        status = "pass"
    reason = "web_review_bundle_unreadable" if status == "fail" else ("web_review_bundle_warning" if status == "warn" else None)
    browser_submit_allowed = status != "fail"
    return {
        "schema": SCHEMA,
        "status": status,
        "reason": reason,
        "safe_default": SAFE_DEFAULT,
        "local_paths": rows,
        "browser_submit_allowed": browser_submit_allowed,
        "agent_action": (
            "Concatenate readable text into one markdown file or attach a small zip (<=5 files)."
            if status == "fail"
            else (
                "Prompt contains local filesystem path references that may not resolve in the browser. "
                "Submission allowed (--warn-only). Verify the paths are documentation text, not file attachments."
                if status == "warn"
                else "Prompt has no bare local filesystem paths."
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight WebGPT prompt for unreadable local paths")
    parser.add_argument("--input", required=True, help="Prompt markdown file")
    parser.add_argument("--warn-only", action="store_true", help="Warn instead of blocking on unresolvable paths")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.input)
    if not path.is_file():
        payload = {
            "schema": SCHEMA,
            "status": "fail",
            "reason": "input_missing",
            "safe_default": SAFE_DEFAULT,
            "local_paths": [],
            "browser_submit_allowed": False,
            "agent_action": f"Input file not found: {path}",
        }
        print(json.dumps(payload, indent=2))
        return 2
    payload = validate_prompt_text(path.read_text(encoding="utf-8", errors="replace"), warn_only=args.warn_only)
    print(json.dumps(payload, indent=2))
    if payload["status"] == "fail":
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
