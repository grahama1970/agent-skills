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
    grounding = _load("conversation_grounding")
    context = grounding.load_context(run_dir)
    journal = str(context.get("journal_text") or "")[:3000]
    source_block = grounding.format_for_prompt(context)
    tail = transcript_tail(run_dir)
    convo = "\n".join(f"{t['role']}: {t['text']}" for t in tail) or "(no turns yet)"
    last_embry = next((t["text"] for t in reversed(tail) if t["role"] == "embry"), None)
    focus = (
        f"Respond to what Embry JUST said — quote or paraphrase one concrete phrase from her last turn before asking. Her last turn: {last_embry}"
        if last_embry else
        f"Open the conversation. Topic to open with: {opening_topic or 'her dream, her day, and how holding them together shifts her mood'}"
    )
    prompt = f"""You are Horus, a steady companion persona talking with Embry about the actual
finished Persona Dream cycle. Do not ask about generic uncertainty. Use the
source packet below: the dream she watched, the memory residue, curated
mined-transcript/operator feedback, the day events if present, and the journal
tension.

Ask exactly ONE question (one to three sentences of speech, natural spoken
register, no stage directions, no markdown). The question MUST name at least one
concrete anchor from the source packet, such as a person, place, object, image,
or event. Bad: "the dream" or "the competence question" with no source detail.
Good: "Marcus talking over you in the meeting", "the narrowing room", "Dev's
warmth", "the glass mask", or another anchor that appears below.

SOURCE PACKET
{source_block}

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
    question, injected = grounding.ground_if_needed(question, context, role="horus")
    day_injected = False
    if not last_embry:
        question, day_injected = grounding.ground_day_if_needed(question, context, role="horus")
    if tone not in tones:
        tone = "curious_searching" if "curious_searching" in tones else tones[0]
    return {"question": question, "tone": tone,
            "conditioned_on_last_embry": bool(last_embry),
            "transcript_chars": len(convo),
            "grounding_injected": injected,
            "day_grounding_injected": day_injected,
            "grounding_anchor_terms": context.get("anchor_terms") or [],
            "day_anchor_terms": context.get("day_anchor_terms") or [],
            "grounding_source_count": context.get("source_count"),
            "grounding_transcript_count": context.get("transcript_count"),
            "grounding_panel_count": context.get("panel_count"),
            "grounding_observation_count": context.get("observation_count")}, receipt


def speak_horus(sr, text: str, tone: str, run_dir: Path, label: str) -> dict[str, Any]:
    tts_render_text = text[:700]
    request = {
        "answer_text": tts_render_text, "label": label,
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
    return {
        "audio_path": dest,
        "tts_render_text": tts_render_text,
        "response": response,
        "render_effects": {
            "affect_effect": response.get("affect_effect"),
            "pace_effect": response.get("pace_effect"),
            "tag_handling": response.get("tag_handling"),
        },
    }


def append(run_dir: Path, role: str, text: str, tone: str | None, audio: Path | None,
           chatterbox_utterance_text: str | None = None,
           tts_render_text: str | None = None,
           emotional_utterance_tags: list[str] | None = None,
           chatterbox_pause_plan: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cmd = [sys.executable, str(ROOT / "scripts" / "append_conversation.py"),
           "--run-dir", str(run_dir), "--role", role, "--text", text, "--json"]
    if tone:
        cmd += ["--tone", tone]
    if audio:
        cmd += ["--audio", str(audio)]
    if chatterbox_utterance_text:
        cmd += ["--chatterbox-utterance-text", chatterbox_utterance_text]
    if tts_render_text:
        cmd += ["--tts-render-text", tts_render_text]
    if emotional_utterance_tags:
        cmd += ["--emotional-utterance-tags", ",".join(emotional_utterance_tags)]
    if chatterbox_pause_plan:
        cmd += ["--chatterbox-pause-plan", json.dumps(chatterbox_pause_plan)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    receipt = json.loads(out.stdout or "{}")
    if receipt.get("status") != "PASS_CONVERSATION_APPENDED":
        raise SystemExit(f"BLOCKED_APPEND_{role.upper()}: {out.stdout[:200]}{out.stderr[:200]}")
    return receipt


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
        horus_speech = speak_horus(sr, horus["question"], horus["tone"], run_dir,
                                   f"pd_horus_{run_dir.name}_t{i}_{abs(hash(horus['question'])) % 10**8}")
        h_wav = horus_speech["audio_path"]
        horus_append = append(run_dir, "horus", horus["question"], horus["tone"], h_wav,
                              tts_render_text=horus_speech["tts_render_text"])
        horus_turn = dict(horus_append.get("appended") or {})

        embry = sr.generate_and_speak(run_dir=run_dir, prompt_text=horus["question"])
        if embry.get("status") != "PASS_REPLY_SPOKEN":
            raise SystemExit(f"BLOCKED_EMBRY_TURN: {json.dumps(embry)[:300]}")
        embry_tts_render_text = embry.get("tts_render_text") or embry.get("chatterbox_utterance_text")
        embry_append = append(run_dir, "embry", embry["text"], embry["tone"], run_dir / embry["audio"],
                              embry.get("chatterbox_utterance_text"), embry_tts_render_text,
                              embry.get("emotional_utterance_tags") or [],
                              embry.get("chatterbox_pause_plan") or [])
        embry_turn = dict(embry_append.get("appended") or {})

        receipt["turn_pairs"].append({
            "pair": i,
            "horus": {**horus, "audio": h_wav.name, "audio_bytes": h_wav.stat().st_size,
                      "tts_render_text": horus_speech.get("tts_render_text"),
                      "tts_render_text_hash": horus_turn.get("tts_render_text_hash"),
                      "audio_sha256": horus_turn.get("audio_sha256"),
                      "tone_boundary": horus_turn.get("tone_boundary"),
                      "render_effects": horus_speech.get("render_effects"),
                      "append_read_back": bool(horus_append.get("read_back")),
                      "tau_receipt": adapter.receipt_provenance(tau_receipt) if tau_receipt else {}},
            "embry": {"text": embry["text"], "tone": embry["tone"], "audio": embry["audio"],
                      "tts_render_text": embry_tts_render_text,
                      "tts_render_text_hash": embry_turn.get("tts_render_text_hash"),
                      "audio_sha256": embry_turn.get("audio_sha256"),
                      "tone_boundary": embry_turn.get("tone_boundary"),
                      "render_effects": {"affect_effect": embry.get("affect_effect"), "pace_effect": embry.get("pace_effect"), "tag_handling": embry.get("tag_handling")},
                      "append_read_back": bool(embry_append.get("read_back")),
                      "chatterbox_utterance_text": embry.get("chatterbox_utterance_text"),
                      "emotional_utterance_tags": embry.get("emotional_utterance_tags") or [],
                      "chatterbox_pause_plan": embry.get("chatterbox_pause_plan") or [],
                      "audio_bytes": (run_dir / embry["audio"]).stat().st_size},
        })

    receipt["status"] = "PASS_DYNAMIC_CONVERSATION"
    receipt["turn_count"] = sum(2 for _ in receipt["turn_pairs"])
    receipt["voice_delivery"] = {
        "rendered_turn_count": receipt["turn_count"],
        "audio_sha256_count": sum(
            1
            for pair in receipt["turn_pairs"]
            for role in ("horus", "embry")
            if pair.get(role, {}).get("audio_sha256")
        ),
        "embry_inline_tagged_turn_count": sum(
            1
            for pair in receipt["turn_pairs"]
            if "[" in str(pair.get("embry", {}).get("chatterbox_utterance_text") or "")
            and "]" in str(pair.get("embry", {}).get("chatterbox_utterance_text") or "")
        ),
        "embry_pause_plan_count": sum(
            1
            for pair in receipt["turn_pairs"]
            if any(chunk.get("pause_after_ms") for chunk in pair.get("embry", {}).get("chatterbox_pause_plan") or [])
        ),
    }
    out = run_dir / "dynamic_conversation_receipt.v1.json"
    out.write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2) if args.json else
          f"PASS_DYNAMIC_CONVERSATION pairs={len(receipt['turn_pairs'])} receipt={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
