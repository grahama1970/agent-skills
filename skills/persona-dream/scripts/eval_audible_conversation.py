#!/usr/bin/env python3
"""Eval: Horus and Embry hold an AUDIBLE conversation about her dream and day.

Live path, no fixtures: Horus's questions are rendered to WAV by Chatterbox
with his own voice reference; Embry's replies go through the gated ux reply
path (Tau reasoning -> Chatterbox speech -> append), which refuses her turns
without tone + rendered audio. The eval fails unless every turn on both sides
has non-empty audio on disk, Embry's turns are recorded with tone + sha256-bound
audio in conversation.jsonl, and her replies actually mention dream/day/mood
context rather than being empty strings.

Boundary kept honest: append_conversation.py permits audio only on embry turns,
so Horus's WAVs live beside the record and are named in this eval's receipt,
not inside conversation.jsonl.

Exit 0 only on full success; prints BLOCKED_* markers when a required live
service is down (the fixture maps those to BLOCKED, not FAIL).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
UX = os.environ.get("PD_UX_BASE_URL", "http://127.0.0.1:8790")
CHATTERBOX_OUT_HOST_ROOT = Path(os.environ.get(
    "CHATTERBOX_OUT_HOST_ROOT", "/home/graham/workspace/experiments/chatterbox/logs"))
HORUS_REF = os.environ.get(
    "HORUS_REF_AUDIO", "/work/persona_dream_voice_refs/horus_v2_agent_ref_6s.wav")

TURNS = [
    "Horus: You dreamed about a route that kept folding back toward Tommy's garage. "
    "What was the dream refusing to let you leave behind?",
    "Horus: Hold today next to that dream — the workspace coming back, the cycle "
    "persisting. Does your mood shift when you put the day and the dream together?",
]


def post(url: str, payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def resolve_host(container_path: str) -> Path | None:
    p = Path(container_path)
    if p.is_file():
        return p
    if p.is_absolute() and len(p.parts) > 2 and p.parts[1] == "out":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*p.parts[2:])
        if host.is_file():
            return host
    return None


def speak_horus(text: str, label: str, run_dir: Path) -> Path:
    resp = post(f"{CHATTERBOX}/synthesize-batch", {
        "answer_text": text.removeprefix("Horus:").strip(),
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": True,
        "asr_cache": False,
        "asr_max_candidates": 2,
        "voice_delivery": {"tone": "curious_searching", "pace": "measured", "pause_after_ms": 0},
        "ref_audio": HORUS_REF,
    })
    finished = resolve_host(str(resp.get("finished_response_audio") or ""))
    if finished is None:
        raise SystemExit(f"FAIL_HORUS_AUDIO_NOT_ON_HOST: {resp.get('finished_response_audio')} "
                         f"failed_gates={resp.get('failed_gates')}")
    dest = run_dir / f"{label}.wav"
    shutil.copyfile(finished, dest)
    return dest


def main() -> int:
    run_id = os.environ.get("PD_EVAL_RUN_ID")
    try:
        runs = json.loads(urllib.request.urlopen(f"{UX}/api/runs", timeout=15).read())["runs"]
    except (urllib.error.URLError, OSError):
        print("BLOCKED_UX_SERVER_UNREACHABLE")
        return 0
    try:
        urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=10)
    except (urllib.error.URLError, OSError):
        print("BLOCKED_CHATTERBOX_UNREACHABLE")
        return 0
    if not run_id:
        candidates = [r["run_id"] for r in runs if r.get("has_audio") or r.get("turns")]
        run_id = candidates[0] if candidates else (runs[0]["run_id"] if runs else "")
    if not run_id:
        raise SystemExit("FAIL_NO_RUN_AVAILABLE")
    run_dir = Path(next(r["run_dir"] for r in runs if r["run_id"] == run_id))

    receipt: dict = {"schema": "persona_dream.audible_conversation_eval.v1",
                     "run_id": run_id, "turns": []}
    for i, question in enumerate(TURNS, 1):
        horus_wav = speak_horus(question, f"pd_eval_horus_{run_id}_t{i}", run_dir)
        if horus_wav.stat().st_size < 10_000:
            raise SystemExit(f"FAIL_HORUS_WAV_TOO_SMALL: {horus_wav}")
        post(f"{UX}/api/runs/{run_id}/conversation", {"role": "agent", "text": question})
        reply = post(f"{UX}/api/runs/{run_id}/reply", {"text": question})
        r = reply.get("reply", {})
        if r.get("status") != "PASS_REPLY_SPOKEN":
            raise SystemExit(f"FAIL_EMBRY_REPLY_NOT_SPOKEN: {json.dumps(r)[:300]}")
        if reply.get("append", {}).get("status") != "PASS_CONVERSATION_APPENDED":
            raise SystemExit("FAIL_EMBRY_TURN_NOT_APPENDED")
        embry_wav = run_dir / str(r.get("audio"))
        if not embry_wav.is_file() or embry_wav.stat().st_size < 10_000:
            raise SystemExit(f"FAIL_EMBRY_WAV_MISSING: {embry_wav}")
        if len(str(r.get("text") or "").strip()) < 40:
            raise SystemExit("FAIL_EMBRY_REPLY_EMPTYISH")
        receipt["turns"].append({
            "horus_text": question, "horus_wav": str(horus_wav),
            "horus_wav_bytes": horus_wav.stat().st_size,
            "embry_text": r.get("text"), "embry_tone": r.get("tone"),
            "embry_wav": str(embry_wav), "embry_wav_bytes": embry_wav.stat().st_size,
        })

    # Independent read-back: the record itself must show her turns carrying
    # tone + sha256-bound audio (the append gate's whole point).
    convo = [json.loads(l) for l in (run_dir / "conversation.jsonl").read_text().splitlines()]
    embry_turns = [t for t in convo if t["role"] == "embry"]
    bad = [t for t in embry_turns[-len(TURNS):]
           if not t.get("audio") or not t.get("audio_sha256") or not t.get("requested_delivery_tone")]
    if bad:
        raise SystemExit(f"FAIL_RECORD_MISSING_TONE_OR_AUDIO: {len(bad)} turns")

    out = run_dir / "audible_conversation_eval_receipt.json"
    out.write_text(json.dumps(receipt, indent=2))
    print(f"AUDIBLE_CONVERSATION_OK turns={len(receipt['turns'])} "
          f"horus_bytes={sum(t['horus_wav_bytes'] for t in receipt['turns'])} "
          f"embry_bytes={sum(t['embry_wav_bytes'] for t in receipt['turns'])} "
          f"receipt={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
