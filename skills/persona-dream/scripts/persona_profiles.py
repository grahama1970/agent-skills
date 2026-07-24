#!/usr/bin/env python3
"""Persona profiles — make persona-dream work with ANY persona, nothing hardcoded.

The dream cycle was hardcoded to Embry: her key schema, age-band recency,
`person:` counterpart tags, emotion-valence conflict, and face reference sheet.
A different persona (e.g. horus_lupercal) has a different corpus schema —
book_id, entities.people counterparts, tom_state_type=unresolved_thread +
contradiction_risks as the conflict signal, and no face sheet.

Rather than bake in a per-persona registry, a profile is DISCOVERED at runtime
from (a) the persona's own memory documents and (b) the filesystem:

  - self identity  -> token match against persona_id (no alias lists)
  - counterparts   -> whichever field the corpus exposes (tags OR entities.people)
  - conflict signal-> emotion valence if present, else unresolved-thread + risks
  - recency band   -> age band if the keys carry one, else book_id, ordered by a
                      value derived from the bands present (numeric age desc; else
                      timeline_order / salience)
  - reference sheet-> globbed from the persona media root (None if absent)
  - selector       -> DETECTED from corpus shape, not from persona identity

Adding a persona requires no code change. Pure derivation + predicates over the
docs already fetched; the only filesystem read is the reference-sheet glob.
Deterministic.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# Environment config (NOT a per-persona constant): where persona media lives.
MEDIA_ROOT = Path(os.environ.get(
    "PERSONA_MEDIA_ROOT", "/mnt/storage12tb/media/personas"))

# Valence lexicon for corpora that expose an `emotion` field.
POS = {"trust", "longing", "pride", "relief"}
NEG = {"grief", "guilt", "fear", "anger", "shame", "uncertainty"}

_AGE_KEY = re.compile(r"_age(\d+)")


def _tid(person_tag: str) -> str:
    return person_tag.split("person:", 1)[-1]


def _as_list(v) -> list[str]:
    """Normalize a field that may be a list, a comma string, or a scalar."""
    if isinstance(v, list):
        return [str(x) for x in v]
    if v is None:
        return []
    return [s for s in str(v).split(",")]


@dataclass
class PersonaProfile:
    persona_id: str
    strategy: str                 # "age_band_counterpart" | "generic"
    reference_sheet: Path | None
    band_recency: list[str]

    @property
    def has_identity_gate(self) -> bool:
        return self.reference_sheet is not None and self.reference_sheet.exists()

    # --- self identity (derived, no alias list) ----------------------------
    def is_self_tag(self, person_tag: str) -> bool:
        t = _tid(person_tag)
        pid = self.persona_id
        return (t == pid or pid.startswith(t + "_") or t.startswith(pid + "_")
                or t.split("_")[0] == pid.split("_")[0])

    # --- corpus predicates the selector engine calls -----------------------
    def roots(self, docs: list[dict]) -> dict[str, dict]:
        if self.strategy == "age_band_counterpart":
            return {d["_key"]: d for d in docs
                    if d.get("_key") and _AGE_KEY.search(d["_key"])}
        return {d["_key"]: d for d in docs if d.get("_key")}

    def band(self, key: str, doc: dict) -> str | None:
        if self.strategy == "age_band_counterpart":
            m = re.match(r".+_(age[0-9_a-z]+?)_b\d+_memory_\d+$", key)
            return m.group(1) if m else None
        b = doc.get("book_id") or doc.get("source_work")
        return str(b) if b else None

    def counterparts(self, doc: dict) -> set[str]:
        if self.strategy == "age_band_counterpart":
            cands = [t for t in (doc.get("tags") or [])
                     if isinstance(t, str) and t.startswith("person:")]
        else:
            cands = [p for p in ((doc.get("entities") or {}).get("people") or [])
                     if isinstance(p, str) and p.startswith("person:")]
        return {t for t in cands if not self.is_self_tag(t)}

    def recency_index(self, band: str) -> int:
        return (self.band_recency.index(band)
                if band in self.band_recency else len(self.band_recency))

    def conflict_score(self, doc: dict) -> tuple:
        if self.strategy == "age_band_counterpart":
            e = {x.strip() for x in _as_list(doc.get("emotion")) if str(x).strip()}
            return ((len(e & POS) > 0) + (len(e & NEG) > 0), len(e))
        # Generic corpora (e.g. horus_lupercal) under-state explicit emotion, so
        # the conflict lives in HELD TENSION: an unresolved-thread ToM state,
        # explicit contradiction_risks, and ambivalence (a primary vs a distinct
        # secondary emotional_context state). Rank by how conflicted, not how
        # emotive — a full character's conflict, not stoicism.
        unresolved = 1 if "unresolved_thread" in _as_list(doc.get("tom_state_type")) else 0
        risks = doc.get("contradiction_risks") or []
        n = len(risks) if isinstance(risks, list) else 0
        ec = doc.get("emotional_context") or {}
        ambivalent = 0
        if isinstance(ec, dict):
            p = str(ec.get("primary_state") or "").strip().lower()
            s = str(ec.get("secondary_state") or "").strip().lower()
            skip = {"", "not stated in source"}
            if p not in skip and s not in skip and p != s:
                ambivalent = 1
        return (unresolved + (1 if n else 0) + ambivalent, n + ambivalent)

    def edges(self, doc: dict) -> list[str]:
        """Raw inline edge targets AS STORED (schema-specific): Embry keys
        memory->memory (target_memory_id/target_id); the generic corpus keys
        memory->entity (to_id -> person:/object:/event:). Kept for provenance;
        cross-schema traversal goes through entities_of (below), not this."""
        out = []
        if self.strategy == "age_band_counterpart":
            for e in (doc.get("graph_edges_raw") or []):
                if isinstance(e, dict):
                    # BOTH conventions: half key targets as target_memory_id,
                    # half as target_id; reading one drops the other half.
                    t = e.get("target_memory_id") or e.get("target_id")
                    if t:
                        out.append(t)
        else:
            for e in (doc.get("graph_edges") or []):
                if isinstance(e, dict):
                    t = (e.get("to_id") or e.get("target_id")
                         or e.get("target_memory_id"))
                    if t:
                        out.append(t)
        return out

    def entities_of(self, doc: dict) -> set[str]:
        """Schema-agnostic entity references (the UNIVERSAL traversal bridge).
        Inline memory->memory edges differ per corpus and don't cross personas;
        the entity graph is shared, so multi-hop is memory -> entity -> memory.
        Embry: `person:` tags. Generic: the entities dict (people/places/objects/
        organizations/factions/events). Self is excluded so a hop is associative,
        not a self-loop."""
        ents: set[str] = set()
        if self.strategy == "age_band_counterpart":
            ents |= {t for t in (doc.get("tags") or [])
                     if isinstance(t, str) and t.startswith("person:")}
        ent = doc.get("entities") or {}
        if isinstance(ent, dict):
            for vals in ent.values():
                if isinstance(vals, list):
                    ents |= {v for v in vals if isinstance(v, str)}
        return {e for e in ents if not self.is_self_tag(e)}

    def affect_keys(self, doc: dict) -> set[str]:
        """Schema-agnostic AFFECT/ToM bridge keys — the connector that links the
        emotional states of DIFFERENT personas. Named entities never overlap
        across fictional worlds (SPARTA vs 40k), but affect does: both hold
        `tom:unresolved_thread`, `emotion:fear`, `tom:boundary`, etc. Multi-hop
        over these keys is how Embry's and Horus's inner states connect."""
        keys: set[str] = set()
        for t in _as_list(doc.get("tom_state_type")):
            t = t.strip().lower()
            if t:
                keys.add("tom:" + t)
        for e in _as_list(doc.get("emotion")):
            e = e.strip().lower()
            if e and e != "not stated in source":
                keys.add("emotion:" + e)
        ec = doc.get("emotional_context")
        if isinstance(ec, dict):
            for k in ("primary_state", "secondary_state"):
                s = str(ec.get(k) or "").strip().lower()
                if s and s != "not stated in source":
                    keys.add("emotion:" + s)
        for tag in (doc.get("tags") or []):
            if isinstance(tag, str) and tag.startswith("tom:"):
                keys.add(tag.strip().lower())
        return keys

    def intra_neighbors(self, key: str, doc: dict, members: set[str],
                        entity_index: dict[str, set[str]]) -> list[str]:
        """Neighbors of a root WITHIN a cluster, for the deterministic walk.
        Age strategy uses the inline memory->memory edges (unchanged, proven).
        Generic strategy is entity-mediated: members sharing an entity."""
        if self.strategy == "age_band_counterpart":
            return [t for t in self.edges(doc) if t in members]
        neigh: set[str] = set()
        for ent in self.entities_of(doc):
            neigh |= entity_index.get(ent, set())
        return sorted(m for m in neigh if m in members and m != key)


def _detect_strategy(docs: list[dict]) -> str:
    """Age-band strategy iff the corpus actually carries age-keyed memories with
    an emotion field; otherwise the generic book/entity/ToM strategy."""
    age_keyed = sum(1 for d in docs[:200] if _AGE_KEY.search(d.get("_key") or ""))
    has_emotion = any(str(d.get("emotion") or "").strip() for d in docs[:200])
    return "age_band_counterpart" if (age_keyed and has_emotion) else "generic"


def _derive_band_recency(strategy: str, docs: list[dict]) -> list[str]:
    """Order the bands present most-recent-first, derived from the data — not a
    hardcoded list. Only a tie-break in cluster ordering."""
    if strategy == "age_band_counterpart":
        bands = {m.group(1) for d in docs
                 if (m := re.match(r".+_(age[0-9_a-z]+?)_b\d+_memory_\d+$",
                                   d.get("_key") or ""))}

        def age_of(b):  # higher age = more recent
            n = _AGE_KEY.search("_" + b)
            return int(n.group(1)) if n else -1
        return sorted(bands, key=age_of, reverse=True)
    # generic: books ordered by most-recent timeline_order, then salience (count)
    counts, tmax = {}, {}
    for d in docs:
        b = d.get("book_id") or d.get("source_work")
        if not b:
            continue
        counts[b] = counts.get(b, 0) + 1
        to = d.get("timeline_order")
        if isinstance(to, (int, float)):
            tmax[b] = max(tmax.get(b, to), to)
    return sorted(counts, key=lambda b: (tmax.get(b, 0), counts[b]), reverse=True)


def _discover_reference_sheet(persona_id: str) -> Path | None:
    """Discover a face reference for the ArcFace identity gate from the persona
    media root (None if absent). Two asset conventions: an explicit
    *contact_sheet*.png (Embry), or a dream cast identity_pack front/three_quarter
    face (Horus's first dream shipped cast/HORUS/identity_pack/front.png). Identity
    packs are matched to THIS persona by path token so a counterpart's pack (e.g.
    SANGUINIUS) is never mistaken for the dreamer's face."""
    short = persona_id.split("_")[0].lower()
    tokens = {persona_id.lower(), short}
    face_rank = {"front.png": 0, "three_quarter.png": 1, "full_body.png": 2}
    for base in {persona_id, short}:
        root = MEDIA_ROOT / base
        if not root.exists():
            continue
        cs = sorted(root.rglob("*contact_sheet*.png"))
        if cs:
            return cs[-1]
        packs = []
        for p in root.rglob("*.png"):
            parts = {x.lower() for x in p.parts}
            if "identity_pack" in parts and p.name in face_rank \
                    and any(t in " ".join(x.lower() for x in p.parts) for t in tokens):
                packs.append(p)
        if packs:
            return sorted(packs, key=lambda p: (face_rank[p.name], str(p)))[0]
    return None


