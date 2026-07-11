#!/usr/bin/env python3
import json

import httpx


last = {}
for attempt in range(1, 4):
    resp = httpx.post(
        "http://localhost:4001/v1/chat/completions",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "X-Caller-Skill": "persona-dream",
        },
        json={
            "model": "gpt-5.5",
            "messages": [
                {
                    "role": "user",
                    "content": 'Return exactly {"pass":true,"finding":""}',
                }
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    content = resp.json()["choices"][0]["message"]["content"]
    last = json.loads(content)
    if resp.status_code == 200 and last == {"pass": True, "finding": ""}:
        print(json.dumps({"rung": 1, "attempts": attempt, "pass": True}))
        raise SystemExit(0)

print(json.dumps({"rung": 1, "attempts": 3, "pass": False, "last": last}))
raise SystemExit(1)
