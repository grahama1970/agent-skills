#!/usr/bin/env python3
"""Screen blinded listener-study stimuli for technical confounds before rating (#1127).

Exact stimulus hashes and ASR WER 0.0 prove the right words were spoken by the
right files. They do not prove the four files differ ONLY in the requested
``voice_delivery`` envelope. If one condition is louder, longer, pausier, or
carries more vocoder artifact than the others, a rater can separate the files
for reasons that have nothing to do with dream-derived mood -- and the study
would score that as emotion recognition.

Upstream ``resemble-ai/chatterbox#536`` reports a persistent ~4.9 kHz vocoder
tone and an elevated silence floor in base-model output, so that artifact is
measured explicitly rather than assumed absent.

The calibration rule is the point of this screen. Tolerances are derived from a
preregistered NEUTRAL REPEAT SET -- N renders issued with byte-identical request
parameters -- so the question asked is:

    does this condition differ from neutral by more than the renderer's own
    same-parameter stochastic spread?

Choosing thresholds after looking at the four target WAVs would let the screen
be tuned until the existing stimuli pass, which the ticket forbids. The
tolerance rule below is frozen in code, hashed into the manifest, and applied
unchanged to every condition.

The renderer's own ``/health`` reports ``deterministic_seed: false`` for every
backend, and its ``stage_preset_affect_status`` records that preset-driven
acoustic shifts previously measured BELOW same-parameter stochastic spread.
Both facts are why neutral-repeat calibration is required rather than optional.

PASS proves technical comparability and quality screening only. It is not
evidence that any requested emotion was realized, that a listener perceives it,
or that a listener recognizes Embry.

Runtime: requires numpy/scipy/librosa. Use the Chatterbox virtualenv
interpreter, matching the precedent set by the speaker-recognition lane:

    /home/graham/workspace/experiments/chatterbox/.venv/bin/python
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
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
NEUTRAL_DIR_NAME = "neutral_calibration"
DEFAULT_NEUTRAL_RENDERS = 8
DEFAULT_OUTPUT_NORMALIZATION_POLICY = {
    "schema": "persona_dream.output_normalization_policy.v1",
    "name": "ffmpeg_loudnorm_i27_tp2_lra7_pcm16_v1",
    "tool": "ffmpeg",
    "filter": "loudnorm=I=-27:TP=-2:LRA=7",
    "codec": "pcm_s16le",
    "sample_rate": 24000,
    "channels": 1,
}

#: Frozen BEFORE any target condition is measured. A condition metric may sit
#: at most ``k_sd`` neutral standard deviations from the neutral median. The
#: floors exist because a neutral set can be coincidentally tight on a metric;
#: without them a zero-variance draw would make the tolerance zero and block
#: every condition for differences no listener could hear. Floors are physical
#: audibility-scale quantities, not values fitted to these four WAVs.
TOLERANCE_RULE: dict[str, Any] = {
    "schema": "persona_dream.technical_screen_tolerance_rule.v1",
    "rule": "abs(condition_value - neutral_median) <= max(k_sd * neutral_sd, floor)",
    "k_sd": 3.0,
    "floors": {
        "duration_s": 0.30,
        "k_weighted_loudness_lkfs": 1.0,
        "rms_dbfs": 1.0,
        "peak_dbfs": 2.0,
        "clipping_ratio": 0.001,
        "f0_median_hz": 15.0,
        "f0_range_hz": 60.0,
        "voiced_ratio": 0.10,
        "pause_ratio": 0.08,
        "pause_count": 2.0,
        "band_4900_prominence_db": 3.0,
        "silence_floor_dbfs": 6.0,
        "trailing_energy_dbfs": 8.0,
    },
    "intended_mediator_policy": (
        "A metric may be exempted only when the preregistration names it "
        "prospectively as an intended mediator of the requested envelope, with "
        "its own tolerance. Metrics are never reclassified after seeing results."
    ),
    "hard_gates_independent_of_neutral_spread": {
        "clipping_ratio_max": 0.001,
        "asr_wer_max": 0.0,
        "max_repeated_ngram": 2,
        "identical_encoding_required": ["sample_rate", "channels", "sample_width_bits"],
    },
}

#: Metrics that carry the requested envelope for these conditions. The study
#: manipulates intensity/valence, which legitimately move pitch and pacing; it
#: does not license a louder file, a clipped file, or more vocoder artifact.
#: Declared here, before measurement, per the rule above.
INTENDED_MEDIATORS = ("f0_median_hz", "f0_range_hz", "voiced_ratio", "pause_ratio", "pause_count")

NUISANCE_METRICS = (
    "duration_s",
    "k_weighted_loudness_lkfs",
    "rms_dbfs",
    "peak_dbfs",
    "clipping_ratio",
    "band_4900_prominence_db",
    "silence_floor_dbfs",
    "trailing_energy_dbfs",
)


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_norm_loudness(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("--norm-loudness must be true or false")


def normalize_wav(raw_audio: Path, final_audio: Path,
                  policy: dict[str, Any] | None = None) -> dict[str, Any]:
    effective = policy or DEFAULT_OUTPUT_NORMALIZATION_POLICY
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
        str(effective["filter"]),
        "-ar",
        str(effective["sample_rate"]),
        "-ac",
        str(effective["channels"]),
        "-c:a",
        str(effective["codec"]),
        str(final_audio),
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def resolve_bundle_path(raw: str | None) -> Path:
    if not isinstance(raw, str) or not raw:
        return Path("")
    path = Path(raw)
    if path.is_absolute():
        return path
    if raw.startswith("reports/"):
        return ROOT / raw
    return REPO_ROOT / raw


# --------------------------------------------------------------------------
# Acoustic measurement
# --------------------------------------------------------------------------


def _k_weighting_filters(sr: int):
    """ITU-R BS.1770 K-weighting: a high-shelf and a high-pass biquad."""
    import numpy as np

    # Stage 1: high-shelf (pre-filter).
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / sr)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh ** 0.4996667741545416
    denom = 1.0 + k / q + k * k
    b1 = np.array([(vh + vb * k / q + k * k) / denom,
                   2.0 * (k * k - vh) / denom,
                   (vh - vb * k / q + k * k) / denom])
    a1 = np.array([1.0, 2.0 * (k * k - 1.0) / denom, (1.0 - k / q + k * k) / denom])

    # Stage 2: high-pass (RLB).
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / sr)
    b2 = np.array([1.0, -2.0, 1.0])
    a2 = np.array([1.0,
                   2.0 * (k * k - 1.0) / (1.0 + k / q + k * k),
                   (1.0 - k / q + k * k) / (1.0 + k / q + k * k)])
    return (b1, a1), (b2, a2)


def k_weighted_loudness_lkfs(samples, sr: int) -> float:
    """Ungated K-weighted loudness.

    Deliberately NOT called integrated LUFS: BS.1770 gating is not applied, so
    this is a comparable relative loudness measure across same-length speech
    clips, not a broadcast-compliant integrated loudness value.
    """
    import numpy as np
    from scipy.signal import lfilter

    (b1, a1), (b2, a2) = _k_weighting_filters(sr)
    y = lfilter(b1, a1, samples)
    y = lfilter(b2, a2, y)
    mean_square = float(np.mean(np.square(y)))
    if mean_square <= 0.0:
        return -120.0
    return round(-0.691 + 10.0 * math.log10(mean_square), 6)


def band_prominence_db(samples, sr: int, *, lo: float, hi: float,
                       ref_bands: tuple[tuple[float, float], ...]) -> float:
    """Mean power in [lo,hi] relative to the mean power of the reference bands."""
    import numpy as np
    from scipy.signal import welch

    nperseg = min(8192, len(samples))
    if nperseg < 256:
        return 0.0
    freqs, psd = welch(samples, fs=sr, nperseg=nperseg)

    def _mean(f_lo: float, f_hi: float) -> float:
        mask = (freqs >= f_lo) & (freqs < f_hi)
        return float(np.mean(psd[mask])) if mask.any() else 0.0

    target = _mean(lo, hi)
    refs = [_mean(a, b) for a, b in ref_bands]
    refs = [r for r in refs if r > 0]
    if target <= 0 or not refs:
        return 0.0
    return round(10.0 * math.log10(target / (sum(refs) / len(refs))), 6)


def measure_wav(path: Path, *, expected_text: str = "") -> dict[str, Any]:
    """Every acoustic quantity the screen compares, plus format facts."""
    import numpy as np
    import librosa
    import soundfile as sf

    info = sf.info(str(path))
    samples, sr = librosa.load(str(path), sr=None, mono=True)
    samples = np.asarray(samples, dtype=np.float64)
    duration = float(len(samples) / sr) if sr else 0.0
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
    clipped = int(np.sum(np.abs(samples) >= 0.999))

    # Frame energy for pause / silence-floor / truncation diagnostics.
    frame, hop = 1024, 256
    if len(samples) >= frame:
        energy = librosa.feature.rms(y=samples, frame_length=frame, hop_length=hop)[0]
    else:
        energy = np.array([rms])
    energy_db = 20.0 * np.log10(np.maximum(energy, 1e-10))
    speech_floor = float(np.percentile(energy_db, 95)) - 35.0
    silent = energy_db < speech_floor
    pause_ratio = float(np.mean(silent)) if len(silent) else 0.0

    runs, run = [], 0
    for flag in silent:
        if flag:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    min_pause_frames = max(1, int(0.2 * sr / hop))
    pauses = [r for r in runs if r >= min_pause_frames]

    # The floor is the quietest part of the file wherever it occurs -- interior
    # pause, lead-in, or tail. Sampling only the first/last 150 ms measures
    # speech on any clip that starts talking immediately, which is exactly the
    # case for these stimuli, and would miss a condition-specific noise floor.
    lead_n = max(1, int(0.15 * sr / hop))
    silence_floor = float(np.percentile(energy_db, 5)) if len(energy_db) else -120.0
    trailing_energy = float(np.median(energy_db[-lead_n:])) if len(energy_db) > lead_n else float(np.median(energy_db))

    try:
        f0, voiced_flag, _ = librosa.pyin(
            samples.astype(np.float32), fmin=60.0, fmax=400.0, sr=sr,
            frame_length=2048, hop_length=hop,
        )
        voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        voiced_ratio = float(np.mean(voiced_flag)) if voiced_flag is not None and len(voiced_flag) else 0.0
    except Exception:  # noqa: BLE001 - pitch tracking must not abort the screen
        voiced, voiced_ratio = np.array([]), 0.0

    f0_median = float(np.median(voiced)) if len(voiced) else 0.0
    f0_range = float(np.percentile(voiced, 95) - np.percentile(voiced, 5)) if len(voiced) else 0.0

    return {
        "path": rel(path),
        "wav_sha256": sha_file(path),
        "bytes": path.stat().st_size,
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "sample_width_bits": int(re.sub(r"\D", "", info.subtype) or 0) if info.subtype else 0,
        "subtype": info.subtype,
        "duration_s": round(duration, 6),
        "peak_dbfs": round(20.0 * math.log10(max(peak, 1e-10)), 6),
        "rms_dbfs": round(20.0 * math.log10(max(rms, 1e-10)), 6),
        "clipping_ratio": round(clipped / max(len(samples), 1), 8),
        "k_weighted_loudness_lkfs": k_weighted_loudness_lkfs(samples, sr),
        "f0_median_hz": round(f0_median, 4),
        "f0_range_hz": round(f0_range, 4),
        "voiced_ratio": round(voiced_ratio, 6),
        "pause_ratio": round(pause_ratio, 6),
        "pause_count": float(len(pauses)),
        "median_pause_s": round(float(np.median(pauses)) * hop / sr, 6) if pauses else 0.0,
        "speech_rate_voiced_per_s": round(voiced_ratio * duration / max(duration, 1e-9), 6),
        "band_4900_prominence_db": band_prominence_db(
            samples, sr, lo=4850.0, hi=4950.0,
            ref_bands=((4650.0, 4800.0), (5000.0, 5150.0)),
        ),
        "silence_floor_dbfs": round(silence_floor, 6),
        "trailing_energy_dbfs": round(trailing_energy, 6),
    }


def max_repeated_ngram(text: str, n: int = 3) -> int:
    tokens = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split()
    if len(tokens) < n:
        return 0
    counts: dict[tuple[str, ...], int] = {}
    for i in range(len(tokens) - n + 1):
        key = tuple(tokens[i:i + n])
        counts[key] = counts.get(key, 0) + 1
    return max(counts.values()) if counts else 0


# --------------------------------------------------------------------------
# Neutral calibration set
# --------------------------------------------------------------------------


def post_json(url: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_neutral_set(study_dir: Path, count: int, *, ref_audio: str, answer_text: str,
                       voice_delivery: dict[str, Any], norm_loudness: bool | None = None,
                       post_processing_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render N byte-identical neutral requests to measure stochastic spread."""
    out_dir = study_dir / NEUTRAL_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    host_root = Path(os.environ.get("CHATTERBOX_OUT_HOST_ROOT",
                                    "/home/graham/workspace/experiments/chatterbox/logs"))
    request = {
        "answer_text": answer_text,
        "label": "technical_screen_neutral_calibration",
        "use_blessed_qra_cache": False,
        "asr_verify": True,
        "asr_cache": False,
        "asr_max_candidates": 1,
        "asr_max_wer": 0.0,
        "voice_delivery": voice_delivery,
        "ref_audio": ref_audio,
    }
    if norm_loudness is not None:
        request["norm_loudness"] = norm_loudness
    health = json.loads(urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=30).read().decode())
    renders: list[dict[str, Any]] = []
    for idx in range(1, count + 1):
        response = post_json(f"{CHATTERBOX}/synthesize-batch", request)
        source = (response.get("finished_response_audio")
                  or (response.get("chunks") or [{}])[0].get("audio_path"))
        src_path = Path(str(source))
        if not src_path.is_file() and src_path.is_absolute() and len(src_path.parts) > 2 \
                and src_path.parts[1] == "out":
            src_path = host_root.joinpath(*src_path.parts[2:])
        if not src_path.is_file():
            raise RuntimeError(f"neutral render {idx}: audio not found at {source!r}")
        raw_dest = out_dir / f"neutral_{idx:02d}.raw.wav"
        dest = out_dir / f"neutral_{idx:02d}.wav"
        raw_dest.write_bytes(src_path.read_bytes())
        normalization_result = None
        if post_processing_policy:
            normalization_result = normalize_wav(raw_dest, dest, post_processing_policy)
            if normalization_result["exit_code"] != 0:
                raise RuntimeError(
                    f"neutral render {idx}: output normalization failed: "
                    f"{normalization_result['stderr']}"
                )
        else:
            dest.write_bytes(raw_dest.read_bytes())
        renders.append({
            "index": idx,
            "raw_wav": rel(raw_dest),
            "raw_wav_sha256": sha_file(raw_dest),
            "wav": rel(dest),
            "wav_sha256": sha_file(dest),
            "engine": response.get("engine"),
            "asr_transcript": response.get("asr_transcript"),
            "post_processing": post_processing_policy or "none",
            "post_processing_result": normalization_result,
        })
    manifest = {
        "schema": "persona_dream.technical_screen_neutral_calibration.v1",
        "created_at": utc_now(),
        "mocked": False,
        "live": True,
        "endpoint": f"POST {CHATTERBOX}/synthesize-batch",
        "render_count": len(renders),
        "request": request,
        "request_sha256": sha_obj(request),
        "normalization_policy": {
            "schema": "persona_dream.listener_study_normalization_policy.v1",
            "norm_loudness": norm_loudness,
            "scope": "neutral calibration renders",
        },
        "post_processing_policy": post_processing_policy or "none",
        "server_boot": {
            "started_at_utc": health.get("started_at_utc"),
            "engine": health.get("engine"),
            "device": health.get("device"),
            "model_load_seconds": health.get("model_load_seconds"),
        },
        "backend_capability_digests": {
            name: (spec.get("capability_digest"))
            for name, spec in (health.get("voice_backends") or {}).items()
        },
        "deterministic_seed": {
            name: ((spec.get("capabilities") or {}).get("deterministic_seed"))
            for name, spec in (health.get("voice_backends") or {}).items()
        },
        "renders": renders,
        "boundary": (
            "Measures same-parameter renderer spread only. Not evidence of "
            "emotion, identity, or naturalness."
        ),
    }
    path = out_dir / "NEUTRAL_CALIBRATION_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def calibrate(neutral_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-metric neutral median and spread; tolerance from the frozen rule."""
    import numpy as np

    metrics = sorted(set(INTENDED_MEDIATORS) | set(NUISANCE_METRICS))
    out: dict[str, Any] = {}
    for metric in metrics:
        values = [float(row[metric]) for row in neutral_metrics if metric in row]
        if len(values) < 2:
            continue
        median = float(np.median(values))
        sd = float(np.std(values, ddof=1))
        floor = float(TOLERANCE_RULE["floors"].get(metric, 0.0))
        out[metric] = {
            "n": len(values),
            "median": round(median, 6),
            "sd": round(sd, 6),
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "tolerance": round(max(TOLERANCE_RULE["k_sd"] * sd, floor), 6),
            "tolerance_source": "k_sd*sd" if TOLERANCE_RULE["k_sd"] * sd >= floor else "floor",
            "class": "intended_mediator" if metric in INTENDED_MEDIATORS else "nuisance",
        }
    return out


