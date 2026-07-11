#!/usr/bin/env python3
import asyncio
import json
import time

import httpx


URL = "http://localhost:4001/v1/scillm/chutes/completions"
HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "persona-dream",
}
MODEL = "Qwen/Qwen3-32B-TEE"


async def review(client, item):
    t0 = time.monotonic()
    r = await client.post(
        URL,
        headers=HEADERS,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": item["prompt"]}],
            "stream": False,
        },
        timeout=180,
    )
    return {
        "id": item["id"],
        "status": r.status_code,
        "seconds": round(time.monotonic() - t0, 2),
        "text": r.json()["choices"][0]["message"]["content"].strip(),
    }


async def main():
    items = [
        {"id": "security", "prompt": "Reply exactly: security-pass"},
        {"id": "quality", "prompt": "Reply exactly: quality-pass"},
    ]
    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(review(client, item)) for item in items]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            print(json.dumps({"completed": result["id"], "seconds": result["seconds"]}))
            results.append(result)

    by_id = {r["id"]: r["text"].lower() for r in results}
    ok = "security-pass" in by_id.get("security", "") and "quality-pass" in by_id.get("quality", "")
    print(json.dumps({"rung": 2, "as_completed": True, "count": len(results), "ok": ok}))
    raise SystemExit(0 if ok else 1)


asyncio.run(main())
