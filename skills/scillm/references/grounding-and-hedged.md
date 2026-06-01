# Grounding And Hedged

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

## Hedged Calls (Race Two Models)

Client-side — fire two models, take the first response:

```python
async def hedged_call(client, prompt, primary="text", backup="text-gemini"):
    async def call(model):
        resp = await client.post(
            "http://localhost:4001/v1/chat/completions",
            headers={"Authorization": "Bearer sk-dev-proxy-123"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=30.0,
        )
        return resp.json()["choices"][0]["message"]["content"]

    done, pending = await asyncio.wait(
        [asyncio.create_task(call(primary)), asyncio.create_task(call(backup))],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
    return await next(iter(done))
```

---

