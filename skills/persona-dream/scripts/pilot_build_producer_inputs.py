#!/usr/bin/env python3
"""Build the producer inputs for one pilot run (protocol v3).

Reads the appended selection addendum (fail-closed if absent), fetches the
selected root-memory records live from the GMO, and writes for the requested
set (r1|r2):

- residue_links.json — schema persona_dream.residue_links.v1, one item per
  selected root memory (id, persona, collection, full text). Identical shape
  to the residue packet phase 13 already consumes.
- reflection_packet.json (C arm only) — an observation-packet-shaped input
  whose only observation surface is transcript_facts, one fact per root
  memory (fact_id reflection_fact_<source_id>). This routes the C arm through
  the SAME phase-13 citation gates (claim must cite an observation id AND a
  source-memory id) with zero Watch/render evidence — the arm difference is
  the evidence surface, not the gate logic.
- root_set_reading.md — the human-readable root set shown to the producer
  (subject to the producer-blinding receipt before use).

Every output embeds the selection receipt's members_selected_sha256 so a
mismatch between inputs and the frozen addendum is machine-detectable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"
ADDENDUM_JSON = ROOT / "contracts/pilot_r1_r2_selection_addendum.v1.json"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{GMO}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", required=True, choices=["r1", "r2"])
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if not ADDENDUM_JSON.exists():
        print("BLOCKED_PILOT_INPUTS_ADDENDUM_MISSING", file=sys.stderr)
        return 2
    addendum = json.loads(ADDENDUM_JSON.read_text())
    selected = addendum[args.set]["members_selected"]
    expected_sha = addendum[args.set]["members_selected_sha256"]
    if sha256_text(json.dumps(selected)) != expected_sha:
        print("BLOCKED_PILOT_INPUTS_ADDENDUM_INTERNAL_MISMATCH", file=sys.stderr)
        return 2

    items = []
    for key in selected:
        docs = post("/list", {"collection": "persona_memory",
                              "filters": {"_key": key}}).get("documents") or []
        if len(docs) != 1:
            print(f"BLOCKED_PILOT_INPUTS_ROOT_MISSING: {key}", file=sys.stderr)
            return 2
        doc = docs[0]
        text = str(doc.get("retrieval_text") or doc.get("claim_text") or "").strip()
        if not text:
            print(f"BLOCKED_PILOT_INPUTS_ROOT_TEXT_EMPTY: {key}", file=sys.stderr)
            return 2
        items.append({
            "collection": "persona_memory",
            "persona_id": doc.get("persona_id"),
            "source_id": key,
            "source_path": f"gmo:persona_memory/{key}",
            "text": text,
        })

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    binding = {
        "set": args.set,
        "set_id": addendum[args.set]["set_id"],
        "members_selected_sha256": expected_sha,
        "addendum_sha256": sha256_text(ADDENDUM_JSON.read_text()),
    }

    residue = {
        "schema": "persona_dream.residue_links.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "idea_id": f"pilot_{args.set}",
        "items": items,
        "pilot_binding": binding,
    }
    (out / "residue_links.json").write_text(json.dumps(residue, indent=2) + "\n")

    reflection = {
        "schema": "persona_dream.pilot_reflection_packet.v1",
        "packet_status": "ACCEPTED",
        "evidence_class": "synthetic_reflection",
        "frame_evidence": [],
        "step_hooks": {},
        "coverage_gaps": [],
        "transcript_facts": [
            {"fact_id": f"reflection_fact_{it['source_id']}",
             "time_range": None,
             "statement": it["text"][:600]}
            for it in items
        ],
        "pilot_binding": binding,
    }
    (out / "reflection_packet.json").write_text(json.dumps(reflection, indent=2) + "\n")

    reading = ["# Assigned root memory set", ""]
    for it in items:
        reading += [f"## {it['source_id']}", "", it["text"], ""]
    (out / "root_set_reading.md").write_text("\n".join(reading))

    print(json.dumps({"set": args.set, "set_id": binding["set_id"],
                      "roots": [it["source_id"] for it in items],
                      "out_dir": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