def build_profile(persona_id: str, docs: list[dict]) -> PersonaProfile:
    strategy = _detect_strategy(docs)
    return PersonaProfile(
        persona_id=persona_id,
        strategy=strategy,
        reference_sheet=_discover_reference_sheet(persona_id),
        band_recency=_derive_band_recency(strategy, docs),
    )


if __name__ == "__main__":
    import json
    import sys
    import urllib.request

    pid = sys.argv[1] if len(sys.argv) > 1 else "embry"
    gmo = os.environ.get("GMO", "http://127.0.0.1:8601")
    d, off = [], 0
    while True:
        req = urllib.request.Request(
            f"{gmo}/list", headers={"Content-Type": "application/json"},
            data=json.dumps({"collection": "persona_memory",
                             "filters": {"persona_id": pid},
                             "limit": 100, "offset": off}).encode())
        page = json.loads(urllib.request.urlopen(req, timeout=30).read())
        d += page.get("documents", [])
        off += 100
        if off >= page.get("total", 0):
            break
    p = build_profile(pid, d)
    print(json.dumps({"persona_id": p.persona_id, "docs": len(d),
                      "strategy": p.strategy,
                      "reference_sheet": str(p.reference_sheet),
                      "has_identity_gate": p.has_identity_gate,
                      "band_recency": p.band_recency}, indent=2))
