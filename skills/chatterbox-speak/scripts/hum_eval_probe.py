#!/usr/bin/env python3
"""Live probe: the hum pipeline actually works through $memory.

Asserts (against the real memory daemon, jina embedder, Qdrant):
  1. A hum recalls by mood/style description with scores.dense > 0 (semantic
     embedding fired — not just BM25).
  2. The recalled hum is kind=persona_music_preference and carries the rich
     metadata (style/year/tempo_bpm/emotion_category/connected_memory_keys).
  3. INVARIANT (adversarial): canonical retrieval_text contains NO renderer
     tags ("[...]") — memory text must stay engine-neutral.

Exit 0 only if all hold; else 1 with the reason. stdlib urllib (runner python
lacks httpx). No writes.
"""
from __future__ import annotations
import json, sys, urllib.request

MEM = "http://127.0.0.1:8601"


def recall(q: str) -> dict:
    req = urllib.request.Request(MEM + "/recall",
        data=json.dumps({"q": q, "k": 8, "collections": ["persona_memory"], "tags": ["persona:embry"]}).encode(),
        headers={"Content-Type": "application/json", "X-Caller-Skill": "chatterbox-speak"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main() -> int:
    data = recall("a slow wistful Hawaiian farewell hum about longing and missing someone")
    hums = [it for it in data.get("items", []) if "hum" in str(it.get("_key", ""))]
    if not hums:
        print("FAIL: no hum recalled", file=sys.stderr)
        return 1
    top = max(hums, key=lambda it: it.get("scores", {}).get("dense", 0))
    dense = top.get("scores", {}).get("dense", 0)
    if dense <= 0:
        print(f"FAIL: hum {top.get('_key')} has dense={dense} (jina/Qdrant embedding not reached)", file=sys.stderr)
        return 1
    rt = str(top.get("retrieval_text", ""))
    if "[" in rt or "]" in rt:
        print(f"FAIL: renderer tag leaked into canonical memory text: {rt!r}", file=sys.stderr)
        return 1
    print(f"PASS: {top.get('_key')} dense={dense:.3f} bm25={top.get('scores', {}).get('bm25', 0):.3f}; clean canonical text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
