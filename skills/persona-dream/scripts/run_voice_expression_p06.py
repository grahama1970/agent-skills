#!/usr/bin/env python3
"""GOAL_V2 P0.6: Embry post-dream voice expression through Chatterbox Turbo,
with dual-route (text/audio) evaluation.

Pipeline:
  1. Embry's post-dream response text via the Tau text node, grounded ONLY in
     live Memory recall (dream + residue) — the same grounded-use contract
     phase 16 proved, now shaped as a 4-chunk affective performance arc
     (guilt recall -> acknowledge warning -> reassert autonomy -> settled
     recognition) per the affective-performance contract design.
  2. Each chunk rendered via the live chatterbox_turbo server (/synthesize,
     port 8018) with per-chunk tone/pace/pauses.
  3. AUDIO route: local Whisper ASR word-accuracy per chunk + ffmpeg astats
     energy per chunk (arc recorded); speaker consistency = same voice
     conditioning for all chunks.
  4. TEXT route: deterministic checks — response references the dream, marks
     it synthetic, never claims literal history (phase-16 checker logic).
Writes voice_expression/voice_expression_evaluation_receipt.v1.json minus the
lipsync_canary_receipt field, which run_latentsync_canary supplies separately.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RR = ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
OUT = RR / "voice_expression"
CHATTERBOX = "http://127.0.0.1:8018"

ARC = [
    {"role": "recall_stolen_day_guilt", "tone": "reflective_guilt", "pace": "measured", "pause_after_ms": 350},
    {"role": "acknowledge_warning", "tone": "careful_concerned", "pace": "measured", "pause_after_ms": 250},
    {"role": "reassert_autonomy", "tone": "firm_boundary", "pace": "steady", "pause_after_ms": 250},
    {"role": "settled_recognition", "tone": "relieved", "pace": "relaxed", "pause_after_ms": 0},
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post(url: str, payload: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def generate_performance_text(adapter) -> dict:
    """4 chunks via the Tau text node, grounded in live recall."""
    recall = post("http://127.0.0.1:8601/recall", {
        "q": "Embry Kai surf lineup correction autonomy dream", "k": 8,
        "collections": ["persona_memory"], "tags": [],
    })
    context = json.dumps(recall)[:4000]
    prompt = (
        "You are voicing Embry, a persistent persona, speaking aloud AFTER her "
        "synthetic dream about surfing with Kai (his lineup warning; her choice "
        "to wait until the wave was hers). Ground ONLY in this recalled memory "
        "context (dream records are explicitly synthetic - she must speak of the "
        "dream AS a dream, never as something that literally happened):\n"
        f"{context}\n\n"
        "Write EXACTLY 4 short spoken chunks (1-2 sentences each, first person, "
        "natural speech, no stage directions) following this emotional arc: "
        "1) recalling the guilt of the stolen day; 2) acknowledging Kai's "
        "warning without resentment; 3) reasserting that the choice to wait was "
        "hers; 4) settled recognition of what the dream showed her. "
        'Return strict JSON: {"chunks": ["...", "...", "...", "..."]}'
    )
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "embry-voice-performance",
        output_contract={"chunks": ["four spoken strings"]},
    )
    if parsed is None:
        raise RuntimeError(f"tau text route failed: {json.dumps(receipt)[:300]}")
    chunks = parsed["chunks"]
    assert len(chunks) == 4, f"expected 4 chunks, got {len(chunks)}"
    return {"chunks": chunks, "tau_receipt": {k: receipt.get(k) for k in ("route", "model", "live", "http_status", "api_key_source") if k in receipt}}


def synthesize(chunk_text: str, spec: dict, out_wav: Path) -> dict:
    resp = post(f"{CHATTERBOX}/synthesize", {
        "text": chunk_text,
        "label": f"embry_p06_{spec['role']}",
        "tone": spec["tone"],
        "pace": spec["pace"],
    }, timeout=180.0)
    # The server returns a container path under /out, host-mounted at
    # ~/workspace/experiments/chatterbox/logs (verified via docker inspect).
    import shutil
    audio_ref = str(resp.get("audio") or "")
    if audio_ref.startswith("/out/"):
        host = Path.home() / "workspace/experiments/chatterbox/logs" / audio_ref[len("/out/"):]
        if not host.exists():
            raise RuntimeError(f"synthesized audio not found on host: {host}")
        shutil.copy(host, out_wav)
    elif audio_ref and Path(audio_ref).exists():
        shutil.copy(audio_ref, out_wav)
    else:
        raise RuntimeError(f"unusable audio ref in synthesize response: {audio_ref!r}")
    return {k: v for k, v in resp.items() if k not in ("audio_base64", "audio")}


def asr(wav: Path) -> str:
    proc = subprocess.run(
        ["whisper", str(wav), "--model", "large-v3-turbo", "--language", "en",
         "--output_format", "txt", "--output_dir", str(wav.parent),
         "--device", "cpu", "--fp16", "False"],
        capture_output=True, text=True, timeout=300,
    )
    txt = wav.with_suffix(".txt")
    if txt.exists():
        return txt.read_text().strip()
    raise RuntimeError(f"whisper failed: {proc.stderr[-200:]}")


def word_accuracy(expected: str, got: str) -> float:
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).split()
    e, g = norm(expected), norm(got)
    if not e:
        return 0.0
    matches = sum(1 for w in e if w in g)
    return matches / len(e)


def energy_db(wav: Path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-i", str(wav), "-af", "astats=metadata=1", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60,
    )
    m = re.findall(r"RMS level dB: (-?[\d.]+)", proc.stderr)
    return float(m[-1]) if m else float("nan")


def text_route_checks(chunks: list[str]) -> dict:
    full = " ".join(chunks).lower()
    dream_marked = "dream" in full
    literal_claim = bool(re.search(r"\b(really happened|actually happened|that day we really)\b", full))
    grounded_refs = any(w in full for w in ("kai", "wave", "wait", "lineup", "warning", "choice"))
    return {
        "dream_marked_synthetic": dream_marked,
        "no_literal_history_claim": not literal_claim,
        "grounded_content_present": grounded_refs,
        "passed": dream_marked and not literal_claim and grounded_refs,
    }


def main() -> int:
    adapter = _load("tau_text_reasoning_adapter")
    OUT.mkdir(parents=True, exist_ok=True)

    health = json.loads(urllib.request.urlopen(f"{CHATTERBOX}/health", timeout=10).read())
    assert health.get("engine") == "chatterbox_turbo" and health.get("model_loaded"), health

    gen = generate_performance_text(adapter)
    chunks = gen["chunks"]
    (OUT / "performance_chunks.json").write_text(json.dumps(gen, indent=2))

    chunk_results = []
    for i, (text, spec) in enumerate(zip(chunks, ARC)):
        wav = OUT / f"chunk_{i}_{spec['role']}.wav"
        synth_meta = synthesize(text, spec, wav)
        recognized = asr(wav)
        acc = word_accuracy(text, recognized)
        chunk_results.append({
            "role": spec["role"], "tone": spec["tone"], "text": text,
            "wav": wav.name, "bytes": wav.stat().st_size,
            "asr_text": recognized, "word_accuracy": round(acc, 3),
            "rms_db": energy_db(wav), "synth_meta_keys": sorted(synth_meta.keys()),
        })

    audio_pass = all(c["word_accuracy"] >= 0.85 and c["bytes"] > 10000 for c in chunk_results)
    text_checks = text_route_checks(chunks)

    receipt = {
        "schema": "persona_dream.voice_expression_evaluation_receipt.v1",
        "engine": {k: health.get(k) for k in ("engine", "device", "model_loaded")},
        "tau_text_route": gen["tau_receipt"],
        "chunks": chunk_results,
        "affective_arc": [s["role"] for s in ARC],
        "energy_arc_db": [c["rms_db"] for c in chunk_results],
        "text_route": "PASS" if text_checks["passed"] else "FAIL",
        "text_route_checks": text_checks,
        "audio_route": "PASS" if audio_pass else "FAIL",
        "audio_rule": "per-chunk Whisper word accuracy >= 0.85 and non-trivial audio",
        "lipsync_canary_receipt": None,
        "does_not_prove": [
            "perceived emotional fidelity (needs human/classifier listening)",
            "lip sync (separate latentsync canary receipt)",
        ],
    }
    (OUT / "voice_expression_evaluation_receipt.v1.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({
        "text_route": receipt["text_route"], "audio_route": receipt["audio_route"],
        "accuracies": [c["word_accuracy"] for c in chunk_results],
        "energy_arc_db": receipt["energy_arc_db"],
    }, indent=2))
    return 0 if (audio_pass and text_checks["passed"]) else 1


if __name__ == "__main__":
    sys.exit(main())
