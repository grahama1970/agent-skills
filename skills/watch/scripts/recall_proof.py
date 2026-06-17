"""E2E sanity: verify 3 QRA pairs stored in watch_content and recallable."""
import json, sys, httpx

BASE = "http://127.0.0.1:8601"

# 1. List watch_content documents
resp = httpx.post(f"{BASE}/list", json={"collection": "watch_content", "limit": 10}, timeout=10.0)
data = resp.json()
docs = data.get("documents", data.get("items", []))
assert len(docs) >= 3, f"expected 3+ docs, got {len(docs)}"
print(f"  {len(docs)} watch_content docs")

# 2. By-key recall for each
for i, doc in enumerate(docs[:3], 1):
    k = doc["_key"]
    resp = httpx.post(f"{BASE}/recall/by-keys",
        json={"collection": "watch_content", "keys": [k]}, timeout=10.0)
    rd = resp.json().get("documents", [])
    assert rd, f"by-key missing: {k}"
    q = rd[0].get("question", "")
    a = rd[0].get("answer", "")
    assert len(a) > 20, f"answer too short for {k}: {len(a)} chars"
    print(f"  Q{i}: {q[:60]}...")
    print(f"  A{i}: {a[:60]}...")

# 3. General recall finds watch_content
resp = httpx.post(f"{BASE}/recall", json={"q": "Claude Skill Watches Videos", "k": 10}, timeout=30.0)
items = resp.json().get("items", [])
wc = [i for i in items if i.get("_source") == "watch_content"]
assert len(wc) >= 2, f"expected 2+ watch_content in recall, got {len(wc)}"
print(f"  general recall: {len(wc)} watch_content results")

print("  MEMORY RECALL PROOF: PASS")
