#!/usr/bin/env python3
"""Qualify a Horus audio source receipt for counted audio e2e runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


COUNTABLE = {"physical_live_horus", "recorded_physical_horus", "qualified_horus_clone"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-mode", required=True, choices=sorted(COUNTABLE))
    parser.add_argument("--receipt", type=Path, required=True, help="live/recorded Horus qualification receipt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if receipt.get("typed_transcript") or receipt.get("fixture_response"):
        raise ValueError("typed_transcripts_and_fixture_responses_not_countable")
    if receipt.get("speaker_id") not in {"horus_lupercal", "horus"}:
        raise ValueError("horus_source_not_proven")
    if receipt.get("live") is False or receipt.get("mocked") is True:
        raise ValueError("source_not_live_countable")

    qualification = {
        "schema": "embry.audio_e2e_horus_source_qualification.v1",
        "source_mode": args.source_mode,
        "receipt_path": str(args.receipt),
        "receipt_sha256": "sha256:" + hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
        "speaker_id": receipt.get("speaker_id"),
        "countable": True,
    }
    qualification["qualification_sha256"] = "sha256:" + hashlib.sha256(canonical(qualification)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(qualification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(qualification, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
