#!/usr/bin/env python3
"""Run reviewed ElevenLabs prompt experiments for Orpheus emotion tags.

This is the missing loop between "we think this prompt might work" and "this
clip can be considered for Orpheus training":

1. write the prompt candidates to a prompt-review bundle
2. require `prompt-reviewer-receipt.json` with PASS before spending API credits
3. call ElevenLabs v3 TTS with a persona voice_id
4. convert MP3 to 24 kHz mono WAV
5. reject obvious literal spoken tags with ASR, for example saying "cough"
6. classify the WAV with the Orpheus audio classifier
7. write every attempt, prompt, settings, ASR result, classifier result, and
   accepted/rejected decision to JSON

The point of the script is prompt search, not a single generation. For each
persona/tag, keep varying the provider prompt and ElevenLabs settings until the
returned sound has the required sonic characteristics:

- `<laugh>`: sustained, higher-energy, repeated transient peaks over a longer
  duration; not a short low-amplitude chuckle
- `<chuckle>`: short, lower-amplitude, restrained laugh event
- `<sigh>`: one smooth exhale-forward sound without repeated transient pulses
- `<sniffle>`: nasal inhale/pull events, often helped by cold-context prompts
  like "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]"
- `<cough>`: sharp throat transients; reject clips that literally say "cough"

This script may start from human-supplied prompt candidates, learned successful
prompts, or future prompt-reviewer/subagent mutations. It preserves which
prompts/settings worked or failed for a persona and tag so later runs can reuse
successful recipes instead of rediscovering them.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
VOICE_SEGMENT_SELECTOR = ROOT / "voice-segment-selector" / "scripts"
if str(VOICE_SEGMENT_SELECTOR) not in sys.path:
    sys.path.insert(0, str(VOICE_SEGMENT_SELECTOR))

from lib.export import _literal_tag_asr_check_clip  # noqa: E402
from lib.orpheus_audio_classifier import classify_audio_file  # noqa: E402
from lib.orpheus_sfx import (  # noqa: E402
    MANIFEST_SCHEMA,
    convert_to_wav24k,
    elevenlabs_generate_voice_tts,
    prompt_review_receipt_status,
    write_json,
)

EXPERIMENT_SCHEMA = "orpheus_tts_voice_trainer.elevenlabs_prompt_experiment.v1"
PROMPT_REVIEW_SCHEMA = "orpheus_tts_voice_trainer.prompt_experiment_review_bundle.v1"

DEFAULT_PROMPTS: dict[str, tuple[str, ...]] = {
    "laugh": (
        "Wait, really?!!!!! [full belly laugh, not a chuckle]",
        "WHAT DO YOU MEAN?!!!!! [full belly laugh, not a chuckle]",
        "WHAT DO YOU MEAN?!!!!! [big open-mouth laugh with repeated HA pulses, not a chuckle]",
        "[cackles!!!!!!] WHAT DO YOU MEAN?!!!!!",
    ),
    "chuckle": (
        "Yeah, sure... [short dry chuckle]",
        "Heh. [quiet restrained chuckle, short amused exhale, not a laugh]",
        "Hmph. [short low dry chuckle, one brief pulse, not a laugh]",
    ),
    "sigh": (
        "Not again... [long smooth exhale sigh, no pulses]",
        "Okay... [long breathy exhale sigh!!!!!! one smooth breath]",
        "I know... [quiet sigh!!!!!! smooth breath out]",
    ),
    "cough": (
        "I've got a bad cold.. [short dry cough!!!!!!]",
        "I've got a bad cold.. [coughing fit, three dry coughs, no spoken word cough!!!!!!]",
        "Continue. [sharp dry cough!!!!!!] Continue.",
    ),
    "sniffle": (
        "I've got a bad cold.. [sniffle!!!!!!]",
        "I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]",
        "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]",
    ),
    "groan": (
        "Not again... [low tired groan!!!!!!]",
        "Ngh. [deep annoyed groan, not a sigh]",
        "Ugh. [long low groan with rough texture]",
    ),
    "yawn": (
        "I'm so tired... [yawn!!!!!!]",
        "I'm so tired... [long open-mouth yawn!!!!!!]",
        "I'm so tired... [sleepy yawn with inhale and exhale!!!!!!]",
    ),
    "gasp": (
        "Oh! [tiny sharp inhale gasp!]",
        "Hah! [sharp startled inhale gasp!!!!!! very short]",
        "What?! [brief hard gasp!!!!!! startled intake]",
    ),
}

MUTATION_PROMPTS: dict[str, tuple[str, ...]] = {
    "laugh": (
        "WHAT DO YOU MEAN?!!!!! [full sustained belly laugh with repeated HA pulses, not a chuckle!!!!!!]",
        "WHAT DO YOU MEAN?!!!!! [cackles!!!!!! full voiced laugh, not a giggle or chuckle]",
        "Wait, really?!!!!! [open-mouth laugh, sustained, several strong peaks, not a chuckle]",
        "[maniacal laugh!!!!!!] WHAT DO YOU MEAN?!!!!!",
    ),
    "chuckle": (
        "Yeah, sure... [short low chuckle, one small pulse, not a laugh]",
        "Heh. [brief restrained chuckle, low amplitude, not sustained]",
        "Hmph. [dry half-second chuckle, not a belly laugh]",
    ),
    "sigh": (
        "Not again... [one smooth tired exhale sigh, no pulses!!!!!!]",
        "Okay... [slow single breath-out sigh, smooth falling envelope!!!!!!]",
        "I know... [quiet resigned sigh, one continuous exhale, not a gasp]",
    ),
    "cough": (
        "I've got a bad cold.. [three sharp dry throat coughs!!!!!! no spoken words]",
        "Continue. [single sharp dry throat cough!!!!!! do not say cough] Continue.",
        "I've got a bad cold.. [short dry coughing sound!!!!!! not the word cough]",
    ),
    "sniffle": (
        "I've got a bad cold.. [sniffle!!!!!!]",
        "I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]",
        "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]",
        "I've got a bad cold.. [three nasal sniffle pulls!!!!!!]",
    ),
    "groan": (
        "Not again... [low rough groan!!!!!! not a sigh]",
        "Ugh. [long voiced groan with strain!!!!!!]",
        "Ngh. [deep tired groan, sustained, not a yawn]",
    ),
    "yawn": (
        "I'm so tired... [yawn!!!!!!]",
        "I'm so tired... [long open-mouth yawn with inhale and exhale!!!!!!]",
        "I'm so tired... [sleepy wide-mouth yawn!!!!!! not a sigh]",
    ),
    "gasp": (
        "Hah! [sharp startled inhale gasp!!!!!! very short]",
        "What?! [brief hard gasp!!!!!! startled intake]",
        "Oh! [tiny sharp inhale gasp!]",
    ),
}


@dataclass(frozen=True)
class AttemptSpec:
    id: str
    prompt: str
    tts_text: str
    voice_settings: dict


def normalize_tag(value: str) -> str:
    tag = value.strip().lower().removeprefix("<").removesuffix(">")
    if tag not in DEFAULT_PROMPTS:
        raise ValueError(f"unsupported tag {value!r}; expected one of {', '.join(DEFAULT_PROMPTS)}")
    return tag


def default_tts_text(prompt: str, tag: str) -> str:
    return re.sub(r"\[[^\]]+\]", f"<{tag}>", prompt)


def load_prompt_lines(args: argparse.Namespace, tag: str) -> list[str]:
    prompts: list[str] = []
    prompts.extend(args.prompt or [])
    if args.prompts_file:
        prompts.extend(
            line.strip()
            for line in args.prompts_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not prompts:
        prompts.extend(DEFAULT_PROMPTS[tag])
    return prompts


def build_prompt_plan(*, tag: str, seeds: list[str], max_attempts: int) -> list[str]:
    prompts: list[str] = []
    seen: set[str] = set()
    for prompt in [*seeds, *MUTATION_PROMPTS[tag], *DEFAULT_PROMPTS[tag]]:
        clean = prompt.strip()
        if not clean or clean in seen:
            continue
        prompts.append(clean)
        seen.add(clean)
        if len(prompts) >= max_attempts:
            break
    return prompts


def build_attempts(*, persona: str, tag: str, prompts: list[str]) -> list[AttemptSpec]:
    settings_grid = (
        {"stability": 0.25, "similarity_boost": 0.75, "style": 0.55, "use_speaker_boost": True},
        {"stability": 0.30, "similarity_boost": 0.70, "style": 0.40, "use_speaker_boost": True},
        {"stability": 0.20, "similarity_boost": 0.80, "style": 0.65, "use_speaker_boost": True},
    )
    attempts: list[AttemptSpec] = []
    for index, prompt in enumerate(prompts, start=1):
        attempts.append(
            AttemptSpec(
                id=f"{persona}_{tag}_prompt_{index:04d}",
                prompt=prompt,
                tts_text=default_tts_text(prompt, tag),
                voice_settings=settings_grid[(index - 1) % len(settings_grid)],
            )
        )
    return attempts


def write_prompt_review_bundle(*, path: Path, persona: str, tag: str, voice_id: str, attempts: list[AttemptSpec]) -> None:
    write_json(
        path,
        {
            "schema": PROMPT_REVIEW_SCHEMA,
            "created_at": datetime.now(UTC).isoformat(),
            "persona": persona,
            "tag": f"<{tag}>",
            "voice_id": voice_id,
            "policy": {
                "no_elevenlabs_generation_before_pass": True,
                "reject_prompts_that_speak_event_word_literally": True,
                "prompts_must_use_elevenlabs_v3_audio_tags": True,
            },
            "expected_response_schema": {
                "verdict": "PASS | NEEDS_CHANGES | BLOCKED",
                "rejected_prompt_ids": ["string"],
                "required_edits": [{"prompt_id": "string", "replacement_prompt": "string", "reason": "string"}],
            },
            "prompts": [
                {
                    "id": attempt.id,
                    "provider_prompt": attempt.prompt,
                    "training_tts_text": attempt.tts_text,
                    "voice_settings": attempt.voice_settings,
                }
                for attempt in attempts
            ],
        },
    )


def generate_voice_tts_with_settings(
    *,
    text: str,
    voice_id: str,
    api_key: str,
    output_path: Path,
    model_id: str,
    voice_settings: dict,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = {
        "model_id": model_id,
        "text": text,
        "voice_settings": voice_settings,
    }
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        response = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json=request,
        )
    if response.status_code != 200:
        return {
            "status": "error",
            "status_code": response.status_code,
            "error": response.text[:1000],
            "endpoint": "text-to-speech",
            "voice_id": voice_id,
            "request": request,
        }
    output_path.write_bytes(response.content)
    return {
        "status": "ok",
        "status_code": response.status_code,
        "bytes": output_path.stat().st_size,
        "endpoint": "text-to-speech",
        "voice_id": voice_id,
        "request": request,
    }


def run(args: argparse.Namespace) -> dict:
    persona = args.persona.strip().lower()
    tag = normalize_tag(args.tag)
    job_dir = args.job_dir.expanduser().resolve()
    raw_dir = job_dir / "raw_mp3"
    wav_dir = job_dir / "wav24k"
    review_dir = job_dir / "prompt-review"
    review_path = review_dir / "prompt_review_bundle.json"
    report_path = job_dir / "prompt-experiment-report.json"
    prompts = build_prompt_plan(tag=tag, seeds=load_prompt_lines(args, tag), max_attempts=args.max_attempts)
    attempts = build_attempts(persona=persona, tag=tag, prompts=prompts)
    write_prompt_review_bundle(path=review_path, persona=persona, tag=tag, voice_id=args.voice_id, attempts=attempts)

    base_report = {
        "schema": EXPERIMENT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "persona": persona,
        "tag": f"<{tag}>",
        "voice_id": args.voice_id,
        "model_id": args.model_id,
        "job_dir": str(job_dir),
        "prompt_review_bundle": str(review_path),
        "attempt_count_planned": len(attempts),
        "loop_policy": {
            "mode": "preplanned_prompt_mutation_loop",
            "reason": "all prompt mutations must be prompt-reviewed before paid ElevenLabs generation",
            "stop_on_first_accept": args.stop_on_first_accept,
        },
        "attempts": [],
    }
    if args.dry_run:
        base_report["status"] = "DRY_RUN"
        base_report["attempts"] = [asdict(attempt) for attempt in attempts]
        write_json(report_path, base_report)
        return base_report | {"report_path": str(report_path)}

    review_status = prompt_review_receipt_status(review_dir, review_path)
    if not review_status.get("ok"):
        base_report["status"] = "BLOCKED"
        base_report["blocker"] = "prompt_review_required"
        base_report["prompt_review_status"] = review_status
        base_report["attempts"] = [asdict(attempt) for attempt in attempts]
        write_json(report_path, base_report)
        return base_report | {"report_path": str(report_path)}

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        base_report["status"] = "BLOCKED"
        base_report["blocker"] = "ELEVENLABS_API_KEY_missing"
        write_json(report_path, base_report)
        return base_report | {"report_path": str(report_path)}

    accepted = []
    records = []
    for attempt in attempts:
        mp3_path = raw_dir / f"{attempt.id}.mp3"
        wav_path = wav_dir / f"{attempt.id}.wav"
        generation = generate_voice_tts_with_settings(
            text=attempt.prompt,
            voice_id=args.voice_id,
            api_key=api_key,
            output_path=mp3_path,
            model_id=args.model_id,
            voice_settings=attempt.voice_settings,
        )
        record = {
            "id": attempt.id,
            "prompt": attempt.prompt,
            "tts_text": attempt.tts_text,
            "voice_settings": attempt.voice_settings,
            "generation": generation,
        }
        if generation.get("status") == "ok":
            conversion = convert_to_wav24k(mp3_path, wav_path)
            record["conversion"] = conversion
            if conversion.get("status") == "ok":
                literal = _literal_tag_asr_check_clip(wav_path, [f"<{tag}>"], attempt.tts_text)
                classification = classify_audio_file(
                    wav_path,
                    expected_tag=f"<{tag}>",
                    source_type="elevenlabs_voice_context",
                    use_ast=not args.no_ast,
                )
                record["wav_path"] = str(wav_path)
                record["literal_tag_asr_check"] = literal
                record["classification"] = classification
                record["decision"] = (
                    "accept"
                    if literal.get("status") == "PASS" and classification.get("decision") == "accept"
                    else "reject"
                )
                record["reject_reasons"] = []
                if literal.get("status") != "PASS":
                    record["reject_reasons"].append(literal.get("reason", "literal_tag_asr_failed"))
                if classification.get("decision") != "accept":
                    record["reject_reasons"].extend(classification.get("reasons", []))
                if record["decision"] == "accept":
                    accepted.append(record["id"])
        records.append(record)
        if accepted and args.stop_on_first_accept:
            break

    base_report["status"] = "PASS" if accepted else "NO_ACCEPTED_PROMPT"
    base_report["accepted_attempt_ids"] = accepted
    base_report["attempts"] = records
    base_report["manifest_schema"] = MANIFEST_SCHEMA
    write_json(report_path, base_report)
    return base_report | {"report_path": str(report_path)}


def self_test() -> None:
    sniffle_prompt = "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]"
    assert default_tts_text(sniffle_prompt, "sniffle") == "I've got a bad cold.. <sniffle>"
    sniffle_plan = build_prompt_plan(tag="sniffle", seeds=[sniffle_prompt], max_attempts=4)
    assert sniffle_plan[0] == sniffle_prompt
    assert "I've got a bad cold.. [sniffle!!!!!!]" in sniffle_plan
    assert "I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]" in sniffle_plan
    laugh_plan = build_prompt_plan(
        tag="laugh",
        seeds=["Wait, really?!!!!! [full belly laugh, not a chuckle]"],
        max_attempts=3,
    )
    assert laugh_plan[0] == "Wait, really?!!!!! [full belly laugh, not a chuckle]"
    assert any("sustained" in prompt or "cackles" in prompt for prompt in laugh_plan[1:])
    attempts = build_attempts(persona="embry", tag="sniffle", prompts=sniffle_plan)
    assert attempts[0].tts_text == "I've got a bad cold.. <sniffle>"
    assert attempts[0].voice_settings != attempts[1].voice_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona")
    parser.add_argument("--tag")
    parser.add_argument("--voice-id")
    parser.add_argument("--job-dir", type=Path)
    parser.add_argument("--prompt", action="append", help="Repeat for explicit provider prompts")
    parser.add_argument("--prompts-file", type=Path)
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--model-id", default="eleven_v3")
    parser.add_argument("--api-key")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-ast", action="store_true")
    parser.add_argument("--stop-on-first-accept", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"status": "PASS", "self_test": True}, indent=2))
        return
    missing = [name for name in ("persona", "tag", "voice_id", "job_dir") if getattr(args, name) in (None, "")]
    if missing:
        parser.error(f"missing required arguments unless --self-test is used: {', '.join(missing)}")
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
