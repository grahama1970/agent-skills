#!/usr/bin/env python3
"""Fail-closed identity checks for controlled ChatGPT/WebGPT tabs."""

from __future__ import annotations

import argparse
import json
import sys

from resolve_webgpt_tab import parse_tab_list, resolve_url


def _tab_payload(tab: dict[str, str] | None) -> dict[str, str] | None:
    if not tab:
        return None
    return {"id": tab["id"], "title": tab["title"], "url": tab["url"]}


def check_identity(
    tab_id: str,
    tab_list_text: str,
    *,
    expected_url: str = "",
    expected_title: str = "",
    allow_unverified_tab_id: bool = False,
    source: str = "tab-id",
) -> dict:
    digits = "".join(c for c in str(tab_id or "") if c.isdigit())[:20]
    all_chatgpt_tabs = parse_tab_list(tab_list_text)
    tab = next((row for row in all_chatgpt_tabs if row["id"] == digits), None)
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("tab_id_valid", bool(digits), digits or "invalid --tab-id")
    if not digits:
        return {
            "ok": False,
            "error": "invalid_tab_id",
            "tab_id": None,
            "tab": None,
            "chatgpt_tabs_count": len(all_chatgpt_tabs),
            "expected_url": expected_url or None,
            "expected_title": expected_title or None,
            "source": source,
            "checks": checks,
        }

    add("tab_open_chatgpt", tab is not None, "ok" if tab else f"no open chatgpt tab {digits}")
    if tab is None:
        return {
            "ok": False,
            "error": "tab_not_open_chatgpt",
            "tab_id": digits,
            "tab": None,
            "chatgpt_tabs_count": len(all_chatgpt_tabs),
            "expected_url": expected_url or None,
            "expected_title": expected_title or None,
            "source": source,
            "checks": checks,
        }

    url_verified = False
    title_verified = False

    if expected_url:
        resolved = resolve_url(expected_url, all_chatgpt_tabs)
        ok = bool(resolved.get("ok") and resolved.get("tab_id") == digits)
        detail = (
            f"expected_url matched tab {digits}"
            if ok
            else f"expected_url resolved {resolved.get('tab_id')} error={resolved.get('error')}"
        )
        add("expected_url_matches_tab", ok, detail)
        if not ok:
            return {
                "ok": False,
                "error": "expected_url_mismatch",
                "tab_id": digits,
                "tab": _tab_payload(tab),
                "chatgpt_tabs_count": len(all_chatgpt_tabs),
                "expected_url": expected_url,
                "expected_title": expected_title or None,
                "url_resolution": resolved,
                "source": source,
                "checks": checks,
            }
        url_verified = True

    if expected_title:
        ok = expected_title.casefold() in tab["title"].casefold()
        add(
            "expected_title_matches_tab",
            ok,
            "ok" if ok else f"title={tab['title']!r}",
        )
        if not ok:
            return {
                "ok": False,
                "error": "expected_title_mismatch",
                "tab_id": digits,
                "tab": _tab_payload(tab),
                "chatgpt_tabs_count": len(all_chatgpt_tabs),
                "expected_url": expected_url or None,
                "expected_title": expected_title,
                "source": source,
                "checks": checks,
            }
        title_verified = True

    verified = url_verified or title_verified or allow_unverified_tab_id or source in {
        "url",
        "create-tab",
    }
    if len(all_chatgpt_tabs) > 1 and not verified:
        add(
            "tab_identity_verified_or_allowed",
            False,
            "multiple ChatGPT tabs require --expect-url, --expect-title, --url, --create-tab, or --allow-unverified-tab-id",
        )
        return {
            "ok": False,
            "error": "unverified_tab_id_with_multiple_chatgpt_tabs",
            "tab_id": digits,
            "tab": _tab_payload(tab),
            "chatgpt_tabs_count": len(all_chatgpt_tabs),
            "expected_url": expected_url or None,
            "expected_title": expected_title or None,
            "source": source,
            "checks": checks,
        }

    add(
        "tab_identity_verified_or_allowed",
        True,
        "verified" if (url_verified or title_verified) else "allowed",
    )
    return {
        "ok": True,
        "error": None,
        "tab_id": digits,
        "tab": _tab_payload(tab),
        "chatgpt_tabs_count": len(all_chatgpt_tabs),
        "expected_url": expected_url or None,
        "expected_title": expected_title or None,
        "source": source,
        "checks": checks,
    }


def cmd_check(args: argparse.Namespace) -> int:
    result = check_identity(
        args.tab_id,
        sys.stdin.read(),
        expected_url=args.expect_url or "",
        expected_title=args.expect_title or "",
        allow_unverified_tab_id=args.allow_unverified_tab_id,
        source=args.source,
    )
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if result["ok"] else 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Validate a controlled WebGPT tab id")
    check.add_argument("--tab-id", required=True)
    check.add_argument("--expect-url", default="")
    check.add_argument("--expect-title", default="")
    check.add_argument("--allow-unverified-tab-id", action="store_true")
    check.add_argument(
        "--source",
        choices=["tab-id", "url", "create-tab", "remembered"],
        default="tab-id",
    )
    check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
