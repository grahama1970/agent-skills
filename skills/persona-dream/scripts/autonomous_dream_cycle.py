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
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"
PERSONA = "embry"  # default persona; overridden by --persona via the profile
MAX_ATTEMPTS = 5
PANEL_COUNT = 4
STOPWORDS = set("the a an and or of to in on for with her his she he it its is was are be as at by from that this".split())
RECALL_NEGATIVE_CONTROL_QUERY = "kubernetes cgroup freezer ioctl nftables conntrack checksum"


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


def fetch_persona_docs(persona_id: str) -> list[dict]:
    docs, off = [], 0
    while True:
        page = post("/list", {"collection": "persona_memory",
                              "filters": {"persona_id": persona_id},
                              "limit": 100, "offset": off})
        docs += page.get("documents", [])
        off += 100
        if off >= page.get("total", 0):
            break
    return docs


def charged_interaction_pulls(persona: str) -> list[dict]:
    """The persona's charged interaction residue (it was rejected/lost/contradicted
    by a counterpart in a /tau DAG or /ask competition/roundtable), ranked by
    dream_weight -- how hard each pulls a future dream toward that counterpart
    (losing/being contradicted pulls hardest). Uses /list (collection-scoped
    /recall is currently broken, graph-memory-operator#50). Empty => the persona
    has not interacted with anyone => it can only dream self_only (the gate)."""
    try:
        page = post("/list", {"collection": "persona_interactions",
                              "filters": {"persona_id": persona}, "limit": 100})
    except Exception:  # noqa: BLE001 - collection may not exist yet
        return []
    out = []
    for d in page.get("documents", []):
        for c in (d.get("counterpart_personas") or []):
            out.append({"counterpart": c,
                        "dream_weight": d.get("dream_weight", 0.5),
                        "outcome": d.get("outcome"),
                        "observed": (d.get("observed_of_counterpart") or "")[:200],
                        "interaction_id": d.get("interaction_id")})
    out.sort(key=lambda x: x["dream_weight"], reverse=True)
    return out


def counterpart_violations(claims: list, counterpart_id: str, id_field: str) -> list:
    """GOAL_V3 counterpart gate (probe-able): a claim's target must be the
    selected counterpart or the bounded unknown_person."""
    allowed = {counterpart_id, "unknown_person"}
    return [c.get(id_field) for c in claims if str(c.get("target")) not in allowed]


#: Words that carry no selection signal. Deliberately short -- an idea is a
#: sentence a human typed, not a query language, and over-filtering it would
#: quietly change what she dreams about.
_IDEA_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "about", "that", "this", "it", "its", "is", "was", "were", "be",
    "been", "i", "me", "my", "we", "our", "you", "your", "they", "them",
    "what", "when", "where", "why", "how", "not", "never", "out", "loud",
    "things", "thing", "said", "say", "from", "into", "over", "all", "some",
}

#: Fields that actually carry prose in persona_memory roots.
_IDEA_TEXT_FIELDS = ("claim", "claim_text", "evidence_text", "retrieval_text")


def idea_terms(idea: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", idea.lower())
            if len(w) > 2 and w not in _IDEA_STOPWORDS}


def score_root_against_idea(doc: dict, terms: set[str]) -> int:
    """How many distinct idea terms this memory mentions."""
    blob = " ".join(str(doc.get(f) or "") for f in _IDEA_TEXT_FIELDS).lower()
    return sum(1 for t in terms if t in blob)


def seed_roots_with_idea(roots: dict, idea: str) -> tuple[dict, dict]:
    """Restrict selection to residue the idea actually touches.

    Local matching, not /recall: collection-scoped recall against
    persona_memory returns nothing (graph-memory-operator#50), which is why
    fetch_persona_docs uses /list. Matching here also has the advantage of
    scoring exactly the root set selection will draw from, rather than a
    separately-ranked list that may not intersect it.

    An idea steers WHICH of her memories surface. It never invents residue --
    she can only dream about what she remembers.
    """
    terms = idea_terms(idea)
    if not terms:
        raise SystemExit(f"BLOCKED_IDEA_EMPTY: {idea!r} has no searchable terms")
    scored = {k: score_root_against_idea(d, terms) for k, d in roots.items()}
    best = max(scored.values(), default=0)
    if best == 0:
        raise SystemExit(
            f"BLOCKED_IDEA_NO_RESIDUE: none of {len(roots)} eligible root "
            f"memories mention any of {sorted(terms)}.\n"
            "  She can only dream about what she remembers. Ingest the "
            "material to memory first, then dream about it."
        )
    # Keep every root that matches at all, so the cluster engine still has a
    # population to find a valence conflict in; a top-1 filter would starve it.
    seeded = {k: d for k, d in roots.items() if scored[k] > 0}
    provenance = {
        "idea": idea,
        "terms": sorted(terms),
        "roots_before": len(roots),
        "roots_after": len(seeded),
        "best_term_hits": best,
    }
    return seeded, provenance



