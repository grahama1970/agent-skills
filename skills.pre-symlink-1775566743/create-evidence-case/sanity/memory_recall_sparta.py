#!/usr/bin/env python3
"""Sanity script: /memory daemon recall for sparta_qra scope.

Verifies that the memory daemon is running and can recall QRAs
from the sparta_qra scope.

Exit codes: 0=PASS, 1=FAIL
"""
import json
import os
import sys
from pathlib import Path

import httpx

MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)

socket_path = Path(MEMORY_SOCKET)
if not socket_path.exists():
    print(f"FAIL: Memory daemon socket not found: {MEMORY_SOCKET}")
    sys.exit(1)

transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
client = httpx.Client(transport=transport, base_url="http://memory-daemon", timeout=30.0)

try:
    resp = client.post("/recall", json={"q": "system hardening countermeasures", "scope": "sparta_qra", "limit": 5})
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])

    if not items:
        print("FAIL: /recall returned 0 items for sparta_qra scope")
        sys.exit(1)

    # Check that items have expected fields
    first = items[0]
    has_question = "question" in first or "problem" in first
    has_answer = "answer" in first or "solution" in first

    if not (has_question and has_answer):
        print(f"FAIL: Recall items missing question/answer fields. Keys: {list(first.keys())[:10]}")
        sys.exit(1)

    # Check for citations field
    has_citations = any("citations" in item for item in items)

    print(f"PASS: /recall returned {len(items)} items from sparta_qra")
    print(f"  Fields: {sorted(list(first.keys()))[:12]}")
    print(f"  Citations present: {has_citations}")
    sys.exit(0)

except httpx.HTTPStatusError as e:
    print(f"FAIL: /recall returned {e.response.status_code}: {e.response.text[:200]}")
    sys.exit(1)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
finally:
    client.close()
