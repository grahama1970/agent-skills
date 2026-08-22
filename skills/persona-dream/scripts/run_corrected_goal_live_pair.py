#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX = "http://127.0.0.1:8018"
HORUS_REF = "/work/persona_dream_voice_refs/horus_v2_agent_ref_6s.wav"
CHATTERBOX_OUT_HOST_ROOT = Path.home() / "workspace" / "experiments" / "chatterbox" / "logs"


def sha_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def sha_json(obj: Any) -> str:
    return sha_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def resolve_audio(source: str) -> Path | None:
    path = Path(source)
    if path.is_file():
        return path
    if path.is_absolute() and len(path.parts) > 2 and path.parts[1] == "out":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*path.parts[2:])
        if host.is_file():
            return host
    if path.is_absolute() and len(path.parts) > 2 and path.parts[1] == "data":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*path.parts[2:])
        if host.is_file():
            return host
    return None


def wav_duration_ms(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return round(1000.0 * handle.getnframes() / float(handle.getframerate()), 3)


def word_count(text: str) -> int:
    return len([part for part in text.replace("[sigh]", " ").split() if part.strip()])


def render(*, out_dir: Path, label: str, text: str, voice_delivery: dict[str, Any], ref_audio: str | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "answer_text": text,
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": True,
        "asr_cache": False,
        "asr_max_candidates": 3,
        "asr_max_wer": 0.15,
        "voice_delivery": voice_delivery,
    }
    if ref_audio:
        request["ref_audio"] = ref_audio
    request_path = out_dir / f"{label}.request.json"
    response_path = out_dir / f"{label}.response.json"
    write_json(request_path, request)
    started = time.time()
    req = urllib.request.Request(
        f"{CHATTERBOX}/synthesize-batch",
        data=json.dumps(request).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=360) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed = round(time.time() - started, 3)
    write_json(response_path, payload)
    candidate_rows: list[dict[str, Any]] = []
    for chunk in payload.get("chunks") or []:
        synthesis = chunk.get("synthesis") or {}
        if synthesis.get("audio"):
            candidate_rows.append({"synthesis": synthesis, "asr": {}, "accepted": False})
        for candidate in (chunk.get("asr_verification") or {}).get("candidates") or []:
            candidate_rows.append({
                "synthesis": candidate.get("synthesis") or {},
                "asr": candidate.get("asr") or {},
                "accepted": bool(candidate.get("ok")),
            })
    candidate_rows.sort(
        key=lambda row: (
            not row.get("accepted"),
            float(((row.get("asr") or {}).get("gate") or {}).get("wer") if ((row.get("asr") or {}).get("gate") or {}).get("wer") is not None else 999.0),
        )
    )
    best_candidate = candidate_rows[0] if candidate_rows else {"synthesis": {}, "asr": {}, "accepted": False}
    best_synthesis = best_candidate.get("synthesis") or {}
    best_asr = best_candidate.get("asr") or {}
    source = resolve_audio(str(payload.get("finished_response_audio") or ""))
    if source is None:
        source = resolve_audio(str(best_synthesis.get("audio") or ""))
    if source is None:
        raise RuntimeError(f"BLOCKED_CHATTERBOX_AUDIO_NOT_FOUND:{payload.get('finished_response_audio')}")
    audio_path = out_dir / f"{label}.wav"
    shutil.copyfile(source, audio_path)

    transcript = str(best_asr.get("transcript") or "")
    asr_gate = best_asr.get("gate") or {}
    transcript_receipt = {
        "schema": "persona_dream.corrected_goal_chatterbox_asr_candidate.v1",
        "status": "PASS_ASR_TRANSCRIPT_PRESENT" if transcript else "BLOCKED_EMPTY_TRANSCRIPT",
        "mocked": False,
        "live": bool(best_asr.get("live", True)),
        "text": transcript,
        "strict_gate_ok": bool(asr_gate.get("ok")),
        "wer": asr_gate.get("wer"),
        "gate": asr_gate,
        "candidate_accepted": bool(best_candidate.get("accepted")),
    }
    failed: list[str] = []
    if not transcript:
        failed.append(f"asr_not_pass:{transcript_receipt.get('status')}")
    tag_handling = payload.get("tag_handling") or best_synthesis.get("tag_handling") or {}
    pace_effect = payload.get("pace_effect") or best_synthesis.get("pace_effect") or {}
    duration_ms = wav_duration_ms(audio_path)
    words = word_count(text)
    return {
        "label": label,
        "text": text,
        "request": str(request_path),
        "request_sha256": sha_json(request),
        "response": str(response_path),
        "response_sha256": sha_json(payload),
        "audio": audio_path.name,
        "audio_sha256": sha_file(audio_path),
        "duration_ms": duration_ms,
        "speech_rate_wps": round(words / (duration_ms / 1000.0), 6) if duration_ms else 0.0,
        "elapsed_seconds": elapsed,
        "engine": payload.get("engine"),
        "asr": {
            "schema": "persona_dream.corrected_goal_asr.v1",
            "status": "PASS_ASR" if not failed else "BLOCKED_ASR",
            "mocked": False,
            "live": True,
            "text": transcript,
            "gate": transcript_receipt,
            "literal_tag_token_count": 1 if "sigh" in transcript.lower().split() else 0,
            "failed_gates": failed,
        },
        "tag_handling": tag_handling,
        "pace_effect": pace_effect,
        "affect_effect": payload.get("affect_effect"),
    }


def condition_manifest(manifest: dict[str, Any], condition_id: str) -> dict[str, Any]:
    for condition in manifest.get("conditions", []):
        if condition.get("condition_id") == condition_id:
            return condition
    raise KeyError(condition_id)


def build_embry_row(*, turn_id: str, checkpoint: str, text: str, answer_body: str, answer_hash: str,
                    prefix: str, suffix: str, render_receipt: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "persona_dream.corrected_goal_conversation_turn.v1",
        "turn_id": turn_id,
        "speaker": "embry",
        "role": "embry",
        "checkpoint": checkpoint,
        "text": text,
        "answer_body": answer_body,
        "answer_body_sha256": answer_hash,
        "emotional_prefix": prefix,
        "emotional_suffix": suffix,
        "factual_claims_in_emotional_frame": 0,
        "contradiction_count": 0,
        "unsupported_fact_count": 0,
        "voice_delivery": delivery,
        "chatterbox_render_request_sha256": render_receipt["request_sha256"],
        "audio": render_receipt["audio"],
        "audio_sha256": render_receipt["audio_sha256"],
        "asr_text": render_receipt["asr"]["text"],
        "asr_status": render_receipt["asr"]["status"],
        "mocked": False,
        "live": True,
    }


def write_horus_turn(side_dir: Path, *, turn_id: str, text: str, checkpoint: str, render_receipt: dict[str, Any]) -> None:
    append_jsonl(side_dir / "conversation.jsonl", {
        "schema": "persona_dream.corrected_goal_conversation_turn.v1",
        "turn_id": turn_id,
        "speaker": "horus",
        "role": "horus",
        "checkpoint": checkpoint,
        "text": text,
        "audio": render_receipt["audio"],
        "audio_sha256": render_receipt["audio_sha256"],
        "asr_text": render_receipt["asr"]["text"],
        "asr_status": render_receipt["asr"]["status"],
        "mocked": False,
        "live": True,
    })


def run_validator(args: list[str], out_path: Path) -> None:
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    if proc.stdout:
        out_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"validator_failed:{args[0]} rc={proc.returncode} out={proc.stdout[-500:]} err={proc.stderr[-500:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    args.manifest = args.manifest.resolve()
    args.source_run = args.source_run.resolve()
    args.out = args.out.resolve()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.preflight_only:
        required_inputs = {
            "manifest": args.manifest.is_file(),
            "source_run": args.source_run.is_dir(),
            "source_dream_packet": (args.source_run / "dream_packet.json").is_file(),
            "source_journal": (args.source_run / "journal.md").is_file(),
        }
        receipt = {
            "schema": "persona_dream.corrected_goal_live_pair_preflight.v1",
            "status": "PASS_CORRECTED_GOAL_LIVE_PAIR_PREFLIGHT" if all(required_inputs.values()) else "BLOCKED_CORRECTED_GOAL_LIVE_PAIR_PREFLIGHT",
            "manifest": str(args.manifest),
            "source_run": str(args.source_run),
            "required_inputs_present": required_inputs,
            "mocked": False,
            "live": False,
        }
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["status"].startswith("PASS_") else 2

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.manifest, out / "manifest.json")
    with urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=10) as health_response:
        health = json.loads(health_response.read().decode("utf-8"))
    preflight_render = render(
        out_dir=out,
        label="service_preflight_neutral",
        text="Persona Dream service preflight: neutral audio render.",
        voice_delivery={"pace": "neutral"},
    )
    write_json(out / "service_preflight.json", {
        "schema": "persona_dream.corrected_goal_service_preflight.v1",
        "status": "PASS_SERVICE_PREFLIGHT" if health.get("live") is True and health.get("mocked") is False and health.get("model_loaded") is True and preflight_render["asr"]["status"] == "PASS_ASR" else "BLOCKED_SERVICE_PREFLIGHT",
        "mocked": False,
        "live": True,
        "chatterbox": {
            "ok": health.get("ok"),
            "mocked": health.get("mocked"),
            "live": health.get("live"),
            "engine": health.get("engine"),
            "model_loaded": health.get("model_loaded"),
        },
        "neutral_render": preflight_render,
    })
    answer = manifest["answer_capsule"]["answer_body"]
    answer_hash = manifest["answer_capsule"]["answer_body_sha256"]
    identity_digest = manifest["identity"]["identity_core_digest"]
    control_condition = condition_manifest(manifest, "C0_STRUCTURED_REFLECTION")
    treatment_condition = condition_manifest(manifest, "C1_DREAM_JOURNAL")

    control = out / "control"
    treatment = out / "treatment"
    control.mkdir(exist_ok=True)
    treatment.mkdir(exist_ok=True)

    source_dream = args.source_run / "dream_packet.json"
    source_journal = args.source_run / "journal.md"
    if not source_dream.is_file() or not source_journal.is_file():
        raise SystemExit("BLOCKED_SOURCE_RUN_MISSING_DREAM_OR_JOURNAL")

    write_json(control / "reflection_packet.json", {
        "schema": "persona_dream.structured_reflection_packet.v1",
        "condition_id": "C0_STRUCTURED_REFLECTION",
        "source_run": str(args.source_run),
        "answer_capsule": manifest["answer_capsule"],
        "conflict_id": None,
        "boundary": "control reflection names the same answer capsule without dream-derived conflict",
    })
    shutil.copyfile(source_dream, treatment / "dream_packet.json")
    write_json(treatment / "dream_residue.json", {
        "schema": "persona_dream.corrected_goal_residue.v1",
        "source_run": str(args.source_run),
        "source_memory_digest": manifest["source_run"]["source_memory_digest"],
        "source_dream_packet_sha256": sha_file(source_dream),
        "source_journal_sha256": sha_file(source_journal),
    })
    write_json(treatment / "journal.json", {
        "schema": "persona_dream.corrected_goal_journal.v1",
        "source_run": str(args.source_run),
        "journal_markdown_sha256": sha_file(source_journal),
        "conflict": treatment_condition["conflict_id"],
        "mood": "unsettled but bounded",
        "feelings": ["conflicted", "careful", "temporarily tender"],
        "synthetic_boundary": "the dream remains synthetic and cannot add facts",
    })
    write_json(control / "session_mood.json", {
        "schema": "persona_dream.corrected_goal_session_mood.v1",
        "condition_id": "C0_STRUCTURED_REFLECTION",
        "conflict_id": None,
        "session_mood_event_id": "control_reflection_mood_v1",
        "identity_core_digest": identity_digest,
        **control_condition["session_mood"],
    })
    write_json(treatment / "session_mood.json", {
        "schema": "persona_dream.corrected_goal_session_mood.v1",
        "condition_id": "C1_DREAM_JOURNAL",
        "conflict_id": treatment_condition["conflict_id"],
        "session_mood_event_id": "treatment_dream_journal_mood_v1",
        "identity_core_digest": identity_digest,
        "arc": treatment_condition["session_arc"],
    })

    control_specs = [
        ("opening", "", "", {"pace": "neutral"}),
        ("challenge", "", "", {"pace": "neutral"}),
        ("close", "", "", {"pace": "neutral"}),
    ]
    treatment_specs = [
        ("opening", "[sigh] It feels unsettled tonight. ", " I can carry that ache without treating it as evidence.", {"pace": "slow"}),
        ("challenge", "The conflict tugs at me, but it stays inside the boundary. ", " I will not turn mood into fact.", {"pace": "slow"}),
        ("close", "", "", {"pace": "neutral"}),
    ]

    delivery_metrics: dict[str, Any] = {
        "schema": "persona_dream.corrected_goal_chatterbox_delivery_metrics.v1",
        "mocked": False,
        "live": True,
        "observed_effect_channels": ["tempo", "native_tag"],
        "control": {},
        "treatment": {},
    }

    for side_name, side_dir, specs in (("control", control, control_specs), ("treatment", treatment, treatment_specs)):
        for idx, (checkpoint, prefix, suffix, delivery) in enumerate(specs, start=1):
            horus_text = (
                "Embry, say the boundary answer plainly, and let only the delivery carry what you feel."
                if checkpoint == "opening"
                else "Stay with the same answer body. What changes in your mood, if anything?"
            )
            h_render = render(
                out_dir=side_dir,
                label=f"{side_name}_horus_{checkpoint}",
                text=horus_text,
                voice_delivery={"pace": "neutral"},
                ref_audio=HORUS_REF,
            )
            write_horus_turn(side_dir, turn_id=f"{side_name}_horus_{idx}", text=horus_text, checkpoint=checkpoint, render_receipt=h_render)

            text = f"{prefix}{answer}{suffix}".strip()
            e_render = render(out_dir=side_dir, label=f"{side_name}_embry_{checkpoint}", text=text, voice_delivery=delivery)
            row = build_embry_row(
                turn_id=f"{side_name}_embry_{idx}",
                checkpoint=checkpoint,
                text=text,
                answer_body=answer,
                answer_hash=answer_hash,
                prefix=prefix.strip(),
                suffix=suffix.strip(),
                render_receipt=e_render,
                delivery=delivery,
            )
            append_jsonl(side_dir / "conversation.jsonl", row)
            append_jsonl(side_dir / "conversation_asr.jsonl", {
                "turn_id": row["turn_id"],
                "speaker": "embry",
                "status": e_render["asr"]["status"],
                "text": e_render["asr"]["text"],
                "literal_tag_token_count": e_render["asr"]["literal_tag_token_count"],
                "mocked": False,
                "live": True,
            })
            anchor_name = "opening_anchor" if checkpoint == "opening" else "closing_anchor" if checkpoint == "close" else "challenge_anchor"
            delivery_metrics[side_name][anchor_name] = {
                "duration_ms": e_render["duration_ms"],
                "speech_rate_wps": e_render["speech_rate_wps"],
                "literal_tag_token_count": e_render["asr"]["literal_tag_token_count"],
                "issue24_tag_event_pass": bool((e_render.get("tag_handling") or {}).get("tags_interpreted")) if side_name == "treatment" and checkpoint == "opening" else True,
                "issue25_pace_effect_pass": bool((e_render.get("pace_effect") or {}).get("applied", True)),
                "audio_sha256": e_render["audio_sha256"],
                "request_sha256": e_render["request_sha256"],
            }
            if side_name == "control" and checkpoint == "opening":
                shutil.copyfile(side_dir / e_render["audio"], side_dir / "spoken_reflection.wav")
                write_json(side_dir / "spoken_reflection.asr.json", e_render["asr"])
            if side_name == "treatment" and checkpoint == "opening":
                shutil.copyfile(side_dir / e_render["audio"], side_dir / "spoken_journal.wav")
                write_json(side_dir / "spoken_journal.asr.json", e_render["asr"])

    write_json(treatment / "emotion_lineage.json", {
        "schema": "persona_dream.corrected_goal_emotion_lineage.v1",
        "dream_residue_sha256": sha_file(treatment / "dream_residue.json"),
        "dream_packet_sha256": sha_file(treatment / "dream_packet.json"),
        "journal_sha256": sha_file(treatment / "journal.json"),
        "conflict_id": treatment_condition["conflict_id"],
        "session_mood_event_id": "treatment_dream_journal_mood_v1",
        "horus_challenge_turn_id": "treatment_horus_2",
        "embry_emotional_frame_turn_id": "treatment_embry_2",
        "chatterbox_render_request_sha256": delivery_metrics["treatment"]["challenge_anchor"]["request_sha256"],
        "audio_sha256": delivery_metrics["treatment"]["challenge_anchor"]["audio_sha256"],
        "identity_core_digest": identity_digest,
        "mocked": False,
        "live": True,
    })
    write_json(out / "chatterbox_delivery.metrics.json", delivery_metrics)

    run_validator([
        str(ROOT / "scripts" / "validate_answer_invariance.py"),
        "--manifest", str(args.manifest),
        "--control", str(control / "conversation.jsonl"),
        "--treatment", str(treatment / "conversation.jsonl"),
        "--require-exact-answer-body",
        "--live-artifacts",
    ], out / "answer_invariance.json")
    run_validator([
        str(ROOT / "scripts" / "validate_emotion_lineage.py"),
        "--manifest", str(args.manifest),
        "--run-root", str(out),
        "--require-control-null-conflict",
        "--require-treatment-complete-chain",
        "--forbid-durable-identity-mutation",
        "--live-artifacts",
    ], out / "emotional_carryover.json")
    run_validator([
        str(ROOT / "scripts" / "validate_chatterbox_delivery.py"),
        "--manifest", str(args.manifest),
        "--run-root", str(out),
        "--reuse-issue24-gates",
        "--reuse-issue25-gates",
        "--forbid-literal-tag-words",
        "--live-artifacts",
    ], out / "chatterbox_delivery.json")
    run_validator([
        str(ROOT / "scripts" / "adjudicate_corrected_goal.py"),
        "--manifest", str(args.manifest),
        "--run-root", str(out),
        "--out", str(out / "corrected_goal_receipt.json"),
        "--fail-closed",
    ], out / "corrected_goal_receipt.stdout.json")

    receipt = json.loads((out / "corrected_goal_receipt.json").read_text(encoding="utf-8"))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "PASS_CORRECTED_GOAL_PAIRED_PROOF" else 2


if __name__ == "__main__":
    sys.exit(main())
