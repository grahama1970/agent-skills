#!/usr/bin/env python3
"""Eval: Horus and Embry hold a DYNAMIC, fully audible conversation.

Drives scripts/dynamic_conversation.py over the newest journal-bearing run:
each Horus turn is drafted live by Tau from her journal and the transcript,
spoken in his own voice; each Embry turn goes through the gated reply path.
Both roles are voiced first-class — append_conversation.py refuses either turn
without tone + rendered audio.

Oracles (all independent read-backs, not the loop's own status):
- conversation.jsonl gains 2 horus + 2 embry turns, every one carrying
  requested_delivery_tone + audio + audio_sha256, and the WAVs exist non-empty;
- the receipt proves dynamism: the second Horus turn was conditioned on
  Embry's actual previous reply (conditioned_on_last_embry) and its question
  text differs from the first;
- Tau receipt provenance is present for every Horus draft (generated, not
  scripted).

Prints BLOCKED_* when a required live service is down, so a dead service reads
as BLOCKED rather than FAIL.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
UX = os.environ.get("PD_UX_BASE_URL", "http://127.0.0.1:8790")


def main() -> int:
    try:
        urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=10)
    except (urllib.error.URLError, OSError):
        print("BLOCKED_CHATTERBOX_UNREACHABLE")
        return 0
    run_id = os.environ.get("PD_EVAL_RUN_ID")
    try:
        runs = json.loads(urllib.request.urlopen(f"{UX}/api/runs", timeout=15).read())["runs"]
    except (urllib.error.URLError, OSError):
        print("BLOCKED_UX_SERVER_UNREACHABLE")
        return 0
    if not run_id:
        candidates = [r["run_id"] for r in runs if r.get("turns") or r.get("has_audio")]
        run_id = candidates[0] if candidates else (runs[0]["run_id"] if runs else "")
    if not run_id:
        raise SystemExit("FAIL_NO_RUN_AVAILABLE")
    run_dir = Path(next(r["run_dir"] for r in runs if r["run_id"] == run_id))

    convo_path = run_dir / "conversation.jsonl"
    before = len(convo_path.read_text().splitlines()) if convo_path.is_file() else 0

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dynamic_conversation.py"),
         "--run-dir", str(run_dir), "--turns", "2"],
        capture_output=True, text=True, timeout=1500)
    # Only service-down markers pass through as BLOCKED; every other failure
    # must surface its diagnostics and FAIL (a swallowed BLOCKED_EMBRY_TURN
    # cost the 2026-08-20 suite run its root cause).
    service_markers = ("BLOCKED_CHATTERBOX_UNREACHABLE", "BLOCKED_UX_SERVER_UNREACHABLE")
    if proc.returncode != 0:
        for marker in service_markers:
            if marker in (proc.stdout + proc.stderr):
                print(marker)
                return 0
    if proc.returncode != 0 or "PASS_DYNAMIC_CONVERSATION" not in proc.stdout:
        raise SystemExit(f"FAIL_DYNAMIC_CONVERSATION: rc={proc.returncode} "
                         f"out={proc.stdout[-200:]} err={proc.stderr[-200:]}")

    turns = [json.loads(l) for l in convo_path.read_text().splitlines()][before:]
    horus = [t for t in turns if t["role"] == "horus"]
    embry = [t for t in turns if t["role"] == "embry"]
    if len(horus) != 2 or len(embry) != 2:
        raise SystemExit(f"FAIL_TURN_COUNT: horus={len(horus)} embry={len(embry)}")
    for t in turns:
        if t["role"] not in ("horus", "embry"):
            continue
        if not t.get("requested_delivery_tone") or not t.get("audio") or not t.get("audio_sha256"):
            raise SystemExit(f"FAIL_TURN_NOT_VOICED: {t['role']} {str(t.get('text'))[:60]}")
        wav = run_dir / t["audio"]
        if not wav.is_file() or wav.stat().st_size < 10_000:
            raise SystemExit(f"FAIL_WAV_MISSING_OR_EMPTY: {wav}")

    receipt = json.loads((run_dir / "dynamic_conversation_receipt.v1.json").read_text())
    pairs = receipt["turn_pairs"]
    if not pairs[1]["horus"]["conditioned_on_last_embry"]:
        raise SystemExit("FAIL_NOT_DYNAMIC: second Horus turn not conditioned on Embry's reply")
    if pairs[0]["horus"]["question"] == pairs[1]["horus"]["question"]:
        raise SystemExit("FAIL_NOT_DYNAMIC: identical Horus questions")
    for p in pairs:
        if not p["horus"].get("tau_receipt"):
            raise SystemExit("FAIL_NO_TAU_PROVENANCE: Horus turn lacks a Tau receipt")

    print(f"AUDIBLE_CONVERSATION_OK turns=2 dynamic=true "
          f"horus_bytes={sum(p['horus']['audio_bytes'] for p in pairs)} "
          f"embry_bytes={sum(p['embry']['audio_bytes'] for p in pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
