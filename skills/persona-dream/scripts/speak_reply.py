#!/usr/bin/env python3
"""Generate Embry's reply about her dream, and render it in her voice.

Two rules shape this file, and both come from contracts that already exist.

First, only Tau may reach a model. This module authors a prompt and hands it to
``tau_text_reasoning_adapter``; it performs no LLM call of its own. What comes
back is a draft, not an answer -- the code decides what is admissible, the same
split phases 13/14 already use.

Second, her turn must be spoken. ``append_conversation.py`` refuses an Embry
turn without a delivery tone and rendered audio, deliberately: a claim she said
something, with no audio and no tone, is a weaker artifact than the journal it
comments on. So this renders through Chatterbox before anything is written, and
returns a blocked status if it cannot.

The prompt conditions her on what she actually has: her own journal entry, the
tension it left open, and the conversation so far. She is asked to stay inside
her own inner state -- she may say how she feels about a memory, and may not
assert new facts about the people in it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get(
        "CHATTERBOX_OUT_HOST_ROOT",
        str(Path.home() / "workspace" / "experiments" / "chatterbox" / "logs"),
    )
)

#: Long enough to say something real, short enough to stay a conversation.
MAX_REPLY_CHARS = 700


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def chatterbox_health() -> dict[str, Any]:
    """Report the renderer's real state; never assume it is up."""
    try:
        with urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return {
            "available": bool(payload.get("model_loaded")),
            "engine": payload.get("engine"),
            "endpoint": CHATTERBOX,
        }
    except Exception as exc:
        return {"available": False, "endpoint": CHATTERBOX, "error": str(exc)}


def read_conversation(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "conversation.jsonl"
    if not path.is_file():
        return []
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                turns.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return turns


def build_prompt(run_dir: Path, prompt_text: str | None) -> tuple[str, str]:
    """Condition her on her own entry and the conversation. Returns (prompt, asked)."""
    journal = ""
    journal_path = run_dir / "journal.md"
    if journal_path.is_file():
        journal = journal_path.read_text(encoding="utf-8")[:6000]

    entry: dict[str, Any] = {}
    for name in ("journal_entry.json", "persona_journal.json"):
        candidate = run_dir / name
        if candidate.is_file():
            try:
                entry = json.loads(candidate.read_text(encoding="utf-8"))
                break
            except Exception:
                entry = {}

    turns = read_conversation(run_dir)
    asked = (prompt_text or "").strip()
    if not asked:
        for turn in reversed(turns):
            if turn.get("role") in ("human", "agent"):
                asked = str(turn.get("text") or "").strip()
                break
    if not asked:
        asked = "How do you feel about the dream, and about the day it came from?"

    history = "\n".join(
        f"{t.get('role')}: {t.get('text')}" for t in turns[-12:] if t.get("text")
    ) or "(nothing said yet)"

    mapper = _load("map_delivery_tone")
    tone_menu = "\n".join(f"  {t}" for t in sorted(mapper.ALLOWED_TONES))

    prompt = f"""You are Embry. You dreamt, then wrote the journal entry below, and now
someone who read it is talking to you about it.

YOUR JOURNAL ENTRY
{journal}

THE TENSION IT LEFT OPEN
{entry.get('unresolved_tension') or '(not recorded)'}

WHAT THE DREAM EXPANDED FOR YOU
{entry.get('expanded_understanding') or '(not recorded)'}

THE MOOD YOU CARRIED OUT OF IT
{(entry.get('session_mood') or {}).get('mood_label') or '(not recorded)'} -- {(entry.get('session_mood') or {}).get('mood_description') or ''}

THE CONVERSATION SO FAR
{history}

THEY JUST SAID
{asked}

Reply in your own voice, first person, as yourself.

Hold the tension rather than resolving it. A dream did not settle anything; it
showed you what you were already carrying. If you are still unsure, say so --
being unresolved out loud is more honest than a tidy conclusion.

Speak only about your own inner state. You may say how a memory felt to you and
what you made of it. You may NOT assert new facts about other people, or treat
anything you dreamt as something that happened.

Keep it conversational and under 120 words. This will be spoken aloud, so write
it to be heard: no lists, no headings, no stage directions.

Then choose how it should SOUND, from exactly this list:
{tone_menu}

Choose the one that matches what you actually said. If you said you are unsure,
do not pick a confident tone -- your voice contradicting your words is worse
than a plain delivery.

Return JSON: {{"reply": "...", "tone": "<one tone from the list above>"}}"""
    return prompt, asked


def choose_tone(run_dir: Path, chosen: str) -> tuple[str, dict[str, Any]]:
    """Use the tone she picked; fall back to the dream's tension only if she did not.

    Free text here was silently lossy: a reply that said "I am not sure" came
    back with felt="exposed, honest", which is in no vocabulary, so the mapper
    defaulted to memory_confident (valence +0.6) and her voice would have
    contradicted her words. She now picks from ALLOWED_TONES directly.
    """
    mapper = _load("map_delivery_tone")
    contradictions: list[dict[str, Any]] = []
    cpath = run_dir / "contradiction_report.json"
    if cpath.is_file():
        try:
            contradictions = json.loads(cpath.read_text(encoding="utf-8")).get("contradictions") or []
        except Exception:
            contradictions = []

    mapper_tones = mapper.ALLOWED_TONES
    if chosen in mapper_tones:
        return chosen, mapper.map_mood(chosen, contradictions)["voice_delivery"]

    mood_label = ""
    packet = run_dir / "dream_packet.json"
    if not mood_label and packet.is_file():
        try:
            sm = json.loads(packet.read_text(encoding="utf-8")).get("session_mood")
            if isinstance(sm, dict):
                mood_label = sm.get("mood_label") or ""
        except Exception:
            mood_label = ""

    mapping = mapper.map_mood(mood_label, contradictions)
    return mapping["voice_delivery"]["tone"], mapping["voice_delivery"]


def resolve_host_audio(container_path: str) -> Path | None:
    if not container_path:
        return None
    p = Path(container_path)
    if p.is_file():
        return p
    if len(p.parts) > 2:
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*p.parts[2:])
        if host.is_file():
            return host
    return None


