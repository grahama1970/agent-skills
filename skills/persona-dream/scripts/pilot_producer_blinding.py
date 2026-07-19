#!/usr/bin/env python3
"""Producer-blinding receipt for the C-vs-F pilot (protocol v2).

Protocol requirement: the agents executing C and F receive the cognition
contract and root set ONLY — never the protocol, the probes, or the metrics.
"Enforced by prompt-content receipt (hash of everything shown to the producer,
checked against a probe-string denylist)."

This tool takes the EXACT files that will be (or were) shown to a producer,
hashes each and the concatenation, and scans every byte against the frozen
denylist below. Any hit fails closed — no receipt, exit 2. A clean scan writes
persona_dream.pilot_producer_blinding_receipt.v1 next to --out.

The denylist is frozen with this file (its sha256 is recorded in the receipt):
the v1/v2 probe texts, the M-metric vocabulary, protocol file names, and the
decision-rule phrasing. Case-insensitive substring match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

DENYLIST = [
    # M1 probes (frozen v1 text, reused by v2)
    "a time someone's caution changed what she decided without deciding for her",
    "feeling pulled between what she owed people and what she wanted for herself",
    "a moment where waiting was the stronger choice",
    "orbital telemetry calibration procedures",
    # M3 probe
    "did that actually happen?",
    # metric / protocol vocabulary a producer must never see
    "m1 recall",
    "m2 grounding",
    "m3 distinction",
    "m4 identity",
    "m5 blind read",
    "blind read",
    "negative control",
    "decision rule",
    "pilot_c_vs_f_frozen_protocol",
    "frozen protocol",
    "pre-registered outcome",
    "states the central conflict more precisely",
    "reveals something the other does not",
    "over-interprets",
    "producer blinding",
    "probe-string denylist",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--producer-role", required=True,
                        help="e.g. C:R1, F:R2 — which arm/set this producer runs")
    parser.add_argument("--shown-file", type=Path, action="append", required=True,
                        help="a file whose full content is shown to the producer; repeatable")
    parser.add_argument("--out", type=Path, required=True,
                        help="receipt output path (json)")
    args = parser.parse_args()

    files = []
    violations = []
    concat = hashlib.sha256()
    for path in args.shown_file:
        if not path.exists():
            print(f"BLOCKED_PILOT_BLINDING_SHOWN_FILE_MISSING: {path}", file=sys.stderr)
            return 2
        data = path.read_bytes()
        concat.update(data)
        lowered = data.decode(errors="replace").lower()
        hits = sorted({needle for needle in DENYLIST if needle.lower() in lowered})
        if hits:
            violations.append({"file": str(path), "denylist_hits": hits})
        files.append({"path": str(path), "sha256": sha256_bytes(data), "bytes": len(data)})

    if violations:
        print("BLOCKED_PILOT_BLINDING_DENYLIST_HIT", file=sys.stderr)
        print(json.dumps(violations, indent=2), file=sys.stderr)
        return 2

    receipt = {
        "schema": "persona_dream.pilot_producer_blinding_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "producer_role": args.producer_role,
        "shown_files": files,
        "shown_concat_sha256": concat.hexdigest(),
        "denylist_sha256": sha256_bytes(json.dumps(DENYLIST, sort_keys=True).encode()),
        "denylist_entries": len(DENYLIST),
        "blinding_tool_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "verdict": "BLINDED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"verdict": "BLINDED", "producer_role": args.producer_role,
                      "shown_concat_sha256": receipt["shown_concat_sha256"],
                      "receipt": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
