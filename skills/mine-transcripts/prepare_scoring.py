"""Build bounded scoring packets for the judgment-feature fanout.

Each packet is a compact per-trace digest (turn index, role, tool, text head)
plus the deterministic pre-pass results. Children never open the raw session
file; they read one small packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from reasoning_trace import WRITE_TOOLS, READ_TOOLS, _digest, _extract_text, parse_pi_session

MAX_TEXT_HEAD = 220
MAX_TURNS = 400


def build_digest(session_path: str) -> list[dict]:
    turns = []
    with open(session_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "message":
                continue
            msg = d.get("message", {})
            role = msg.get("role")
            content = msg.get("content", [])
            if role == "assistant":
                for c in content:
                    if c.get("type") == "toolCall":
                        turns.append({"i": len(turns), "role": "tool", "name": c.get("name", "?"), "head": json.dumps(c.get("arguments", {}), default=str)[:MAX_TEXT_HEAD]})
                    elif c.get("type") == "text" and c.get("text", "").strip():
                        turns.append({"i": len(turns), "role": "assistant", "head": c["text"].strip()[:MAX_TEXT_HEAD]})
            elif role == "user":
                t = _extract_text(content)
                if t:
                    turns.append({"i": len(turns), "role": "user", "head": t[:MAX_TEXT_HEAD]})
            elif role == "toolResult":
                t = _extract_text(content)
                if t:
                    turns.append({"i": len(turns), "role": "result", "head": ("ERROR: " if any(m in t[:200].lower() for m in ("traceback", "error", "exit code 1")) else "") + t[:MAX_TEXT_HEAD]})
            if len(turns) >= MAX_TURNS:
                break
    return turns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/rt_corpus_200.jsonl")
    ap.add_argument("--out-dir", default="data/rt_packets")
    ap.add_argument("--max-packets", type=int, default=60)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.corpus, encoding="utf-8")]
    # priority: outcome candidates first (supervision signal), then the rest
    with_outcome = [r for r in rows if r.get("outcome_events")]
    rest = [r for r in rows if not r.get("outcome_events")]
    selected = (with_outcome + rest)[: args.max_packets]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for r in selected:
        digest = build_digest(r["session_path"])
        packet = {
            "schema": "reasoning.scoring_packet.v1",
            "trace_key": r["_key"],
            "repo": r.get("repo"),
            "task_kind": r.get("task_kind"),
            "deterministic_features": r.get("deterministic_features"),
            "has_outcome_candidates": bool(r.get("outcome_events")),
            "turns": digest,
        }
        pid = hashlib.sha256(r["_key"].encode()).hexdigest()[:12]
        path = out_dir / f"{pid}.json"
        path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
        manifest.append({"packet": str(path), "trace_key": r["_key"], "turns": len(digest), "has_outcome": bool(r.get("outcome_events"))})
    print(json.dumps({"packets": len(manifest), "with_outcome": sum(1 for m in manifest if m["has_outcome"]), "out_dir": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
