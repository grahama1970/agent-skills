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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", default=True,
                    help="JSON output (always on; flag exists so the immutable "
                         "GOAL_V3.md proof command runs verbatim)")
    ap.add_argument("--cycle-id", default=None,
                    help="explicit cycle binding; default = newest by cycle_id timestamp name")
    args = ap.parse_args()
    results, notes = {}, []
    cycles = sorted((GV3 / "cycles").glob("*/autonomous_cycle_receipt.v1.json"),
                    key=lambda q: q.parent.name)
    if args.cycle_id:
        cycles = [c for c in cycles if c.parent.name == args.cycle_id]
    cycle_path = cycles[-1] if cycles else None
    cycle = json.loads(cycle_path.read_text()) if cycle_path else None

    # ---- v3_3 recomputed ----
    v3_3 = False
    counterpart_ok = node_active = instruments_ok = anchors_ok = False
    if cycle:
        cyc_dir = cycle_path.parent
        node = stored("persona_memory", cycle["dream_node_key"])
        # strict for new cycles: must be explicitly active
        node_active = bool(node) and node.get("visibility_state") == "active"
        # counterpart derived from the SELECTION receipt, never the top-level field
        sel = json.loads((cyc_dir / "selection_receipt.v1.json").read_text())
        derived_cp = sel["chosen"]["cluster_id"].split(":person:")[1].split("_")[0]
        person_tag = sel["chosen"]["cluster_id"].split(":", 1)[1]
        sel_ids = sorted(sel["chosen"]["selected"])
        selection_bound = bool(node) and sel_ids == sorted(node.get("source_memory_ids") or [])
        roots_tagged = all(
            (lambda d: bool(d) and person_tag in (d.get("tags") or []))(stored("persona_memory", rid))
            for rid in sel_ids)
        # every expected ToM candidate must resolve, be commit-owned, and match
        targets = set()
        toms_resolved = 0
        dream_commit = (node or {}).get("commit_id")
        manifest_entries = None
        if dream_commit:
            m = stored("persona_dream_commit_manifests", dream_commit)
            if m and m.get("active") and m.get("record_index"):
                manifest_entries = {(e["collection"], e["key"]) for e in m["record_index"]}
        expected = (node or {}).get("accepted_tom_candidate_ids") or []
        if node:
            did = node.get("dream_id")
            for cid in expected:
                doc = (stored("tom_candidates", f"dream:embry:{did}:tom:{cid}")
                       or stored("tom_candidates", cid))
                if doc:
                    toms_resolved += 1
                    targets.add(str(doc.get("target")))
                    if manifest_entries is not None and                             ("tom_candidates", doc["_key"]) not in manifest_entries:
                        targets.add(f"NOT_MANIFEST_OWNED:{doc['_key']}")
        # payload-hash recompute for ToM candidates vs manifest payload_sha256
        tom_hashes_ok = False
        try:
            proof = json.loads((cyc_dir / "persist_proof.json").read_text())
            snap = {s["document"]["_key"]: s["document"]
                    for s in proof["final_write_set_snapshot"]}
            mdoc = stored("persona_dream_commit_manifests", dream_commit) or {}
            mhash = {e["key"]: e.get("payload_sha256") for e in mdoc.get("record_index", [])}
            p15h = _load("phase15_dream_persistence")
            checked = 0
            ok_all = True
            for key, authored in snap.items():
                if key not in mhash or "tom" not in str(key):
                    continue
                doc = stored("tom_candidates", key)
                if not doc:
                    ok_all = False
                    continue
                recon = {k: doc.get(k) for k in authored if not k.startswith("_") or k == "_key"}
                if recon.get("visibility_state") == "active" and authored.get("visibility_state") == "pending":
                    recon["visibility_state"] = "pending"
                ok_all = ok_all and p15h.authored_sha(recon) == mhash[key]
                checked += 1
            tom_hashes_ok = ok_all and checked > 0
        except Exception:
            tom_hashes_ok = False
        counterpart_ok = (bool(targets) and toms_resolved == len(expected)
                          and targets <= {derived_cp, "unknown_person"}
                          and manifest_entries is not None
                          and selection_bound and roots_tagged and tom_hashes_ok)
        # frame sha recompute from disk
        frames = cycle.get("frames") or []
        frames_ok = (len(frames) == 4
                     and [f.get("panel_id") for f in frames] == ["sb_001", "sb_002", "sb_003", "sb_004"]
                     and all(str(f["frame"]).startswith(str(cyc_dir)) for f in frames)
                     and all(Path(f["frame"]).exists()
                             and hashlib.sha256(Path(f["frame"]).read_bytes()).hexdigest() == f["frame_sha256"]
                             for f in frames))
        inst = cyc_dir / "instruments.v1.json"
        instruments_ok = inst.exists() and hashlib.sha256(
            inst.read_text().encode()).hexdigest() == cycle.get("instruments_sha256")
        # anchors recompute via the frozen m4 logic
        pm = _load("pilot_metrics")
        p15 = _load("phase15_dream_persistence")
        m4 = pm.m4_identity(p15, cycle["commit_manifest_key"], cyc_dir / "anchor_snapshot.json")
        anchors_ok = bool(m4.get("passed"))
        # live distinction + negative-control recompute
        adapter = _load("tau_text_reasoning_adapter")
        pm2 = _load("pilot_metrics")
        m3 = pm2.m3_distinction(adapter, cycle["dream_node_key"])
        inst_doc = json.loads(inst.read_text()) if inst.exists() else {}
        n_items = post("/recall", {"q": inst_doc.get("negative_control", ""),
                                   "k": 10, "collections": ["persona_memory"],
                                   "tags": []}).get("items") or []
        n1_ok = cycle["dream_node_key"] not in [it.get("_key") for it in n_items[:10]]
        # voice receipt path containment (no out-of-cycle absolute paths)
        vw_rel_ok = str(cycle.get("voice_weights_receipt", "")).startswith(str(cyc_dir))
        v3_3 = (cycle.get("status") == "PASS_AUTONOMOUS_CYCLE" and node_active
                and counterpart_ok and instruments_ok and anchors_ok
                and frames_ok and bool(m3.get("passed")) and n1_ok and vw_rel_ok)
        notes.append({"counterpart_derived_from_selection": derived_cp,
                      "selection_bound_to_node_sources": selection_bound,
                      "roots_carry_person_tag": roots_tagged,
                      "tom_payload_hashes_recomputed": tom_hashes_ok,
                      "counterpart_targets_reread": sorted(targets),
                      "toms_resolved": f"{toms_resolved}/{len(expected)}",
                      "manifest_owned": manifest_entries is not None,
                      "node_strictly_active": node_active,
                      "frames_sha_recomputed": frames_ok,
                      "distinction_recomputed": m3.get("passed"),
                      "negative_control_recomputed": n1_ok,
                      "voice_path_in_cycle": vw_rel_ok,
                      "instruments_sha_match": instruments_ok,
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
            engine_temp = ((vw.get("render") or {}).get("engine_meta") or {}).get("generation", {})
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
