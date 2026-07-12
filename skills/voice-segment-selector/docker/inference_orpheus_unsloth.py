#!/usr/bin/env python3
"""Live GPU inference for Orpheus Unsloth LoRA adapters."""

from __future__ import annotations

import argparse
import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
import torch
from peft import PeftModel
from snac import SNAC
from unsloth import FastLanguageModel

SNAC_MODEL_NAME = "hubertsiuzdak/snac_24khz"
SNAC_SAMPLE_RATE = 24000

DEFAULT_TEMPERATURE = float(os.environ.get("ORPHEUS_TEMPERATURE", "0.6"))
DEFAULT_TOP_P = float(os.environ.get("ORPHEUS_TOP_P", "0.9"))
DEFAULT_REPETITION_PENALTY = float(os.environ.get("ORPHEUS_REPETITION_PENALTY", "1.1"))

START_OF_HUMAN = 128259
END_OF_HUMAN = 128260
START_OF_AI = 128261
END_OF_AI = 128262
START_OF_SPEECH = 128257
END_OF_SPEECH = 128258
END_OF_TEXT = 128009
AUDIO_OFFSET = 128266
PAD_TOKEN = 128263


@dataclass
class LoadedVoice:
    speaker: str
    lora_dir: str
    model_name: str
    load_in_4bit: bool
    model: object
    tokenizer: object


class OrpheusRuntime:
    """Warm GPU runtime: load once per speaker, synthesize many times."""

    def __init__(self) -> None:
        self._voices: dict[str, LoadedVoice] = {}
        self._snac: SNAC | None = None

    def _snac_model(self) -> SNAC:
        if self._snac is None:
            self._snac = SNAC.from_pretrained(SNAC_MODEL_NAME).to("cpu").eval()
        return self._snac

    def ensure_loaded(
        self,
        *,
        speaker: str,
        lora_dir: Path,
        model_name: str = "unsloth/orpheus-3b-0.1-ft",
        max_seq_length: int = 2048,
        load_in_4bit: bool = True,
    ) -> LoadedVoice:
        key = f"{speaker}:{lora_dir.resolve()}:{model_name}:{load_in_4bit}"
        cached = self._voices.get(key)
        if cached is not None:
            return cached

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU required for Orpheus inference")

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_name,
            max_seq_length=max_seq_length,
            dtype=None,
            load_in_4bit=load_in_4bit,
        )
        model = PeftModel.from_pretrained(model, str(lora_dir))
        FastLanguageModel.for_inference(model)
        loaded = LoadedVoice(
            speaker=speaker,
            lora_dir=str(lora_dir),
            model_name=model_name,
            load_in_4bit=load_in_4bit,
            model=model,
            tokenizer=tokenizer,
        )
        self._voices[key] = loaded
        return loaded

    def synthesize(
        self,
        *,
        speaker: str,
        prompt: str,
        lora_dir: Path,
        output_dir: Path,
        model_name: str = "unsloth/orpheus-3b-0.1-ft",
        load_in_4bit: bool = True,
        min_duration_sec: float = 0.5,

        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        repetition_penalty: float = DEFAULT_REPETITION_PENALTY,
        max_new_tokens: int | None = None,
        verified: str = "live",
    ) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = output_dir / "inference_smoke.wav"
        receipt: dict = {
            "schema": "voice_segment_selector.orpheus_inference_receipt.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "speaker": speaker,
            "prompt": prompt,
            "model_name": model_name,
            "lora_dir": str(lora_dir),
            "wav_path": str(wav_path),
            "verified": verified,
            "warm_runtime": True,

            "temperature": temperature,
            "top_p": top_p,
            "repetition_penalty": repetition_penalty,
            "max_new_tokens": max_new_tokens,
        }

        if not lora_dir.is_dir():
            receipt["error"] = f"Missing lora dir: {lora_dir}"
            write_receipt(output_dir, receipt)
            return receipt

        try:
            voice = self.ensure_loaded(
                speaker=speaker,
                lora_dir=lora_dir,
                model_name=model_name,
                load_in_4bit=load_in_4bit,
            )
            input_ids, attention_mask = build_prompt_input_ids(
                voice.tokenizer,
                speaker=speaker,
                prompt=prompt,
            )
            input_ids = input_ids.to("cuda")
            attention_mask = attention_mask.to("cuda")

            if max_new_tokens is None:
                # Orpheus/SNAC emits seven audio-code tokens per frame. A
                # dynamic cap prevents the LM from free-running into invalid
                # codec tokens after it has spoken the requested text.
                max_new_tokens = min(int(len(prompt) * 1.3) * 7 + 21, 700)
                receipt["max_new_tokens"] = max_new_tokens

            generated_ids = voice.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                num_return_sequences=1,
                eos_token_id=[END_OF_SPEECH, END_OF_AI],
                pad_token_id=PAD_TOKEN,
                use_cache=True,
            )

            audio_array = decode_generated_audio(
                generated_ids.cpu(),
                prompt_token_count=int(input_ids.shape[1]),
                snac_model=self._snac_model(),
            )
            duration_sec = float(len(audio_array)) / SNAC_SAMPLE_RATE
            wavfile.write(str(wav_path), SNAC_SAMPLE_RATE, audio_array)

            receipt.update(
                {
                    "duration_sec": round(duration_sec, 3),
                    "wav_bytes": wav_path.stat().st_size,
                    "gpu": torch.cuda.get_device_name(0),
                }
            )
            if duration_sec < min_duration_sec:
                receipt["error"] = f"Generated audio too short: {duration_sec:.3f}s"
            elif wav_path.stat().st_size < 10_000:
                receipt["error"] = f"Generated WAV too small: {wav_path.stat().st_size} bytes"
            else:
                receipt["status"] = "PASS"
        except Exception as exc:
            receipt["error"] = str(exc)

        write_receipt(output_dir, receipt)
        return receipt


