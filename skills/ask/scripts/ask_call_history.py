#!/usr/bin/env python3
"""Print $ask call history for one handler from $memory.

Usage:
  python3 scripts/ask_call_history.py --handler webgemini
  python3 scripts/ask_call_history.py --handler webgpt --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ask import call_log  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handler", required=True, help="handler name, e.g. webgemini, webgpt, gpt-5.5-high")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    history = call_log.call_history(args.handler, limit=args.limit)
    if args.json:
        print(json.dumps(history, indent=2))
        return 0
    print(f"handler: {history['handler']}  records: {history['total']}")
    last = history["last_success"]
    if last:
        print(f"last success: {last.get('ts')} run={last.get('run_dir')}")
        if last.get("conversation_url"):
            print(f"  conversation: {last['conversation_url']} (tab {last.get('controlled_tab_id')})")
    else:
        print("last success: none recorded")
    failures = history["recent_failures"]
    print(f"recent failures: {len(failures)}")
    for doc in failures:
        print(f"  {doc.get('ts')} {doc.get('failure_code') or 'unknown'} run={doc.get('run_dir')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
