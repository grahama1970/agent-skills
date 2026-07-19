#!/usr/bin/env python3
"""Deterministic modality-trace redaction for M5 claims (protocol v3).

The frozen protocol requires the operator to receive interpretation text
"stripped of evidence_class, artifact paths, modality traces". The frozen
pilot_m5_presentation.py leak gate FAILS CLOSED on such traces (it never
scrubs). This unfrozen preprocessing step performs the stripping the protocol
mandates, mechanically and identically for BOTH arms:

- a fixed, published word-map replaces overt pipeline/modality terms with
  neutral placeholders;
- every replacement (claim index, span, before, after) is recorded in a
  redaction receipt with before/after content hashes;
- the output must still pass the frozen leak gate — the gate remains the
  authority; this tool only prepares its input.

The map is fixed in this file. Applying it to C claims (which normally
contain no traces) is a no-op recorded as zero replacements — symmetry is
part of the design and is auditable from the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

REDACTION_MAP = [
    (re.compile(r"\bidentity[- ]continuity (?:pass|review|check)\b", re.I), "the consistent recurring figure"),
    (re.compile(r"\bacross all frames\b", re.I), "throughout the dream"),
    (re.compile(r"\bin (?:each|every) frame\b", re.I), "throughout the dream"),
    (re.compile(r"\bframes?\b", re.I), "moments"),
    (re.compile(r"\bpanels?\b", re.I), "moments"),
    (re.compile(r"\bstoryboards?\b", re.I), "dream sequence"),
    (re.compile(r"\brender(?:ed|ing|s)?\b", re.I), "depicted"),
    (re.compile(r"\bcontact sheets?\b", re.I), "imagery"),
    (re.compile(r"\bobservation packets?\b", re.I), "recollection"),
    (re.compile(r"\bwatch gauntlet\b", re.I), "recollection"),
    (re.compile(r"\bmontage\b", re.I), "imagery"),
    (re.compile(r"\bevidence_class\b", re.I), ""),
    (re.compile(r"\bsynthetic_(?:reflection|dream_memory|dream)\b", re.I), ""),
    (re.compile(r"\b(?:phase[ _]?\d{1,2})\b", re.I), ""),
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in-claims", type=Path, required=True,
                        help="JSON list of raw claim strings")
    parser.add_argument("--arm", required=True, choices=["C", "F"])
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--out-claims", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    claims = json.loads(args.in_claims.read_text())
    if not (isinstance(claims, list) and claims):
        print("BLOCKED_M5_NORMALIZE_INPUT_INVALID", file=sys.stderr)
        return 2

    replacements = []
    out = []
    for i, claim in enumerate(claims):
        text = claim
        for pattern, repl in REDACTION_MAP:
            def _sub(m, _i=i, _repl=repl):
                replacements.append({"claim_index": _i, "before": m.group(0), "after": _repl})
                return _repl
            text = pattern.sub(_sub, text)
        out.append(re.sub(r"\s{2,}", " ", text).strip())

    args.out_claims.write_text(json.dumps(out, indent=2) + "\n")
    receipt = {
        "schema": "persona_dream.pilot_m5_claim_redaction_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pair_id": args.pair_id,
        "arm": args.arm,
        "input_sha256": sha256_text(args.in_claims.read_text()),
        "output_sha256": sha256_text(args.out_claims.read_text()),
        "redaction_map_sha256": sha256_text(json.dumps(
            [(p.pattern, r) for p, r in REDACTION_MAP])),
        "replacement_count": len(replacements),
        "replacements": replacements,
        "note": "same fixed map applied to both arms; frozen leak gate in "
                "pilot_m5_presentation.py remains the authority on the output",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pair": args.pair_id, "arm": args.arm,
                      "replacements": len(replacements)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
