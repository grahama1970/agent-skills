#!/usr/bin/env python3
"""Minimum PersonaPlex research loop proof.

Purpose:
    Prove the smallest useful loop:

    1. Classify/recall Embry persona memory through the memory daemon.
    2. Fetch current external facts through the Brave Search skill.
    3. Compact those facts into a tiny PersonaPlex prompt.
    4. Run one PersonaPlex offline probe using the latest Embry `.pt`.
    5. Write a receipt that separates retrieval proof from PersonaPlex audio proof.

This is intentionally not the production full-duplex server. It is a small,
real, non-mocked artifact to build from without hiding slow or bad behavior.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path("/home/graham/workspace/experiments/agent-skills")
PERSONAPLEX_ROOT = Path("/home/graham/workspace/experiments/personaplex")
PERSONAPLEX_PYTHON = PERSONAPLEX_ROOT / ".venv/bin/python"
BRAVE_RUN = ROOT / "skills/brave-search/run.sh"
MEMORY_URL = "http://127.0.0.1:8601"
VOICE_DIR = Path(
    "/mnt/storage12tb/skills/personaplex/outputs/e2e/"
    "embry-conversational-20260622T152647Z/neutral"
)
VOICE_PT = VOICE_DIR / "voice-prompt.pt"
OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/mwe-research-loop/embry")
DEFAULT_QUESTION = (
    "Embry, what is the weather like in Hawaii today, "
    "and how would that make you feel about surfing with Kai?"
)
DEFAULT_BRAVE_QUERY = "Hawaii surf forecast today south swell weather"


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def short(value: Any, limit: int = 1000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(), **event}, sort_keys=True) + "\n")


def timed_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    try:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{MEMORY_URL}{endpoint}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
            status_code = response.status
            content_type = response.headers.get("content-type", "")
        parsed = json.loads(text) if "application/json" in content_type else None
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "request": payload,
            "json": parsed,
            "text_excerpt": None if parsed is not None else text[:1000],
        }
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "request": payload,
            "text_excerpt": text[:1000],
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "request": payload,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def run_memory(question: str) -> dict[str, Any]:
    intent = timed_post("/intent", {"q": question, "scope": "personaplex", "fast": True})
    recall = timed_post(
        "/recall",
        {
            "q": "What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain?",
            "k": 4,
            "collections": ["persona_memory"],
            "tags": ["persona:embry"],
        },
    )
    return {"intent": intent, "recall": recall}


def run_brave(query: str, count: int) -> dict[str, Any]:
    start = time.monotonic()
    command = [
        "bash",
        "-lc",
        f"source ~/.zshrc >/dev/null 2>&1; {BRAVE_RUN} web {json.dumps(query)} --count {count} --json",
    ]
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=45)
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
        "command": ["bash", "-lc", "source ~/.zshrc; skills/brave-search/run.sh web <query> --count <n> --json"],
        "returncode": completed.returncode,
        "stderr_excerpt": completed.stderr[-1200:],
    }
    try:
        result["json"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result["ok"] = False
        result["stdout_excerpt"] = completed.stdout[:1200]
        result["error"] = "Brave output was not JSON"
    return result


def compact_memory_line(memory: dict[str, Any]) -> str:
    recall_json = memory.get("recall", {}).get("json") or {}
    items = recall_json.get("items") or []
    for item in items:
        text = item.get("retrieval_text") or item.get("text") or item.get("problem") or item.get("summary")
        if text:
            return short(text, 220)
    return "No strong Embry memory was returned."


def compact_brave_line(brave: dict[str, Any]) -> str:
    results = (brave.get("json") or {}).get("results") or []
    if not results:
        return "No Brave result was returned."
    top = results[0]
    return short(f"{top.get('title', '')}: {top.get('description', '')}", 260)


def synthesize_question_wav(text: str, output_dir: Path) -> Path:
    raw = output_dir / "user-question-raw.wav"
    wav = output_dir / "user-question-24khz-mono.wav"
    espeak = subprocess.run(["bash", "-lc", "command -v espeak-ng || command -v espeak"], capture_output=True, text=True)
    espeak_path = espeak.stdout.strip().splitlines()[0] if espeak.stdout.strip() else ""
    if not espeak_path:
        raise RuntimeError("missing espeak/espeak-ng")
    subprocess.run([espeak_path, "-w", str(raw), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    return wav


def wav_metrics(path: Path) -> dict[str, Any]:
    import soundfile as sf

    data, sample_rate = sf.read(str(path), always_2d=True)
    info = sf.info(str(path))
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
        "sample_rate": sample_rate,
        "channels": int(data.shape[1]),
        "frames": int(data.shape[0]),
        "duration_s": round(float(info.duration), 3),
        "peak": float(abs(data).max()) if data.size else 0.0,
        "rms": float((data * data).mean() ** 0.5) if data.size else 0.0,
    }


def venv_library_path() -> str:
    code = (
        "import site, pathlib\n"
        "libs=[]\n"
        "for root_text in site.getsitepackages():\n"
        "    root=pathlib.Path(root_text)/'nvidia'\n"
        "    if root.exists():\n"
        "        libs.extend(str(p) for p in root.glob('*/lib') if p.exists())\n"
        "print(':'.join(libs))\n"
    )
    run = subprocess.run([str(PERSONAPLEX_PYTHON), "-c", code], capture_output=True, text=True)
    return run.stdout.strip()


def run_personaplex(prompt: str, input_wav: Path, output_dir: Path) -> dict[str, Any]:
    wav = output_dir / "personaplex-mwe-response.wav"
    text = output_dir / "personaplex-mwe-response.json"
    stdout = output_dir / "moshi-offline.stdout.log"
    stderr = output_dir / "moshi-offline.stderr.log"
    events = output_dir / "moshi-offline.events.jsonl"
    command = [
        str(PERSONAPLEX_PYTHON),
        "-m",
        "moshi.offline",
        "--input-wav",
        str(input_wav),
        "--output-wav",
        str(wav),
        "--output-text",
        str(text),
        "--text-prompt",
        prompt,
        "--voice-prompt",
        VOICE_PT.name,
        "--voice-prompt-dir",
        str(VOICE_DIR),
        "--device",
        "cuda",
        "--seed",
        "42424242",
    ]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    libs = venv_library_path()
    if libs:
        env["LD_LIBRARY_PATH"] = f"{libs}:{env.get('LD_LIBRARY_PATH', '')}" if env.get("LD_LIBRARY_PATH") else libs
    append_event(events, {"event": "command_started", "command": command, "prompt_chars": len(prompt)})
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=str(PERSONAPLEX_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    sel = selectors.DefaultSelector()
    sel.register(process.stdout, selectors.EVENT_READ, "stdout")
    sel.register(process.stderr, selectors.EVENT_READ, "stderr")
    out_lines: list[str] = []
    err_lines: list[str] = []
    while sel.get_map():
        for key, _ in sel.select(timeout=1.0):
            line = key.fileobj.readline()
            if not line:
                sel.unregister(key.fileobj)
                continue
            stream = key.data
            (out_lines if stream == "stdout" else err_lines).append(line)
            append_event(events, {"event": "stream_line", "stream": stream, "elapsed_ms": round((time.monotonic() - start) * 1000, 2), "line": line.rstrip("\n")})
    returncode = process.wait()
    stdout.write_text("".join(out_lines), encoding="utf-8")
    stderr.write_text("".join(err_lines), encoding="utf-8")
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    append_event(events, {"event": "command_exited", "returncode": returncode, "elapsed_ms": elapsed_ms, "stdout_lines": len(out_lines), "stderr_lines": len(err_lines)})
    return {
        "ok": returncode == 0 and wav.exists() and text.exists(),
        "returncode": returncode,
        "elapsed_ms": elapsed_ms,
        "command": command,
        "events_jsonl": str(events),
        "stdout_log": str(stdout),
        "stderr_log": str(stderr),
        "output_wav": wav_metrics(wav) if wav.exists() else None,
        "output_text": {
            "path": str(text),
            "sha256": sha256_path(text),
            "size_bytes": text.stat().st_size,
            "preview": short(text.read_text(encoding="utf-8", errors="replace"), 600),
        }
        if text.exists()
        else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--brave-query", default=DEFAULT_BRAVE_QUERY)
    parser.add_argument("--brave-count", type=int, default=3)
    parser.add_argument("--skip-personaplex", action="store_true")
    return parser.parse_args()


def main() -> int:
    if Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])

    args = parse_args()
    output_dir = OUTPUT_ROOT / utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=False)

    missing = [str(p) for p in [PERSONAPLEX_PYTHON, PERSONAPLEX_ROOT, BRAVE_RUN, VOICE_PT] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing required inputs: {missing}")

    memory = run_memory(args.question)
    brave = run_brave(args.brave_query, args.brave_count)
    compact = {
        "question": args.question,
        "memory": compact_memory_line(memory),
        "brave": compact_brave_line(brave),
    }
    prompt = (
        "You are Embry Lawson. Answer in one short, grounded sentence.\n"
        f"Question: {compact['question']}\n"
        f"Embry memory: {compact['memory']}\n"
        f"Current search: {compact['brave']}\n"
        "Do not invent facts. If unsure, say the evidence is limited."
    )
    prompt_path = output_dir / "compact-personaplex-prompt.txt"
    write_json(output_dir / "retrieval.json", {"memory": memory, "brave": brave, "compact": compact})
    prompt_path.write_text(prompt, encoding="utf-8")

    personaplex: dict[str, Any] | None = None
    input_wav: dict[str, Any] | None = None
    if not args.skip_personaplex:
        question_wav = synthesize_question_wav(args.question, output_dir)
        input_wav = wav_metrics(question_wav)
        personaplex = run_personaplex(prompt, question_wav, output_dir)

    receipt = {
        "schema": "personaplex.mwe_research_loop.v1",
        "status": "PASS"
        if memory["recall"].get("ok")
        and ((memory["recall"].get("json") or {}).get("items"))
        and brave.get("ok")
        and ((brave.get("json") or {}).get("results"))
        and (args.skip_personaplex or (personaplex or {}).get("ok"))
        else "FAIL",
        "claim_boundary": "minimum file-to-file proof; not live full-duplex; PersonaPlex semantic quality must be human-reviewed",
        "voice_prompt": {
            "path": str(VOICE_PT),
            "sha256": sha256_path(VOICE_PT),
            "size_bytes": VOICE_PT.stat().st_size,
        },
        "question": args.question,
        "prompt_path": str(prompt_path),
        "retrieval_path": str(output_dir / "retrieval.json"),
        "memory_recall_ok": memory["recall"].get("ok") and bool((memory["recall"].get("json") or {}).get("items")),
        "brave_search_ok": brave.get("ok") and bool((brave.get("json") or {}).get("results")),
        "input_wav": input_wav,
        "personaplex_probe": personaplex,
    }
    receipt_path = output_dir / "personaplex-mwe-research-loop-receipt.json"
    write_json(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
