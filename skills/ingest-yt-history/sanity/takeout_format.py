#!/usr/bin/env python3
"""
Sanity script: Verify Google Takeout watch-history.json format.

PURPOSE: Validate that we can parse Takeout JSON structure.
EXIT CODES: 0=PASS, 1=FAIL, 42=CLARIFY (needs human)
"""
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
FIXTURE = SKILL_DIR / "fixtures" / "sample_watch_history.json"


def verify_takeout_format():
    """Verify Takeout JSON has expected structure."""
    if not FIXTURE.exists():
        print(f"FAIL: Fixture not found: {FIXTURE}")
        return 1

    with open(FIXTURE) as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("FAIL: Takeout JSON should be a list of watch entries")
        return 1

    required_fields = {"title", "titleUrl", "time"}
    for i, entry in enumerate(data):
        missing = required_fields - set(entry.keys())
        if missing:
            print(f"FAIL: Entry {i} missing fields: {missing}")
            return 1

        # Verify URL contains video ID
        url = entry.get("titleUrl", "")
        if "watch?v=" not in url:
            print(f"FAIL: Entry {i} URL doesn't contain video ID: {url}")
            return 1

        # Verify timestamp is ISO format
        ts = entry.get("time", "")
        if not ts.endswith("Z") and "T" not in ts:
            print(f"FAIL: Entry {i} timestamp not ISO format: {ts}")
            return 1

    print(f"PASS: Takeout format verified ({len(data)} entries)")
    print(f"  - All entries have: title, titleUrl, time")
    print(f"  - URL format: watch?v=VIDEO_ID")
    print(f"  - Timestamp format: ISO 8601")

    # Show sample entry
    sample = data[0]
    print(f"\nSample entry:")
    print(f"  header: {sample.get('header', 'N/A')}")
    print(f"  title: {sample.get('title', 'N/A')}")
    print(f"  url: {sample.get('titleUrl', 'N/A')}")
    print(f"  time: {sample.get('time', 'N/A')}")
    print(f"  products: {sample.get('products', [])}")

    return 0


if __name__ == "__main__":
    sys.exit(verify_takeout_format())
