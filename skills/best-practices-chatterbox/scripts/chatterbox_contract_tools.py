#!/usr/bin/env python3
"""Utilities for applying the Chatterbox rendering guidance contract.

The tools produce JSON plans and local audio-reference checks. They do not load
or call the Chatterbox model directly; the renderer service owns synthesis.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import wave
import xml.etree.ElementTree as ET
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

NATIVE_TAGS = {
    "clear throat": "[clear throat]",
    "sigh": "[sigh]",
    "shush": "[shush]",
    "cough": "[cough]",
    "groan": "[groan]",
    "sniff": "[sniff]",
    "gasp": "[gasp]",
    "chuckle": "[chuckle]",
    "laugh": "[laugh]",
    "laughter": "[laugh]",
}
EXTENDED_TAGS = {
    "angry": "[angry]",
    "fear": "[fear]",
    "surprised": "[surprised]",
    "whispering": "[whispering]",
    "dramatic": "[dramatic]",
    "narration": "[narration]",
    "crying": "[crying]",
    "happy": "[happy]",
    "sarcastic": "[sarcastic]",
}
EMOTION_MAP = {**NATIVE_TAGS, **EXTENDED_TAGS, "clear-throat": "[clear throat]", "clear_throat": "[clear throat]"}
PAUSE_RE = re.compile(r"\[pause:(\d+ms|\d+(?:\.\d+)?s)\]", re.I)
TAG_RE = re.compile(r"\[([^\]]+)\]")
SENTENCE_RE = re.compile(r"([.!?])\s+")


@dataclass(frozen=True, slots=True)
class ReferenceAudioReport:
    is_valid: bool
    duration_sec: float
    sample_rate: int
    num_channels: int
    snr_db: float
    clipping_ratio: float
    speech_ratio: float
    rms_db: float
    warnings: list[str]
    errors: list[str]


def normalize_delay_markup(text: str) -> str:
    clean = " ".join(str(text or "").split())
    clean = re.sub(r"\s*\.\.\.\s*", " ... ", clean)
    clean = re.sub(r"\.{4,}", " ... ", clean)
    clean = re.sub(r"\s+([,;!?])", r"\1", clean)
    return " ".join(clean.split())


def preprocess_text(text: str, *, convert_markdown_emphasis: bool = True) -> str:
    value = str(text or "")
    if convert_markdown_emphasis:
        value = re.sub(r"\*\*([^*]+)\*\*|\*([^*]+)\*", lambda m: (m.group(1) or m.group(2)).upper(), value)
    value = re.sub(r"\s*--\s*", " — ", value)
    value = normalize_delay_markup(value)

    def anchor_tag(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        lowered = raw.lower()
        if lowered.startswith("pause:"):
            return f"[{lowered}]"
        mapped = EMOTION_MAP.get(lowered)
        if mapped:
            return f" ... {mapped}"
        return match.group(0)

    value = TAG_RE.sub(anchor_tag, value)
    value = normalize_delay_markup(value)
    value = re.sub(r"\s+([,;!?—])", r"\1", value)
    return " ".join(value.split())


def ssml_to_chatterbox(ssml_text: str) -> str:
    clean = str(ssml_text or "").strip()
    if not clean.startswith("<speak"):
        clean = f"<speak>{clean}</speak>"
    clean = re.sub(r"<(/?)\w+:", r"<\1", clean)
    try:
        root = ET.fromstring(clean)
        return preprocess_text(_parse_ssml_node(root), convert_markdown_emphasis=False)
    except ET.ParseError:
        return preprocess_text(_fallback_ssml_regex(str(ssml_text or "")), convert_markdown_emphasis=False)


def _parse_ssml_node(node: ET.Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        tag = child.tag.lower()
        if tag == "break":
            parts.append(f" [pause:{child.attrib.get('time', '500ms')}] ")
        elif tag == "emphasis":
            inner = _parse_ssml_node(child)
            parts.append(inner.upper() if child.attrib.get("level", "strong") in {"strong", "moderate"} else inner)
        elif tag in {"express-as", "emotion"}:
            expr = (child.attrib.get("type") or child.attrib.get("name") or "").lower()
            parts.append(f" ... {EMOTION_MAP.get(expr, f'[{expr}]')} {_parse_ssml_node(child)} ")
        elif tag in EMOTION_MAP:
            parts.append(f" ... {EMOTION_MAP[tag]} ")
        else:
            parts.append(_parse_ssml_node(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _fallback_ssml_regex(text: str) -> str:
    value = re.sub(r'<break\s+time=["\']([^"\']+)["\']\s*/?>', r" [pause:\1] ", text)
    value = re.sub(r"<emphasis[^>]*>(.*?)</emphasis>", lambda m: m.group(1).upper(), value, flags=re.I | re.S)
    for name, tag in EMOTION_MAP.items():
        value = re.sub(rf'<express-as\s+type=["\']{re.escape(name)}["\']\s*>(.*?)</express-as>', rf" ... {tag} \1 ", value, flags=re.I | re.S)
        value = re.sub(rf"<{re.escape(name)}\s*/?>", f" ... {tag} ", value, flags=re.I)
    return re.sub(r"<[^>]+>", "", value)


def pause_to_ms(token: str) -> int:
    value = token.strip().lower()
    if value.endswith("ms"):
        return int(float(value[:-2]))
    if value.endswith("s"):
        return int(float(value[:-1]) * 1000)
    raise ValueError(f"unsupported_pause_token:{token}")


def plan_render_chunks(text: str, *, tone: str = "neutral_warm", default_sentence_ms: int = 600,
                       default_comma_ms: int = 250, ellipsis_ms: int = 900) -> dict[str, Any]:
    answer_text = preprocess_text(text)
    segments: list[dict[str, Any]] = []
    pending = answer_text
    last_end = 0
    explicit: list[tuple[int, int, int]] = []
    for match in PAUSE_RE.finditer(answer_text):
        explicit.append((match.start(), match.end(), pause_to_ms(match.group(1))))
    if explicit:
        chunks: list[dict[str, Any]] = []
        cursor = 0
        for start, end, pause_ms in explicit:
            chunk_text = answer_text[cursor:start].strip()
            if chunk_text:
                chunks.append({"text": chunk_text, "pause_after_ms": pause_ms, "tone": tone, "role": "explicit_pause"})
            cursor = end
        tail = answer_text[cursor:].strip()
        if tail:
            chunks.append({"text": tail, "pause_after_ms": 0, "tone": tone, "role": "after_pause"})
        return {"answer_text": re.sub(PAUSE_RE, "", answer_text).strip(), "render_chunks": chunks}
    parts = [part.strip() for part in re.split(r"\s+\.\.\.\s+", answer_text) if part.strip()]
    if len(parts) > 1:
        for idx, part in enumerate(parts):
            segments.append({"text": part + (" ..." if idx < len(parts) - 1 else ""), "pause_after_ms": ellipsis_ms if idx < len(parts) - 1 else 0, "tone": tone, "role": "ellipsis_pause" if idx < len(parts) - 1 else "finish"})
        return {"answer_text": answer_text, "render_chunks": segments}
    pause_ms = 0
    if re.search(r"[,;—]\s*$", pending):
        pause_ms = default_comma_ms
    elif re.search(r"[.!?]\s*$", pending):
        pause_ms = default_sentence_ms
    return {"answer_text": answer_text, "render_chunks": [{"text": answer_text, "pause_after_ms": pause_ms, "tone": tone, "role": "single_chunk"}]}


def sweep_plan(text: str, *, backend: str = "chatterbox_base", exaggeration_steps: list[float] | None = None,
               cfg_steps: list[float] | None = None, temperature: float = 0.8, seed: int = 42) -> dict[str, Any]:
    ex_steps = exaggeration_steps or [0.3, 0.5, 0.7, 0.9]
    cfg_values = cfg_steps or [0.0, 0.25, 0.5, 0.75]
    runs = [
        {"text": text, "backend": backend, "exaggeration": ex, "cfg_weight": cfg, "temperature": temperature, "seed": seed}
        for ex in ex_steps for cfg in cfg_values
    ]
    return {
        "schema": "best_practices_chatterbox.sweep_plan.v1",
        "backend": backend,
        "run_count": len(runs),
        "runs": runs,
        "boundary": "In the verified local service, chatterbox_turbo ignores exaggeration and cfg_weight; use this sweep for backends that honor those knobs or as an explicit comparison.",
    }


def check_reference_audio(path: Path, *, min_duration_sec: float = 3.0, max_duration_sec: float = 12.0,
                          target_sample_rate: int = 24_000, max_clipping_ratio: float = 0.001,
                          min_snr_db: float = 18.0, min_speech_ratio: float = 0.60,
                          min_rms_db: float = -35.0, max_rms_db: float = -3.0) -> ReferenceAudioReport:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return ReferenceAudioReport(False, 0.0, 0, 0, 0.0, 0.0, 0.0, -float("inf"), [], [f"File not found: {path}"])
    with wave.open(str(path), "rb") as fh:
        channels = fh.getnchannels()
        sample_rate = fh.getframerate()
        sample_width = fh.getsampwidth()
        frames = fh.readframes(fh.getnframes())
    if sample_width != 2:
        errors.append(f"Unsupported sample width: {sample_width}")
        return ReferenceAudioReport(False, 0.0, sample_rate, channels, 0.0, 0.0, 0.0, -float("inf"), warnings, errors)
    pcm = array("h")
    pcm.frombytes(frames)
    values = list(pcm)
    if channels > 1:
        warnings.append(f"Audio has {channels} channels; mono downmixing will occur during inference.")
        values = [sum(values[i:i + channels]) / channels for i in range(0, len(values), channels)]
    samples = [float(v) / 32768.0 for v in values]
    duration = len(samples) / sample_rate if sample_rate else 0.0
    if sample_rate != target_sample_rate:
        warnings.append(f"Sample rate ({sample_rate} Hz) does not match target ({target_sample_rate} Hz); resample needed.")
    if duration < min_duration_sec:
        errors.append(f"Duration ({duration:.2f}s) is below minimum threshold ({min_duration_sec}s).")
    elif duration > max_duration_sec:
        warnings.append(f"Duration ({duration:.2f}s) exceeds optimal range ({max_duration_sec}s); prompt may be truncated.")
    abs_samples = [abs(x) for x in samples]
    clipping_ratio = sum(1 for x in abs_samples if x >= 0.99) / len(abs_samples) if abs_samples else 0.0
    if clipping_ratio > max_clipping_ratio:
        errors.append(f"Excessive clipping detected ({clipping_ratio * 100:.2f}% of total samples).")
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0.0
    rms_db = 20 * math.log10(max(rms, 1e-8))
    if rms_db < min_rms_db:
        errors.append(f"Audio level is too quiet ({rms_db:.1f} dB RMS). Target >= {min_rms_db} dB.")
    elif rms_db > max_rms_db:
        warnings.append(f"Audio level is exceptionally loud ({rms_db:.1f} dB RMS). Risk of dynamic distortion.")
    frame_len = max(1, int(sample_rate * 0.02))
    frames_rms = []
    for pos in range(0, len(samples) - frame_len + 1, frame_len):
        chunk = samples[pos:pos + frame_len]
        frames_rms.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)))
    if not frames_rms:
        return ReferenceAudioReport(False, round(duration, 2), sample_rate, channels, 0.0, clipping_ratio, 0.0, round(rms_db, 1), warnings, [*errors, "Audio sample is too short for frame analysis."])
    sorted_rms = sorted(frames_rms)
    noise_floor = sorted_rms[max(0, int(len(sorted_rms) * 0.20) - 1)]
    speech_threshold = max(noise_floor * 3.0, 1e-4)
    speech = [v for v in frames_rms if v >= speech_threshold]
    noise = [v for v in frames_rms if v < speech_threshold]
    speech_ratio = len(speech) / len(frames_rms)
    if speech_ratio < min_speech_ratio:
        errors.append(f"Insufficient active speech detected ({speech_ratio * 100:.1f}%). Trim silent margins.")
    speech_power = sum(v * v for v in speech) / len(speech) if speech else 1e-8
    noise_power = sum(v * v for v in noise) / len(noise) if noise else 1e-8
    snr_db = 10 * math.log10(max(speech_power / max(noise_power, 1e-8), 1.0))
    if snr_db < min_snr_db:
        errors.append(f"Signal-to-noise ratio is too low ({snr_db:.1f} dB).")
    return ReferenceAudioReport(not errors, round(duration, 2), sample_rate, channels, round(snr_db, 1), round(clipping_ratio, 4), round(speech_ratio, 2), round(rms_db, 1), warnings, errors)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_pre = sub.add_parser("preprocess")
    p_pre.add_argument("--text", required=True)
    p_ssml = sub.add_parser("ssml")
    p_ssml.add_argument("--text", required=True)
    p_plan = sub.add_parser("plan-silence")
    p_plan.add_argument("--text", required=True)
    p_plan.add_argument("--tone", default="neutral_warm")
    p_sweep = sub.add_parser("sweep-plan")
    p_sweep.add_argument("--text", required=True)
    p_sweep.add_argument("--backend", default="chatterbox_base")
    p_ref = sub.add_parser("check-reference")
    p_ref.add_argument("--audio", required=True, type=Path)
    args = ap.parse_args()
    if args.cmd == "preprocess":
        result = {"schema": "best_practices_chatterbox.preprocess.v1", "text": preprocess_text(args.text)}
    elif args.cmd == "ssml":
        result = {"schema": "best_practices_chatterbox.ssml_conversion.v1", "text": ssml_to_chatterbox(args.text)}
    elif args.cmd == "plan-silence":
        result = {"schema": "best_practices_chatterbox.render_plan.v1", **plan_render_chunks(args.text, tone=args.tone)}
    elif args.cmd == "sweep-plan":
        result = sweep_plan(args.text, backend=args.backend)
    else:
        result = {"schema": "best_practices_chatterbox.reference_audio_report.v1", **asdict(check_reference_audio(args.audio))}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("is_valid", True) is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
