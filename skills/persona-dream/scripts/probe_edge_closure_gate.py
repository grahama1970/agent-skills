#!/usr/bin/env python3
"""GOAL_V3.2 negative probe: the LIVE persist layer must refuse a write set
containing a dangling citation edge, before any staging write.

Drives the real persist_canonical against the live store with a minimal dream
document plus one extra edge whose _to endpoint does not exist anywhere.
Expected: status BLOCKED_EDGE_ENDPOINT_UNRESOLVED, no commit manifest, and a
store read-back proving the probe dream key was never written. Writes
reports/goal_v3/edge_closure_gate_probe_receipt.v1.json.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
PROBE_DREAM_ID = "goal_v3_edge_closure_probe"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def main() -> int:
    p15 = _load("phase15_dream_persistence")

    interp = {"status": "PASS_PROBE", "accepted_interpretations": [],
              "source_memory_bindings": [], "observation_packet_sha256": "sha256:probe"}
    tom = {"status": "PASS_PROBE", "accepted_tom_candidates": []}
    packet = {"status": "PROBE", "evidence_origin": "probe",
              "source_video_sha256": "sha256:probe"}
    dream_doc = {"_key": f"dream_{PROBE_DREAM_ID}", "kind": "synthetic_dream_memory",
                 "persona_id": "embry", "dream_id": PROBE_DREAM_ID,
                 "retrieval_text": "edge-closure gate probe (never persisted)"}
    def edge(key, frm, to, drop=None):
        d = {"_key": key, "_from": frm, "_to": to,
             "relationship_type": "observed_in_scene"}
        if drop:
            d.pop(drop)
        return {"collection": "persona_memory_edges", "kind": "edge", "document": d}

    CASES = {
        "dangling_vertex": [edge(f"{PROBE_DREAM_ID}__e1",
                                 f"persona_memory/dream_{PROBE_DREAM_ID}",
                                 "persona_dream_watch_evidence/does_not_exist_anywhere_v3_probe")],
        "missing_endpoint": [edge(f"{PROBE_DREAM_ID}__e2",
                                  f"persona_memory/dream_{PROBE_DREAM_ID}", None,
                                  drop="_to")],
        "malformed_ref": [edge(f"{PROBE_DREAM_ID}__e3",
                               f"persona_memory/dream_{PROBE_DREAM_ID}",
                               "not-a-collection-key-ref")],
        "both_endpoints_absent": [
            {"collection": "persona_memory_edges", "kind": "edge",
             "document": {"_key": f"{PROBE_DREAM_ID}__e6",
                          "relationship_type": "observed_in_scene"}}],
        "both_endpoints_null": [edge(f"{PROBE_DREAM_ID}__e7", None, None)],
        "edge_targeting_endpointless_edge": [
            {"collection": "persona_memory_edges", "kind": "edge",
             "document": {"_key": f"{PROBE_DREAM_ID}__e8",
                          "relationship_type": "observed_in_scene"}},
            edge(f"{PROBE_DREAM_ID}__e9",
                 f"persona_memory/dream_{PROBE_DREAM_ID}",
                 f"persona_memory_edges/{PROBE_DREAM_ID}__e8")],
        "edge_to_edge": [edge(f"{PROBE_DREAM_ID}__e4",
                              f"persona_memory/dream_{PROBE_DREAM_ID}",
                              f"persona_memory_edges/{PROBE_DREAM_ID}__e5"),
                         edge(f"{PROBE_DREAM_ID}__e5",
                              f"persona_memory/dream_{PROBE_DREAM_ID}",
                              f"persona_memory/dream_{PROBE_DREAM_ID}")],
    }
    case_results = {}
    for name, dangling in CASES.items():
        proof = p15.persist_canonical(
            dream_doc, interp, tom, [], BASE,
            dream_id=PROBE_DREAM_ID, return_id="probe", packet=packet,
            phase13_sha="sha256:probe13", phase14_sha="sha256:probe14",
            include_dream_node=True, extra_edges=dangling,
            justification=f"GOAL_V3.2 negative closure probe: {name}",
        )
        case_results[name] = {
            "blocked_status": proof.get("status"),
            "unresolved": (proof.get("unresolved_endpoints") or [])[:4],
            "blocked": proof.get("status") == "BLOCKED_EDGE_ENDPOINT_UNRESOLVED",
        }
    blocked = all(c["blocked"] for c in case_results.values())

    written = []
    for vs in ("active", "pending", None):
        filt = {"_key": f"dream_{PROBE_DREAM_ID}"}
        if vs:
            filt["visibility_state"] = vs
        written += post("/list", {"collection": "persona_memory",
                                  "filters": filt}).get("documents") or []
    store_untouched = not written

    receipt = {
        "schema": "persona_dream.edge_closure_gate_probe_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "live": True,
        "cases": case_results,
        "probe_dream_key_absent_from_store": store_untouched,
        "passed": blocked and store_untouched,
    }
    out = ROOT / "reports/goal_v3/edge_closure_gate_probe_receipt.v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
