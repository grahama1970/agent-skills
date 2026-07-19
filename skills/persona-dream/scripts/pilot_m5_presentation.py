#!/usr/bin/env python3
"""M5 presentation normalization + sealed X/Y order for the C-vs-F pilot.

Protocol v2: "the operator receives ONLY the final interpretation text blocks
(same template, stripped of evidence_class, artifact paths, modality traces),
labeled X/Y in per-pair random order recorded in a sealed receipt opened after
judgment."

prepare: takes the two arms' final interpretation claims (JSON list of strings
per arm), fails closed if any claim leaks paths/modality/evidence-class
markers (no silent scrubbing), renders both arms into one identical template
as pair_<id>_X.md / pair_<id>_Y.md with a cryptographically random arm->label
assignment, and writes the assignment into sealed/pair_<id>_order.json plus a
public commitment (sha256 of the sealed file). The operator judges from the
X/Y files only.

unseal: after the operator's judgment file exists, verifies the commitment
hash and reveals which arm was X.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
import time
from pathlib import Path

LEAK_PATTERNS = [
    (re.compile(r"[\w/.-]+\.(?:json|mp4|png|jpg|wav|md|yaml)\b", re.I), "artifact path"),
    (re.compile(r"evidence_class", re.I), "evidence_class marker"),
    (re.compile(r"\b(?:storyboard|render|watch gauntlet|observation packet|frame|video|contact sheet|montage)\b", re.I), "modality trace"),
    (re.compile(r"\b(?:phase[ _]?1[0-9]|phase[ _]?0[0-9])\b", re.I), "pipeline phase marker"),
    (re.compile(r"synthetic_reflection|synthetic_dream_memory", re.I), "record-class marker"),
]

TEMPLATE = """# Interpretation set {label} (pair {pair_id})

{claims}
"""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_claims(path: Path, arm: str) -> list[str]:
    data = json.loads(path.read_text())
    if not (isinstance(data, list) and data and all(isinstance(c, str) and c.strip() for c in data)):
        print(f"BLOCKED_PILOT_M5_CLAIMS_INVALID: {arm} {path}", file=sys.stderr)
        raise SystemExit(2)
    leaks = []
    for i, claim in enumerate(data):
        for pattern, kind in LEAK_PATTERNS:
            m = pattern.search(claim)
            if m:
                leaks.append({"arm": arm, "claim_index": i, "kind": kind, "match": m.group(0)})
    if leaks:
        print("BLOCKED_PILOT_M5_PRESENTATION_LEAK", file=sys.stderr)
        print(json.dumps(leaks, indent=2), file=sys.stderr)
        raise SystemExit(2)
    return data


def render(pair_id: str, label: str, claims: list[str]) -> str:
    body = "\n".join(f"{i + 1}. {c.strip()}" for i, c in enumerate(claims))
    return TEMPLATE.format(label=label, pair_id=pair_id, claims=body)


def cmd_prepare(args: argparse.Namespace) -> int:
    c_claims = load_claims(args.c_claims, "C")
    f_claims = load_claims(args.f_claims, "F")
    x_is_c = secrets.randbits(1) == 1
    mapping = {"X": "C", "Y": "F"} if x_is_c else {"X": "F", "Y": "C"}
    by_label = {"X": c_claims if x_is_c else f_claims,
                "Y": f_claims if x_is_c else c_claims}

    out = args.out_dir
    sealed_dir = out / "sealed"
    sealed_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for label in ("X", "Y"):
        p = out / f"pair_{args.pair_id}_{label}.md"
        p.write_text(render(args.pair_id, label, by_label[label]))
        files[label] = {"path": str(p), "sha256": sha256_text(p.read_text())}

    sealed = {
        "schema": "persona_dream.pilot_m5_sealed_order.v1",
        "pair_id": args.pair_id,
        "mapping": mapping,
        "nonce": secrets.token_hex(16),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    sealed_path = sealed_dir / f"pair_{args.pair_id}_order.json"
    if sealed_path.exists():
        print(f"BLOCKED_PILOT_M5_ORDER_ALREADY_SEALED: {sealed_path}", file=sys.stderr)
        return 2
    sealed_path.write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n")
    commitment = {
        "schema": "persona_dream.pilot_m5_order_commitment.v1",
        "pair_id": args.pair_id,
        "sealed_order_sha256": sha256_text(sealed_path.read_text()),
        "presented_files": files,
        "created_at": sealed["created_at"],
    }
    commit_path = out / f"pair_{args.pair_id}_order_commitment.json"
    commit_path.write_text(json.dumps(commitment, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pair_id": args.pair_id, "presented": files,
                      "commitment": str(commit_path),
                      "sealed_order_sha256": commitment["sealed_order_sha256"]}, indent=2))
    return 0


def cmd_unseal(args: argparse.Namespace) -> int:
    out = args.out_dir
    sealed_path = out / "sealed" / f"pair_{args.pair_id}_order.json"
    commit_path = out / f"pair_{args.pair_id}_order_commitment.json"
    if not args.judgment.exists():
        print(f"BLOCKED_PILOT_M5_UNSEAL_BEFORE_JUDGMENT: missing {args.judgment}", file=sys.stderr)
        return 2
    judgment = json.loads(args.judgment.read_text())
    if judgment.get("author") != "human":
        print("BLOCKED_PILOT_M5_JUDGMENT_NOT_HUMAN_AUTHORED", file=sys.stderr)
        return 2
    commitment = json.loads(commit_path.read_text())
    actual = sha256_text(sealed_path.read_text())
    if actual != commitment["sealed_order_sha256"]:
        print("BLOCKED_PILOT_M5_COMMITMENT_MISMATCH", file=sys.stderr)
        return 2
    sealed = json.loads(sealed_path.read_text())
    print(json.dumps({"pair_id": args.pair_id, "mapping": sealed["mapping"],
                      "commitment_verified": True,
                      "judgment_file_sha256": sha256_text(args.judgment.read_text())}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--pair-id", required=True)
    p.add_argument("--c-claims", type=Path, required=True,
                   help="JSON list of C-arm final interpretation claim strings")
    p.add_argument("--f-claims", type=Path, required=True,
                   help="JSON list of F-arm final interpretation claim strings")
    p.add_argument("--out-dir", type=Path, required=True)
    p.set_defaults(func=cmd_prepare)
    u = sub.add_parser("unseal")
    u.add_argument("--pair-id", required=True)
    u.add_argument("--out-dir", type=Path, required=True)
    u.add_argument("--judgment", type=Path, required=True,
                   help="operator judgment JSON (author must be 'human')")
    u.set_defaults(func=cmd_unseal)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
