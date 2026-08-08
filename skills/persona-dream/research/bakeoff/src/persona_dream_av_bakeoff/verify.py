"""verify - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .fal_utils import subscribe
from .io_utils import write_json
from .media import download, ffprobe_duration_seconds, sha256_file


def normalize_text(text: str) -> str:
    chars: list[str] = []
    for ch in text.lower():
        if ch.isalnum() or ch.isspace():
            chars.append(ch)
    return " ".join("".join(chars).split())


def similarity(expected: str, actual: str) -> float:
    return difflib.SequenceMatcher(None, normalize_text(expected), normalize_text(actual)).ratio()


def transcribe(url: str, *, model_id: str = "fal-ai/whisper", with_logs: bool = True) -> dict[str, Any]:
    return subscribe(
        model_id,
        {
            "audio_url": url,
            "task": "transcribe",
            "language": "en",
            "chunk_level": "word",
        },
        with_logs=with_logs,
    )


def verify_lane(
    *,
    lane: str,
    contract: dict[str, Any],
    shot: dict[str, Any],
    base_video: dict[str, Any],
    tts: dict[str, Any],
    lipsync: dict[str, Any],
    out_dir: str | Path,
    with_logs: bool = True,
) -> dict[str, Any]:
    lane_dir = Path(out_dir)
    media_dir = lane_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    audio_url = tts["audio_url"]
    final_video_url = lipsync["video_url"]
    base_video_url = base_video["video_url"]

    audio_path = download(audio_url, media_dir, f"{lane}_audio")
    base_video_path = download(base_video_url, media_dir, "shared_base_video.mp4")
    final_video_path = download(final_video_url, media_dir, f"{lane}_lipsync_video.mp4")

    audio_duration = ffprobe_duration_seconds(audio_path)
    base_video_duration = ffprobe_duration_seconds(base_video_path)
    final_video_duration = ffprobe_duration_seconds(final_video_path)

    expected_dialogue = shot["dialogue"]
    audio_asr = transcribe(audio_url, with_logs=with_logs)
    final_asr = transcribe(final_video_url, with_logs=with_logs)

    audio_text = audio_asr.get("text", "")
    final_text = final_asr.get("text", "")

    audio_sim = similarity(expected_dialogue, audio_text)
    final_sim = similarity(expected_dialogue, final_text)

    checks: dict[str, bool | None] = {
        "contract_has_source_residue_ids": bool(shot.get("source_grounded_residue_ids")),
        "contract_declares_audio_first": bool(shot.get("audio_first")),
        "contract_declares_lipsync_required": bool(shot.get("lip_sync_required")),
        "audio_url_present": bool(audio_url),
        "final_video_url_present": bool(final_video_url),
        "audio_transcript_similarity_ge_0_82": audio_sim >= 0.82,
        "final_video_transcript_similarity_ge_0_82": final_sim >= 0.82,
        "audio_duration_known": audio_duration is not None,
        "base_video_duration_known": base_video_duration is not None,
        "final_video_duration_known": final_video_duration is not None,
    }

    if audio_duration is not None and base_video_duration is not None:
        checks["audio_fits_inside_base_video_plus_350ms"] = audio_duration <= base_video_duration + 0.35
        checks["audio_duration_min_2s_for_kling"] = audio_duration >= 2.0

    if audio_duration is not None and final_video_duration is not None:
        checks["final_duration_close_to_audio_1250ms"] = abs(final_video_duration - audio_duration) <= 1.25

    hard_keys = [
        "contract_has_source_residue_ids",
        "contract_declares_audio_first",
        "contract_declares_lipsync_required",
        "audio_url_present",
        "final_video_url_present",
        "audio_transcript_similarity_ge_0_82",
        "final_video_transcript_similarity_ge_0_82",
    ]
    duration_keys = [
        "audio_duration_known",
        "base_video_duration_known",
        "final_video_duration_known",
        "audio_fits_inside_base_video_plus_350ms",
        "audio_duration_min_2s_for_kling",
        "final_duration_close_to_audio_1250ms",
    ]

    hard_pass = all(checks.get(k) is True for k in hard_keys)
    duration_pass = all(checks.get(k) is True for k in duration_keys if k in checks)
    machine_verdict = "pass" if hard_pass and duration_pass else ("needs_review" if hard_pass else "fail")

    receipt = {
        "schema_version": "persona_dream_av_lane_receipt.v0.2",
        "lane": lane,
        "machine_verdict": machine_verdict,
        "contract_experiment_id": contract.get("experiment_id"),
        "shot_id": shot["shot_id"],
        "urls": {
            "audio_url": audio_url,
            "base_video_url": base_video_url,
            "lipsync_video_url": final_video_url,
        },
        "local_files": {
            "audio_path": str(audio_path),
            "base_video_path": str(base_video_path),
            "lipsync_video_path": str(final_video_path),
            "audio_sha256": sha256_file(audio_path),
            "base_video_sha256": sha256_file(base_video_path),
            "lipsync_video_sha256": sha256_file(final_video_path),
        },
        "durations_sec": {
            "audio": audio_duration,
            "base_video": base_video_duration,
            "lipsync_video": final_video_duration,
            "audio_minus_base": (
                None if audio_duration is None or base_video_duration is None else audio_duration - base_video_duration
            ),
            "final_minus_audio": (
                None if final_video_duration is None or audio_duration is None else final_video_duration - audio_duration
            ),
        },
        "dialogue": {
            "expected": expected_dialogue,
            "audio_asr_text": audio_text,
            "final_video_asr_text": final_text,
            "audio_similarity": audio_sim,
            "final_video_similarity": final_sim,
        },
        "checks": checks,
        "manual_review_template": {
            "voice_persona_fit_1_to_5": None,
            "lip_sync_quality_1_to_5": None,
            "mouth_visible_entire_line": None,
            "visual_lore_drift": None,
            "notes": "",
        },
        "no_write_assertions": {
            "memory_write": False,
            "arango_upsert": False,
            "qdrant_upsert": False,
        },
    }

    write_json(lane_dir / "lane_receipt.json", receipt)
    return receipt


def compare_lanes(lane_receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # Machine-only score. Manual visual review can override.
    scores: dict[str, float] = {}
    for lane, receipt in lane_receipts.items():
        dialogue = receipt.get("dialogue", {})
        durations = receipt.get("durations_sec", {})
        checks = receipt.get("checks", {})

        score = 0.0
        score += 40.0 * float(dialogue.get("final_video_similarity", 0.0))
        score += 25.0 * float(dialogue.get("audio_similarity", 0.0))

        final_minus_audio = durations.get("final_minus_audio")
        if isinstance(final_minus_audio, (int, float)):
            score += max(0.0, 20.0 - min(abs(final_minus_audio), 2.0) * 10.0)

        audio_minus_base = durations.get("audio_minus_base")
        if isinstance(audio_minus_base, (int, float)):
            # Penalize audio longer than base video; small negative gap is okay.
            score += max(0.0, 10.0 - max(0.0, audio_minus_base) * 10.0)

        if receipt.get("machine_verdict") == "pass":
            score += 5.0
        elif receipt.get("machine_verdict") == "needs_review":
            score += 2.0

        if not checks.get("audio_fits_inside_base_video_plus_350ms", True):
            score -= 15.0

        scores[lane] = round(score, 3)

    winner = None
    if scores:
        winner = sorted(scores.items(), key=lambda x: x[1], reverse=True)[0][0]

    return {
        "machine_scores": scores,
        "machine_winner": winner,
        "manual_review_can_override": True,
        "scoring_notes": [
            "Machine score heavily weights final-video ASR similarity and duration fit.",
            "It does not judge voice persona fit or visual lip-sync realism.",
            "Use manual_review_template fields before choosing production backend.",
        ],
    }
