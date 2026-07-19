#!/usr/bin/env python3
"""Frozen R1/R2 root-set selection for the C-vs-F pilot (protocol v3).

Implements EXACTLY the selection rules frozen in
contracts/pilot_c_vs_f_frozen_protocol.v3.md ("Root sets, order, and
blinding"). Summary of the frozen rules (the protocol text is authoritative):

- cluster := Embry root memories within one biographical age band sharing a
  person:<x> tag, x != Embry herself.
- eligibility: (a) every member ingested_at present, ISO-8601-parseable, and
  strictly before 2026-07-01T00:00:00Z — missing/unparseable on ANY candidate
  root fails the whole selection closed; (b) no member id overlaps dream-004's
  source_memory_ids (read live from the canonical dream node); (c) >= 3
  members.
- ordering: age-band recency (age23_current first), then within a band by
  SHA256(seed || cluster_id) ascending, where seed = sha256 of the protocol
  file content BEFORE the addendum. No size preference.
- R1 = first passing cluster; R2 = next cluster in the SAME original order
  whose FULL member set is disjoint from R1's FULL member set.
- member cap: exactly 3 members per selected cluster, the lowest
  SHA256(seed || member_record_sha256) ascending; member_record_sha256 =
  sha256 of the record's sorted-key JSON excluding system fields other than
  _key. All candidate member scores recorded.

--append-addendum (one-time) appends the receipt to the v3 protocol file and
writes contracts/pilot_r1_r2_selection_addendum.v1.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"
PROTOCOL = ROOT / "contracts/pilot_c_vs_f_frozen_protocol.v3.md"
ADDENDUM_JSON = ROOT / "contracts/pilot_r1_r2_selection_addendum.v1.json"
ADDENDUM_MARKER = "## Addendum: R1/R2 selection receipt"
DREAM_NODE_KEY = "dream_dream_successor_943b01ecd9a3"
INGEST_CUTOFF = "2026-07-01T00:00:00Z"
AGE_BAND_RECENCY = ["age23_current", "age19_23", "age15_19", "age10_15", "age04_10"]
SELF_TAGS = {"person:embry", "person:embry_lawson"}
MIN_MEMBERS = 3
MEMBER_CAP = 3


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{GMO}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def protocol_seed() -> str:
    """sha256 of the protocol text BEFORE any addendum."""
    text = PROTOCOL.read_text()
    if ADDENDUM_MARKER in text:
        text = text[: text.index(ADDENDUM_MARKER)].rstrip() + "\n"
    return sha256_text(text)


def fetch_embry_docs() -> list[dict]:
    docs: list[dict] = []
    offset = 0
    while True:
        page = post("/list", {"collection": "persona_memory",
                              "filters": {"persona_id": "embry"},
                              "limit": 100, "offset": offset})
        docs += page.get("documents", [])
        offset += 100
        if offset >= page.get("total", 0):
            break
    return docs


def band_of(key: str) -> str | None:
    m = re.match(r"embry_(age[0-9_a-z]+?)_b\d+_memory_\d+$", key)
    return m.group(1) if m else None


def parse_ts(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def record_sha(doc: dict) -> str:
    slim = {k: v for k, v in doc.items() if not k.startswith("_") or k == "_key"}
    return sha256_text(json.dumps(slim, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--append-addendum", action="store_true",
                        help="append the selection addendum to the v3 protocol "
                             "and write the addendum receipt JSON (one-time)")
    args = parser.parse_args()

    seed = protocol_seed()
    docs = fetch_embry_docs()
    roots = {d["_key"]: d for d in docs if re.match(r"embry_age\d", d["_key"])}
    if not roots:
        print("BLOCKED_PILOT_SELECTION_NO_ROOTS", file=sys.stderr)
        return 2

    # rule (a): strict timestamps, fail closed on ANY candidate root.
    cutoff = parse_ts(INGEST_CUTOFF)
    bad_ts = {}
    for key, doc in roots.items():
        ts = parse_ts(doc.get("ingested_at"))
        if ts is None:
            bad_ts[key] = f"missing/unparseable: {doc.get('ingested_at')!r}"
        elif not (ts < cutoff):
            bad_ts[key] = f"not before cutoff: {doc.get('ingested_at')}"
    if bad_ts:
        print(f"BLOCKED_PILOT_SELECTION_TIMESTAMPS: {dict(list(bad_ts.items())[:5])}",
              file=sys.stderr)
        return 2

    dream_node = post("/list", {"collection": "persona_memory",
                                "filters": {"_key": DREAM_NODE_KEY}, "limit": 1})
    dream_docs = dream_node.get("documents", [])
    if len(dream_docs) != 1:
        print("BLOCKED_PILOT_SELECTION_DREAM004_NODE_MISSING", file=sys.stderr)
        return 2
    dream4_sources = set(dream_docs[0].get("source_memory_ids") or [])
    if not dream4_sources:
        print("BLOCKED_PILOT_SELECTION_DREAM004_SOURCES_EMPTY", file=sys.stderr)
        return 2

    # cluster ontology
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, doc in roots.items():
        band = band_of(key)
        if band is None:
            continue
        for tag in doc.get("tags") or []:
            if tag.startswith("person:") and tag not in SELF_TAGS:
                groups[(band, tag)].add(key)

    candidates = []
    for (band, tag), members in groups.items():
        cluster_id = f"{band}:{tag}"
        eligible = (not (members & dream4_sources)) and len(members) >= MIN_MEMBERS
        candidates.append({
            "cluster_id": cluster_id,
            "age_band": band,
            "person_tag": tag,
            "members_full": sorted(members),
            "order_hash": sha256_text(seed + cluster_id),
            "eligible": eligible,
        })
    # frozen ordering: band recency, then seeded hash ascending; NO size term.
    candidates.sort(key=lambda c: (AGE_BAND_RECENCY.index(c["age_band"]),
                                   c["order_hash"]))
    eligible = [c for c in candidates if c["eligible"]]
    if not eligible:
        print("BLOCKED_PILOT_SELECTION_NO_QUALIFYING_CLUSTERS", file=sys.stderr)
        return 2
    r1 = eligible[0]
    r1_members = set(r1["members_full"])
    r2 = next((c for c in eligible[1:]
               if not (set(c["members_full"]) & r1_members)), None)
    if r2 is None:
        print("BLOCKED_PILOT_SELECTION_NO_DISJOINT_SECOND_CLUSTER", file=sys.stderr)
        return 2

    def cap_members(cluster: dict) -> dict:
        scored = sorted(
            ({"member": k,
              "record_sha256": record_sha(roots[k]),
              "score": sha256_text(seed + record_sha(roots[k]))}
             for k in cluster["members_full"]),
            key=lambda s: s["score"])
        return {"selected": [s["member"] for s in scored[:MEMBER_CAP]],
                "all_scores": scored}

    r1_cap = cap_members(r1)
    r2_cap = cap_members(r2)

    receipt = {
        "schema": "persona_dream.pilot_r1_r2_selection_addendum.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol_path": str(PROTOCOL.relative_to(ROOT)),
        "protocol_seed_sha256_pre_addendum": seed,
        "selection_script_sha256": sha256_text(Path(__file__).read_text()),
        "frozen_rules_reference": "pilot_c_vs_f_frozen_protocol.v3.md#root-sets-order-and-blinding",
        "ingest_cutoff": INGEST_CUTOFF,
        "dream_004_excluded_sources": sorted(dream4_sources),
        "candidate_clusters": [
            {k: c[k] for k in ("cluster_id", "order_hash", "eligible")}
            | {"member_count": len(c["members_full"])}
            for c in candidates
        ],
        "r1": {
            "set_id": r1["cluster_id"],
            "members_full": r1["members_full"],
            "members_selected": r1_cap["selected"],
            "member_scores": r1_cap["all_scores"],
            "members_selected_sha256": sha256_text(json.dumps(r1_cap["selected"])),
        },
        "r2": {
            "set_id": r2["cluster_id"],
            "members_full": r2["members_full"],
            "members_selected": r2_cap["selected"],
            "member_scores": r2_cap["all_scores"],
            "members_selected_sha256": sha256_text(json.dumps(r2_cap["selected"])),
        },
        "full_sets_disjoint": not (set(r1["members_full"]) & set(r2["members_full"])),
        "member_cap": MEMBER_CAP,
    }
    print(json.dumps({
        "seed": seed[:16],
        "candidates": len(candidates),
        "eligible": len(eligible),
        "r1": {"set_id": receipt["r1"]["set_id"],
               "selected": receipt["r1"]["members_selected"],
               "sha256": receipt["r1"]["members_selected_sha256"]},
        "r2": {"set_id": receipt["r2"]["set_id"],
               "selected": receipt["r2"]["members_selected"],
               "sha256": receipt["r2"]["members_selected_sha256"]},
        "full_sets_disjoint": receipt["full_sets_disjoint"],
    }, indent=2))

    if not args.append_addendum:
        return 0

    protocol_text = PROTOCOL.read_text()
    if ADDENDUM_MARKER in protocol_text:
        print("BLOCKED_PILOT_SELECTION_ADDENDUM_ALREADY_APPENDED", file=sys.stderr)
        return 2
    ADDENDUM_JSON.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    addendum = (
        f"\n{ADDENDUM_MARKER} (appended before first run)\n\n"
        f"- Receipt: `contracts/{ADDENDUM_JSON.name}` "
        f"(sha256:{sha256_text(ADDENDUM_JSON.read_text())})\n"
        f"- Protocol seed (pre-addendum sha256): {seed}\n"
        f"- Selection script sha256: {receipt['selection_script_sha256']}\n"
        f"- R1: `{receipt['r1']['set_id']}` — members "
        f"{', '.join(receipt['r1']['members_selected'])} "
        f"(sha256 {receipt['r1']['members_selected_sha256']})\n"
        f"- R2: `{receipt['r2']['set_id']}` — members "
        f"{', '.join(receipt['r2']['members_selected'])} "
        f"(sha256 {receipt['r2']['members_selected_sha256']})\n"
    )
    PROTOCOL.write_text(protocol_text + addendum)
    print(f"addendum appended to {PROTOCOL.name}; receipt at {ADDENDUM_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
