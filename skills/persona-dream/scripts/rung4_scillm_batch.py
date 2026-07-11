#!/usr/bin/env python3
import json

import httpx


r = httpx.post(
    "http://localhost:4001/v1/scillm/chutes/batch",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "persona-dream",
    },
    json={
        "requests": [
            {
                "item_id": "security",
                "model": "Qwen/Qwen3-32B-TEE",
                "messages": [{"role": "user", "content": "Reply exactly: security-pass"}],
            },
            {
                "item_id": "quality",
                "model": "Qwen/Qwen3-32B-TEE",
                "messages": [{"role": "user", "content": "Reply exactly: quality-pass"}],
            },
        ],
        "concurrency": 2,
        "wall_time_s": 180,
    },
    timeout=240,
)
r.raise_for_status()

events = []
for line in r.text.splitlines():
    if not line.strip() or line.startswith(":"):
        continue
    if line.startswith("data:"):
        line = line.removeprefix("data:").strip()
    events.append(json.loads(line))

by_id = {}
for e in events:
    if "item_id" in e:
        by_id.setdefault(e["item_id"], "")
        by_id[e["item_id"]] += json.dumps(e).lower()
ok = "security-pass" in by_id.get("security", "") and "quality-pass" in by_id.get("quality", "")
print(json.dumps({"rung": 4, "scillm_batch": True, "items": sorted(by_id), "ok": ok}))
raise SystemExit(0 if ok else 1)
