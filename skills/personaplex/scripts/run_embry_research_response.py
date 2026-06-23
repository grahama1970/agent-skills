#!/usr/bin/env python3
"""Run the Embry PersonaPlex offline response from the latest prompt-cache.

This is an evidence script, not a benchmark. It proves whether the current
PersonaPlex runtime can consume the Embry `.pt` voice prompt plus a research
injection packet and produce a real WAV/text response artifact. It fails closed
when the `.pt`, research packet, PersonaPlex checkout, or output files are
missing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_PERSONAPLEX_ROOT = Path("/home/graham/workspace/experiments/personaplex")
DEFAULT_PYTHON = DEFAULT_PERSONAPLEX_ROOT / ".venv/bin/python"
DEFAULT_VOICE_DIR = Path(
    "/mnt/storage12tb/skills/personaplex/outputs/e2e/"
    "embry-conversational-20260622T152647Z/neutral"
)
DEFAULT_PT = DEFAULT_VOICE_DIR / "voice-prompt.pt"
DEFAULT_QUESTION_TEXT = (
    "Embry, what is the weather like in Hawaii today, "
    "and how would that make you feel about surfing with Kai?"
)
DEFAULT_RESEARCH_PACKET = Path(
    "/mnt/storage12tb/skills/personaplex/outputs/research-gate-sanity/"
    "embry/20260622T182229Z/personaplex-research-injection.json"
)
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/research-response/embry")


def ensure_personaplex_python() -> None:
    """Re-exec this script under the PersonaPlex venv for torch/moshi deps."""
    configured = DEFAULT_PYTHON
    current = Path(sys.executable).resolve()
    if configured.exists() and current != configured.resolve():
        os.execv(str(configured), [str(configured), __file__, *sys.argv[1:]])


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def short_text(value: Any, limit: int = 1400) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def wav_metrics(path: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(str(path))
    data, sample_rate = sf.read(str(path), always_2d=True)
    peak = float(abs(data).max()) if data.size else 0.0
    rms = float((data * data).mean() ** 0.5) if data.size else 0.0
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
        "sample_rate": int(sample_rate),
        "channels": int(data.shape[1]),
        "frames": int(data.shape[0]),
        "duration_s": round(float(info.duration), 3),
        "subtype": info.subtype,
        "peak": peak,
        "rms": rms,
    }


def text_metrics(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
        "preview": short_text(text, 600),
    }


def validate_pt_schema(pt_path: Path) -> dict[str, Any]:
    import torch

    payload = torch.load(pt_path, map_location="cpu")
    if not isinstance(payload, dict):
        raise TypeError(f"expected dict in {pt_path}, got {type(payload)!r}")
    required = {"cache", "embeddings"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"voice prompt missing keys: {missing}")
    schema: dict[str, Any] = {
        "path": str(pt_path),
        "sha256": sha256_path(pt_path),
        "size_bytes": pt_path.stat().st_size,
        "keys": sorted(str(key) for key in payload),
    }
    for key in sorted(required):
        tensor = payload[key]
        schema[key] = {
            "type": type(tensor).__name__,
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype),
            "numel": int(tensor.numel()),
            "finite": bool(torch.isfinite(tensor.float()).all().item()),
        }
    return schema


def synthesize_question_wav(text: str, output_dir: Path) -> Path:
    raw_path = output_dir / "user-question-espeak-raw.wav"
    wav_path = output_dir / "user-question-24khz-mono.wav"
    espeak = subprocess.run(["bash", "-lc", "command -v espeak-ng || command -v espeak"], capture_output=True, text=True)
    espeak_path = espeak.stdout.strip().splitlines()[0] if espeak.stdout.strip() else ""
    if not espeak_path:
        raise RuntimeError("no espeak/espeak-ng command available to synthesize question input")
    subprocess.run([espeak_path, "-w", str(raw_path), text], check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_path),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        check=True,
    )
    return wav_path


def build_prompt(packet: dict[str, Any]) -> str:
    conditioning = packet.get("persona_conditioning_text") or ""
    planner = packet.get("scillm_planner", {}).get("json", {})
    answer_draft = planner.get("answer_draft") or ""
    limitations = planner.get("limitations") or []
    must_not_say = planner.get("must_not_say") or []
    update = planner.get("persona_context_update") or ""
    if not conditioning:
        raise ValueError("research packet missing persona_conditioning_text")

    return "\n\n".join(
        [
            "You are Embry Lawson speaking in a grounded, intimate, lightly raspy conversational register.",
            "Answer the user's latest turn naturally, with a concise researched response. Do not invent current weather details.",
            "Use this verified context packet:",
            short_text(conditioning, 2600),
            "Planner answer draft to preserve as meaning, not exact wording:",
            short_text(answer_draft, 900),
            "Persona context update:",
            short_text(update, 600),
            "Limitations:",
            short_text(limitations, 500),
            "Do not say:",
            short_text(must_not_say, 500),
        ]
    )


def append_event(log_path: Path, event: dict[str, Any]) -> None:
    event = {"ts": dt.datetime.now(dt.UTC).isoformat(), **event}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def venv_library_path(python_path: Path) -> str:
    code = (
        "import site, pathlib; "
        "roots=[]; "
        "[roots.append(pathlib.Path(p)) for p in site.getsitepackages()]; "
        "libs=[]; "
        "\nfor root in roots:\n"
        "    nvidia = root / 'nvidia'\n"
        "    if nvidia.exists():\n"
        "        libs.extend(str(p) for p in nvidia.glob('*/lib') if p.exists())\n"
        "print(':'.join(libs))"
    )
    run = subprocess.run([str(python_path), "-c", code], capture_output=True, text=True, check=False)
    return run.stdout.strip()


def run_streaming_command(
    command: list[str],
    cwd: Path,
    jsonl_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    python_path: Path,
) -> int:
    append_event(jsonl_path, {"event": "command_started", "command": command, "cwd": str(cwd)})
    start = time.monotonic()
    extra_library_path = venv_library_path(python_path)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if extra_library_path:
        env["LD_LIBRARY_PATH"] = (
            f"{extra_library_path}:{env.get('LD_LIBRARY_PATH', '')}"
            if env.get("LD_LIBRARY_PATH")
            else extra_library_path
        )
        append_event(jsonl_path, {"event": "ld_library_path_prepared", "extra_library_path": extra_library_path})
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    assert process.stdout is not None
    assert process.stderr is not None
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    import selectors

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    while selector.get_map():
        for key, _ in selector.select(timeout=1.0):
            line = key.fileobj.readline()
            stream = key.data
            if line:
                if stream == "stdout":
                    stdout_lines.append(line)
                else:
                    stderr_lines.append(line)
                append_event(
                    jsonl_path,
                    {
                        "event": "stream_line",
                        "stream": stream,
                        "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
                        "line": line.rstrip("\n"),
                    },
                )
            else:
                selector.unregister(key.fileobj)
        if process.poll() is not None and not selector.get_map():
            break

    returncode = process.wait()
    stdout_path.write_text("".join(stdout_lines), encoding="utf-8")
    stderr_path.write_text("".join(stderr_lines), encoding="utf-8")
    append_event(
        jsonl_path,
        {
            "event": "command_exited",
            "returncode": returncode,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "stdout_lines": len(stdout_lines),
            "stderr_lines": len(stderr_lines),
        },
    )
    return returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--personaplex-root", type=Path, default=DEFAULT_PERSONAPLEX_ROOT)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--voice-prompt-dir", type=Path, default=DEFAULT_VOICE_DIR)
    parser.add_argument("--voice-prompt", type=Path, default=DEFAULT_PT)
    parser.add_argument("--input-wav", type=Path, default=None)
    parser.add_argument("--question-text", default=DEFAULT_QUESTION_TEXT)
    parser.add_argument("--research-packet", type=Path, default=DEFAULT_RESEARCH_PACKET)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--play", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [str(path) for path in [args.personaplex_root, args.python, args.voice_prompt, args.research_packet] if not path.exists()]
    if args.input_wav is not None and not args.input_wav.exists():
        missing.append(str(args.input_wav))
    if missing:
        raise FileNotFoundError(f"missing required inputs: {missing}")

    output_dir = args.output_root / utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=False)
    jsonl_path = output_dir / "personaplex-offline-events.jsonl"
    stdout_path = output_dir / "moshi-offline.stdout.log"
    stderr_path = output_dir / "moshi-offline.stderr.log"
    wav_path = output_dir / "embry-personaplex-research-response.wav"
    text_path = output_dir / "embry-personaplex-research-response.json"
    prompt_path = output_dir / "personaplex-text-prompt.txt"
    receipt_path = output_dir / "personaplex-research-response-receipt.json"

    pt_schema = validate_pt_schema(args.voice_prompt)
    packet = load_json(args.research_packet)
    prompt = build_prompt(packet)
    prompt_path.write_text(prompt, encoding="utf-8")
    input_wav = args.input_wav or synthesize_question_wav(args.question_text, output_dir)
    input_wav_info = wav_metrics(input_wav)

    command = [
        str(args.python),
        "-m",
        "moshi.offline",
        "--input-wav",
        str(input_wav),
        "--output-wav",
        str(wav_path),
        "--output-text",
        str(text_path),
        "--text-prompt",
        prompt,
        "--voice-prompt",
        args.voice_prompt.name,
        "--voice-prompt-dir",
        str(args.voice_prompt_dir),
        "--device",
        args.device,
        "--seed",
        "42424242",
    ]
    if args.cpu_offload:
        command.append("--cpu-offload")

    returncode = run_streaming_command(command, args.personaplex_root, jsonl_path, stdout_path, stderr_path, args.python)

    receipt: dict[str, Any] = {
        "schema": "personaplex.research_response_audio.v1",
        "status": "PASS" if returncode == 0 and wav_path.exists() and text_path.exists() else "FAIL",
        "claim_boundary": "offline moshi.offline response artifact; not live full-duplex WebSocket proof",
        "voice_prompt": pt_schema,
        "research_packet": {
            "path": str(args.research_packet),
            "sha256": sha256_path(args.research_packet),
            "size_bytes": args.research_packet.stat().st_size,
            "schema": packet.get("schema"),
            "persona": packet.get("persona"),
        },
        "input_wav": input_wav_info,
        "question_text": args.question_text,
        "prompt_path": str(prompt_path),
        "run": {
            "command": command,
            "cwd": str(args.personaplex_root),
            "returncode": returncode,
            "events_jsonl": str(jsonl_path),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
    }
    if wav_path.exists():
        receipt["output_wav"] = wav_metrics(wav_path)
    if text_path.exists():
        receipt["output_text"] = text_metrics(text_path)

    playback: dict[str, Any] | None = None
    if args.play and wav_path.exists():
        player = subprocess.run(["bash", "-lc", "command -v pw-play || command -v paplay || command -v aplay || command -v ffplay"], capture_output=True, text=True)
        player_path = player.stdout.strip().splitlines()[0] if player.stdout.strip() else ""
        if player_path:
            play_cmd = [player_path, str(wav_path)]
            if Path(player_path).name == "ffplay":
                play_cmd = [player_path, "-nodisp", "-autoexit", str(wav_path)]
            play_run = subprocess.run(play_cmd, capture_output=True, text=True, timeout=30)
            playback = {
                "command": play_cmd,
                "returncode": play_run.returncode,
                "stdout": short_text(play_run.stdout, 800),
                "stderr": short_text(play_run.stderr, 800),
            }
        else:
            playback = {"error": "no playback command found"}
        receipt["playback"] = playback

    write_json(receipt_path, receipt)
    print(json.dumps({"receipt": str(receipt_path), "status": receipt["status"], "wav": str(wav_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        ensure_personaplex_python()
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        raise