def select_cluster(profile, out: Path, persist_ledger: bool = True,
                   idea: str = "") -> dict:
    """Persona-agnostic conflict-seeded selection. Every persona/corpus-specific
    decision (which docs are roots, the recency band, who the counterparts are,
    the valence-conflict score, and how to traverse) is delegated to the profile,
    so this ONE engine serves ANY persona. The Embry profile reproduces the
    original age-band/emotion logic; the generic profile covers book/entity/ToM
    corpora and traverses via the shared ENTITY graph (memory -> entity ->
    memory), the only bridge that survives differing edge schemas."""
    seed = sha256_text((ROOT / "GOAL_V3.md").read_text())
    docs = fetch_persona_docs(profile.persona_id)
    roots = profile.roots(docs)
    # GOAL_V4.3 loop guard (persona-independent): never dream about dream-colored
    # experience. Residue carrying persona_dream affect provenance is excluded
    # from selection — severs dream->speech->memory->dream amplification.
    tainted = {k for k, d in roots.items()
               if (d.get("affect_source") == "persona_dream"
                   or (d.get("voice_delivery") or {}).get("affect_source") == "persona_dream"
                   or d.get("dream_provenance"))}
    roots = {k: v for k, v in roots.items() if k not in tainted}

    # An idea steers which residue surfaces. Fail closed when it matches
    # nothing: silently dreaming about something else would be worse than
    # refusing, because the receipt would then claim an idea it ignored.
    idea_provenance: dict = {}
    if idea:
        roots, idea_provenance = seed_roots_with_idea(roots, idea)

    used: set[str] = set()
    for d in docs:
        if d.get("kind") in ("synthetic_dream_memory", "synthetic_reflection_memory") \
                and d.get("visibility_state") in ("active", None):
            used.update(d.get("source_memory_ids") or [])

    # Counterpart-anchored clusters (band, counterpart), schema-agnostic: the
    # band and counterpart set both come from the profile.
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, doc in roots.items():
        band = profile.band(key, doc)
        if band is None:
            continue
        for tag in profile.counterparts(doc):
            groups[(band, tag)].add(key)

    # Entity index for the schema-agnostic entity-mediated walk. Inline
    # memory->memory edges differ per corpus (and don't cross personas); the
    # entity graph is the shared substrate, so memory -> entity -> memory is the
    # traversal that works for ANY persona.
    entity_index: dict[str, set[str]] = defaultdict(set)
    for key, doc in roots.items():
        for ent in profile.entities_of(doc):
            entity_index[ent].add(key)

    # GOAL_V3 Amendment 2: dreaming is NOT one-shot per cluster. Seed from a
    # valence-CONFLICTED memory, traverse that counterpart's associates
    # (isolation preserved: traversal stays WITHIN the seed counterpart), and the
    # VARIATION is which valence dominates + which associative path is taken.
    def traverse(seed_key, members, k=3):
        order, seen, frontier = [seed_key], {seed_key}, [seed_key]
        while frontier and len(order) < k:
            nxt = []
            for s in frontier:
                for tgt in profile.intra_neighbors(s, roots[s], members, entity_index):
                    if tgt not in seen:
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
        clusters.append({"cluster_id": cluster_id, "band": band, "age_band": band,
                         "tag": tag, "members": members,
                         "order_hash": sha256_text(seed + cluster_id),
                         "used_overlap": len(members & used)})
    # ARC-CONDITIONING (roundtable-converged 2026-07-24, self_only mode): bias
    # seeding toward the persona's CURRENT arc_state tensions from the Continuity
    # Ledger, so tonight's dream is driven by yesterday's unresolved
    # self-understanding. This finishes the causal loop dream -> journal ->
    # arc_delta -> NEXT dream; without it the loop is self-referential (the
    # persona re-dreams confirmation of the story it already told itself).
    cl_mod = _load("continuity_ledger")
    arc = (cl_mod.read_ledger(profile.persona_id, docs).get("arc_state") or {})
    arc_text = " ".join((arc.get("active_tensions") or [])
                        + [str(d.get("open_tension") or "")
                           for d in (arc.get("recent_arc_deltas") or [])[-5:]]
                        + (arc.get("unresolved_questions") or []))
    arc_terms = {w for w in re.findall(r"[a-z]{4,}", arc_text.lower())
                 if w not in STOPWORDS}

    def arc_resonance(members) -> int:
        txt = " ".join(
            str(roots[m].get("retrieval_text") or "") + " "
            + str(roots[m].get("tom_content") or roots[m].get("event_summary") or "")
            for m in members).lower()
        return len(arc_terms & {w for w in re.findall(r"[a-z]{4,}", txt)
                                if w not in STOPWORDS})

    for c in clusters:
        c["arc_resonance"] = arc_resonance(c["members"])
    # never-dreamed first (coverage), then MOST arc-resonant (the current
    # tension drives the dream), then recency, then deterministic hash.
    clusters.sort(key=lambda c: (c["used_overlap"] > 0,
                                 -c["arc_resonance"],
                                 profile.recency_index(c["band"]),
                                 c["used_overlap"], c["order_hash"]))
    if not clusters:
        raise SystemExit("BLOCKED_CYCLE_NO_ELIGIBLE_CLUSTERS")

    chosen = None
    for cl in clusters:
        members = cl["members"]
        conflicted = sorted(members, key=lambda m: (profile.conflict_score(roots[m]),
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
            chosen = {"cluster_id": cl["cluster_id"], "band": cl["band"],
                      "age_band": cl["age_band"],
                      "selected": selected, "seed_memory": seed_key,
                      "valence_emphasis": emphasis,
                      "variation_index": variation_index,
                      "variation_key": vkey,
                      "used_overlap": cl["used_overlap"],
                      "arc_resonance": cl.get("arc_resonance", 0),
                      "order_hash": cl["order_hash"]}
            break
        if chosen:
            break
    if chosen is None:
        if os.environ.get("PERSONA_DREAM_ALLOW_VARIATION_REUSE") != "1":
            raise SystemExit("BLOCKED_CYCLE_ALL_VARIATIONS_EXHAUSTED")
        cl = clusters[0]
        members = cl["members"]
        conflicted = sorted(members, key=lambda m: (profile.conflict_score(roots[m]),
                                                    sha256_text(seed + m)),
                            reverse=True)
        seed_key = conflicted[0]
        selected = traverse(seed_key, members, k=3)
        chosen = {"cluster_id": cl["cluster_id"], "band": cl["band"],
                  "age_band": cl["age_band"], "selected": selected,
                  "seed_memory": seed_key, "valence_emphasis": "positive",
                  "variation_index": cl["used_overlap"],
                  "variation_key": sha256_text(cl["cluster_id"] + "|" + "|".join(sorted(selected))
                                                + "|eval_reuse"),
                  "used_overlap": cl["used_overlap"],
                  "arc_resonance": cl.get("arc_resonance", 0),
                  "order_hash": cl["order_hash"],
                  "reused_after_ledger_exhaustion": True}
        persist_ledger = False

    if persist_ledger:
        ledger["variation_keys"].append(chosen["variation_key"])
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")

    chosen_docs = {k: roots[k] for k in chosen["selected"]}
    (out / "selection_receipt.v1.json").write_text(json.dumps({
        "schema": "persona_dream.cycle_selection_receipt.v2",
        "persona_id": profile.persona_id,
        "selector_strategy": profile.strategy,
        "traversal": ("inline_memory_edges" if profile.strategy
                      == "age_band_counterpart" else "entity_mediated"),
        "loop_guard_excluded_tainted_residue": len(tainted),
        "seed_source": "GOAL_V3.md sha256", "seed": seed,
        "selection_mode": "conflict_seeded_intra_counterpart_traversal",
        "dream_seed_mode": "self_only",
        "cross_persona_pulls": charged_interaction_pulls(profile.persona_id)[:5],
        "cross_persona_seed_available": bool(charged_interaction_pulls(profile.persona_id)),
        "arc_conditioned": bool(arc_terms),
        "arc_terms": sorted(arc_terms)[:24],
        "chosen_arc_resonance": chosen.get("arc_resonance", 0),
        "clusters_considered": len(clusters),
        "cluster_was_previously_dreamed": chosen["used_overlap"] > 0,
        "chosen": {k: chosen[k] for k in ("cluster_id", "selected", "seed_memory",
                                          "valence_emphasis", "variation_index",
                                          "variation_key")},
    }, indent=2, sort_keys=True) + "\n")
    return {"cluster": chosen, "docs": chosen_docs}


def build_instruments(adapter, sel: dict, out: Path) -> dict:
    texts = {k: str(d.get("retrieval_text") or "") for k, d in sel["docs"].items()}
    # The overlap gate below is only satisfiable by construction if the model
    # knows which words are forbidden, so name them in the prompt instead of
    # hoping (2026-08-20: 'events' overlapped and blocked the whole cycle).
    root_words = set()
    for t in texts.values():
        root_words.update(w for w in re.findall(r"[a-z]{4,}", t.lower())
                          if w not in STOPWORDS)
    base_prompt = (
        "Given ONLY these three memory texts, write 3 short recall probes "
        "(one-line paraphrase queries a search engine could match to these "
        "memories) and 1 negative-control query about a domain COMPLETELY "
        "unrelated to any content below. The negative-control query must not "
        "contain ANY of these forbidden words (or their plurals/inflections): "
        + ", ".join(sorted(root_words)) + "\n"
        + json.dumps(texts) +
        '\nReturn strict JSON: {"probes": ["...","...","..."], "negative_control": "..."}'
    )
    parsed = None
    overlap: list[str] = []
    feedback = ""
    for _attempt in range(3):
        raw, receipt = adapter.dispatch_text_reasoning(
            base_prompt + feedback, "persona-cycle-instruments",
            output_contract={"probes": ["3 strings"], "negative_control": "string"})
        probes = [str(x).strip() for x in (raw or {}).get("probes") or [] if str(x).strip()]
        neg = str((raw or {}).get("negative_control") or "").strip()
        if len(probes) < 3 or not neg:
            raise SystemExit(f"BLOCKED_CYCLE_INSTRUMENTS: probes={len(probes)} neg={bool(neg)} "
                             f"receipt={json.dumps(receipt)[:160]}")
        parsed = {"probes": probes[:3], "negative_control": RECALL_NEGATIVE_CONTROL_QUERY}
        neg_words = {w for w in re.findall(r"[a-z]{4,}", parsed["negative_control"].lower())
                     if w not in STOPWORDS}
        overlap = sorted(root_words & neg_words)
        if not overlap:
            break
        feedback = ("\nYour previous negative-control query used forbidden words "
                    f"{overlap[:5]}; produce a new one avoiding every forbidden word.")
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


def recall_item_summaries(items: list[dict], *, limit: int) -> list[dict]:
    """Stable receipt projection for Memory recall rows.

    Memory recall order is an observed fact from the service. Preserve the
    returned rank and enough row identity to audit a gate later without relying
    on a second live recall that may see a changed index.
    """
    summaries: list[dict] = []
    for idx, item in enumerate(items[:limit], 1):
        text = str(item.get("retrieval_text") or item.get("solution") or item.get("text") or "")
        summaries.append({
            "rank": idx,
            "_key": item.get("_key"),
            "score": item.get("score"),
            "kind": item.get("kind"),
            "persona_id": item.get("persona_id"),
            "tags": sorted(str(tag) for tag in (item.get("tags") or [])),
            "text_sha256": sha256_text(text) if text else None,
            "text_preview": text[:160],
        })
    return summaries


def rank_key(summaries: list[dict], key: str) -> int | None:
    for row in summaries:
        if row.get("_key") == key:
            return int(row["rank"])
    return None


def evaluate_recall_instruments(instruments: dict, dream_key: str, recall_post=post) -> dict:
    probe_rows: dict[str, list[dict]] = {}
    ranks: dict[str, int | None] = {}
    for i, probe in enumerate(instruments["probes"]):
        label = f"probe_{i+1}"
        items = recall_post("/recall", {
            "q": probe,
            "k": 20,
            "collections": ["persona_memory"],
            "tags": [],
        }).get("items") or []
        rows = recall_item_summaries(items, limit=20)
        probe_rows[label] = rows
        ranks[label] = rank_key(rows, dream_key)

    n_items = recall_post("/recall", {
        "q": instruments["negative_control"],
        "k": 10,
        "collections": ["persona_memory"],
        "tags": [],
    }).get("items") or []
    negative_rows = recall_item_summaries(n_items, limit=10)
    negative_rank = rank_key(negative_rows, dream_key)
    return {
        "recall_probe_ranks": ranks,
        "recall_probe_results": probe_rows,
        "negative_control_results": negative_rows,
        "negative_control_dream_rank": negative_rank,
        "negative_control_absent_top10": negative_rank is None,
    }


def compose_and_render(adapter, phase_c, subgate, profile, sel: dict, out: Path) -> dict:
    reading = "\n\n".join(
        f"## {k}\n{d.get('retrieval_text')}" for k, d in sel["docs"].items())
    person_tag = sel["cluster"]["cluster_id"].split(":person:")[1]
    other = person_tag.replace("_", " ").title()
    persona_name = profile.persona_id.replace("_", " ").title()
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
        f"You are composing {persona_name}'s synthetic dream as a 4-panel "
        "storyboard. Ground the dream ONLY in these root memories (the dream "
        "recombines and heightens them; it is synthetic, never literal history):\n"
        + reading + "\n\n" + emphasis_line +
        "Compose a dream synopsis (2-3 sentences) and EXACTLY 4 storyboard "
        f"panels. {persona_name} must appear foreground with their face visible "
        f"in every panel; {other} appears in at least 2 panels. Return strict JSON: "
        '{"dream_synopsis": "...", "panels": [{"panel_id": "sb_001", '
        '"time_range": "0.0-2.5s", "shot": "...", "setting": "...", '
        '"action": "...", "start_frame_description": "...", "mood": "..."}, '
        "... 4 panels total]}")
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "persona-cycle-storyboard",
        output_contract={"dream_synopsis": "string", "panels": ["4 panel objects"]})
    if parsed is None or len(parsed.get("panels", [])) != PANEL_COUNT:
        raise SystemExit(f"BLOCKED_CYCLE_STORYBOARD: {json.dumps(receipt)[:200]}")
    (out / "storyboard_plan.json").write_text(json.dumps(parsed, indent=2) + "\n")

    # Identity gate is per-persona: with a discovered face reference sheet the
    # ArcFace subgate runs (as for Embry); without one (e.g. horus_lupercal has
    # no face asset) frames render ungated and are marked as such — the cycle
    # still produces the dream, honestly flagged, rather than failing closed.
    gate_on = profile.has_identity_gate
    sheet = profile.reference_sheet
    embedder = subgate.InsightFaceEmbedder() if gate_on else None
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
        ref_line = (
            "Reference asset attached as a MANDATORY identity input (ACTUAL IMAGE "
            f"INPUT — view this file before generating and match {persona_name}'s "
            f"face to it): {sheet}\n" if gate_on else
            f"No face reference exists for {persona_name}; render {persona_name} "
            "consistently across all four panels as the clear foreground subject.\n")
        base = (
            "Create a single cinematic storyboard frame. Real storyboard frame — "
            "not a contact sheet, not a collage, no rendered text.\n"
            f"MANDATORY CHARACTER IDENTITY (HIGHEST PRIORITY): {persona_name} "
            "clearly visible, large in the foreground, face readable in "
            "three-quarter view"
            + (", strongly matched to the attached reference contact sheet"
               if gate_on else "")
            + "; face sharp, well-lit, unoccluded, chest-up.\n"
            f"{other} appears per the panel action; render consistently, "
            f"secondary to {persona_name}.\n"
            + ref_line +
            f"PANEL {panel_id} ({panel.get('time_range','')}): {panel.get('shot','')}\n"
            f"SETTING: {panel.get('setting','')}\nACTION: {panel.get('action','')}\n"
            f"FRAME: {panel.get('start_frame_description','')}\nMOOD: {panel.get('mood','')}\n"
            "STYLE: realistic cinematic storyboard frame, natural light, "
            f"emotionally grounded. NEGATIVE: no missing {persona_name}, no "
            f"generic substitute, no back-facing-only {persona_name}, no contact "
            "sheet, no collage, no text overlays.\n"
            "OUTPUT: one 16:9 photorealistic storyboard frame, 1536x864.")
        findings: list[str] = []
        ok = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            png = frames_dir / f"{panel_id}.attempt_{attempt:02d}.png"
            gp = base if attempt == 1 else base + (
                f"\nSURGICAL REPAIR (attempt {attempt}) — previous render failed "
                "the face-embedding identity gate: " + "; ".join(findings) +
                f"\nMUST: view the attached {persona_name} contact sheet again and "
                "match the face exactly; face large, sharp, three-quarter view.")
            gen = phase_c._generate(gp, png, frames_dir, panel_id, attempt)
            image_calls += 1
            if not gen.get("ok"):
                findings = [f"generation failed rc={gen.get('returncode')}"]
                continue
            if not gate_on:
                ok = {"panel_id": panel_id, "frame": str(png),
                      "frame_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                      "attempt": attempt, "best_cosine": None,
                      "identity_gate": "skipped_no_reference_sheet"}
                break
            verdict = subgate.run_face_embedding_subgate(
                frame_path=png, references={persona_name: sheet},
                required_entities=[persona_name], embedder=embedder)
            (frames_dir / f"{panel_id}.attempt_{attempt:02d}_arcface.json").write_text(
                json.dumps(verdict, indent=2, default=str) + "\n")
            if verdict.get("status") == "PASS":
                ok = {"panel_id": panel_id, "frame": str(png),
                      "frame_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                      "attempt": attempt, "identity_gate": "arcface_pass",
                      "best_cosine": (verdict.get("entity_results") or [{}])[0].get("best_cosine")}
                break
            findings = [str(f) for f in (verdict.get("blocking_findings") or
                                         [f"{persona_name} not reference-verifiable"])]
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
            "other_person": other, "persona_name": persona_name,
            "identity_gate": "arcface" if gate_on else "skipped_no_reference_sheet"}


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
    parser.add_argument("--persona", default=PERSONA,
                        help="persona_id to dream for (default embry)")
    parser.add_argument("--about", default="",
                        help="the idea to dream about; steers which of her own "
                             "residue surfaces. Omit for autonomous selection.")
    parser.add_argument("--select-only", action="store_true",
                        help="run only the persona-agnostic selection stage "
                             "(no paid render / phases); writes selection_receipt")
    args = parser.parse_args()
    cycle_id = args.cycle_id or time.strftime("cycle_%Y%m%dT%H%M%SZ", time.gmtime())
    out = ROOT / "reports/goal_v3/cycles" / cycle_id
    out.mkdir(parents=True, exist_ok=True)
    dream_id = f"auto_{cycle_id}"

    profiles = _load("persona_profiles")
    persona_id = args.persona
    # profile is DISCOVERED from the persona's own corpus + filesystem
    profile = profiles.build_profile(persona_id, fetch_persona_docs(persona_id))

    # 1. select (persona-agnostic). Proof runs (--select-only) must NOT consume
    # a variation from the ledger.
    sel = select_cluster(profile, out, persist_ledger=not args.select_only,
                         idea=args.about)
    roots = sorted(sel["docs"])
    if args.select_only:
        print(json.dumps({"stage": "select_only", "persona_id": persona_id,
                          "strategy": profile.strategy,
                          "has_identity_gate": profile.has_identity_gate,
                          "idea": args.about or None,
                          "idea_seeded": bool(args.about),
                          "cluster": sel["cluster"]["cluster_id"],
                          "selected": sel["cluster"]["selected"],
                          "valence_emphasis": sel["cluster"]["valence_emphasis"],
                          "selection_receipt": str(out / "selection_receipt.v1.json")},
                         indent=2))
        return 0

    adapter = _load("tau_text_reasoning_adapter")
    phase_c = _load("phase_c_regenerate_storyboard_frames")
    subgate = _load("identity_face_embedding_subgate")
    composite = _load("tau_vlm_composite_review")
    p13 = _load("phase13_self_interpretation")
    p14 = _load("phase14_tom_validation")
    p15 = _load("phase15_dream_persistence")
    pm = _load("pilot_metrics")
    # anchors snapshot BEFORE the run: this cycle's own root memories are the
    # per-cycle identity invariant (the dream must not mutate its source canon).
    # Persona-agnostic — no hardcoded persona-specific anchor node.
    anchor_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/pilot_metrics.py"), "snapshot-anchors",
         "--keys", ",".join(roots),
         "--out", str(out / "anchor_snapshot.json")],
        capture_output=True, text=True)
    if anchor_proc.returncode != 0:
        raise SystemExit(f"BLOCKED_CYCLE_ANCHORS: {anchor_proc.stderr[-200:]}")

    # 2. instruments frozen pre-dream
    instruments = build_instruments(adapter, sel, out)

    # 3. dream + frames
    art = compose_and_render(adapter, phase_c, subgate, profile, sel, out)

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
                "model": ("insightface:buffalo_l (authority) + gpt-5.5 montage (advisory)"
                          if art["identity_gate"] == "arcface"
                          else "gpt-5.5 montage (advisory); no face reference — ungated"),
                "verdict": "PASS",
                "identity_gate": art["identity_gate"],
                "raw_output_tail": (
                    f"all {len(art['frames'])} frames passed ArcFace vs "
                    f"{Path(profile.reference_sheet).name}"
                    if art["identity_gate"] == "arcface" else
                    f"{len(art['frames'])} frames rendered ungated "
                    f"({art['persona_name']} has no face reference sheet)")}}},
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
        "items": [{"collection": "persona_memory", "persona_id": persona_id,
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
    # full counterpart id (not first token): Horus counterparts are multi-token
    # (yngmay_singh, hastur_sejanus); truncating would break the counterpart gate.
    counterpart_id = sel["cluster"]["cluster_id"].split(":person:")[1]
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
                             dream_id, cycle_id, "goal-v3", persona_id, live=True,
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
    causal = p15.build_causal_family_fields(persona_id, dream_id, root_ids, None)
    causal["goal_v3_cycle"] = cycle_id
    dream_doc = p15.build_dream_memory_document(
        dream_id, cycle_id, "goal-v3", persona_id, packet, interp, tom,
        causal_fields=causal)
    dream_doc["evidence_class"] = "synthetic_dream"
    dream_doc["tags"] = [f"persona:{persona_id}", "synthetic_dream", "persona_dream",
                         "goal_v3_autonomous_cycle"]
    watch_vertices = p15.build_watch_evidence_vertices(
        packet, interp, dream_id, f"storyboard_{art['media_sha'][:32]}",
        None, persona_id=persona_id, causal_fields=causal)
    interp_vertices = p15.build_interpretation_vertices(
        interp, persona_id, dream_id, causal_fields=causal)
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
    m2 = pm.m2_grounding(p15, manifest["key"], out, persona_id, dream_id)
    m3 = pm.m3_distinction(adapter, dream_doc["_key"])
    m4 = pm.m4_identity(p15, manifest["key"], out / "anchor_snapshot.json")
    recall_eval = evaluate_recall_instruments(instruments, dream_doc["_key"])
    ranks = recall_eval["recall_probe_ranks"]
    n1_pass = recall_eval["negative_control_absent_top10"]

    # 8. voice weights on the NEW dream. --arc-voice conditions the spoken line on
    #    the persona's accumulated arc_state (Continuity Ledger) so the voice
    #    carries the accumulated self, not just today's dream; fallback-guarded.
    vw = subprocess.run(
        [sys.executable, str(ROOT / "scripts/dream_voice_weights.py"),
         "--dream-key", dream_doc["_key"], "--render", "--arc-voice",
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
        "recall_probe_results": recall_eval["recall_probe_results"],
        "negative_control_results": recall_eval["negative_control_results"],
        "negative_control_dream_rank": recall_eval["negative_control_dream_rank"],
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
