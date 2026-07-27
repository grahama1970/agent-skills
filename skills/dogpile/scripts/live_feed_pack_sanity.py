#!/usr/bin/env python3
"""Live Dogpile feed-pack sanity harness."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR.parent))

from dogpile.feeds import search_feeds


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Dogpile feed-pack checks")
    parser.add_argument("--pack", action="append", default=["security_code", "security_code_extended"])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--timeout-s", type=int, default=150)
    parser.add_argument("--out-dir", type=Path, default=SKILL_DIR / "reports" / f"feed-pack-sanity-{_utc_stamp()}")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    for pack in args.pack:
        result = search_feeds("dogpile feed pack sanity", limit=args.limit, feed_pack=pack, timeout_s=args.timeout_s)
        check = {
            "pack": pack,
            "status": "passed" if "error" not in result and result.get("parsed_total", 0) > 0 else "failed",
            "source_count": result.get("source_count"),
            "parsed_total": result.get("parsed_total"),
            "error_total": result.get("error_total"),
            "default_use": result.get("default_use"),
            "inherited_packs": result.get("inherited_packs", []),
            "error": result.get("error"),
            "degraded": [item for item in result.get("results", []) if item.get("errors")],
        }
        checks.append(check)

    failed = [check for check in checks if check["status"] == "failed"]
    receipt = {
        "schema": "dogpile.feed_pack_sanity.v1",
        "mocked": False,
        "live": True,
        "packs": args.pack,
        "limit": args.limit,
        "checks": checks,
        "status": "failed" if failed else "passed",
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.out_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))

    print(json.dumps({"status": receipt["status"], "receipt_path": str(receipt_path), "failed": failed}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
