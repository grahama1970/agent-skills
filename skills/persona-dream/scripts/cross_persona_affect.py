#!/usr/bin/env python3
"""Connect the emotional states of ANY personas by multi-hop graph traversal.

The crucial point (operator 2026-07-24): all personas share ONE affective/ToM
graph. Their named entities never overlap across fictional worlds (Embry Lawson
in SPARTA vs Horus Lupercal in 40k — both fictional characters), but their INNER
STATES do: both hold `tom:unresolved_thread`, `emotion:fear`, `tom:boundary`.
Multi-hop over these shared affect nodes is how one persona's emotional state
connects to another's — Embry's shame about Kai resonating with Horus's conflict
about the Emperor, through theory of mind rather than shared facts.

This is a READ-ONLY traversal capability (no writes, no dream seeding — the
dream selector keeps counterpart isolation WITHIN a persona). It surfaces the
cross-persona affect bridges and emits concrete linking paths with a receipt.

  python cross_persona_affect.py --personas embry horus_lupercal --out receipt.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


profiles = _load("persona_profiles")


def _fetch(persona_id: str) -> list[dict]:
    docs, off = [], 0
    while True:
        req = urllib.request.Request(
            f"{GMO}/list", headers={"Content-Type": "application/json"},
            data=json.dumps({"collection": "persona_memory",
                             "filters": {"persona_id": persona_id},
                             "limit": 100, "offset": off}).encode())
        page = json.loads(urllib.request.urlopen(req, timeout=30).read())
        docs += page.get("documents", [])
        off += 100
        if off >= page.get("total", 0):
            break
    return docs


def _text(d: dict) -> str:
    return str(d.get("retrieval_text") or d.get("event_summary") or "")[:200]


def build(personas: list[str], max_paths: int = 25) -> dict:
    # affect node -> {persona_id -> [(key, text)]}, using each persona's own
    # (schema-correct) profile to extract affect keys.
    index: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    per_counts = {}
    for pid in personas:
        docs = _fetch(pid)
        profile = profiles.build_profile(pid, docs)
        per_counts[pid] = len(docs)
        for d in docs:
            for ak in profile.affect_keys(d):
                index[ak][pid].append((d["_key"], _text(d)))

    # shared = affect nodes present in >= 2 personas (the cross-persona bridges)
    shared = {ak: pmap for ak, pmap in index.items() if len(pmap) >= 2}
    paths = []
    for ak in sorted(shared, key=lambda k: (-len(shared[k]), k)):
        pmap = shared[ak]
        present = sorted(pmap)
        # one deterministic linking path per adjacent persona pair on this node
        for a, b in zip(present, present[1:]):
            ka, ta = sorted(pmap[a])[0]
            kb, tb = sorted(pmap[b])[0]
            paths.append({
                "affect_node": ak,
                "hop": [{"persona_id": a, "memory_key": ka, "text": ta},
                        {"persona_id": b, "memory_key": kb, "text": tb}],
            })
        if len(paths) >= max_paths:
            break

    return {
        "schema": "persona_dream.cross_persona_affect.v1",
        "capability": "connect emotional states of personas via shared "
                      "affect/ToM nodes (multi-hop, read-only)",
        "personas": personas,
        "persona_memory_counts": per_counts,
        "shared_affect_nodes": sorted(shared),
        "shared_affect_node_count": len(shared),
        "sample_paths": paths[:max_paths],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--personas", nargs="+", default=["embry", "horus_lupercal"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-paths", type=int, default=25)
    args = ap.parse_args()
    receipt = build(args.personas, args.max_paths)
    if args.out:
        Path(args.out).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in
                      ("personas", "persona_memory_counts",
                       "shared_affect_node_count", "shared_affect_nodes")},
                     indent=2))
    print("--- sample cross-persona affect paths ---")
    for p in receipt["sample_paths"][:6]:
        h = p["hop"]
        print(f"[{p['affect_node']}]")
        print(f"  {h[0]['persona_id']}: {h[0]['text'][:120]}")
        print(f"  {h[1]['persona_id']}: {h[1]['text'][:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
