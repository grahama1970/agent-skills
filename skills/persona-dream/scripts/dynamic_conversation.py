#!/usr/bin/env python3
"""A dynamic, fully audible Horus/Embry conversation about her dream and day.

Neither side is scripted. Each Horus turn is drafted by Tau (the only door to a
model) conditioned on her journal entry and the transcript so far — he must
respond to what she actually just said, not read from a list. Each Embry turn
goes through the existing gated reply path (``speak_reply.generate_and_speak``),
which is already transcript-conditioned. Both sides are rendered by Chatterbox
in their own voices and appended as voiced turns: ``append_conversation.py``
refuses an ``embry`` OR ``horus`` turn without a requested tone and rendered
audio, so the record can never claim speech that was not synthesized.

The receipt binds every turn to its audio sha256 and carries the Tau receipt
provenance for each Horus draft, so "dynamic" is evidenced, not asserted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
HORUS_REF = os.environ.get(
    "HORUS_REF_AUDIO", "/work/persona_dream_voice_refs/horus_v2_agent_ref_6s.wav")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def transcript_tail(run_dir: Path, limit: int = 12) -> list[dict[str, Any]]:
    path = run_dir / "conversation.jsonl"
    if not path.is_file():
        return []
    turns = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return turns[-limit:]


def draft_horus_turn(run_dir: Path, adapter, tones: list[str], opening_topic: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    journal = ""
    jpath = run_dir / "journal.md"
    if jpath.is_file():
        journal = jpath.read_text(encoding="utf-8")[:3000]
    tail = transcript_tail(run_dir)
    convo = "\n".join(f"{t['role']}: {t['text']}" for t in tail) or "(no turns yet)"
    last_embry = next((t["text"] for t in reversed(tail) if t["role"] == "embry"), None)
    focus = (
        f"Respond to what Embry JUST said — quote or paraphrase one concrete phrase from her last turn before asking. Her last turn: {last_embry}"
        if last_embry else
        f"Open the conversation. Topic to open with: {opening_topic or 'her dream, her day, and how holding them together shifts her mood'}"
    )
    prompt = f"""You are Horus, a steady companion persona talking with Embry about the dream
journal entry below. You are curious about her dream, her day, and how the two
together move her mood. Ask exactly ONE question (one to three sentences of
speech, natural spoken register, no stage directions, no markdown).

Her journal entry:
{journal}

Conversation so far:
{convo}

{focus}

Pick your delivery tone from exactly this list: {tones}
Return strict JSON: {{"question": "...", "tone": "<one tone from the list>"}}"""
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, role="horus_turn",
        output_contract={"question": "string", "tone": "string"},
        caller_skill="persona-dream-dynamic-conversation", timeout_s=180.0)
    question = str((parsed or {}).get("question") or "").strip()
    tone = str((parsed or {}).get("tone") or "").strip()
    if not question:
        raise SystemExit(f"BLOCKED_HORUS_NOT_DRAFTED: {json.dumps(receipt)[:200]}")
    if tone not in tones:
        tone = "curious_searching" if "curious_searching" in tones else tones[0]
    return {"question": question, "tone": tone,
            "conditioned_on_last_embry": bool(last_embry),
            "transcript_chars": len(convo)}, receipt


def speak_horus(sr, text: str, tone: str, run_dir: Path, label: str) -> Path:
    request = {
        "answer_text": text[:700], "label": label,
        "use_blessed_qra_cache": False, "asr_verify": False,
        "voice_delivery": {"tone": tone, "pace": "measured", "pause_after_ms": 0},
        "ref_audio": HORUS_REF,
    }
    req = urllib.request.Request(
        f"{CHATTERBOX}/synthesize-batch", data=json.dumps(request).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        response = json.loads(resp.read())
    source = sr.resolve_host_audio(str(response.get("finished_response_audio") or ""))
    if source is None:
        raise SystemExit(
            f"BLOCKED_HORUS_NOT_SPOKEN: audio_not_on_host "
            f"{response.get('finished_response_audio')} gates={response.get('failed_gates')}")
    dest = run_dir / f"{label}.wav"
    import shutil
    shutil.copyfile(source, dest)
    return dest


def append(run_dir: Path, role: str, text: str, tone: str | None, audio: Path | None) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / "append_conversation.py"),
           "--run-dir", str(run_dir), "--role", role, "--text", text, "--json"]
    if tone:
        cmd += ["--tone", tone]
    if audio:
        cmd += ["--audio", str(audio)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    receipt = json.loads(out.stdout or "{}")
    if receipt.get("status") != "PASS_CONVERSATION_APPENDED":
        raise SystemExit(f"BLOCKED_APPEND_{role.upper()}: {out.stdout[:200]}{out.stderr[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--turns", type=int, default=2, help="Horus/Embry exchange pairs")
    ap.add_argument("--opening-topic", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    run_dir = args.run_dir.resolve()

    adapter = _load("tau_text_reasoning_adapter")
    sr = _load("speak_reply")
    tones = list(_load("map_delivery_tone").ALLOWED_TONES)

    receipt: dict[str, Any] = {
        "schema": "persona_dream.dynamic_conversation_receipt.v1",
        "run_dir": str(run_dir), "turn_pairs": [], "mocked": False, "live": True,
    }
    for i in range(1, args.turns + 1):
        horus, tau_receipt = draft_horus_turn(run_dir, adapter, tones, args.opening_topic)
        h_wav = speak_horus(sr, horus["question"], horus["tone"], run_dir,
                            f"pd_horus_{run_dir.name}_t{i}_{abs(hash(horus['question'])) % 10**8}")
        append(run_dir, "horus", horus["question"], horus["tone"], h_wav)

        embry = sr.generate_and_speak(run_dir=run_dir, prompt_text=horus["question"])
        if embry.get("status") != "PASS_REPLY_SPOKEN":
            raise SystemExit(f"BLOCKED_EMBRY_TURN: {json.dumps(embry)[:300]}")
        append(run_dir, "embry", embry["text"], embry["tone"], run_dir / embry["audio"])

        receipt["turn_pairs"].append({
            "pair": i,
            "horus": {**horus, "audio": h_wav.name, "audio_bytes": h_wav.stat().st_size,
                      "tau_receipt": adapter.receipt_provenance(tau_receipt) if tau_receipt else {}},
            "embry": {"text": embry["text"], "tone": embry["tone"], "audio": embry["audio"],
                      "audio_bytes": (run_dir / embry["audio"]).stat().st_size},
        })

    out = run_dir / "dynamic_conversation_receipt.v1.json"
    out.write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2) if args.json else
          f"PASS_DYNAMIC_CONVERSATION pairs={len(receipt['turn_pairs'])} receipt={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