def build_prompt_input_ids(tokenizer, *, speaker: str, prompt: str) -> tuple[torch.Tensor, torch.Tensor]:
    text_prompt = f"{speaker}: {prompt.strip()}"
    text_ids = tokenizer.encode(text_prompt, add_special_tokens=True)
    input_ids = torch.tensor(
        [[START_OF_HUMAN] + text_ids + [END_OF_TEXT, END_OF_HUMAN, START_OF_AI, START_OF_SPEECH]],
        dtype=torch.int64,
    )
    attention_mask = torch.ones_like(input_ids)
    return input_ids, attention_mask


def decode_generated_audio(generated_ids: torch.Tensor, *, prompt_token_count: int, snac_model: SNAC) -> np.ndarray:
    row = generated_ids[0][prompt_token_count:]
    eos_positions = ((row == END_OF_SPEECH) | (row == END_OF_AI)).nonzero(as_tuple=True)
    if len(eos_positions[0]) > 0:
        row = row[: eos_positions[0][0].item()]

    row = row[(row >= AUDIO_OFFSET) & (row < AUDIO_OFFSET + 7 * 4096)]
    new_length = (row.size(0) // 7) * 7
    if new_length < 7:
        raise RuntimeError("Model did not emit enough SNAC frames for decode")
    trimmed = [int(t - AUDIO_OFFSET) for t in row[:new_length].tolist()]

    layer_1: list[int] = []
    layer_2: list[int] = []
    layer_3: list[int] = []
    for i in range(len(trimmed) // 7):
        layer_1.append(trimmed[7 * i])
        layer_2.append(trimmed[7 * i + 1] - 4096)
        layer_3.append(trimmed[7 * i + 2] - (2 * 4096))
        layer_3.append(trimmed[7 * i + 3] - (3 * 4096))
        layer_2.append(trimmed[7 * i + 4] - (4 * 4096))
        layer_3.append(trimmed[7 * i + 5] - (5 * 4096))
        layer_3.append(trimmed[7 * i + 6] - (6 * 4096))

    def validate_layer(values: list[int], layer_name: str) -> list[int]:
        invalid = [value for value in values if value < 0 or value > 4095]
        if invalid:
            raise RuntimeError(
                f"Decoded {len(invalid)} out-of-range {layer_name} SNAC tokens; "
                "refusing to clip invalid codec output into audible noise"
            )
        return values

    codes = [
        torch.tensor(validate_layer(layer_1, "layer_1")).unsqueeze(0),
        torch.tensor(validate_layer(layer_2, "layer_2")).unsqueeze(0),
        torch.tensor(validate_layer(layer_3, "layer_3")).unsqueeze(0),
    ]
    with torch.inference_mode():
        audio_hat = snac_model.decode(codes)
    return audio_hat.detach().squeeze().cpu().numpy()


def write_receipt(output_dir: Path, receipt: dict) -> None:
    path = output_dir / "inference_receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lora-dir", required=True)
    parser.add_argument("--speaker", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--prompt",
        default="Hey there, this is a smoke test of the fine-tuned Orpheus voice.",
    )
    parser.add_argument("--model-name", default="unsloth/orpheus-3b-0.1-ft")
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--min-duration-sec", type=float, default=0.5)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=DEFAULT_TOP_P)
    parser.add_argument("--repetition-penalty", type=float, default=DEFAULT_REPETITION_PENALTY)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = OrpheusRuntime()
    receipt = runtime.synthesize(
        speaker=args.speaker,
        prompt=args.prompt,
        lora_dir=Path(args.lora_dir).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
        model_name=args.model_name,
        load_in_4bit=args.load_in_4bit,
        min_duration_sec=args.min_duration_sec,
        temperature=args.temperature,
        top_p=args.top_p,
        repetition_penalty=args.repetition_penalty,
        max_new_tokens=args.max_new_tokens,
        verified="live",
    )
    print(json.dumps(receipt, indent=2))
    if receipt.get("status") != "PASS":
        raise SystemExit(receipt.get("error") or "inference smoke failed")


if __name__ == "__main__":
    main()
