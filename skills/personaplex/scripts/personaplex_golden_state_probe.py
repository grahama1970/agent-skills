#!/usr/bin/env python3
"""Measure whether PersonaPlex can restore a preconditioned Embry stream state.

Purpose
-------
This is a narrow, real-runtime probe for the PersonaPlex live-server bottleneck:
stock ``moshi.server`` spends roughly 15 seconds per WebSocket connection running
voice + text prompt pre-roll before the handshake. The intended production fix is
not to speculate about "golden state" cloning, but to prove whether the actual
``LMGen`` streaming state can be captured after pre-roll, restored quickly, and
then used for normal audio/text generation.

The probe performs these checks in one file:

1. load the real PersonaPlex/Moshi runtime;
2. load the current Embry PersonaPlex ``.pt`` voice prompt;
3. run the exact server-style prompt pre-roll once;
4. recursively clone the ``LMGen`` streaming state as a candidate golden state;
5. restore that state multiple times and time the restore path;
6. after each restore, feed real encoded silence frames through the model and
   decode returned audio tokens so the restore is not a no-op.

This does not patch the live server. It creates the evidence needed to decide
whether a server fork should use cached preconditioned state.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import torch


ROOT = Path("${HOME}/workspace/experiments/agent-skills")
PERSONAPLEX_ROOT = Path("${HOME}/workspace/experiments/personaplex")
PERSONAPLEX_PYTHON = PERSONAPLEX_ROOT / ".venv/bin/python"
DEFAULT_VOICE_PROMPT = Path(
    "/mnt/storage12tb/skills/personaplex/outputs/e2e/"
    "embry-conversational-20260622T152647Z/neutral/voice-prompt.pt"
)
OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/golden-state-probe/embry")
DEFAULT_TEXT_PROMPT = (
    "You are Embry Lawson. You are warm, concise, grounded, and emotionally "
    "present. You may acknowledge uncertainty, but you do not invent facts."
)


def ensure_runtime_python() -> None:
    if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clone_streaming_state(value: Any) -> Any:
    """Clone a nested streaming-state object without sharing tensor storage."""
    if torch.is_tensor(value):
        return value.detach().clone()
    if dataclasses.is_dataclass(value):
        kwargs = {field.name: clone_streaming_state(getattr(value, field.name)) for field in dataclasses.fields(value)}
        return type(value)(**kwargs)
    if isinstance(value, dict):
        return {key: clone_streaming_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clone_streaming_state(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clone_streaming_state(item) for item in value)
    return value


def summarize_state(value: Any) -> Any:
    """Return tensor shapes/dtypes for a receipt without dumping model state."""
    if torch.is_tensor(value):
        return {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "device": str(value.device),
            "numel": int(value.numel()),
        }
    if dataclasses.is_dataclass(value):
        return {field.name: summarize_state(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): summarize_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [summarize_state(item) for item in value[:8]]
    if isinstance(value, tuple):
        return [summarize_state(item) for item in value[:8]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return type(value).__name__


def env_summary() -> dict[str, Any]:
    return {
        "python": sys.executable,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch": torch.__version__,
    }


def seed_all(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    random.seed(seed)


def wrap_with_system_tags(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("<system>") and cleaned.endswith("<system>"):
        return cleaned
    return f"<system> {cleaned} <system>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-prompt", type=Path, default=DEFAULT_VOICE_PROMPT)
    parser.add_argument("--text-prompt", default=DEFAULT_TEXT_PROMPT)
    parser.add_argument("--restores", type=int, default=3)
    parser.add_argument("--probe-frames", type=int, default=8)
    parser.add_argument("--device", default="cuda")
    return parser.parse_args()


def main() -> int:
    ensure_runtime_python()
    args = parse_args()
    output_dir = OUTPUT_ROOT / utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = output_dir / "personaplex-golden-state-probe-receipt.json"

    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema": "personaplex.golden_state_probe.v1",
        "status": "STARTED",
        "output_dir": str(output_dir),
        "runtime": env_summary(),
        "voice_prompt": str(args.voice_prompt),
        "text_prompt_chars": len(args.text_prompt),
        "restores_requested": args.restores,
        "probe_frames": args.probe_frames,
    }
    write_json(receipt_path, receipt)

    if not args.voice_prompt.exists():
        receipt["status"] = "FAIL"
        receipt["error"] = f"voice prompt not found: {args.voice_prompt}"
        write_json(receipt_path, receipt)
        return 1

    sys.path.insert(0, str(PERSONAPLEX_ROOT))
    from huggingface_hub import hf_hub_download
    import sentencepiece
    from moshi.models import loaders, LMGen

    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    seed_all(42424242)

    load_start = time.monotonic()
    mimi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
    tokenizer_path = hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)
    moshi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
    mimi = loaders.get_mimi(mimi_weight, device)
    other_mimi = loaders.get_mimi(mimi_weight, device)
    tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)  # type: ignore
    lm = loaders.get_moshi_lm(moshi_weight, device=device, cpu_offload=False)
    lm.eval()
    frame_size = int(mimi.sample_rate / mimi.frame_rate)
    lm_gen = LMGen(
        lm,
        audio_silence_frame_cnt=int(0.5 * mimi.frame_rate),
        sample_rate=mimi.sample_rate,
        device=device,
        frame_rate=mimi.frame_rate,
        save_voice_prompt_embeddings=False,
    )
    mimi.streaming_forever(1)
    other_mimi.streaming_forever(1)
    lm_gen.streaming_forever(1)
    if device.type == "cuda":
        torch.cuda.synchronize()
    receipt["load_ms"] = round((time.monotonic() - load_start) * 1000, 2)

    # Minimal warmup matching the server's shape path.
    warm_start = time.monotonic()
    with torch.no_grad():
        for _ in range(4):
            chunk = torch.zeros(1, 1, frame_size, dtype=torch.float32, device=device)
            codes = mimi.encode(chunk)
            _ = other_mimi.encode(chunk)
            for c in range(codes.shape[-1]):
                tokens = lm_gen.step(codes[:, :, c : c + 1])
                if tokens is None:
                    continue
                _ = mimi.decode(tokens[:, 1:9])
                _ = other_mimi.decode(tokens[:, 1:9])
    if device.type == "cuda":
        torch.cuda.synchronize()
    receipt["warmup_ms"] = round((time.monotonic() - warm_start) * 1000, 2)

    lm_gen.load_voice_prompt_embeddings(str(args.voice_prompt))
    lm_gen.text_prompt_tokens = tokenizer.encode(wrap_with_system_tags(args.text_prompt))

    pre_roll_start = time.monotonic()
    with torch.no_grad():
        mimi.reset_streaming()
        other_mimi.reset_streaming()
        lm_gen.reset_streaming()
        lm_gen.step_system_prompts(mimi)
        mimi.reset_streaming()
    if device.type == "cuda":
        torch.cuda.synchronize()
    receipt["pre_roll_ms"] = round((time.monotonic() - pre_roll_start) * 1000, 2)

    clone_start = time.monotonic()
    golden_state = clone_streaming_state(lm_gen.get_streaming_state())
    if device.type == "cuda":
        torch.cuda.synchronize()
    receipt["clone_ms"] = round((time.monotonic() - clone_start) * 1000, 2)
    receipt["golden_state_summary"] = summarize_state(golden_state)

    restore_runs: list[dict[str, Any]] = []
    for index in range(args.restores):
        restore_start = time.monotonic()
        with torch.no_grad():
            mimi.reset_streaming()
            other_mimi.reset_streaming()
            lm_gen.set_streaming_state(clone_streaming_state(golden_state))
        if device.type == "cuda":
            torch.cuda.synchronize()
        restore_ms = round((time.monotonic() - restore_start) * 1000, 2)

        probe_start = time.monotonic()
        text_tokens: list[int] = []
        audio_frames = 0
        with torch.no_grad():
            for _ in range(args.probe_frames):
                chunk = torch.zeros(1, 1, frame_size, dtype=torch.float32, device=device)
                codes = mimi.encode(chunk)
                for c in range(codes.shape[-1]):
                    tokens = lm_gen.step(codes[:, :, c : c + 1])
                    if tokens is None:
                        continue
                    pcm = mimi.decode(tokens[:, 1:9])
                    _ = other_mimi.decode(tokens[:, 1:9])
                    audio_frames += int(pcm.shape[-1])
                    text_token = int(tokens[0, 0, 0].item())
                    if text_token not in (0, 3):
                        text_tokens.append(text_token)
        if device.type == "cuda":
            torch.cuda.synchronize()
        restore_runs.append(
            {
                "index": index,
                "restore_ms": restore_ms,
                "post_restore_probe_ms": round((time.monotonic() - probe_start) * 1000, 2),
                "audio_frames_decoded": audio_frames,
                "text_token_count": len(text_tokens),
                "text_preview": "".join(tokenizer.id_to_piece(token).replace("▁", " ") for token in text_tokens)[:200],
            }
        )

    receipt["restore_runs"] = restore_runs
    receipt["restore_ms_median"] = round(statistics.median(run["restore_ms"] for run in restore_runs), 2) if restore_runs else None
    receipt["restore_ms_max"] = max((run["restore_ms"] for run in restore_runs), default=None)
    receipt["status"] = "PASS" if restore_runs and all(run["audio_frames_decoded"] > 0 for run in restore_runs) else "FAIL"
    receipt["total_ms"] = round((time.monotonic() - started) * 1000, 2)
    write_json(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
