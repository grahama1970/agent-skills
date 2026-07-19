#!/usr/bin/env python3
"""Frozen R1/R2 root-set selection for the C-vs-F pilot (protocol v2).

Protocol rule (verbatim): the two most-recent Embry residue clusters in Memory
that (a) predate this protocol's commit, (b) share no source-memory id with
dream-004, (c) contain >= 3 source memories. Selection executed by script with
these three rules only; the script output (set ids + hashes) is appended to the
protocol file as an addendum receipt BEFORE the first run.

Operationalization (disclosed, deterministic — the store cannot discriminate
"most-recent" by write time):

- Measured fact: every Embry root memory in persona_memory shares one
  ingestion timestamp (2026-06-19T16:02:36Z, single bulk ingest), and the only
  explicit graph_edges component is inside embry_age04_10_b01. Store-time
  recency is therefore degenerate and cannot order clusters.
- "Residue cluster" := the set of root memories within one biographical age
  band that share a person:<x> tag (x != Embry herself). Person-anchored
  co-occurrence is the same relational-residue notion dream-004's residue
  used (its three sources share person:kai).
- "Most-recent" := persona-biographical recency of the age band
  (age23_current > age19_23 > age15_19 > age10_15 > age04_10), then larger
  cluster, then lexicographic tag. R1 = first cluster passing all three
  protocol rules; its members are then removed and R2 = next passing cluster
  (disjointness enforced so the two arms never share a source memory).

Everything above is frozen by this file's content hash, recorded in the
selection receipt.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"
PROTOCOL = ROOT / "contracts/pilot_c_vs_f_frozen_protocol.v2.md"
ADDENDUM_JSON = ROOT / "contracts/pilot_r1_r2_selection_addendum.v1.json"
DREAM_NODE_KEY = "dream_dream_successor_943b01ecd9a3"
PROTOCOL_FROZEN_DATE = "2026-07-19"
AGE_BAND_RECENCY = ["age23_current", "age19_23", "age15_19", "age10_15", "age04_10"]
SELF_TAGS = {"person:embry", "person:embry_lawson"}
MIN_MEMBERS = 3


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{GMO}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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


def build_clusters(roots: dict[str, dict], excluded: set[str]) -> list[dict]:
    """All (age_band, person tag) clusters, protocol rules applied, ranked."""
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, doc in roots.items():
        band = band_of(key)
        if band is None:
            continue
        for tag in doc.get("tags") or []:
            if tag.startswith("person:") and tag not in SELF_TAGS:
                groups[(band, tag)].add(key)
    clusters = []
    for (band, tag), members in groups.items():
        if members & excluded:            # rule (b)
            continue
        if len(members) < MIN_MEMBERS:    # rule (c)
            continue
        clusters.append({
            "cluster_id": f"{band}:{tag}",
            "age_band": band,
            "person_tag": tag,
            "members": sorted(members),
        })
    clusters.sort(key=lambda c: (AGE_BAND_RECENCY.index(c["age_band"]),
                                 -len(c["members"]), c["person_tag"]))
    return clusters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--append-addendum", action="store_true",
                        help="append the selection addendum to the protocol file "
                             "and write the addendum receipt JSON (one-time)")
    args = parser.parse_args()

    docs = fetch_embry_docs()
    roots = {d["_key"]: d for d in docs if re.match(r"embry_age\d", d["_key"])}
    if not roots:
        print("BLOCKED_PILOT_SELECTION_NO_ROOTS", file=sys.stderr)
        return 2

    # rule (a): every candidate must predate the protocol freeze date.
    stale = {k: str(v.get("ingested_at")) for k, v in roots.items()
             if not (str(v.get("ingested_at") or "") < PROTOCOL_FROZEN_DATE)}
    if stale:
        print(f"BLOCKED_PILOT_SELECTION_POSTDATED_ROOTS: {sorted(stale)[:5]}",
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

    clusters = build_clusters(roots, dream4_sources)
    if not clusters:
        print("BLOCKED_PILOT_SELECTION_NO_QUALIFYING_CLUSTERS", file=sys.stderr)
        return 2
    r1 = clusters[0]
    remaining = {k: v for k, v in roots.items() if k not in set(r1["members"])}
    clusters_after_r1 = build_clusters(remaining, dream4_sources)
    if not clusters_after_r1:
        print("BLOCKED_PILOT_SELECTION_NO_SECOND_CLUSTER", file=sys.stderr)
        return 2
    r2 = clusters_after_r1[0]

    script_text = Path(__file__).read_text()
    protocol_text = PROTOCOL.read_text()
    receipt = {
        "schema": "persona_dream.pilot_r1_r2_selection_addendum.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol_path": str(PROTOCOL.relative_to(ROOT)),
        "protocol_sha256_before_addendum": sha256_text(protocol_text),
        "selection_script_sha256": sha256_text(script_text),
        "frozen_rules": {
            "a_predate_protocol_commit": f"all root ingested_at < {PROTOCOL_FROZEN_DATE} (verified)",
            "b_no_dream004_source_overlap": sorted(dream4_sources),
            "c_min_source_memories": MIN_MEMBERS,
        },
        "operationalization_disclosure": {
            "store_time_recency_degenerate": "all 312 embry root memories share one bulk ingestion timestamp; graph_edges components exist only inside embry_age04_10_b01",
            "residue_cluster": "root memories in one age band sharing a person:<x> tag, x != Embry (person-anchored residue, same relational notion as dream-004's kai-anchored residue)",
            "most_recent": "persona-biographical age-band recency, then larger cluster, then lexicographic person tag; R1's members removed before R2 selection (disjoint arms)",
        },
        "candidate_cluster_count": len(clusters),
        "r1": {
            "set_id": r1["cluster_id"],
            "member_count": len(r1["members"]),
            "members": r1["members"],
            "members_sha256": sha256_text(json.dumps(r1["members"])),
        },
        "r2": {
            "set_id": r2["cluster_id"],
            "member_count": len(r2["members"]),
            "members": r2["members"],
            "members_sha256": sha256_text(json.dumps(r2["members"])),
        },
        "disjoint": not (set(r1["members"]) & set(r2["members"])),
    }
    print(json.dumps({k: receipt[k] for k in
                      ("candidate_cluster_count", "disjoint")}
                     | {"r1": {"set_id": receipt["r1"]["set_id"],
                               "member_count": receipt["r1"]["member_count"],
                               "members_sha256": receipt["r1"]["members_sha256"]},
                        "r2": {"set_id": receipt["r2"]["set_id"],
                               "member_count": receipt["r2"]["member_count"],
                               "members_sha256": receipt["r2"]["members_sha256"]}},
                     indent=2))

    if not args.append_addendum:
        return 0

    if "## Addendum: R1/R2 selection receipt" in protocol_text:
        print("BLOCKED_PILOT_SELECTION_ADDENDUM_ALREADY_APPENDED", file=sys.stderr)
        return 2
    ADDENDUM_JSON.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    addendum = (
        "\n## Addendum: R1/R2 selection receipt (appended before first run)\n\n"
        f"- Receipt: `contracts/{ADDENDUM_JSON.name}` "
        f"(sha256:{sha256_text(ADDENDUM_JSON.read_text())})\n"
        f"- Selection script sha256: {receipt['selection_script_sha256']}\n"
        f"- R1: `{receipt['r1']['set_id']}` — {receipt['r1']['member_count']} members, "
        f"members sha256 {receipt['r1']['members_sha256']}\n"
        f"- R2: `{receipt['r2']['set_id']}` — {receipt['r2']['member_count']} members, "
        f"members sha256 {receipt['r2']['members_sha256']}\n"
        "- Disclosed deviation: store-write recency is degenerate (single bulk\n"
        "  ingest), so \"most-recent\" is operationalized as persona-biographical\n"
        "  age-band recency; full disclosure lives in the receipt JSON.\n"
    )
    PROTOCOL.write_text(protocol_text + addendum)
    print(f"addendum appended to {PROTOCOL.name}; receipt at {ADDENDUM_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
