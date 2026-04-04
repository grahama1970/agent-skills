#!/usr/bin/env python3
"""Sanity script: Gemini Flash 2.5 via scillm proxy.

Verifies that the scillm proxy at localhost:4001 can route to
the text-gemini model (Gemini Flash 2.5).

Exit codes: 0=PASS, 1=FAIL
"""
import json
import sys

import httpx

SCILLM_PROXY_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_PROXY_KEY = "sk-dev-proxy-123"
MODEL = "text-gemini"

try:
    resp = httpx.post(
        SCILLM_PROXY_URL,
        headers={"Authorization": f"Bearer {SCILLM_PROXY_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: SANITY_OK"}],
            "max_tokens": 20,
            "temperature": 0.0,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    model_used = data.get("model", "unknown")

    if "SANITY" in content.upper():
        print(f"PASS: text-gemini routes to {model_used}")
        print(f"  Response: {content}")
        sys.exit(0)
    else:
        print(f"WARN: Unexpected response but model responded: {content[:100]}")
        print(f"  Model: {model_used}")
        # Still pass — model is reachable
        sys.exit(0)

except httpx.ConnectError:
    print("FAIL: Cannot connect to scillm proxy at localhost:4001")
    sys.exit(1)
except httpx.TimeoutException:
    print("FAIL: scillm proxy timed out (30s)")
    sys.exit(1)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
