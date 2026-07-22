#!/usr/bin/env python3
"""GOAL_V3 boundary checker v2 — recomputes from children (round-1 review).

Trusts NO top-level receipt field it can recompute:
  v3_1: voice-weights receipt for the newest cycle's dream — profile sha and
        WAV sha RECOMPUTED from the files; duration re-probed via ffprobe.
  v3_2: 4-case closure-negative probe receipt (all cases blocked, store
        untouched) AND the newest cycle's grounding RECOMPUTED live via the
        strict claim resolver (pilot_metrics.m2_grounding), == 1.0.
  v3_3: newest cycle — dream node reread ACTIVE from the store; persisted ToM
        targets reread and matched to the receipt's counterpart; instruments
        file sha recomputed and compared to the receipt binding; anchors
        recomputed against the cycle snapshot.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
GV3 = SKILL / "reports/goal_v3"
GMO = "http://127.0.0.1:8601"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def post(path, payload):
    req = urllib.request.Request(f"{GMO}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def stored(collection, key):
    for vs in ("active", "pending", None):
        filt = {"_key": key}
        if vs:
            filt["visibility_state"] = vs
        docs = post("/list", {"collection": collection, "filters": filt}).get("documents") or []
        if docs:
            return docs[0]
    return None


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    results, notes = {}, []
    cycles = sorted((GV3 / "cycles").glob("*/autonomous_cycle_receipt.v1.json"))
    cycle_path = cycles[-1] if cycles else None
    cycle = json.loads(cycle_path.read_text()) if cycle_path else None

    # ---- v3_3 recomputed ----
    v3_3 = False
    counterpart_ok = node_active = instruments_ok = anchors_ok = False
    if cycle:
        cyc_dir = cycle_path.parent
        node = stored("persona_memory", cycle["dream_node_key"])
        node_active = bool(node) and node.get("visibility_state") in ("active", None)
        # counterpart: reread every persisted ToM target
        targets = set()
        if node:
            did = node.get("dream_id")
            for cid in node.get("accepted_tom_candidate_ids") or []:
                doc = (stored("tom_candidates", f"dream:embry:{did}:tom:{cid}")
                       or stored("tom_candidates", cid))
                if doc:
                    targets.add(str(doc.get("target")))
        counterpart_ok = bool(targets) and targets <= {cycle.get("counterpart_id"), "unknown_person"}
        inst = cyc_dir / "instruments.v1.json"
        instruments_ok = inst.exists() and hashlib.sha256(
            inst.read_text().encode()).hexdigest() == cycle.get("instruments_sha256")
        # anchors recompute via the frozen m4 logic
        pm = _load("pilot_metrics")
        p15 = _load("phase15_dream_persistence")
        m4 = pm.m4_identity(p15, cycle["commit_manifest_key"], cyc_dir / "anchor_snapshot.json")
        anchors_ok = bool(m4.get("passed"))
        v3_3 = (cycle.get("status") == "PASS_AUTONOMOUS_CYCLE" and node_active
                and counterpart_ok and instruments_ok and anchors_ok)
        notes.append({"counterpart_targets_reread": sorted(targets),
                      "node_active": node_active, "instruments_sha_match": instruments_ok,
                      "anchors_recomputed_pass": anchors_ok})
    results["v3_3_autonomous_cycle"] = {
        "state": "PASS" if v3_3 else "MISSING",
        "path": str(cycle_path.relative_to(SKILL)) if cycle_path else "none"}

    # ---- v3_2 recomputed ----
    v3_2 = False
    probe = None
    ppath = GV3 / "edge_closure_gate_probe_receipt.v1.json"
    if ppath.exists():
        probe = json.loads(ppath.read_text())
    grounding = None
    if cycle:
        pm = _load("pilot_metrics")
        p15 = _load("phase15_dream_persistence")
        m2 = pm.m2_grounding(p15, cycle["commit_manifest_key"], cycle_path.parent,
                             "embry", stored("persona_memory", cycle["dream_node_key"]).get("dream_id"))
        grounding = m2.get("fraction_resolved")
    probe_ok = bool(probe and probe.get("passed")
                    and probe.get("probe_dream_key_absent_from_store")
                    and len(probe.get("cases") or {}) >= 4
                    and all(c.get("blocked") for c in probe["cases"].values()))
    v3_2 = probe_ok and grounding == 1.0
    notes.append({"closure_negative_cases": len((probe or {}).get("cases") or {}),
                  "grounding_recomputed_live": grounding})
    results["v3_2_citation_closure"] = {
        "state": "PASS" if v3_2 else "MISSING",
        "path": "reports/goal_v3/edge_closure_gate_probe_receipt.v1.json"}

    # ---- v3_1 recomputed (newest cycle's own voice render) ----
    v3_1 = False
    if cycle and cycle.get("voice_weights_receipt"):
        vw_path = Path(cycle["voice_weights_receipt"])
        if not vw_path.is_absolute():
            vw_path = SKILL / vw_path
        if vw_path.exists():
            vw = json.loads(vw_path.read_text())
            prof = Path(vw["profile_path"])
            render = vw.get("render") or {}
            wav = Path(render.get("wav", "/nonexistent"))
            profile_ok = prof.exists() and hashlib.sha256(
                prof.read_text().encode()).hexdigest() == vw.get("profile_sha256")
            wav_ok = wav.exists() and sha_file(wav) == render.get("wav_sha256")
            dur = 0.0
            if wav.exists():
                pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                     "format=duration", "-of", "csv=p=0", str(wav)],
                                    capture_output=True, text=True, timeout=30)
                dur = float(pr.stdout.strip() or 0)
            temp_sent = "temperature" in json.loads(prof.read_text()).get("synthesis_params", {}) if prof.exists() else False
            v3_1 = profile_ok and wav_ok and dur > 0.2 and temp_sent
            notes.append({"profile_sha_recomputed": profile_ok,
                          "wav_sha_recomputed": wav_ok, "wav_duration_reprobed": dur})
    results["v3_1_dream_voice_weights"] = {
        "state": "PASS" if v3_1 else "MISSING",
        "path": str(cycle.get("voice_weights_receipt")) if cycle else "none"}

    passed = v3_1 and v3_2 and v3_3
    print(json.dumps({
        "schema": "persona_dream.goal_v3_boundary_check.v2",
        "status": "PASS_GOAL_V3_BOUNDARY" if passed else "BLOCKED_GOAL_V3_BOUNDARY",
        "recomputed_from_children": True,
        "criteria": results,
        "recompute_notes": notes,
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
