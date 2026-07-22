#!/usr/bin/env python3
"""P0.1 relevance/accuracy receipt (GOAL_V2_AMENDMENT_1).

Operator-corrected criterion: "the agent's dream is accurate given
experience." This tool VERIFIES, by live read-back, that the canonical dream
node is provenance-bound to the agent's real memories and to the observed
media, then writes the receipt. Every field is a fresh read-back result —
nothing is asserted from prior receipts without re-checking the live store.

Checks (all fail-closed):
1. dream node ACTIVE in persona_memory (default /list visibility);
2. source_memory_ids non-empty AND every id resolves to a stored root memory;
3. synthetic marking: synthetic_origin true, literal_historical_event false;
4. source_video_sha256 matches the expected provider-return hash AND the
   on-disk video file recomputes to that hash;
5. acceptance rung receipt reads PASS_ACCEPTANCE_RUNG.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RR = ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
GMO = "http://127.0.0.1:8601"
DREAM_KEY = "dream_dream_successor_943b01ecd9a3"
VIDEO = RR / ("phase_11_submit_return/provider_return/"
              "97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4/"
              "provider_return.mp4")
EXPECTED_SHA = "59b9ff3155d6ba9d0b90d795bafe7b84cc4e10849db08299217b65d61e211fff"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(f"{GMO}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def main() -> int:
    failures = []

    docs = post("/list", {"collection": "persona_memory",
                          "filters": {"_key": DREAM_KEY}}).get("documents") or []
    node = docs[0] if docs else None
    dream_node_active = bool(node) and node.get("visibility_state") in ("active", None)
    if not dream_node_active:
        failures.append("dream node not active-visible")

    source_ids = (node or {}).get("source_memory_ids") or []
    resolved = []
    for sid in source_ids:
        got = post("/list", {"collection": "persona_memory",
                             "filters": {"_key": sid}}).get("documents") or []
        resolved.append({"source_id": sid, "stored": bool(got)})
    source_bound = bool(source_ids) and all(r["stored"] for r in resolved)
    if not source_bound:
        failures.append(f"source memory binding failed: {resolved}")

    synthetic_ok = bool(node) and node.get("synthetic_origin") is True \
        and node.get("literal_historical_event") is False
    if not synthetic_ok:
        failures.append("synthetic marking failed")

    node_sha = str((node or {}).get("source_video_sha256") or "")
    h = hashlib.sha256()
    with VIDEO.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    file_sha = h.hexdigest()
    media_ok = node_sha.endswith(EXPECTED_SHA) and file_sha == EXPECTED_SHA
    if not media_ok:
        failures.append(f"media hash binding failed: node={node_sha[-16:]} file={file_sha[-16:]}")

    rung = json.loads((RR / "acceptance_rung_receipt.v6.json").read_text())
    rung_ok = rung.get("status") == "PASS_ACCEPTANCE_RUNG"
    if not rung_ok:
        failures.append(f"acceptance rung: {rung.get('status')}")

    if failures:
        print("BLOCKED_RELEVANCE_ACCURACY:", failures, file=sys.stderr)
        return 1

    receipt = {
        "schema": "persona_dream.relevance_accuracy_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "author": "agent:relevance-verifier",
        "delegation": "GOAL_V2_AMENDMENT_1",
        "criterion": "the agent's dream is accurate given experience",
        "dream_node_key": DREAM_KEY,
        "dream_node_active": True,
        "source_memory_ids_bound": True,
        "source_memory_resolution": resolved,
        "synthetic_marking_verified": True,
        "video_sha256": f"sha256:{file_sha}",
        "video_file_recomputed": True,
        "acceptance_rung_status": "PASS_ACCEPTANCE_RUNG",
        "does_not_prove": [
            "subjective aesthetic quality (out of scope per GOAL_V2_AMENDMENT_1)",
        ],
    }
    out = RR / "relevance_accuracy_receipt.v1.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"written": str(out), "sources": len(resolved)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
