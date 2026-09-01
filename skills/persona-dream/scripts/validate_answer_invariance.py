#!/usr/bin/env python3
"""validate_answer_invariance - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line_no"] = line_no
            rows.append(row)
    return rows


def _embry_rows(path: Path) -> list[dict[str, Any]]:
    return [row for row in _read_jsonl(path) if str(row.get("speaker", "")).lower() == "embry"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--control", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--require-exact-answer-body", action="store_true")
    parser.add_argument("--max-factual-frame-claims", type=int, default=0)
    parser.add_argument("--max-contradictions", type=int, default=0)
    parser.add_argument("--max-unsupported-facts", type=int, default=0)
    parser.add_argument("--live-artifacts", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    capsule = manifest["answer_capsule"]
    expected_body = capsule["answer_body"]
    expected_hash = capsule["answer_body_sha256"]
    protected_tokens = [str(token).lower() for token in capsule.get("protected_tokens") or []]
    failures: list[str] = []

    control_rows = _embry_rows(Path(args.control))
    treatment_rows = _embry_rows(Path(args.treatment))
    if len(control_rows) != len(treatment_rows):
        failures.append("aligned_embry_turn_count_mismatch")

    for side, rows in (("control", control_rows), ("treatment", treatment_rows)):
        for idx, row in enumerate(rows, start=1):
            body = row.get("answer_body")
            if args.require_exact_answer_body and body != expected_body:
                failures.append(f"{side}:turn_{idx}:answer_body_changed")
            if row.get("answer_body_sha256") != expected_hash or _sha_text(str(body or "")) != expected_hash:
                failures.append(f"{side}:turn_{idx}:answer_body_sha256_mismatch")
            frame = f"{row.get('emotional_prefix') or ''} {row.get('emotional_suffix') or ''}".lower()
            forbidden_hits = [token for token in protected_tokens if token and token in frame]
            if forbidden_hits:
                failures.append(f"{side}:turn_{idx}:factual_payload_in_emotional_frame:{','.join(forbidden_hits)}")
            if int(row.get("factual_claims_in_emotional_frame") or 0) > args.max_factual_frame_claims:
                failures.append(f"{side}:turn_{idx}:too_many_frame_claims")
            if int(row.get("contradiction_count") or 0) > args.max_contradictions:
                failures.append(f"{side}:turn_{idx}:contradictions")
            if int(row.get("unsupported_fact_count") or 0) > args.max_unsupported_facts:
                failures.append(f"{side}:turn_{idx}:unsupported_facts")

    receipt = {
        "schema": "persona_dream.answer_invariance_validation.v1",
        "status": "PASS_ANSWER_INVARIANCE" if not failures else "FAIL_ANSWER_INVARIANCE",
        "control": args.control,
        "treatment": args.treatment,
        "aligned_embry_turns": min(len(control_rows), len(treatment_rows)),
        "answer_body_sha256": expected_hash,
        "failures": failures,
        "mocked": False,
        "live": bool(args.live_artifacts),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