# --------------------------------------------------------------------------
# Screen
# --------------------------------------------------------------------------


def screen_conditions(condition_metrics: dict[str, dict[str, Any]],
                      calibration: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Compare every condition to neutral. Raw rows survive even when blocking."""
    rows: list[dict[str, Any]] = []
    failed: list[str] = []
    for condition, metrics in sorted(condition_metrics.items()):
        for metric, cal in sorted(calibration.items()):
            if metric not in metrics:
                continue
            value = float(metrics[metric])
            delta = value - float(cal["median"])
            within = abs(delta) <= float(cal["tolerance"])
            row = {
                "condition": condition,
                "metric": metric,
                "class": cal["class"],
                "value": round(value, 6),
                "neutral_median": cal["median"],
                "neutral_sd": cal["sd"],
                "delta": round(delta, 6),
                "tolerance": cal["tolerance"],
                "within_neutral_spread": within,
            }
            rows.append(row)
            # Intended mediators may legitimately move; they are reported, not
            # gated. Nuisance metrics gate.
            if not within and cal["class"] == "nuisance":
                failed.append(f"nuisance_metric_exceeds_neutral_spread:{condition}:{metric}")
    return rows, failed


def hard_gate_failures(condition_metrics: dict[str, dict[str, Any]],
                       asr: dict[str, dict[str, Any]]) -> list[str]:
    """Gates that hold regardless of neutral spread."""
    hard = TOLERANCE_RULE["hard_gates_independent_of_neutral_spread"]
    failed: list[str] = []
    encodings: dict[str, tuple] = {}
    for condition, metrics in sorted(condition_metrics.items()):
        if float(metrics.get("clipping_ratio", 0.0)) > float(hard["clipping_ratio_max"]):
            failed.append(f"clipping_exceeds_hard_gate:{condition}")
        encodings[condition] = tuple(metrics.get(key) for key in hard["identical_encoding_required"])
        row = asr.get(condition) or {}
        if row:
            if row.get("wer") is not None and float(row["wer"]) > float(hard["asr_wer_max"]):
                failed.append(f"asr_wer_exceeds_hard_gate:{condition}")
            if int(row.get("max_repeated_ngram") or 0) > int(hard["max_repeated_ngram"]):
                failed.append(f"repetition_exceeds_hard_gate:{condition}")
    if len(set(encodings.values())) > 1:
        failed.append("encoding_mismatch_across_conditions")
    return failed


def binding_failures(prereg: dict[str, Any], condition_metrics: dict[str, dict[str, Any]],
                     manifest_bindings: dict[str, Any]) -> list[str]:
    """Every scored WAV must bind to one canonical request and one lineage."""
    failed: list[str] = []
    expected = {str(s.get("condition")): s for s in prereg.get("stimuli") or []}
    engines = set()
    refs = set()
    for condition, binding in sorted(manifest_bindings.items()):
        source = expected.get(condition) or {}
        if binding.get("wav_sha256") != source.get("sha256"):
            failed.append(f"stimulus_hash_not_bound_to_preregistration:{condition}")
        engines.add(binding.get("engine"))
        refs.add(binding.get("reference_audio_sha256"))
        if not binding.get("canonical_text_sha256"):
            failed.append(f"canonical_text_binding_missing:{condition}")
        if not binding.get("voice_delivery_sha256"):
            failed.append(f"voice_delivery_binding_missing:{condition}")
    if len(engines) > 1:
        failed.append(f"backend_mismatch_across_conditions:{sorted(str(e) for e in engines)}")
    if len(refs) > 1:
        failed.append("reference_audio_mismatch_across_conditions")
    if len(manifest_bindings) != len(expected):
        failed.append("stimulus_count_mismatch_with_preregistration")
    return failed


def build_bindings(prereg: dict[str, Any], study_dir: Path,
                   condition_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    answer_text = str((prereg.get("stimulus_source") or {}).get("answer_text") or "")
    reference = str((prereg.get("stimulus_source") or {}).get("reference") or "")
    engine_default = str((prereg.get("stimulus_source") or {}).get("engine") or "")
    mapping_version = str(prereg.get("schema") or "")
    bindings: dict[str, Any] = {}
    for stimulus in prereg.get("stimuli") or []:
        condition = str(stimulus.get("condition"))
        metrics = condition_metrics.get(condition) or {}
        bindings[condition] = {
            "condition": condition,
            "canonical_text": answer_text,
            "canonical_text_sha256": "sha256:" + hashlib.sha256(answer_text.encode()).hexdigest(),
            "voice_delivery": stimulus.get("voice_delivery"),
            "voice_delivery_sha256": sha_obj(stimulus.get("voice_delivery") or {}),
            "mapping_version": mapping_version,
            "engine": stimulus.get("engine") or engine_default,
            "reference_audio": reference,
            "reference_audio_sha256": "sha256:" + hashlib.sha256(reference.encode()).hexdigest(),
            "wav": metrics.get("path"),
            "wav_sha256": metrics.get("wav_sha256"),
            "raw_wav": stimulus.get("raw_audio"),
            "raw_wav_sha256": stimulus.get("raw_sha256"),
            "sample_rate": metrics.get("sample_rate"),
            "channels": metrics.get("channels"),
            "duration_s": metrics.get("duration_s"),
            "post_processing": stimulus.get("post_processing") or "none",
            "post_processing_sha256": stimulus.get("post_processing_sha256"),
        }
    return bindings


def run(args: argparse.Namespace) -> dict[str, Any]:
    study_dir = Path(args.study_dir)
    prereg_v2 = study_dir / "PREREGISTRATION_V2.json"
    prereg_path = prereg_v2 if prereg_v2.is_file() else study_dir / "PREREGISTRATION.json"
    prereg = load_json(prereg_path)
    failed: list[str] = []

    neutral_dir = study_dir / NEUTRAL_DIR_NAME
    neutral_manifest_path = neutral_dir / "NEUTRAL_CALIBRATION_MANIFEST.json"

    if args.render_neutral:
        control = next(
            (s for s in prereg.get("stimuli") or [] if str(s.get("condition")) == "control"), {}
        )
        post_processing_policy = (prereg.get("stimulus_source") or {}).get("post_processing_policy")
        render_neutral_set(
            study_dir,
            args.render_neutral,
            ref_audio=args.ref_audio,
            answer_text=str((prereg.get("stimulus_source") or {}).get("answer_text") or ""),
            voice_delivery=control.get("voice_delivery") or {"tone": "neutral", "intensity": 0.0, "valence": 0.0},
            norm_loudness=args.norm_loudness,
            post_processing_policy=post_processing_policy if isinstance(post_processing_policy, dict) else None,
        )

    if not neutral_manifest_path.is_file():
        failed.append("neutral_calibration_set_missing")
        neutral_manifest: dict[str, Any] = {}
        neutral_metrics: list[dict[str, Any]] = []
        neutral_raw_metrics: list[dict[str, Any]] = []
    else:
        neutral_manifest = load_json(neutral_manifest_path)
        neutral_metrics = []
        neutral_raw_metrics = []
        for row in neutral_manifest.get("renders") or []:
            wav = resolve_bundle_path(row.get("wav"))
            if not wav.is_file():
                failed.append(f"neutral_render_missing:{row.get('wav')}")
                continue
            if sha_file(wav) != row.get("wav_sha256"):
                failed.append(f"neutral_render_hash_mismatch:{row.get('wav')}")
                continue
            neutral_metrics.append(measure_wav(wav))
            raw_wav = resolve_bundle_path(row.get("raw_wav"))
            if raw_wav.is_file():
                if row.get("raw_wav_sha256") and sha_file(raw_wav) != row.get("raw_wav_sha256"):
                    failed.append(f"neutral_raw_render_hash_mismatch:{row.get('raw_wav')}")
                neutral_raw_metrics.append(measure_wav(raw_wav))
        if len(neutral_metrics) < int(args.min_neutral):
            failed.append(
                f"neutral_calibration_too_small:{len(neutral_metrics)}<{args.min_neutral}"
            )

    raw_condition_metrics: dict[str, dict[str, Any]] = {}
    condition_metrics: dict[str, dict[str, Any]] = {}
    asr_rows: dict[str, dict[str, Any]] = {}
    expected_text = str((prereg.get("stimulus_source") or {}).get("answer_text") or "")
    for stimulus in prereg.get("stimuli") or []:
        condition = str(stimulus.get("condition"))
        wav = resolve_bundle_path(stimulus.get("audio"))
        if not wav.is_file():
            failed.append(f"stimulus_missing:{condition}")
            continue
        condition_metrics[condition] = measure_wav(wav, expected_text=expected_text)
        raw_wav = resolve_bundle_path(stimulus.get("raw_audio"))
        if raw_wav.is_file():
            if stimulus.get("raw_sha256") and sha_file(raw_wav) != stimulus.get("raw_sha256"):
                failed.append(f"raw_stimulus_hash_mismatch:{condition}")
            raw_condition_metrics[condition] = measure_wav(raw_wav, expected_text=expected_text)

    # ASR rows come from the existing validation receipt so this screen does not
    # duplicate (or diverge from) the study's own transcription authority.
    validation_path = study_dir / "STIMULUS_VALIDATION_RECEIPT.json"
    if validation_path.is_file():
        validation = load_json(validation_path)
        for row in validation.get("stimuli") or []:
            condition = str(row.get("condition"))
            asr = row.get("asr") or {}
            transcript = asr.get("transcript")
            asr_rows[condition] = {
                "transcript": transcript,
                "wer": asr.get("wer"),
                "max_repeated_ngram": max_repeated_ngram(transcript or ""),
                "source_receipt": rel(validation_path),
            }
    else:
        failed.append("stimulus_validation_receipt_missing")

    calibration = calibrate(neutral_metrics) if neutral_metrics else {}
    rows, spread_failures = screen_conditions(condition_metrics, calibration) if calibration else ([], [])
    failed.extend(spread_failures)
    failed.extend(hard_gate_failures(condition_metrics, asr_rows))
    bindings = build_bindings(prereg, study_dir, condition_metrics)
    failed.extend(binding_failures(prereg, condition_metrics, bindings))

    manifest = {
        "schema": "persona_dream.technical_screen_manifest.v1",
        "created_at": utc_now(),
        "issue": "grahama1970/agent-skills#1127",
        "study_dir": rel(study_dir),
        "preregistration": rel(prereg_path),
        "preregistration_sha256": sha_file(prereg_path),
        "tolerance_rule": TOLERANCE_RULE,
        "tolerance_rule_sha256": sha_obj(TOLERANCE_RULE),
        "intended_mediators": list(INTENDED_MEDIATORS),
        "nuisance_metrics": list(NUISANCE_METRICS),
        "neutral_calibration_manifest": rel(neutral_manifest_path) if neutral_manifest else None,
        "neutral_calibration_manifest_sha256": sha_file(neutral_manifest_path)
        if neutral_manifest_path.is_file() else None,
        "neutral_render_count": len(neutral_metrics),
        "neutral_metrics_raw": neutral_raw_metrics,
        "neutral_metrics_final": neutral_metrics,
        "calibration": calibration,
        "stimulus_bindings": bindings,
        "condition_metrics_raw": raw_condition_metrics,
        "condition_metrics_final": condition_metrics,
        "asr": asr_rows,
        "comparison_rows": rows,
    }
    manifest_path = Path(args.manifest_out)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status = "PASS_STIMULUS_TECHNICAL_SCREEN" if not failed else "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    receipt = {
        "schema": "persona_dream.technical_screen_receipt.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": bool(neutral_manifest.get("live")),
        "issue": "grahama1970/agent-skills#1127",
        "blocks": "grahama1970/agent-skills#1058 human collection until PASS",
        "study_dir": rel(study_dir),
        "manifest": rel(manifest_path),
        "manifest_sha256": sha_file(manifest_path),
        "tolerance_rule_sha256": sha_obj(TOLERANCE_RULE),
        "neutral_render_count": len(neutral_metrics),
        "conditions_screened": sorted(condition_metrics),
        "comparison_row_count": len(rows),
        "nuisance_rows_outside_neutral_spread": [
            row for row in rows if row["class"] == "nuisance" and not row["within_neutral_spread"]
        ],
        "intended_mediator_rows_outside_neutral_spread": [
            row for row in rows
            if row["class"] == "intended_mediator" and not row["within_neutral_spread"]
        ],
        "failed_gates": failed,
        "claims": {
            "proves": [
                "every scored WAV binds to one canonical request text, voice_delivery, "
                "backend, and reference audio",
                "no nuisance acoustic metric separates a condition from neutral by more "
                "than the renderer's own same-parameter stochastic spread",
                "no condition clips, drifts in ASR, repeats, or differs in encoding",
            ] if status.startswith("PASS") else [],
            "does_not_prove": [
                "that any requested emotion was realized in the audio",
                "perceived emotion, naturalness, or human identity recognition",
                "anything about conditions or renderers outside this preregistered set",
            ],
        },
    }
    receipt_path = Path(args.out)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR / "TECHNICAL_SCREEN_RECEIPT.json")
    parser.add_argument("--manifest-out", type=Path,
                        default=DEFAULT_STUDY_DIR / "TECHNICAL_SCREEN_MANIFEST.json")
    parser.add_argument("--render-neutral", type=int, default=0,
                        help="Render N neutral repeats through live Chatterbox before screening.")
    parser.add_argument("--min-neutral", type=int, default=DEFAULT_NEUTRAL_RENDERS,
                        help="Fail closed below this many usable neutral renders.")
    parser.add_argument("--ref-audio", default="/data/embry_ref.wav")
    parser.add_argument("--norm-loudness", type=parse_norm_loudness, default=None,
                        help="Pass one Chatterbox norm_loudness policy into live neutral renders.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "receipt": rel(Path(args.out)),
        "manifest": receipt["manifest"],
        "neutral_render_count": receipt["neutral_render_count"],
        "nuisance_outside_spread": len(receipt["nuisance_rows_outside_neutral_spread"]),
        "failed_gates": receipt["failed_gates"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
