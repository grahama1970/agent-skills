#!/usr/bin/env python3
"""Generate a resumable, ASR-gated Horus wake-word corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POSITIVE_TRANSCRIPT_ALIASES = {
    "hey embry": "hey embry",
    "hey embree": "hey embree",
    "hey embrie": "hey embree",
}
POSITIVE_TRANSCRIPTS = frozenset(POSITIVE_TRANSCRIPT_ALIASES)
POSITIVE_PROMPTS = (
    "Hey, Em-bree!",
    "Hey Em-bree!",
)
NEGATIVE_PROMPTS = (
    "Embry!",
    "Hey Em!",
    "Embryo!",
    "Emery!",
    "Henry!",
    "Every!",
    "Entry!",
    "Empty!",
    "Hey Henry.",
    "Hey Emily.",
    "Hey Empty.",
    "Computer!",
    "Jarvis!",
)
NEGATIVE_TRANSCRIPT_ALIASES = {
    "Embry!": frozenset({"embry", "embree", "embrie"}),
    "Embry.": frozenset({"embry", "embree", "embrie"}),
    "Hey Em!": frozenset({"hey em"}),
    "Embryo!": frozenset({"embryo"}),
    "Emery!": frozenset({"emery"}),
    "Henry!": frozenset({"henry"}),
    "Every!": frozenset({"every"}),
    "Entry!": frozenset({"entry"}),
    "Empty!": frozenset({"empty"}),
    "Hey Henry.": frozenset({"hey henry"}),
    "Hey Emily.": frozenset({"hey emily"}),
    "Hey Empty.": frozenset({"hey empty"}),
    "Computer!": frozenset({"computer"}),
    "Jarvis!": frozenset({"jarvis"}),
}
NEGATIVE_PROMPT_FAMILY = {"Embry.": "Embry!"}
SPLIT_OFFSETS = {
    "positive_train": 0,
    "positive_validation": 100_000,
    "negative_train": 200_000,
    "negative_validation": 300_000,
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_transcript(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def positive_transcript_accepted(value: str) -> bool:
    return normalize_transcript(value) in POSITIVE_TRANSCRIPTS


def canonical_positive_transcript(value: str) -> str | None:
    return POSITIVE_TRANSCRIPT_ALIASES.get(normalize_transcript(value))


def negative_transcript_accepted(value: str, *, prompt: str) -> bool:
    normalized = normalize_transcript(value)
    return (
        normalized not in POSITIVE_TRANSCRIPTS
        and normalized in NEGATIVE_TRANSCRIPT_ALIASES[prompt]
    )


def balanced_prompt_targets(prompts: tuple[str, ...], target_count: int) -> dict[str, int]:
    quotient, remainder = divmod(target_count, len(prompts))
    return {
        prompt: quotient + int(index < remainder)
        for index, prompt in enumerate(prompts)
    }


def next_negative_prompt(
    *, records: list[dict[str, Any]], split: str, target_count: int
) -> str | None:
    targets = balanced_prompt_targets(NEGATIVE_PROMPTS, target_count)
    accepted_counts = {
        prompt: sum(
            1
            for record in records
            if record["split"] == split
            and record["accepted"]
            and NEGATIVE_PROMPT_FAMILY.get(record["prompt"], record["prompt"])
            == prompt
        )
        for prompt in NEGATIVE_PROMPTS
    }
    return next(
        (
            prompt
            for prompt in NEGATIVE_PROMPTS
            if accepted_counts[prompt] < targets[prompt]
        ),
        None,
    )


def deterministic_choice(values: tuple[str, ...], *, seed: int, index: int) -> str:
    return random.Random(seed + index).choice(values)


def deterministic_parameters(*, seed: int, index: int) -> dict[str, float]:
    rng = random.Random(seed + index)
    return {
        "temperature": round(rng.uniform(0.35, 0.65), 3),
        "top_p": round(rng.uniform(0.5, 0.9), 3),
        "repetition_penalty": round(rng.uniform(1.05, 1.15), 3),
    }


def json_request(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=canonical_json(payload),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def download(url: str, *, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def multipart_transcribe(
    url: str,
    *,
    audio: bytes,
    filename: str,
    api_key: str,
    timeout: float,
) -> dict[str, Any]:
    boundary = f"embry-{sha256_bytes(audio)[:24]}"
    chunks: list[bytes] = []

    def field(name: str, value: str) -> None:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )

    field("model", "whisper-1")
    field("language", "en")
    field("response_format", "json")
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                "Content-Type: audio/wav\r\n\r\n"
            ).encode(),
            audio,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url,
        data=b"".join(chunks),
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


@dataclass(frozen=True)
class SplitSpec:
    name: str
    label: str
    target_count: int
    prompts: tuple[str, ...]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_receipt(
    *,
    output_dir: Path,
    seed: int,
    specs: list[SplitSpec],
    records: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    accepted = [record for record in records if record["accepted"]]
    counts = {
        spec.name: sum(1 for record in accepted if record["split"] == spec.name)
        for spec in specs
    }
    rejected_counts: dict[str, int] = {}
    for record in records:
        if not record["accepted"]:
            reason = record["rejection_reason"]
            rejected_counts[reason] = rejected_counts.get(reason, 0) + 1
    return {
        "schema": "embry.horus_wake_corpus_receipt.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "live": True,
        "mocked": False,
        "persona": "horus_lupercal",
        "wake_phrase": "Hey Embry",
        "accepted_transcript_variants": sorted(set(POSITIVE_TRANSCRIPT_ALIASES.values())),
        "asr_spelling_aliases": POSITIVE_TRANSCRIPT_ALIASES,
        "positive_alias_rule_id": "whisper_orthographic_embrie_to_embree_v1",
        "negative_phrase_specific_aliases": {
            prompt: sorted(aliases)
            for prompt, aliases in NEGATIVE_TRANSCRIPT_ALIASES.items()
        },
        "seed": seed,
        "output_dir": str(output_dir.resolve()),
        "targets": {spec.name: spec.target_count for spec in specs},
        "accepted_counts": counts,
        "attempt_count": len(records),
        "rejected_counts": rejected_counts,
        "manifest": {
            "path": str((output_dir / "manifest.jsonl").resolve()),
            "sha256": sha256_file(output_dir / "manifest.jsonl") if records else None,
        },
        "failed_gates": [
            f"{spec.name}_incomplete"
            for spec in specs
            if counts[spec.name] < spec.target_count
        ],
    }


def generate(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    manifest_path = output_dir / "manifest.jsonl"
    specs = [
        SplitSpec("positive_train", "positive", args.positive_train, POSITIVE_PROMPTS),
        SplitSpec(
            "positive_validation", "positive", args.positive_validation, POSITIVE_PROMPTS
        ),
        SplitSpec("negative_train", "negative", args.negative_train, NEGATIVE_PROMPTS),
        SplitSpec(
            "negative_validation", "negative", args.negative_validation, NEGATIVE_PROMPTS
        ),
    ]
    records = read_jsonl(manifest_path)
    api_key = args.whisper_api_key_file.read_text().strip()
    if not api_key:
        raise SystemExit("whisper_api_key_empty")

    for spec in specs:
        accepted_count = sum(
            1 for record in records if record["split"] == spec.name and record["accepted"]
        )
        attempts = sum(
            1
            for record in records
            if record["split"] == spec.name
            and record.get("rejection_reason") != "generation_or_validation_error"
        )
        record_index = sum(1 for record in records if record["split"] == spec.name)
        consecutive_service_errors = 0
        max_attempts = max(spec.target_count, spec.target_count * args.max_attempt_multiplier)
        while accepted_count < spec.target_count and attempts < max_attempts:
            index = record_index
            split_seed = args.seed + SPLIT_OFFSETS[spec.name]
            if spec.label == "negative":
                prompt = next_negative_prompt(
                    records=records,
                    split=spec.name,
                    target_count=spec.target_count,
                )
                if prompt is None:
                    break
            else:
                prompt = deterministic_choice(spec.prompts, seed=split_seed, index=index)
            parameters = deterministic_parameters(seed=split_seed, index=index)
            request_payload = {"prompt": prompt, "speaker": "horus", **parameters}
            record_id = sha256_bytes(
                canonical_json(
                    {"split": spec.name, "seed": split_seed, "index": index, **request_payload}
                )
            )[:24]
            try:
                synthesis = json_request(
                    f"{args.orpheus_url.rstrip('/')}/v1/synthesize",
                    request_payload,
                    timeout=args.timeout,
                )
                receipt = synthesis["receipt"]
                request_id = receipt["request_id"]
                audio = download(
                    f"{args.orpheus_url.rstrip('/')}/v1/audio/horus/{request_id}.wav",
                    timeout=args.timeout,
                )
                transcript_response = multipart_transcribe(
                    f"{args.whisper_url.rstrip('/')}/v1/audio/transcriptions",
                    audio=audio,
                    filename=f"{record_id}.wav",
                    api_key=api_key,
                    timeout=args.timeout,
                )
                transcript = str(transcript_response.get("text", ""))
                accepted = (
                    positive_transcript_accepted(transcript)
                    if spec.label == "positive"
                    else negative_transcript_accepted(transcript, prompt=prompt)
                )
                rejection_reason = None if accepted else "transcript_gate_rejected"
                audio_path = output_dir / "audio" / spec.name / f"{record_id}.wav"
                if accepted:
                    audio_path.parent.mkdir(parents=True, exist_ok=True)
                    audio_path.write_bytes(audio)
                record = {
                    "schema": "embry.horus_wake_corpus_record.v1",
                    "record_id": record_id,
                    "split": spec.name,
                    "label": spec.label,
                    "index": index,
                    "seed": split_seed,
                    "prompt": prompt,
                    "parameters": parameters,
                    "request_id": request_id,
                    "orpheus_receipt": receipt,
                    "transcript": transcript,
                    "normalized_transcript": normalize_transcript(transcript),
                    "canonical_positive_transcript": canonical_positive_transcript(transcript),
                    "accepted": accepted,
                    "rejection_reason": rejection_reason,
                    "audio_path": str(audio_path.resolve()) if accepted else None,
                    "audio_sha256": sha256_bytes(audio),
                    "audio_bytes": len(audio),
                }
            except (KeyError, OSError, ValueError, urllib.error.URLError) as error:
                record = {
                    "schema": "embry.horus_wake_corpus_record.v1",
                    "record_id": record_id,
                    "split": spec.name,
                    "label": spec.label,
                    "index": index,
                    "seed": split_seed,
                    "prompt": prompt,
                    "parameters": parameters,
                    "accepted": False,
                    "rejection_reason": "generation_or_validation_error",
                    "error": f"{type(error).__name__}: {error}",
                }
            append_jsonl(manifest_path, record)
            records.append(record)
            record_index += 1
            if record["rejection_reason"] == "generation_or_validation_error":
                consecutive_service_errors += 1
            else:
                attempts += 1
                consecutive_service_errors = 0
            accepted_count += int(record["accepted"])
            print(
                json.dumps(
                    {
                        "split": spec.name,
                        "accepted": accepted_count,
                        "target": spec.target_count,
                        "attempts": attempts,
                        "last_accepted": record["accepted"],
                        "last_transcript": record.get("transcript"),
                    }
                ),
                flush=True,
            )
            if consecutive_service_errors >= args.max_consecutive_service_errors:
                receipt = build_receipt(
                    output_dir=output_dir,
                    seed=args.seed,
                    specs=specs,
                    records=records,
                    status="INCOMPLETE",
                )
                receipt["failed_gates"].append("upstream_service_error_circuit_open")
                receipt["consecutive_service_errors"] = consecutive_service_errors
                (output_dir / "receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n"
                )
                return 2
            if args.delay_seconds:
                time.sleep(args.delay_seconds)

    receipt = build_receipt(
        output_dir=output_dir,
        seed=args.seed,
        specs=specs,
        records=records,
        status="PASS",
    )
    if receipt["failed_gates"]:
        receipt["status"] = "INCOMPLETE"
    receipt_path = output_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orpheus-url", default="http://127.0.0.1:8767")
    parser.add_argument("--whisper-url", default="http://127.0.0.1:9000")
    parser.add_argument("--whisper-api-key-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--positive-train", type=int, default=1500)
    parser.add_argument("--positive-validation", type=int, default=350)
    parser.add_argument("--negative-train", type=int, default=2000)
    parser.add_argument("--negative-validation", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--max-attempt-multiplier", type=int, default=8)
    parser.add_argument("--max-consecutive-service-errors", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    args = parser.parse_args()
    for name in (
        "positive_train",
        "positive_validation",
        "negative_train",
        "negative_validation",
    ):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    return args


if __name__ == "__main__":
    raise SystemExit(generate(parse_args()))
