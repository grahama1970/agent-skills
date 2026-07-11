#!/usr/bin/env python3
import json

import httpx


resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "persona-dream",
    },
    json={
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": 'Return exactly {"ok":true}'}],
        "response_format": {"type": "json_object"},
    },
    timeout=60,
)

content = resp.json()["choices"][0]["message"]["content"]
ok = resp.status_code == 200 and json.loads(content) == {"ok": True}
print(json.dumps({"rung": 0, "ok": ok, "status": resp.status_code}))
raise SystemExit(0 if ok else 1)
