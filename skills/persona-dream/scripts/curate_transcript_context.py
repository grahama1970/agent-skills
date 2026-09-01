#!/usr/bin/env python3
"""Curate mined human transcript examples for Persona Dream conversation grounding.

The mine-transcripts skill is the reader. This script is the Persona Dream
curation boundary: it rejects raw diffs/log blobs, keeps bounded human feedback
signals, probes Memory for stored mined examples, and writes one JSON artifact
that conversation prompts can consume without treating operator feedback as an
Embry life event.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
MINE = REPO_ROOT / "skills" / "mine-transcripts" / "run.sh"
MEMORY = REPO_ROOT / "skills" / "memory" / "run.sh"

KEY_TERMS = (
    "persona-dream", "dream", "journal", "conversation", "generic", "stressed",
    "tone", "voice", "memory", "receipts", "proof", "do not stop", "understand",
    "crucial", "feature", "chatterbox", "embry",
)


def _one_line(text: str, limit: int = 260) -> str:
    return " ".join(str(text or "").split())[:limit].rstrip()


def _is_raw_artifact(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith(("*** ", "--- ", "+++ ", "diff --git")):
        return True
    if "@@" in text and ("---" in text or "+++" in text):
        return True
    if len(text) > 1200:
        return True
    return False


def _score(row: dict[str, Any]) -> int:
    text = str(row.get("text") or "")
    low = text.lower()
    score = 0
    labels = {str(x) for x in row.get("labels") or []}
    if "Fragility" in labels:
        score += 4
    if "Loyalty" in labels or "Resilience" in labels:
        score += 1
    for term in KEY_TERMS:
        if term in low:
            score += 3
    if "?" in text:
        score += 1
    if len(text) < 50:
        score -= 1
    return score


def read_mined(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = str(row.get("text") or "").strip()
        if not text or _is_raw_artifact(text):
            continue
        scored = {"text": _one_line(text), "labels": row.get("labels") or [], "score": _score(row)}
        if scored["score"] > 0:
            rows.append(scored)
    rows.sort(key=lambda r: (-int(r["score"]), str(r["text"]).lower()))
    return rows[:limit]


def run_mine(output: Path, sample: int) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(MINE), "mine", "--all-agents", "--dedupe", "--sample", str(sample), "--output", str(output)],
        cwd=str(MINE.parent), capture_output=True, text=True, timeout=600, check=False,
    )
    return {
        "command": [str(MINE), "mine", "--all-agents", "--dedupe", "--sample", str(sample), "--output", str(output)],
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-1200:],
        "stderr_tail": proc.stderr[-1200:],
        "output": str(output),
    }


def memory_probe(query: str) -> dict[str, Any]:
    proc = subprocess.run(
        [str(MEMORY), "recall", "-q", query, "--scope", "training_examples", "--tags", "mined_transcript", "--brief", "--k", "5"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120, check=False,
    )
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = {}
    return {
        "command": [str(MEMORY), "recall", "-q", query, "--scope", "training_examples", "--tags", "mined_transcript", "--brief", "--k", "5"],
        "returncode": proc.returncode,
        "found": parsed.get("found"),
        "item_count": len(parsed.get("items") or []),
        "confidence": parsed.get("confidence"),
        "stdout_tail": proc.stdout[-1000:],
        "stderr_tail": proc.stderr[-500:],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.output).resolve()
    mined = Path(args.input).resolve() if args.input else out.with_suffix(".mined.jsonl")
    mine_receipt = None
    if args.run_mine or not mined.is_file():
        mine_receipt = run_mine(mined, args.sample)
    items = read_mined(mined, args.limit)
    probe = memory_probe(args.query)
    status = "PASS_TRANSCRIPT_CONTEXT_CURATED" if items else "BLOCKED_NO_TRANSCRIPT_CONTEXT"
    receipt = {
        "schema": "persona_dream.transcript_context.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "mocked": False,
        "live": True,
        "mined_transcripts": str(mined),
        "mine_receipt": mine_receipt,
        "memory_probe": probe,
        "items": items,
        "raw_boundary": "raw mined transcript examples are operator feedback/training context, not Embry episodic memory or dream fact",
        "failed_gates": [] if items else ["no_curated_transcript_items"],
        "claims": {
            "proves": ["Persona Dream curated mined transcript output into bounded conversation guidance"] if items else [],
            "does_not_prove": ["that mined examples were stored to Memory", "that the voice sounded acceptable to a human listener"],
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run-mine", action="store_true")
    ap.add_argument("--sample", type=int, default=120)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--query", default="persona-dream generic stressed conversation specific dream journal voice tone")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    receipt = run(args)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} items={len(receipt['items'])} memory_found={receipt['memory_probe'].get('found')}")
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
