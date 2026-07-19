#!/usr/bin/env python3
"""Deletion-only modality-trace redaction for M5 claims (protocol v3 +
post-run measurement amendment v1).

Per the round-3 webgpt ruling, semantic rewriting is forbidden: every
modality-trace match is replaced by the content-free marker
[modality detail redacted] (never by fluent alternative wording). Exact
character spans, matched text, and before/after hashes are recorded. The
frozen pilot_m5_presentation.py leak gate remains the output authority.
The same fixed pattern list applies to both arms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

MARKER = "[modality detail redacted]"
REDACTION_PATTERNS = [
    re.compile(r"\bidentity[- ]continuity (?:pass|review|check)(?: across (?:all )?frames)?\b", re.I),
    re.compile(r"\bacross (?:all )?frames\b", re.I),
    re.compile(r"\bin (?:each|every) frame\b", re.I),
    re.compile(r"\bframes?\b", re.I),
    re.compile(r"\bpanels?\b", re.I),
    re.compile(r"\bstoryboards?\b", re.I),
    re.compile(r"\brender(?:ed|ing|s)?\b", re.I),
    re.compile(r"\bcontact sheets?\b", re.I),
    re.compile(r"\bobservation packets?\b", re.I),
    re.compile(r"\bwatch gauntlet\b", re.I),
    re.compile(r"\bmontage\b", re.I),
    re.compile(r"\bevidence_class\b", re.I),
    re.compile(r"\bsynthetic_(?:reflection|dream_memory|dream)\b", re.I),
    re.compile(r"\bphase[ _]?\d{1,2}\b", re.I),
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
        for pattern in REDACTION_PATTERNS:
            while True:
                m = pattern.search(text)
                if not m:
                    break
                replacements.append({"claim_index": i, "span": [m.start(), m.end()],
                                     "matched": m.group(0), "replaced_with": MARKER})
                text = text[:m.start()] + MARKER + text[m.end():]
        out.append(re.sub(r"\s{2,}", " ", text).strip())

    args.out_claims.write_text(json.dumps(out, indent=2) + "\n")
    receipt = {
        "schema": "persona_dream.pilot_m5_claim_redaction_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pair_id": args.pair_id,
        "arm": args.arm,
        "input_sha256": sha256_text(args.in_claims.read_text()),
        "output_sha256": sha256_text(args.out_claims.read_text()),
        "redaction_patterns_sha256": sha256_text(json.dumps(
            [p.pattern for p in REDACTION_PATTERNS])),
        "replacement_count": len(replacements),
        "replacements": replacements,
        "note": "deletion-only: every match becomes the content-free marker; "
                "same fixed patterns for both arms; frozen leak gate remains "
                "the output authority",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pair": args.pair_id, "arm": args.arm,
                      "replacements": len(replacements)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
