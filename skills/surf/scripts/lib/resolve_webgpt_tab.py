#!/usr/bin/env python3
"""Resolve Chrome tab ids for ChatGPT/WebGPT from tab.list TSV and URLs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urlparse

_CONV_RE = re.compile(
    r"chatgpt\.com/c/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{10,})",
)


def normalize_chatgpt_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return f"https://{host}{path}"


def conversation_id(url: str) -> str | None:
    match = _CONV_RE.search(url or "")
    return match.group(1).lower() if match else None


def parse_tab_list(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        tab_id, title, tab_url = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not tab_id.isdigit():
            continue
        if "chatgpt.com" not in tab_url:
            continue
        rows.append({"id": tab_id, "title": title, "url": tab_url})
    return rows


def resolve_url(target_url: str, tabs: list[dict[str, str]]) -> dict:
    target_norm = normalize_chatgpt_url(target_url)
    target_cid = conversation_id(target_norm)
    exact: list[dict[str, str]] = []
    by_cid: list[dict[str, str]] = []
    for tab in tabs:
        tab_norm = normalize_chatgpt_url(tab["url"])
        if tab_norm == target_norm:
            exact.append(tab)
            continue
        if target_cid and conversation_id(tab_norm) == target_cid:
            by_cid.append(tab)

    candidates = exact if exact else by_cid
    if not candidates:
        return {
            "ok": False,
            "error": "no_open_tab_for_url",
            "requested_url": target_url,
            "normalized_url": target_norm,
            "tab_id": None,
            "candidates": [],
        }
    if len(candidates) > 1:
        return {
            "ok": False,
            "error": "ambiguous_url",
            "requested_url": target_url,
            "normalized_url": target_norm,
            "tab_id": None,
            "candidates": [
                {"id": t["id"], "url": t["url"], "title": t["title"]} for t in candidates
            ],
        }
    tab = candidates[0]
    return {
        "ok": True,
        "error": None,
        "requested_url": target_url,
        "normalized_url": target_norm,
        "tab_id": tab["id"],
        "matched_url": tab["url"],
        "candidates": [],
    }


def cmd_resolve_url(args: argparse.Namespace) -> int:
    tabs = parse_tab_list(sys.stdin.read())
    result = resolve_url(args.url, tabs)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if result["ok"] else 1


def cmd_normalize_url(args: argparse.Namespace) -> int:
    sys.stdout.write(normalize_chatgpt_url(args.url) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve-url", help="Match --url to an open chatgpt.com tab id")
    resolve.add_argument("--url", required=True)
    resolve.set_defaults(func=cmd_resolve_url)

    norm = sub.add_parser("normalize-url", help="Print normalized ChatGPT URL")
    norm.add_argument("--url", required=True)
    norm.set_defaults(func=cmd_normalize_url)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
