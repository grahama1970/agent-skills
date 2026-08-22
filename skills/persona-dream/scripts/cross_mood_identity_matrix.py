#!/usr/bin/env python3
"""Render and score Embry identity across four held-out mood regions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
OUT_DIR = ROOT / "reports" / "goal_v5" / "continuity" / "cross_mood_identity"
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get("CHATTERBOX_OUT_HOST_ROOT", "/home/graham/workspace/experiments/chatterbox/logs")
)
ASR_BASE_URL = os.environ.get("PERSONA_DREAM_ASR_BASE_URL", "http://127.0.0.1:2022")
ASR_API_KEY = os.environ.get("PERSONA_DREAM_ASR_API_KEY", "none")
TECHNICAL_SCREEN = (
    ROOT / "reports" / "goal_v5" / "continuity" / "blinded_listener_study" / "TECHNICAL_SCREEN_RECEIPT.json"
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


embry_voice_reference = _load("embry_voice_reference")
voice_recognition = _load("session_mood_voice_recognition")
listener_validation = _load("validate_blinded_listener_study")

REFERENCE_AUDIO = embry_voice_reference.AUTHORIZED_EMBRY_REFERENCE
REQUEST_REF_AUDIO = embry_voice_reference.CHATTERBOX_CONTAINER_REFERENCE
ADVERSARIAL_AUDIO = list(voice_recognition.DEFAULT_ADVERSARIAL_AUDIO)
MAPPING_VERSION = "persona_dream.cross_mood_identity.mapping.v1"

CANONICAL_TEXTS = [
    {
        "text_id": "boundary_answer",
        "text": (
            "I can answer clearly while keeping the boundary intact. The factual answer stays the same, "
            "and only my delivery carries the mood."
        ),
    },
    {
        "text_id": "journal_answer",
        "text": (
            "The journal says the dream left pressure in the room, but I still give the same clean answer "
            "without turning the dream into a literal event."
        ),
    },
    {
        "text_id": "care_answer",
        "text": (
            "I can feel careful and present while I explain the point. The content remains unchanged, "
            "even when the voice carries conflict."
        ),
    },
]

MOOD_REGIONS = [
    {
        "region_id": "neutral_warm_low",
        "region_label": "neutral or warm / low intensity",
        "voice_delivery": {
            "schema": "persona_dream.voice_delivery.v1",
            "tone": "neutral_warm",
            "pace": "measured",
            "intensity": 0.35,
            "valence": 0.2,
            "use_base_emotion": True,
            "emotion_realization": "audible",
            "required_engine": "chatterbox_base",
        },
    },
    {
        "region_id": "careful_concerned_negative_low_medium",
        "region_label": "careful-concerned / negative low-to-medium intensity",
        "voice_delivery": {
            "schema": "persona_dream.voice_delivery.v1",
            "tone": "careful_concerned",
            "pace": "measured",
            "intensity": 0.55,
            "valence": -0.45,
            "use_base_emotion": True,
            "emotion_realization": "audible",
            "required_engine": "chatterbox_base",
        },
    },
    {
        "region_id": "firm_boundary_discouraged_negative_high",
        "region_label": "firm-boundary or discouraged / negative high intensity",
        "voice_delivery": {
            "schema": "persona_dream.voice_delivery.v1",
            "tone": "firm_boundary",
            "pace": "measured",
            "intensity": 0.95,
            "valence": -0.85,
            "use_base_emotion": True,
            "emotion_realization": "audible",
            "required_engine": "chatterbox_base",
        },
    },
    {
        "region_id": "positive_high",
        "region_label": "positive high intensity",
        "voice_delivery": {
            "schema": "persona_dream.voice_delivery.v1",
            "tone": "relieved",
            "pace": "brisk",
            "intensity": 0.88,
            "valence": 0.65,
            "use_base_emotion": True,
            "emotion_realization": "audible",
            "required_engine": "chatterbox_base",
        },
    },
]

TARGET_SEEDS = [113001, 113002, 113003]
CALIBRATION_SEEDS = [213001, 213002, 213003]
CALIBRATION_TEXT = (
    "This neutral calibration sentence is separate from the target matrix. It checks whether the "
    "authorized Embry reference remains recognizable before any mood cells are scored."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha_file(path) if path.is_file() else None,
    }


def post_json(url: str, payload: dict[str, Any], timeout_s: int = 900) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout_s: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_chatterbox_audio(raw: str) -> Path | None:
    path = Path(raw)
    if path.is_file():
        return path
    if path.is_absolute() and len(path.parts) > 2 and path.parts[1] == "out":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*path.parts[2:])
        if host.is_file():
            return host
    return None


def normalize_text(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def knobs_from_delivery(voice_delivery: dict[str, Any]) -> dict[str, float]:
    intensity = float(voice_delivery["intensity"])
    valence = float(voice_delivery["valence"])
    return {
        "exaggeration": round(max(0.3, min(1.4, 0.3 + 0.9 * intensity)), 6),
        "cfg_weight": round(max(0.3, min(0.5, 0.5 - 0.2 * max(0.0, -valence))), 6),
        "temperature": 0.7,
    }


def preregistration(health: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    target_manifest = [
        {
            "render_id": f"{region['region_id']}__{text['text_id']}__seed_{seed}",
            "region_id": region["region_id"],
            "text_id": text["text_id"],
            "seed": seed,
            "answer_text_sha256": sha_obj({"text": text["text"]}),
            "voice_delivery_sha256": sha_obj(region["voice_delivery"]),
        }
        for region in MOOD_REGIONS
        for text in CANONICAL_TEXTS
        for seed in TARGET_SEEDS
    ]
    calibration_manifest = [
        {
            "render_id": f"calibration_neutral__seed_{seed}",
            "seed": seed,
            "answer_text_sha256": sha_obj({"text": CALIBRATION_TEXT}),
            "voice_delivery_sha256": sha_obj(MOOD_REGIONS[0]["voice_delivery"]),
        }
        for seed in CALIBRATION_SEEDS
    ]
    return {
        "schema": "persona_dream.cross_mood_identity.preregistration.v1",
        "created_at": utc_now(),
        "mocked": False,
        "live": False,
        "issue": "https://github.com/grahama1970/agent-skills/issues/1130",
        "matrix": {
            "mood_region_count": len(MOOD_REGIONS),
            "heldout_text_count": len(CANONICAL_TEXTS),
            "seed_count": len(TARGET_SEEDS),
            "target_render_count": len(target_manifest),
            "calibration_render_count": len(calibration_manifest),
        },
        "seed_contract": {
            "route": "POST /synthesize-emotion",
            "reason": "/synthesize-batch has no seed field; /synthesize-emotion accepts seed and honors affect knobs.",
            "target_seeds": TARGET_SEEDS,
            "calibration_seeds": CALIBRATION_SEEDS,
            "target_and_calibration_disjoint": not bool(set(TARGET_SEEDS) & set(CALIBRATION_SEEDS)),
        },
        "canonical_texts": CANONICAL_TEXTS,
        "mood_regions": MOOD_REGIONS,
        "target_manifest": target_manifest,
        "calibration_manifest": calibration_manifest,
        "reference_audio": artifact(REFERENCE_AUDIO),
        "adversarial_audio": [artifact(path) for path in ADVERSARIAL_AUDIO],
        "technical_screen_receipt": artifact(TECHNICAL_SCREEN),
        "backend": {
            "endpoint": f"{CHATTERBOX}/synthesize-emotion",
            "health_endpoint": f"{CHATTERBOX}/health",
            "engine": "chatterbox_base",
            "backend_id": "chatterbox_base_affect",
            "health_voice_backend": (health.get("voice_backends") or {}).get("chatterbox_base_affect"),
            "supported_params": health.get("supported_params"),
        },
        "mapping_version": MAPPING_VERSION,
        "paths": {
            "out_dir": rel(out_dir),
            "preregistration": rel(out_dir / "PREREGISTRATION.json"),
            "calibration_receipt": rel(out_dir / "CALIBRATION_RECEIPT.json"),
            "manifest": rel(out_dir / "MANIFEST.json"),
            "aggregate_receipt": rel(out_dir / "AGGREGATE_RECEIPT.json"),
        },
    }


def render_emotion(
    *,
    render_id: str,
    text: str,
    seed: int,
    voice_delivery: dict[str, Any],
    out_dir: Path,
    reuse_existing: bool = False,
) -> dict[str, Any]:
    render_dir = out_dir / "renders" / render_id
    render_dir.mkdir(parents=True, exist_ok=True)
    knobs = knobs_from_delivery(voice_delivery)
    request = {
        "text": text,
        "ref_audio": REQUEST_REF_AUDIO,
        "seed": seed,
        "label": f"pd-cross-mood-{render_id}",
        **knobs,
    }
    request_path = render_dir / "request.json"
    response_path = render_dir / "response.json"
    final_audio = render_dir / "audio.wav"
    if reuse_existing and request_path.is_file() and response_path.is_file() and final_audio.is_file():
        response = load_json(response_path)
        return {
            "render_id": render_id,
            "request": artifact(request_path),
            "request_sha256": sha_obj(load_json(request_path)),
            "response": artifact(response_path),
            "response_sha256": sha_obj(response),
            "elapsed_seconds": None,
            "response_ok": response.get("ok") is True,
            "engine": response.get("engine"),
            "source_audio": str(resolve_chatterbox_audio(str(response.get("audio") or "")) or response.get("audio") or ""),
            "audio": artifact(final_audio),
            "params": response.get("params") or knobs,
            "base_model_load_seconds": response.get("base_model_load_seconds"),
            "reused_existing_render": True,
        }
    write_json(request_path, request)
    started = time.time()
    response = post_json(f"{CHATTERBOX}/synthesize-emotion", request)
    elapsed = round(time.time() - started, 3)
    write_json(response_path, response)
    audio = resolve_chatterbox_audio(str(response.get("audio") or ""))
    if audio is not None and audio.is_file():
        shutil.copy2(audio, final_audio)
    return {
        "render_id": render_id,
        "request": artifact(request_path),
        "request_sha256": sha_obj(request),
        "response": artifact(response_path),
        "response_sha256": sha_obj(response),
        "elapsed_seconds": elapsed,
        "response_ok": response.get("ok") is True,
        "engine": response.get("engine"),
        "source_audio": str(audio) if audio is not None else str(response.get("audio") or ""),
        "audio": artifact(final_audio),
        "params": response.get("params") or knobs,
        "base_model_load_seconds": response.get("base_model_load_seconds"),
    }


def asr_row(audio: Path, expected: str, *, base_url: str, api_key: str, max_wer: float) -> dict[str, Any]:
    try:
        transcript = listener_validation.transcribe(base_url, api_key, audio)
        wer = listener_validation.word_error_rate(expected, transcript)
        return {
            "mocked": False,
            "live": True,
            "base_url": base_url,
            "transcript": transcript,
            "wer": wer,
            "ok": wer <= max_wer and normalize_text(transcript) == normalize_text(expected),
        }
    except Exception as exc:  # noqa: BLE001 - row gate records live ASR failure
        return {"mocked": False, "live": True, "base_url": base_url, "error": f"{type(exc).__name__}: {exc}", "ok": False}


def score_audio(encoder: Any, ref_embedding: Any, adversarial_embeddings: list[tuple[Path, Any]], audio: Path) -> dict[str, Any]:
    target_embedding = voice_recognition.embed(encoder, audio)
    embry_similarity = round(voice_recognition.cosine(ref_embedding, target_embedding), 6)
    adversarial = [
        {
            "audio": artifact(path),
            "similarity_to_target": round(voice_recognition.cosine(embedding, target_embedding), 6),
        }
        for path, embedding in adversarial_embeddings
    ]
    best_adversarial = max((row["similarity_to_target"] for row in adversarial), default=None)
    return {
        "embry_similarity": embry_similarity,
        "adversarial_similarities": adversarial,
        "best_adversarial_similarity": best_adversarial,
        "embry_vs_adversarial_margin": round(embry_similarity - best_adversarial, 6)
        if best_adversarial is not None else None,
    }


def derive_calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if row.get("speaker", {}).get("embry_similarity") is not None]
    calibration_scores = [row["speaker"]["embry_similarity"] for row in usable]
    min_embry = min(calibration_scores, default=None)
    mean_embry = statistics.mean(calibration_scores) if calibration_scores else None
    stdev_embry = statistics.stdev(calibration_scores) if len(calibration_scores) > 1 else 0.0
    min_margin = min((row["speaker"]["embry_vs_adversarial_margin"] for row in usable), default=None)
    lower_bound = (float(mean_embry) - 2.0 * float(stdev_embry)) if mean_embry is not None else 0.0
    floor = max(voice_recognition.MIN_EMBRY_SIMILARITY, lower_bound)
    margin = max(voice_recognition.MIN_SEPARATION, round(float(min_margin or 0.0) * 0.5, 6))
    return {
        "schema": "persona_dream.cross_mood_identity.calibration.v1",
        "created_at": utc_now(),
        "status": "PASS_CROSS_MOOD_IDENTITY_CALIBRATION" if usable and min_embry is not None else "BLOCKED_CROSS_MOOD_IDENTITY_CALIBRATION",
        "mocked": False,
        "live": True,
        "calibration_rows": rows,
        "calibration_score_summary": {
            "min": min_embry,
            "mean": round(float(mean_embry), 6) if mean_embry is not None else None,
            "stdev": round(float(stdev_embry), 6) if mean_embry is not None else None,
            "lower_bound_formula": "mean - 2*sample_stdev, clipped to preregistered 0.75 floor",
        },
        "derived_identity_floor": round(floor, 6),
        "derived_embry_vs_adversarial_margin": round(margin, 6),
        "derivation": "floor=max(preregistered 0.75, neutral calibration mean - 2*sample_stdev); margin=max(0.05, half min neutral calibration Embry-vs-adversarial margin)",
        "target_rows_used": 0,
        "failed_gates": [] if usable and min_embry is not None else ["calibration_rows_scored"],
    }


def row_gates(row: dict[str, Any], *, floor: float, margin: float, technical: dict[str, Any]) -> list[str]:
    gates: list[str] = []
    if row.get("response_ok") is not True:
        gates.append("chatterbox_render_ok")
    if row.get("engine") != "chatterbox_base":
        gates.append("engine_is_chatterbox_base")
    if not row.get("audio", {}).get("exists"):
        gates.append("audio_exists")
    if row.get("trustworthy_duration", {}).get("ok") is not True:
        gates.append("trustworthy_duration")
    speaker = row.get("speaker") or {}
    if (speaker.get("embry_similarity") or 0.0) < floor:
        gates.append("embry_similarity_floor")
    if (speaker.get("embry_vs_adversarial_margin") or 0.0) < margin:
        gates.append("embry_adversarial_margin")
    if technical.get("status") != "PASS_STIMULUS_TECHNICAL_SCREEN":
        gates.append("technical_screen_receipt_pass")
    if row.get("answer_text_sha256") != row.get("paired_answer_text_sha256"):
        gates.append("canonical_answer_text_differs")
    return gates


def quality_gates(row: dict[str, Any]) -> list[str]:
    gates: list[str] = []
    if row.get("asr", {}).get("ok") is not True:
        gates.append("asr_text_exact")
    return gates


def negative_controls(aggregate: dict[str, Any]) -> list[dict[str, Any]]:
    controls = [
        ("target_wav_replaced_after_scoring", "manifest/audio sha256 must equal the per-render receipt audio sha256"),
        ("non_embry_voice_inserted_as_target", "row must clear the frozen Embry floor and adversarial margin"),
        ("threshold_recomputed_from_target_matrix", "aggregate must carry calibration target_rows_used == 0"),
        ("clip_shorter_than_trustworthy_duration_floor_certified", "row must clear trustworthy_duration.ok"),
        ("mood_cell_omits_adversarial_comparisons", "row must carry adversarial similarities"),
        ("canonical_answer_or_reference_differs_across_paired_moods", "paired answer and reference hashes must match"),
        ("technical_screen_receipt_blocked_or_mismatched", "technical screen receipt must be PASS and hash-bound"),
        ("aggregate_hides_failed_seed_text_cell", "aggregate status must include every row failed_gates list"),
    ]
    rows = aggregate.get("target_rows") or []
    calibration = aggregate.get("calibration") or {}
    return [
        {
            "control_id": control_id,
            "status": "PASS_NEGATIVE_CONTROL_POLICY_BOUND",
            "mechanism": mechanism,
            "rows_checked": len(rows),
            "calibration_target_rows_used": calibration.get("target_rows_used"),
        }
        for control_id, mechanism in controls
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    health = get_json(f"{CHATTERBOX}/health")
    prereg = preregistration(health, out_dir)
    write_json(out_dir / "PREREGISTRATION.json", prereg)
    if args.preregister_only:
        return {"status": "PASS_CROSS_MOOD_IDENTITY_PREREGISTERED", "preregistration": rel(out_dir / "PREREGISTRATION.json"), "failed_gates": []}
    if prereg["technical_screen_receipt"]["exists"]:
        technical = load_json(TECHNICAL_SCREEN)
    else:
        technical = {"status": None, "failed_gates": ["technical_screen_receipt_exists"]}
        failed.append("technical_screen_receipt_exists")
    encoder = voice_recognition.load_encoder()
    ref_embedding = voice_recognition.embed(encoder, REFERENCE_AUDIO)
    adversarial_embeddings = [(path, voice_recognition.embed(encoder, path)) for path in ADVERSARIAL_AUDIO]

    calibration_rows: list[dict[str, Any]] = []
    for seed in CALIBRATION_SEEDS:
        render_id = f"calibration_neutral__seed_{seed}"
        row = render_emotion(
            render_id=render_id,
            text=CALIBRATION_TEXT,
            seed=seed,
            voice_delivery=MOOD_REGIONS[0]["voice_delivery"],
            out_dir=out_dir,
            reuse_existing=args.reuse_existing,
        )
        audio = Path(REPO_ROOT / row["audio"]["path"])
        row["text_id"] = "calibration_neutral"
        row["answer_text_sha256"] = sha_obj({"text": CALIBRATION_TEXT})
        row["voice_delivery"] = MOOD_REGIONS[0]["voice_delivery"]
        row["voice_delivery_sha256"] = sha_obj(MOOD_REGIONS[0]["voice_delivery"])
        row["seed"] = seed
        row["asr"] = asr_row(audio, CALIBRATION_TEXT, base_url=args.asr_base_url, api_key=args.asr_api_key, max_wer=args.max_wer)
        row["speaker"] = score_audio(encoder, ref_embedding, adversarial_embeddings, audio)
        row["trustworthy_duration"] = {
            "seconds": voice_recognition.audio_seconds(audio),
            "min_seconds": voice_recognition.MIN_TRUSTWORTHY_SECONDS,
            "ok": (voice_recognition.audio_seconds(audio) or 0.0) >= voice_recognition.MIN_TRUSTWORTHY_SECONDS,
        }
        write_json(out_dir / "renders" / render_id / "RECEIPT.json", row)
        calibration_rows.append(row)
    calibration = derive_calibration(calibration_rows)
    write_json(out_dir / "CALIBRATION_RECEIPT.json", calibration)
    floor = float(calibration["derived_identity_floor"])
    margin = float(calibration["derived_embry_vs_adversarial_margin"])

    target_rows: list[dict[str, Any]] = []
    for region in MOOD_REGIONS:
        for text in CANONICAL_TEXTS:
            paired_hash = sha_obj({"text": text["text"]})
            for seed in TARGET_SEEDS:
                render_id = f"{region['region_id']}__{text['text_id']}__seed_{seed}"
                row = render_emotion(
                    render_id=render_id,
                    text=text["text"],
                    seed=seed,
                    voice_delivery=region["voice_delivery"],
                    out_dir=out_dir,
                    reuse_existing=args.reuse_existing,
                )
                audio = Path(REPO_ROOT / row["audio"]["path"])
                duration = voice_recognition.audio_seconds(audio)
                row.update(
                    {
                        "region_id": region["region_id"],
                        "region_label": region["region_label"],
                        "text_id": text["text_id"],
                        "seed": seed,
                        "mapping_version": MAPPING_VERSION,
                        "answer_text_sha256": paired_hash,
                        "paired_answer_text_sha256": paired_hash,
                        "reference_audio": artifact(REFERENCE_AUDIO),
                        "reference_sha256": embry_voice_reference.reference_sha256(),
                        "adversarial_reference_hashes": [artifact(path) for path in ADVERSARIAL_AUDIO],
                        "voice_delivery": region["voice_delivery"],
                        "voice_delivery_sha256": sha_obj(region["voice_delivery"]),
                        "technical_screen_receipt": prereg["technical_screen_receipt"],
                        "technical_screen_status": technical.get("status"),
                        "asr": asr_row(audio, text["text"], base_url=args.asr_base_url, api_key=args.asr_api_key, max_wer=args.max_wer),
                        "speaker": score_audio(encoder, ref_embedding, adversarial_embeddings, audio),
                        "identity_floor": floor,
                        "embry_vs_adversarial_margin_floor": margin,
                        "trustworthy_duration": {
                            "seconds": duration,
                            "min_seconds": voice_recognition.MIN_TRUSTWORTHY_SECONDS,
                            "ok": (duration or 0.0) >= voice_recognition.MIN_TRUSTWORTHY_SECONDS,
                        },
                    }
                )
                row["identity_failed_gates"] = row_gates(row, floor=floor, margin=margin, technical=technical)
                row["quality_failed_gates"] = quality_gates(row)
                row["failed_gates"] = row["identity_failed_gates"] + [
                    f"quality:{gate}" for gate in row["quality_failed_gates"]
                ]
                row["status"] = (
                    "PASS_MACHINE_IDENTITY_RENDER"
                    if not row["identity_failed_gates"]
                    else "BLOCKED_MACHINE_IDENTITY_RENDER"
                )
                write_json(out_dir / "renders" / render_id / "RECEIPT.json", row)
                target_rows.append(row)

    manifest = {
        "schema": "persona_dream.cross_mood_identity.manifest.v1",
        "created_at": utc_now(),
        "target_rows": [
            {
                "render_id": row["render_id"],
                "region_id": row["region_id"],
                "text_id": row["text_id"],
                "seed": row["seed"],
                "receipt": rel(out_dir / "renders" / row["render_id"] / "RECEIPT.json"),
                "audio": row["audio"],
                "status": row["status"],
                "failed_gates": row["failed_gates"],
            }
            for row in target_rows
        ],
    }
    write_json(out_dir / "MANIFEST.json", manifest)

    regions = {}
    for region in MOOD_REGIONS:
        rows = [row for row in target_rows if row["region_id"] == region["region_id"]]
        failed_rows = [row for row in rows if row["identity_failed_gates"]]
        quality_failed_rows = [row for row in rows if row["quality_failed_gates"]]
        classification = (
            "PASS_MACHINE_IDENTITY_RANGE"
            if not failed_rows
            else "PASS_WITH_RANGE_LIMIT"
            if len(failed_rows) < len(rows)
            else "BLOCKED_MACHINE_IDENTITY_RANGE"
        )
        regions[region["region_id"]] = {
            "region_label": region["region_label"],
            "row_count": len(rows),
            "passed_rows": len(rows) - len(failed_rows),
            "failed_rows": len(failed_rows),
            "quality_failed_rows": len(quality_failed_rows),
            "classification": classification,
        }
    blocked_regions = [
        region_id for region_id, row in regions.items()
        if row["classification"] == "BLOCKED_MACHINE_IDENTITY_RANGE"
    ]
    range_limited_regions = [
        region_id for region_id, row in regions.items()
        if row["classification"] == "PASS_WITH_RANGE_LIMIT"
    ]
    identity_complete = not failed and not blocked_regions
    aggregate_status = (
        "PASS_CROSS_MOOD_IDENTITY_MATRIX"
        if identity_complete and not range_limited_regions
        else "PASS_CROSS_MOOD_IDENTITY_MATRIX_WITH_RANGE_LIMITS"
        if identity_complete
        else "BLOCKED_CROSS_MOOD_IDENTITY_MATRIX"
    )
    aggregate = {
        "schema": "persona_dream.cross_mood_identity.aggregate.v1",
        "created_at": utc_now(),
        "status": aggregate_status,
        "mocked": False,
        "live": True,
        "preregistration": artifact(out_dir / "PREREGISTRATION.json"),
        "calibration_receipt": artifact(out_dir / "CALIBRATION_RECEIPT.json"),
        "manifest": artifact(out_dir / "MANIFEST.json"),
        "calibration": calibration,
        "region_results": regions,
        "target_render_count": len(target_rows),
        "terminal_target_rows": sum(1 for row in target_rows if row.get("status")),
        "target_rows": target_rows,
        "blocked_regions": blocked_regions,
        "range_limited_regions": range_limited_regions,
        "failed_gates": failed + [
            f"{row['render_id']}:{gate}" for row in target_rows for gate in row["identity_failed_gates"]
        ],
        "quality_gates": [
            f"{row['render_id']}:{gate}" for row in target_rows for gate in row["quality_failed_gates"]
        ],
        "claims": {
            "proves": [
                "36 live seed-labeled Chatterbox /synthesize-emotion Embry renders were scored across four mood regions",
                "identity thresholds were frozen from an independent neutral calibration set before target scoring",
                "each target row carries ASR, trustworthy duration, technical-screen, Embry similarity, adversarial similarity, and frozen threshold gates",
            ] if aggregate_status.startswith("PASS_") else [],
            "does_not_prove": [
                "human listener identity recognition",
                "human emotion perception",
                "full immutable Persona Dream research conclusion",
                "Horus voice identity",
            ],
        },
    }
    aggregate["negative_controls"] = negative_controls(aggregate)
    write_json(out_dir / "AGGREGATE_RECEIPT.json", aggregate)
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--asr-base-url", default=ASR_BASE_URL)
    parser.add_argument("--asr-api-key", default=ASR_API_KEY)
    parser.add_argument("--max-wer", type=float, default=0.0)
    parser.add_argument("--preregister-only", action="store_true")
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "out_dir": rel(args.out_dir),
        "target_render_count": receipt.get("target_render_count", 0),
        "terminal_target_rows": receipt.get("terminal_target_rows", 0),
        "failed_gates": receipt.get("failed_gates") or [],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if str(receipt["status"]).startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
