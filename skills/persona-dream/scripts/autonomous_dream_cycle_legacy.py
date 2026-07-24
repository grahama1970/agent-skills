#!/usr/bin/env python3
"""GOAL_V3.3: one full autonomous dream cycle, unattended, receipted.

Pipeline (all live, agent-only):
  1. SELECT the next unused person-anchored residue cluster (biographical
     recency + GOAL_V3-seeded hash; skip clusters already consumed by an
     ACTIVE dream node's source_memory_ids; K=3 members by seeded hash).
  2. INSTRUMENTS AT SELECTION TIME (before any dream content exists):
     3 positive recall probes composed from the ROOT texts via the Tau text
     node, plus a negative control verified to share no content words with
     the roots. Frozen to disk with sha before step 3.
  3. DREAM: 4-panel storyboard composed by Tau grounded ONLY in the roots;
     frames via the standard gpt-image-2 lane with the Embry reference sheet
     named in-prompt; per-frame ArcFace subgate (0.421, <=5 attempts,
     fail -> cycle invalid); 2x2 contact sheet = media identity.
  4. OBSERVE: Tau VLM montage description (advisory), observation packet.
  5. INTERPRET: phases 13/14, unmodified gates.
  6. PERSIST: certified transaction WITH watch-evidence vertices
     (build_watch_evidence_vertices) under the V3.2 edge-closure gate;
     activate; read back ACTIVE.
  7. EVALUATE: strict claim-citation resolution MUST be 1.0 (the pilot read
     0.0); closed-enum distinction DENIED + correct class; anchors
     (dream-004 node + this cycle's roots) byte-unchanged; recall ranks for
     the selection-time probes recorded.
  8. VOICE: dream_voice_weights.py --render on the NEW dream node.
  9. autonomous_cycle_receipt.v1.json, status PASS_AUTONOMOUS_CYCLE.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"
PERSONA = "embry"
AGE_BAND_RECENCY = ["age23_current", "age19_23", "age15_19", "age10_15", "age04_10"]
SELF_TAGS = {"person:embry", "person:embry_lawson"}
EMBRY_SHEET = Path("/mnt/storage12tb/media/personas/embry/assets/contact_sheets/"
                   "embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png")
MAX_ATTEMPTS = 5
PANEL_COUNT = 4
STOPWORDS = set("the a an and or of to in on for with her his she he it its is was are be as at by from that this".split())


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def post(path: str, payload: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(f"{GMO}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fetch_embry_docs() -> list[dict]:
    docs, off = [], 0
    while True:
        page = post("/list", {"collection": "persona_memory",
                              "filters": {"persona_id": PERSONA},
                              "limit": 100, "offset": off})
        docs += page.get("documents", [])
        off += 100
        if off >= page.get("total", 0):
            break
    return docs


def counterpart_violations(claims: list, counterpart_id: str, id_field: str) -> list:
    """GOAL_V3 counterpart gate (probe-able): a claim's target must be the
    selected counterpart or the bounded unknown_person."""
    allowed = {counterpart_id, "unknown_person"}
    return [c.get(id_field) for c in claims if str(c.get("target")) not in allowed]


def select_cluster(out: Path) -> dict:
    seed = sha256_text((ROOT / "GOAL_V3.md").read_text())
    docs = fetch_embry_docs()
    roots = {d["_key"]: d for d in docs if re.match(r"embry_age\d", d["_key"])}
    # GOAL_V4.3 loop guard: never dream about dream-colored experience.
    # Any residue record carrying persona_dream affect provenance (written by
    # the composer's voice_delivery patch when conversation turns become
    # memories) is excluded from dream selection — severs the
    # dream->speech->memory->dream amplification path (roundtable r3).
    tainted = {k for k, d in roots.items()
               if (d.get("affect_source") == "persona_dream"
                   or (d.get("voice_delivery") or {}).get("affect_source") == "persona_dream"
                   or d.get("dream_provenance"))}
    roots = {k: v for k, v in roots.items() if k not in tainted}
    used: set[str] = set()
    for d in docs:
        if d.get("kind") in ("synthetic_dream_memory", "synthetic_reflection_memory") \
                and d.get("visibility_state") in ("active", None):
            used.update(d.get("source_memory_ids") or [])
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, doc in roots.items():
        m = re.match(r"embry_(age[0-9_a-z]+?)_b\d+_memory_\d+$", key)
        if not m:
            continue
        for tag in doc.get("tags") or []:
            if tag.startswith("person:") and tag not in SELF_TAGS:
                groups[(m.group(1), tag)].add(key)

    # GOAL_V3 Amendment 2 (operator 2026-07-23): "different variation of the
    # same dream is human and agentic"; humans hold one memory with BOTH
    # positive and negative valence and resolve the conflict by traversing the
    # graph to associated memories. Dreaming is therefore NOT one-shot per
    # cluster. Seed from a valence-CONFLICTED memory, traverse that
    # counterpart's own graph edges to gather associates (isolation preserved:
    # traversal stays WITHIN the seed counterpart; cross-counterpart traversal
    # needs the counterpart gate amended via tau and is NOT done here), and the
    # VARIATION is which valence dominates + which associative path is taken.
    # A used cluster is re-dreamable as a NEW variation; only an EXACT prior
    # variation (same members + same emphasis) is blocked.
    POS = {"trust", "longing", "pride", "relief"}
    NEG = {"grief", "guilt", "fear", "anger", "shame", "uncertainty"}

    def emo_set(d):
        return {e.strip() for e in (d.get("emotion") or "").split(",") if e.strip()}

    def conflict_score(d):
        e = emo_set(d)
        return ((len(e & POS) > 0) + (len(e & NEG) > 0), len(e))

    edges_by_src: dict[str, list[str]] = defaultdict(list)
    for key, doc in roots.items():
        for e in (doc.get("graph_edges_raw") or []):
            if isinstance(e, dict) and e.get("target_memory_id"):
                edges_by_src[key].append(e["target_memory_id"])

    def traverse(seed_key, members, k=3):
        order, seen, frontier = [seed_key], {seed_key}, [seed_key]
        while frontier and len(order) < k:
            nxt = []
            for s in frontier:
                for tgt in edges_by_src.get(s, []):
                    if tgt in members and tgt not in seen:
                        seen.add(tgt); order.append(tgt); nxt.append(tgt)
                        if len(order) >= k:
                            break
                if len(order) >= k:
                    break
            frontier = nxt
        for m in sorted(members):          # deterministic pad if traversal short
            if len(order) >= k:
                break
            if m not in seen:
                order.append(m); seen.add(m)
        return order[:k]

    ledger_path = ROOT / "reports/goal_v5/variation_ledger.json"
    ledger = (json.loads(ledger_path.read_text())
              if ledger_path.exists() else {"variation_keys": []})
    done_keys = set(ledger["variation_keys"])

    clusters = []
    for (band, tag), members in groups.items():
        if len(members) < 3:
            continue
        cluster_id = f"{band}:{tag}"
        clusters.append({"cluster_id": cluster_id, "age_band": band, "tag": tag,
                         "members": members,
                         "order_hash": sha256_text(seed + cluster_id),
                         "used_overlap": len(members & used)})
    # never-dreamed clusters first, then least-dreamed (variation mode)
    clusters.sort(key=lambda c: (c["used_overlap"] > 0,
                                 AGE_BAND_RECENCY.index(c["age_band"]),
                                 c["used_overlap"], c["order_hash"]))
    if not clusters:
        raise SystemExit("BLOCKED_CYCLE_NO_ELIGIBLE_CLUSTERS")

    chosen = None
    for cl in clusters:
        members = cl["members"]
        conflicted = sorted(members, key=lambda m: (conflict_score(roots[m]),
                                                    sha256_text(seed + m)),
                            reverse=True)
        for vi, seed_key in enumerate(conflicted):
            variation_index = cl["used_overlap"] + vi
            emphasis = "negative" if variation_index % 2 == 1 else "positive"
            selected = traverse(seed_key, members, k=3)
            vkey = sha256_text(cl["cluster_id"] + "|" + "|".join(sorted(selected))
                               + "|" + emphasis)
            if vkey in done_keys:
                continue
            chosen = {"cluster_id": cl["cluster_id"], "age_band": cl["age_band"],
                      "selected": selected, "seed_memory": seed_key,
                      "valence_emphasis": emphasis,
                      "variation_index": variation_index,
                      "variation_key": vkey,
                      "used_overlap": cl["used_overlap"],
                      "order_hash": cl["order_hash"]}
            break
        if chosen:
            break
    if chosen is None:
        raise SystemExit("BLOCKED_CYCLE_ALL_VARIATIONS_EXHAUSTED")

    ledger["variation_keys"].append(chosen["variation_key"])
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")

    chosen_docs = {k: roots[k] for k in chosen["selected"]}
    (out / "selection_receipt.v1.json").write_text(json.dumps({
        "schema": "persona_dream.cycle_selection_receipt.v2",
        "loop_guard_excluded_tainted_residue": len(tainted),
        "seed_source": "GOAL_V3.md sha256", "seed": seed,
        "selection_mode": "conflict_seeded_intra_counterpart_traversal",
        "clusters_considered": len(clusters),
        "cluster_was_previously_dreamed": chosen["used_overlap"] > 0,
        "chosen": {k: chosen[k] for k in ("cluster_id", "selected", "seed_memory",
                                          "valence_emphasis", "variation_index",
                                          "variation_key")},
    }, indent=2, sort_keys=True) + "\n")
    return {"cluster": chosen, "docs": chosen_docs}


def build_instruments(adapter, sel: dict, out: Path) -> dict:
    texts = {k: str(d.get("retrieval_text") or "") for k, d in sel["docs"].items()}
    prompt = (
        "Given ONLY these three memory texts, write 3 short recall probes "
        "(one-line paraphrase queries a search engine could match to these "
        "memories) and 1 negative-control query about a domain COMPLETELY "
        "unrelated to any content below.\n"
        + json.dumps(texts) +
        '\nReturn strict JSON: {"probes": ["...","...","..."], "negative_control": "..."}'
    )
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "embry-cycle-instruments",
        output_contract={"probes": ["3 strings"], "negative_control": "string"})
    probes = [str(x).strip() for x in (parsed or {}).get("probes") or [] if str(x).strip()]
    neg = str((parsed or {}).get("negative_control") or "").strip()
    if len(probes) < 3 or not neg:
        raise SystemExit(f"BLOCKED_CYCLE_INSTRUMENTS: probes={len(probes)} neg={bool(neg)} "
                         f"receipt={json.dumps(receipt)[:160]}")
    parsed = {"probes": probes[:3], "negative_control": neg}
    root_words = set()
    for t in texts.values():
        root_words.update(w for w in re.findall(r"[a-z]{4,}", t.lower())
                          if w not in STOPWORDS)
    neg_words = {w for w in re.findall(r"[a-z]{4,}", parsed["negative_control"].lower())
                 if w not in STOPWORDS}
    overlap = sorted(root_words & neg_words)
    if overlap:
        raise SystemExit(f"BLOCKED_CYCLE_NEGATIVE_CONTROL_OVERLAP: {overlap[:5]}")
    instruments = {
        "schema": "persona_dream.cycle_instruments.v1",
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_before_dream_composition": True,
        "probes": parsed["probes"],
        "negative_control": parsed["negative_control"],
        "negative_control_root_overlap": [],
        "roots": sorted(texts),
    }
    path = out / "instruments.v1.json"
    path.write_text(json.dumps(instruments, indent=2, sort_keys=True) + "\n")
    instruments["sha256"] = sha256_text(path.read_text())
    return instruments


def compose_and_render(adapter, phase_c, subgate, sel: dict, out: Path) -> dict:
    reading = "\n\n".join(
        f"## {k}\n{d.get('retrieval_text')}" for k, d in sel["docs"].items())
    person_tag = sel["cluster"]["cluster_id"].split(":person:")[1]
    other = person_tag.replace("_", " ").title()
    emphasis = sel["cluster"].get("valence_emphasis", "positive")
    vindex = sel["cluster"].get("variation_index", 0)
    emphasis_line = (
        f"This is dream VARIATION #{vindex} of this experience. Humans re-dream "
        f"the same memories differently; the SAME memories are held with both "
        f"positive and negative feeling. For THIS variation, let the "
        f"{emphasis.upper()} reading dominate the emotional arc — surface the "
        + ("warmth, trust, longing, or relief latent in these memories"
           if emphasis == "positive" else
           "grief, guilt, fear, anger, or shame latent in these memories")
        + ". Do not change the facts; change which feeling the dream leans into.\n\n")
    prompt = (
        "You are composing Embry's synthetic dream as a 4-panel storyboard. "
        "Ground the dream ONLY in these root memories (the dream recombines "
        "and heightens them; it is synthetic, never literal history):\n"
        + reading + "\n\n" + emphasis_line +
        "Compose a dream synopsis (2-3 sentences) and EXACTLY 4 storyboard "
        "panels. Embry must appear foreground with her face visible in every "
        f"panel; {other} appears in at least 2 panels. Return strict JSON: "
        '{"dream_synopsis": "...", "panels": [{"panel_id": "sb_001", '
        '"time_range": "0.0-2.5s", "shot": "...", "setting": "...", '
        '"action": "...", "start_frame_description": "...", "mood": "..."}, '
        "... 4 panels total]}")
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "embry-cycle-storyboard",
        output_contract={"dream_synopsis": "string", "panels": ["4 panel objects"]})
    if parsed is None or len(parsed.get("panels", [])) != PANEL_COUNT:
        raise SystemExit(f"BLOCKED_CYCLE_STORYBOARD: {json.dumps(receipt)[:200]}")
    (out / "storyboard_plan.json").write_text(json.dumps(parsed, indent=2) + "\n")

    embedder = subgate.InsightFaceEmbedder()
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    accepted, image_calls = [], 0
    seen_ids: set[str] = set()
    for i, panel in enumerate(parsed["panels"]):
        panel_id = f"sb_{i+1:03d}"  # canonical, never model-supplied (path safety)
        if panel.get("panel_id") not in (None, panel_id):
            panel = {**panel, "panel_id": panel_id}
        if panel_id in seen_ids:
            raise SystemExit(f"BLOCKED_CYCLE_DUPLICATE_PANEL_ID: {panel_id}")
        seen_ids.add(panel_id)
        base = (
            "Create a single cinematic storyboard frame. Real storyboard frame — "
            "not a contact sheet, not a collage, no rendered text.\n"
            "MANDATORY CHARACTER IDENTITY (HIGHEST PRIORITY): Embry clearly "
            "visible, large in the foreground, face readable in three-quarter "
            "view, strongly matched to her reference contact sheet: adult woman "
            "around 30, warm light-tan complexion, brown hair tied back, "
            "expressive brown eyes, softly rounded jaw, navy blue top; face "
            "sharp, well-lit, unoccluded, chest-up.\n"
            f"{other} appears per the panel action; no identity reference "
            "exists for this person — render consistently, secondary to Embry.\n"
            "Reference asset attached as a MANDATORY identity input (ACTUAL "
            "IMAGE INPUT — view this file before generating and match Embry's "
            f"face to it): {EMBRY_SHEET}\n"
            f"PANEL {panel_id} ({panel.get('time_range','')}): {panel.get('shot','')}\n"
            f"SETTING: {panel.get('setting','')}\nACTION: {panel.get('action','')}\n"
            f"FRAME: {panel.get('start_frame_description','')}\nMOOD: {panel.get('mood','')}\n"
            "STYLE: realistic cinematic storyboard frame, natural light, "
            "emotionally grounded. NEGATIVE: no missing Embry, no generic "
            "woman substituted, no back-facing-only Embry, no contact sheet, "
            "no collage, no text overlays.\n"
            "OUTPUT: one 16:9 photorealistic storyboard frame, 1536x864.")
        findings: list[str] = []
        ok = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            png = frames_dir / f"{panel_id}.attempt_{attempt:02d}.png"
            gp = base if attempt == 1 else base + (
                f"\nSURGICAL REPAIR (attempt {attempt}) — previous render failed "
                "the face-embedding identity gate: " + "; ".join(findings) +
                "\nMUST: view the attached Embry contact sheet again and match "
                "her face exactly; face large, sharp, three-quarter view.")
            gen = phase_c._generate(gp, png, frames_dir, panel_id, attempt)
            image_calls += 1
            if not gen.get("ok"):
                findings = [f"generation failed rc={gen.get('returncode')}"]
                continue
            verdict = subgate.run_face_embedding_subgate(
                frame_path=png, references={"Embry": EMBRY_SHEET},
                required_entities=["Embry"], embedder=embedder)
            (frames_dir / f"{panel_id}.attempt_{attempt:02d}_arcface.json").write_text(
                json.dumps(verdict, indent=2, default=str) + "\n")
            if verdict.get("status") == "PASS":
                ok = {"panel_id": panel_id, "frame": str(png),
                      "frame_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                      "attempt": attempt,
                      "best_cosine": (verdict.get("entity_results") or [{}])[0].get("best_cosine")}
                break
            findings = [str(f) for f in (verdict.get("blocking_findings") or
                                         ["Embry not reference-verifiable"])]
        if ok is None:
            raise SystemExit(f"BLOCKED_CYCLE_IDENTITY_GATE: {panel_id}: {findings}")
        accepted.append(ok)

    from PIL import Image
    imgs = [Image.open(f["frame"]) for f in accepted]
    w, h = imgs[0].size
    sheet = Image.new("RGB", (w * 2, h * 2))
    for i, im in enumerate(imgs):
        sheet.paste(im.resize((w, h)), ((i % 2) * w, (i // 2) * h))
    sheet_png = out / "storyboard_contact_sheet.png"
    sheet.save(sheet_png)
    return {"plan": parsed, "frames": accepted, "image_calls": image_calls,
            "sheet": sheet_png,
            "media_sha": hashlib.sha256(sheet_png.read_bytes()).hexdigest(),
            "other_person": other}


def observe(composite, art: dict, out: Path) -> list:
    import base64
    payload = {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text":
             "Describe what is actually visible in each of the 4 storyboard "
             "frames (2x2 grid, reading order): people, activity, setting, "
             'tone. Judge pixels only. Return strict JSON: {"frames": '
             '[{"index": 1, "people": ["..."], "activity": "...", '
             '"setting": "...", "tone": "..."}, ... 4 entries]}'},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," +
                           base64.b64encode(art["sheet"].read_bytes()).decode(),
                           "detail": "high"},
             "label": "storyboard 2x2 contact sheet"}]}],
    }
    vlm_dir = out / "vlm_observation"
    vlm_dir.mkdir(exist_ok=True)
    resp = composite.post_openai_vlm_via_tau(
        payload, artifact_dir=str(vlm_dir),
        caller_skill="persona-dream-cycle-observer",
        purpose="storyboard_content_observation")
    text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    try:
        frames = json.loads(text[text.index("{"):text.rindex("}") + 1]).get("frames", [])
    except Exception:
        frames = []
    if len(frames) != 4:
        raise SystemExit(f"BLOCKED_CYCLE_VLM_PARSE: expected 4 frame entries, got {len(frames)}")
    idxs = [f.get("index") for f in frames]
    if sorted(idxs) != [1, 2, 3, 4]:
        raise SystemExit(f"BLOCKED_CYCLE_VLM_INDICES: {idxs}")
    for f in frames:
        if not all(str(f.get(k) or "").strip() for k in ("activity", "setting", "tone")) \
                or not f.get("people"):
            raise SystemExit(f"BLOCKED_CYCLE_VLM_EMPTY_FIELDS: index {f.get('index')}")
    (out / "vlm_observation.json").write_text(json.dumps(
        {"raw": text[:4000], "frames": frames}, indent=2) + "\n")
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cycle-id", default=None)
    args = parser.parse_args()
    cycle_id = args.cycle_id or time.strftime("cycle_%Y%m%dT%H%M%SZ", time.gmtime())
    out = ROOT / "reports/goal_v3/cycles" / cycle_id
    out.mkdir(parents=True, exist_ok=True)
    dream_id = f"auto_{cycle_id}"

    adapter = _load("tau_text_reasoning_adapter")
    phase_c = _load("phase_c_regenerate_storyboard_frames")
    subgate = _load("identity_face_embedding_subgate")
    composite = _load("tau_vlm_composite_review")
    p13 = _load("phase13_self_interpretation")
    p14 = _load("phase14_tom_validation")
    p15 = _load("phase15_dream_persistence")
    pm = _load("pilot_metrics")

    # 1. select
    sel = select_cluster(out)
    roots = sorted(sel["docs"])
    # anchors snapshot (dream-004 node + this cycle's roots) BEFORE the run
    anchor_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/pilot_metrics.py"), "snapshot-anchors",
         "--keys", ",".join(["dream_dream_successor_943b01ecd9a3"] + roots),
         "--out", str(out / "anchor_snapshot.json")],
        capture_output=True, text=True)
    if anchor_proc.returncode != 0:
        raise SystemExit(f"BLOCKED_CYCLE_ANCHORS: {anchor_proc.stderr[-200:]}")

    # 2. instruments frozen pre-dream
    instruments = build_instruments(adapter, sel, out)

    # 3. dream + frames
    art = compose_and_render(adapter, phase_c, subgate, sel, out)

    # 4. observation packet
    vlm_frames = observe(composite, art, out)
    packet = {
        "schema": "persona_dream.cycle_storyboard_observation_packet.v1",
        "status": "ACCEPTED_STORYBOARD_OBSERVATION",
        "evidence_origin": "storyboard_frames",
        "evidence_class": "synthetic_dream",
        "source_video_sha256": f"sha256:{art['media_sha']}",
        "source_revision_id": cycle_id,
        "frame_evidence": [
            {"index": i + 1, "timestamp_seconds": round(i * 2.5, 2),
             "in_identity_window": True, "in_speaker_window": False,
             "panel_id": art["frames"][i]["panel_id"],
             "frame_path": art["frames"][i]["frame"],
             "frame_sha256": art["frames"][i]["frame_sha256"],
             "path": art["frames"][i]["frame"],
             "sha256": art["frames"][i]["frame_sha256"],
             "observed_entities": (vlm_frames[i].get("people")
                                   if i < len(vlm_frames) else None)}
            for i in range(len(art["frames"]))],
        "transcript_facts": [],
        "step_hooks": {"step_36_identity_temporal_continuity": {
            "identity_window_seconds": [0.0, 10.0],
            "vision_review": {
                "model": "insightface:buffalo_l (authority) + gpt-5.5 montage (advisory)",
                "verdict": "PASS",
                "raw_output_tail": "all 4 frames passed ArcFace vs embry_contact_sheet_v3"}}},
        "coverage_gaps": [
            "no audio track: storyboard frames are the visual artifact",
            "no inter-frame motion",
            f"{art['other_person']} identity advisory (no reference sheet)"],
    }
    packet_path = out / "observation_packet.json"
    packet_path.write_text(json.dumps(packet, indent=2) + "\n")
    residue = {
        "schema": "persona_dream.residue_links.v1",
        "idea_id": dream_id,
        "items": [{"collection": "persona_memory", "persona_id": PERSONA,
                   "source_id": k, "source_path": f"gmo:persona_memory/{k}",
                   "text": str(d.get("retrieval_text") or "")}
                  for k, d in sel["docs"].items()],
    }
    residue_path = out / "residue_links.json"
    residue_path.write_text(json.dumps(residue, indent=2) + "\n")

    # 5. phases 13/14 — cognition contract bound to the SELECTED counterpart
    # (round-1 tau review CRITICAL: default Embry-Kai contract leaked; Brandon
    # roots produced Kai-targeted ToM). The counterpart comes from the cluster.
    cc = _load("persona_dream_cognition_contract")
    counterpart_id = sel["cluster"]["cluster_id"].split(":person:")[1].split("_")[0]
    contract = cc.load_contract()
    contract = json.loads(json.dumps(contract))
    contract["contract_id"] = f"cycle_{counterpart_id}_lane_v1"
    contract["default_target"] = counterpart_id
    contract["counterparts"] = [{"id": counterpart_id,
                                 "display_name": art["other_person"],
                                 "title": art["other_person"],
                                 "relationship_description":
                                 f"person anchoring the selected residue cluster {sel['cluster']['cluster_id']}"}]
    contract["domain"] = {"domain_label": "selected_residue",
                          "activity": "the recalled experiences",
                          "locus": "the settings of the selected root memories"}
    (out / "cycle_cognition_contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    interp = p13.run_phase13(packet_path, residue_path, None, None,
                             dream_id, cycle_id, "goal-v3", PERSONA, live=True,
                             contract=contract)
    p13.write_json(out / "phase13_interpretation.json", interp)
    if not interp["status"].startswith("PASS") or not interp["accepted_interpretations"]:
        raise SystemExit(f"BLOCKED_CYCLE_PHASE13: {interp['status']}")
    bad = counterpart_violations(interp["accepted_interpretations"],
                                 counterpart_id, "interpretation_id")
    if bad:
        raise SystemExit(f"BLOCKED_CYCLE_COUNTERPART_MISMATCH_P13: targets != {counterpart_id}: {bad}")
    tom = p14.run_phase14(interp, dream_id, cycle_id, "goal-v3", live=True)
    p13.write_json(out / "phase14_tom.json", tom)
    if not tom["status"].startswith("PASS") or not tom["accepted_tom_candidates"]:
        raise SystemExit(f"BLOCKED_CYCLE_PHASE14: {tom['status']}")
    bad = counterpart_violations(tom["accepted_tom_candidates"],
                                 counterpart_id, "candidate_id")
    if bad:
        raise SystemExit(f"BLOCKED_CYCLE_COUNTERPART_MISMATCH_P14: targets != {counterpart_id}: {bad}")

    # 6. persist WITH watch vertices, closure-gated
    root_ids = sorted({b.get("source_id") for b in interp.get("source_memory_bindings", [])
                       if b.get("source_id")})
    causal = p15.build_causal_family_fields(PERSONA, dream_id, root_ids, None)
    causal["goal_v3_cycle"] = cycle_id
    dream_doc = p15.build_dream_memory_document(
        dream_id, cycle_id, "goal-v3", PERSONA, packet, interp, tom,
        causal_fields=causal)
    dream_doc["evidence_class"] = "synthetic_dream"
    dream_doc["tags"] = [f"persona:{PERSONA}", "synthetic_dream", "persona_dream",
                         "goal_v3_autonomous_cycle"]
    watch_vertices = p15.build_watch_evidence_vertices(
        packet, interp, dream_id, f"storyboard_{art['media_sha'][:32]}",
        None, persona_id=PERSONA, causal_fields=causal)
    interp_vertices = p15.build_interpretation_vertices(
        interp, PERSONA, dream_id, causal_fields=causal)
    return_id = f"storyboard_{art['media_sha'][:32]}"
    allowed, blockers = p15.canonical_write_decision(packet, True, return_id)
    if not allowed:
        raise SystemExit(f"BLOCKED_CYCLE_WRITE_DECISION: {blockers}")
    proof = p15.persist_canonical(
        dream_doc, interp, tom, watch_vertices, GMO,
        dream_id=dream_id, return_id=return_id, packet=packet,
        phase13_sha=p15.canonical_sha(interp), phase14_sha=p15.canonical_sha(tom),
        interpretation_vertices=interp_vertices, causal_fields=causal,
        include_dream_node=True,
        justification=f"GOAL_V3 autonomous cycle {cycle_id}")
    p13.write_json(out / "persist_proof.json", proof)
    manifest = proof.get("commit_manifest") or {}
    if not (proof.get("all_exact_reread_match") and manifest.get("exact_reread_match")
            and manifest.get("active")):
        raise SystemExit(f"BLOCKED_CYCLE_PERSIST: {proof.get('status')}")
    act = post("/persona-dream/commit/activate",
               {"commit_id": manifest.get("key"), "dream_id": dream_id}, timeout=120)
    if act.get("outcome") != "activated" or not act.get("reread_verified"):
        raise SystemExit(f"BLOCKED_CYCLE_ACTIVATION: {act.get('outcome')}")

    # 7. evaluate
    m2 = pm.m2_grounding(p15, manifest["key"], out, PERSONA, dream_id)
    m3 = pm.m3_distinction(adapter, dream_doc["_key"])
    m4 = pm.m4_identity(p15, manifest["key"], out / "anchor_snapshot.json")
    ranks = {}
    for i, probe in enumerate(instruments["probes"]):
        items = post("/recall", {"q": probe, "k": 20,
                                 "collections": ["persona_memory"], "tags": []}).get("items") or []
        keys = [it.get("_key") for it in items]
        ranks[f"probe_{i+1}"] = (keys.index(dream_doc["_key"]) + 1) if dream_doc["_key"] in keys else None
    n_items = post("/recall", {"q": instruments["negative_control"], "k": 10,
                               "collections": ["persona_memory"], "tags": []}).get("items") or []
    n1_pass = dream_doc["_key"] not in [it.get("_key") for it in n_items[:10]]

    # 8. voice weights on the NEW dream
    vw = subprocess.run(
        [sys.executable, str(ROOT / "scripts/dream_voice_weights.py"),
         "--dream-key", dream_doc["_key"], "--render",
         "--out-dir", str(out / "voice_weights")],
        capture_output=True, text=True, timeout=300)
    voice_ok = vw.returncode == 0

    passed = (m2.get("fraction_resolved") == 1.0 and m3.get("passed") is True
              and m4.get("passed") is True and n1_pass and voice_ok)
    receipt = {
        "schema": "persona_dream.autonomous_cycle_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cycle_id": cycle_id,
        "status": "PASS_AUTONOMOUS_CYCLE" if passed else "BLOCKED_AUTONOMOUS_CYCLE",
        "cluster": sel["cluster"]["cluster_id"],
        "counterpart_id": counterpart_id,
        "counterpart_gate": "all accepted p13/p14 targets in {counterpart, unknown_person}",
        "roots": roots,
        "instruments_sha256": instruments["sha256"],
        "instruments_frozen_before_dream": True,
        "dream_node_key": dream_doc["_key"],
        "commit_manifest_key": manifest.get("key"),
        "media_sha256": art["media_sha"],
        "frames": art["frames"],
        "image_calls": art["image_calls"],
        "arcface_cosines": [f.get("best_cosine") for f in art["frames"]],
        "grounding_fraction": m2.get("fraction_resolved"),
        "distinction": {k: m3.get(k) for k in
                        ("literal_occurrence_status", "record_class", "passed")},
        "anchors_unchanged": m4.get("passed"),
        "recall_probe_ranks": ranks,
        "negative_control_absent_top10": n1_pass,
        "voice_weights_receipt": str(out / "voice_weights/dream_voice_weights_receipt.v1.json") if voice_ok else None,
        "human_touches": 0,
    }
    (out / "autonomous_cycle_receipt.v1.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: receipt[k] for k in
                      ("status", "cycle_id", "dream_node_key", "grounding_fraction",
                       "recall_probe_ranks", "negative_control_absent_top10",
                       "arcface_cosines", "image_calls")}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
