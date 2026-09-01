#!/usr/bin/env python3
"""Render the blinded listener-study stimuli under one normalization policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
DEFAULT_STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get("CHATTERBOX_OUT_HOST_ROOT", "/home/graham/workspace/experiments/chatterbox/logs")
)
DEFAULT_REF_AUDIO = "/data/embry_ref.wav"
OUTPUT_NORMALIZATION_POLICY = {
    "schema": "persona_dream.output_normalization_policy.v1",
    "name": "ffmpeg_loudnorm_i27_tp2_lra7_pcm16_v1",
    "tool": "ffmpeg",
    "filter": "loudnorm=I=-27:TP=-2:LRA=7",
    "codec": "pcm_s16le",
    "sample_rate": 24000,
    "channels": 1,
    "scope": "applied identically to every target condition after live Chatterbox render",
}
ASR_MAX_WER = 0.08
ASR_MAX_DURATION_RATIO = 10.0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_bundle_path(raw: str | None, *, study_dir: Path) -> Path:
    if not isinstance(raw, str) or not raw:
        return Path("")
    path = Path(raw)
    if path.is_absolute():
        return path
    if raw.startswith("reports/"):
        return ROOT / raw
    return study_dir / raw


def resolve_host_audio(source: str) -> Path | None:
    if not source:
        return None
    path = Path(source)
    if path.is_file():
        return path
    if path.is_absolute() and len(path.parts) > 2 and path.parts[1] == "out":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*path.parts[2:])
        if host.is_file():
            return host
    return None


def post_json(url: str, payload: dict[str, Any], timeout: int = 900) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_text(text: str | None) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split())


def accepted_asr(response: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    chunks = response.get("chunks") or []
    if not chunks:
        return response.get("asr_transcript"), response.get("asr_gate")
    transcripts: list[str] = []
    gate: dict[str, Any] | None = None
    for chunk in chunks:
        verification = chunk.get("asr_verification") or {}
        candidates = verification.get("candidates") or []
        idx = verification.get("accepted_candidate_index")
        if idx is None:
            idx = 0
        accepted = candidates[idx] if 0 <= idx < len(candidates) else (candidates[0] if candidates else {})
        asr = accepted.get("asr") or {}
        transcript = asr.get("transcript")
        if transcript:
            transcripts.append(str(transcript))
        gate = asr.get("gate") or gate
    return " ".join(transcripts).strip() or response.get("asr_transcript"), gate


def parse_norm_loudness(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("--norm-loudness must be true or false")


def normalize_wav(raw_audio: Path, final_audio: Path) -> dict[str, Any]:
    final_audio.parent.mkdir(parents=True, exist_ok=True)
    if final_audio.exists():
        final_audio.unlink()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(raw_audio),
        "-af",
        OUTPUT_NORMALIZATION_POLICY["filter"],
        "-ar",
        str(OUTPUT_NORMALIZATION_POLICY["sample_rate"]),
        "-ac",
        str(OUTPUT_NORMALIZATION_POLICY["channels"]),
        "-c:a",
        str(OUTPUT_NORMALIZATION_POLICY["codec"]),
        str(final_audio),
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def prereg_paths(study_dir: Path) -> list[Path]:
    return [path for path in (study_dir / "PREREGISTRATION.json", study_dir / "PREREGISTRATION_V2.json") if path.is_file()]


def render_condition(
    *,
    study_dir: Path,
    render_dir: Path,
    stimulus: dict[str, Any],
    answer_text: str,
    ref_audio: str,
    norm_loudness: bool,
    run_id: str,
) -> tuple[dict[str, Any], list[str]]:
    condition = str(stimulus.get("condition") or "")
    failed: list[str] = []
    voice_delivery = dict(stimulus.get("voice_delivery") or {})
    request = {
        "answer_text": answer_text,
        "label": f"pd_listener_{run_id}_{condition}",
        "use_blessed_qra_cache": False,
        "asr_verify": True,
        "asr_cache": False,
        "asr_max_candidates": 3,
        "asr_max_wer": ASR_MAX_WER,
        "asr_max_duration_ratio": ASR_MAX_DURATION_RATIO,
        "voice_delivery": voice_delivery,
        "ref_audio": ref_audio,
        "norm_loudness": norm_loudness,
    }
    request_path = render_dir / f"{condition}_request.json"
    response_path = render_dir / f"{condition}_response.json"
    write_json(request_path, request)
    started = time.time()
    response = post_json(f"{CHATTERBOX}/synthesize-batch", request)
    elapsed = round(time.time() - started, 3)
    write_json(response_path, response)

    source = response.get("finished_response_audio") or (response.get("chunks") or [{}])[0].get("audio_path")
    source_path = resolve_host_audio(str(source or ""))
    audio_path = study_dir / "stimuli" / f"{condition}.wav"
    raw_audio_path = study_dir / "raw_stimuli" / run_id / f"{condition}.raw.wav"
    normalization_result: dict[str, Any] | None = None
    if source_path is None:
        failed.append(f"audio_not_found_on_host:{condition}:{source}")
    else:
        raw_audio_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, raw_audio_path)
        normalization_result = normalize_wav(raw_audio_path, audio_path)
        if normalization_result["exit_code"] != 0:
            failed.append(f"output_normalization_failed:{condition}:{normalization_result['stderr']}")

    engine = response.get("engine") or response.get("chunk_engine") or response.get("cache_material_engine")
    cache_material = response.get("cache_material") or {}
    chunk_norm_values = [
        (chunk.get("generation_params") or {}).get("norm_loudness")
        for chunk in (response.get("chunks") or [])
        if isinstance(chunk, dict)
    ]
    response_norm = (cache_material.get("generation_params") or {}).get("norm_loudness")
    if response_norm is None and chunk_norm_values:
        response_norm = chunk_norm_values[0]
    fingerprint_norm = (cache_material.get("reference_audio") or {}).get("norm_loudness")
    transcript, asr_gate = accepted_asr(response)
    if engine != "chatterbox_base":
        failed.append(f"engine_not_chatterbox_base:{condition}:{engine}")
    if response_norm is not norm_loudness:
        failed.append(f"norm_loudness_not_echoed:{condition}:{response_norm}:{fingerprint_norm}")
    if any(value is not norm_loudness for value in chunk_norm_values):
        failed.append(f"norm_loudness_chunk_mismatch:{condition}:{chunk_norm_values}")
    if fingerprint_norm is not None and fingerprint_norm is not norm_loudness:
        failed.append(f"norm_loudness_reference_mismatch:{condition}:{fingerprint_norm}")
    if asr_gate and asr_gate.get("ok") is not True:
        failed.append(f"asr_gate_not_ok:{condition}:{asr_gate}")
    elif asr_gate is None and normalize_text(transcript) != normalize_text(answer_text):
        failed.append(f"asr_text_drift:{condition}")
    if response.get("affect_effect") and (response.get("affect_effect") or {}).get("applied") is not True:
        failed.append(f"affect_effect_not_applied:{condition}")

    rendered = {
        "condition": condition,
        "request": rel(request_path),
        "request_sha256": sha_obj(request),
        "response": rel(response_path),
        "response_sha256": sha_obj(response),
        "elapsed_seconds": elapsed,
        "engine": engine,
        "norm_loudness": norm_loudness,
        "response_norm_loudness": response_norm,
        "conditioning_norm_loudness": fingerprint_norm,
        "chunk_norm_loudness_values": chunk_norm_values,
        "voice_delivery": voice_delivery,
        "voice_delivery_sha256": sha_obj(voice_delivery),
        "source_audio": str(source),
        "raw_audio": rel(raw_audio_path),
        "raw_sha256": sha_file(raw_audio_path) if raw_audio_path.is_file() else None,
        "raw_bytes": raw_audio_path.stat().st_size if raw_audio_path.is_file() else 0,
        "audio": rel(audio_path),
        "sha256": sha_file(audio_path) if audio_path.is_file() else None,
        "bytes": audio_path.stat().st_size if audio_path.is_file() else 0,
        "post_processing": OUTPUT_NORMALIZATION_POLICY,
        "post_processing_sha256": sha_obj(OUTPUT_NORMALIZATION_POLICY),
        "post_processing_result": normalization_result,
        "asr_max_wer": ASR_MAX_WER,
        "asr_max_duration_ratio": ASR_MAX_DURATION_RATIO,
        "asr_transcript": transcript,
        "asr_gate": asr_gate,
        "normalized_tone": response.get("normalized_tone"),
        "requested_tone": response.get("requested_tone"),
        "affect_effect": response.get("affect_effect"),
        "finished_response_metrics": response.get("finished_response_metrics"),
    }
    return rendered, failed


def update_preregistrations(
    *,
    paths: list[Path],
    rendered_by_condition: dict[str, dict[str, Any]],
    norm_loudness: bool,
    receipt_path: Path,
) -> list[str]:
    failed: list[str] = []
    policy = {
        "schema": "persona_dream.listener_study_normalization_policy.v1",
        "norm_loudness": norm_loudness,
        "scope": "all target stimuli in this preregistration",
        "proof_receipt": rel(receipt_path),
    }
    policy["sha256"] = sha_obj(policy)
    for path in paths:
        prereg = load_json(path)
        source = prereg.setdefault("stimulus_source", {})
        source["normalization_policy"] = policy
        source["post_processing_policy"] = OUTPUT_NORMALIZATION_POLICY
        source["post_processing_policy_sha256"] = sha_obj(OUTPUT_NORMALIZATION_POLICY)
        source["endpoint"] = f"POST {CHATTERBOX}/synthesize-batch"
        for stimulus in prereg.get("stimuli") or []:
            condition = str(stimulus.get("condition") or "")
            rendered = rendered_by_condition.get(condition)
            if not rendered:
                failed.append(f"render_missing_for_prereg_condition:{path.name}:{condition}")
                continue
            stimulus["audio"] = rendered["audio"]
            stimulus["raw_audio"] = rendered["raw_audio"]
            stimulus["raw_sha256"] = rendered["raw_sha256"]
            stimulus["raw_bytes"] = rendered["raw_bytes"]
            stimulus["sha256"] = rendered["sha256"]
            stimulus["bytes"] = rendered["bytes"]
            stimulus["engine"] = rendered["engine"]
            stimulus["post_processing"] = rendered["post_processing"]
            stimulus["post_processing_sha256"] = rendered["post_processing_sha256"]
            stimulus["normalization_policy_sha256"] = policy["sha256"]
            stimulus["render_receipt"] = rel(receipt_path)
            stimulus["render_request_sha256"] = rendered["request_sha256"]
            stimulus["render_response_sha256"] = rendered["response_sha256"]
        write_json(path, prereg)
    return failed


def run(args: argparse.Namespace) -> dict[str, Any]:
    study_dir = Path(args.study_dir)
    paths = prereg_paths(study_dir)
    failed: list[str] = []
    if not paths:
        return {
            "schema": "persona_dream.blinded_listener_stimuli_render.v1",
            "created_at": utc_now(),
            "status": "BLOCKED_RENDER_STIMULI",
            "mocked": False,
            "live": False,
            "study_dir": rel(study_dir),
            "failed_gates": ["preregistration_missing"],
        }

    primary_prereg = load_json(study_dir / "PREREGISTRATION_V2.json" if (study_dir / "PREREGISTRATION_V2.json").is_file() else paths[0])
    answer_text = str((primary_prereg.get("stimulus_source") or {}).get("answer_text") or "")
    if not answer_text:
        failed.append("answer_text_missing")

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    render_dir = study_dir / "rendered_stimuli" / run_id
    render_dir.mkdir(parents=True, exist_ok=True)

    health = get_json(f"{CHATTERBOX}/health")
    supported = set(health.get("supported_params") or [])
    if "norm_loudness" not in supported:
        failed.append("chatterbox_norm_loudness_not_supported")

    rendered: list[dict[str, Any]] = []
    for stimulus in primary_prereg.get("stimuli") or []:
        row, row_failed = render_condition(
            study_dir=study_dir,
            render_dir=render_dir,
            stimulus=stimulus,
            answer_text=answer_text,
            ref_audio=args.ref_audio,
            norm_loudness=args.norm_loudness,
            run_id=run_id,
        )
        rendered.append(row)
        failed.extend(row_failed)

    receipt_path = Path(args.out) if args.out else study_dir / "RENDER_STIMULI_RECEIPT.json"
    rendered_by_condition = {row["condition"]: row for row in rendered}
    if not failed:
        failed.extend(
            update_preregistrations(
                paths=paths,
                rendered_by_condition=rendered_by_condition,
                norm_loudness=args.norm_loudness,
                receipt_path=receipt_path,
            )
        )

    norm_values = {
        (row.get("response_norm_loudness"), row.get("conditioning_norm_loudness"))
        for row in rendered
    }
    if len({row.get("norm_loudness") for row in rendered}) > 1:
        failed.append("norm_loudness_policy_mismatch_across_conditions")

    receipt = {
        "schema": "persona_dream.blinded_listener_stimuli_render.v1",
        "created_at": utc_now(),
        "status": "PASS_RENDERED_BLINDED_LISTENER_STIMULI" if not failed else "BLOCKED_RENDER_STIMULI",
        "mocked": False,
        "live": True,
        "study_dir": rel(study_dir),
        "endpoint": f"POST {CHATTERBOX}/synthesize-batch",
        "run_id": run_id,
        "normalization_policy": {
            "schema": "persona_dream.listener_study_normalization_policy.v1",
            "norm_loudness": args.norm_loudness,
            "norm_loudness_echo_pairs": sorted(str(value) for value in norm_values),
        },
        "post_processing_policy": OUTPUT_NORMALIZATION_POLICY,
        "post_processing_policy_sha256": sha_obj(OUTPUT_NORMALIZATION_POLICY),
        "preregistrations": [rel(path) for path in paths],
        "health": {
            "engine": health.get("engine"),
            "device": health.get("device"),
            "started_at_utc": health.get("started_at_utc"),
            "supported_params": health.get("supported_params"),
            "voice_backends": {
                name: {
                    "state": spec.get("state"),
                    "capability_digest": spec.get("capability_digest"),
                }
                for name, spec in (health.get("voice_backends") or {}).items()
            },
        },
        "rendered": rendered,
        "failed_gates": failed,
        "claims": {
            "proves": [
                "all four preregistered target stimuli were rendered by live Chatterbox",
                "every target render used one identical norm_loudness policy",
                "the copied WAVs are hash-bound back into both preregistration files",
                "ASR readback stayed within the retained WER ceiling for the shared answer text",
            ] if not failed else [],
            "does_not_prove": [
                "human perception of the target emotion",
                "Embry speaker recognition by listeners",
                "technical comparability against neutral spread; run the technical screen next",
                "listener-study analysis or research conclusion",
            ],
        },
    }
    write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR / "RENDER_STIMULI_RECEIPT.json")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--ref-audio", default=DEFAULT_REF_AUDIO)
    parser.add_argument("--norm-loudness", type=parse_norm_loudness, default=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "receipt": rel(args.out),
        "rendered": len(receipt.get("rendered") or []),
        "norm_loudness": (receipt.get("normalization_policy") or {}).get("norm_loudness"),
        "failed_gates": receipt.get("failed_gates") or [],
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