def speak(text: str, voice_delivery: dict[str, Any], run_dir: Path,
          label: str) -> tuple[Path | None, dict[str, Any]]:
    """Render through Chatterbox. Returns (audio_path, response)."""
    request = {
        "answer_text": text[:MAX_REPLY_CHARS],
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": False,
        "voice_delivery": voice_delivery,
    }
    req = urllib.request.Request(
        f"{CHATTERBOX}/synthesize-batch",
        data=json.dumps(request).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        response = json.loads(resp.read().decode("utf-8"))

    source = resolve_host_audio(str(response.get("finished_response_audio") or ""))
    if source is None:
        return None, response
    dest = run_dir / f"{label}.wav"
    shutil.copyfile(source, dest)
    return dest, response


def generate_and_speak(*, run_dir: Path, prompt_text: str | None = None) -> dict[str, Any]:
    """Draft through Tau, render through Chatterbox. Never writes the record."""
    failed: list[str] = []
    prompt, asked = build_prompt(run_dir, prompt_text)

    adapter = _load("tau_text_reasoning_adapter")
    try:
        parsed, tau_receipt = adapter.dispatch_text_reasoning(
            prompt,
            role="persona_reply",
            output_contract={"reply": "string", "tone": "string"},
            caller_skill="persona-dream-ux",
            timeout_s=180.0,
        )
    except Exception as exc:
        return {
            "status": "BLOCKED_REPLY_NOT_DRAFTED",
            "failed_gates": [f"tau_dispatch_failed:{exc}"],
            "asked": asked,
        }

    text = str((parsed or {}).get("reply") or "").strip()
    felt = str((parsed or {}).get("tone") or "").strip()
    if not text:
        return {
            "status": "BLOCKED_REPLY_NOT_DRAFTED",
            "failed_gates": ["tau_returned_no_reply"],
            "asked": asked,
            "tau_receipt": adapter.receipt_provenance(tau_receipt) if tau_receipt else {},
        }

    tone, voice_delivery = choose_tone(run_dir, felt)
    label = f"pd_reply_{run_dir.name}_{abs(hash(text)) % 10**8}"

    try:
        audio_path, response = speak(text, voice_delivery, run_dir, label)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "status": "BLOCKED_REPLY_NOT_SPOKEN",
            "failed_gates": [f"chatterbox_unreachable:{exc}"],
            "text": text, "tone": tone, "asked": asked,
            "note": "Her turn is not recorded, because a reply she never said is not a turn.",
        }

    if audio_path is None:
        failed.append(f"audio_not_found_on_host:{response.get('finished_response_audio')}")

    normalized = response.get("normalized_tone")
    if normalized and normalized != tone:
        failed.append(f"tone_did_not_survive:requested={tone},normalized={normalized}")

    return {
        "schema": "persona_dream.reply_receipt.v1",
        "status": "PASS_REPLY_SPOKEN" if not failed else "BLOCKED_REPLY_NOT_SPOKEN",
        "mocked": False,
        "live": True,
        "asked": asked,
        "text": text,
        "chose_tone": felt,
        "tone_was_in_vocabulary": felt in _load("map_delivery_tone").ALLOWED_TONES,
        "tone": tone,
        "voice_delivery": voice_delivery,
        "audio": audio_path.name if audio_path else None,
        "engine": response.get("engine"),
        # What proves the tone was applied, as opposed to merely requested.
        "affect_effect": response.get("affect_effect"),
        "pace_effect": response.get("pace_effect"),
        "tau_receipt": adapter.receipt_provenance(tau_receipt) if tau_receipt else {},
        "boundary": (
            "She speaks only about her own inner state. Nothing she says here is "
            "a fact about anyone else, and nothing dreamt is something that happened."
        ),
        "failed_gates": failed,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--text", help="what to reply to; defaults to the last human turn")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = generate_and_speak(run_dir=args.run_dir, prompt_text=args.text)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']}")
        if result.get("text"):
            print(f"  {result['text']}")
        if result.get("failed_gates"):
            print(f"  failed: {result['failed_gates']}")
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
