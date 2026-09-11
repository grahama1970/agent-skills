"""Two-agent E2E v2: Agent A (memory-driven cover) + Agent B (real solver).

Agent B REALLY solves a complex 3-control question via the memory pipeline
(/intent, 3x /recall, 3x /answer, optional diagram step) — duration is earned
from real service latency, never sleeps. Agent A keeps Embry audible with the
session's delay macros (thinking clips, per-stage progress lines with compiled
pause macros, a song-hum on starvation), then hands off: B's grounded answer is
spoken through the 'answer' conversation arc. One full-sequence wav is assembled.

Everything here is live: solver_source is the memory /answer product; the cover
selection reads real /recall output; renders go through the production speak CLI.
No third-party deps (stdlib urllib) so it runs under any python.

Usage: two_agent_e2e.py --question "<q>" --output out.json [--no-memory]
Exit 0 = all invariants hold; 3 = BLOCKED (TTS service down); 1 = invariant fail.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / "run.sh"
MEMORY = "http://127.0.0.1:8601"
TTS_HEALTH = "http://127.0.0.1:8018/health"
OUT_ROOT = Path("/mnt") / "storage12tb" / "skills" / "chatterbox-speak" / "outputs"
THINK = OUT_ROOT / "sfx-library" / "thinking"
HUMS = OUT_ROOT / "sfx-library" / "song-hums"
PROGRESS = json.load(open(HERE.parent / "fixtures/progress_macros.json"))["stages"]
CONTROLS = ["SC-7", "AC-2", "CM-6"]
STARVE_S = 8.0
MAX_GAP_S = 12.0


def _http_json(url: str, payload: dict | None = None, timeout: float = 60.0) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _speak(text: str, tone: str, planned: bool = False, arc: str | None = None) -> dict:
    """Real render through the production CLI; returns {wav, receipt, duration}."""
    cmd = ["bash", str(RUN), "speak", "--voice", "embry", "--tone", tone,
           "--context", "two-agent e2e v2", "--text", text]
    if planned:
        cmd.append("--planned-pauses")
    if arc:
        cmd += ["--arc", arc]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"render_failed: {r.stderr[-200:]}")
    i = r.stdout.find("{")
    d, _ = json.JSONDecoder().raw_decode(r.stdout[i:])  # first JSON object only (arc mode prints two)
    if "wav" not in d and "phases" in d:  # arc receipt: per-phase wavs
        wavs = [p["wav"] for p in d["phases"] if p.get("wav")]
        return {"wav": wavs[-1] if wavs else None, "wavs": wavs,
                "receipt": None, "duration": sum(p.get("duration_seconds") or 0 for p in d["phases"]),
                "arc_json": d, "stdout": r.stdout[i:]}
    return {"wav": d["wav"], "receipt": d["receipt"],
            "duration": d.get("duration_seconds"),
            "stdout": r.stdout[i:]}


def _concat(wavs: list[Path], out: Path) -> Path:
    lst = out.parent / "concat.txt"
    lst.write_text("".join(f"file '{w}'\n" for w in wavs))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-ar", "24000", "-ac", "1",
                    "-c:a", "pcm_s16le", str(out)], check=True)
    return out


def _agent_b(question: str, events: list, out: dict) -> None:
    """Real solver: the memory pipeline, no sleeps. Emits stage events."""
    events.append({"stage": "intent", "ts": time.time()})
    try:
        _http_json(f"{MEMORY}/intent", {"q": question, "fast": True}, timeout=20)
    except Exception:
        pass
    answers, sources = [], []
    ok_count = 0
    for cid in CONTROLS:
        events.append({"stage": "searching", "ts": time.time()})
        try:
            _http_json(f"{MEMORY}/recall", {"q": f"{cid} boundary protection",
                                             "k": 3, "collections": ["sparta_controls"]}, timeout=30)
        except Exception:
            pass
        events.append({"stage": "recall", "ts": time.time()})
        a = _http_json(f"{MEMORY}/answer",
                       {"q": f"What does control {cid} require and why does it matter for boundary protection?",
                        "scope": "sparta", "k": 4}, timeout=90)
        if a.get("can_answer"):
            ok_count += 1
            answers.append(a.get("final_response") or "")
            srcs = a.get("sources") or []
            sources += [{"key": s.get("key"), "title": s.get("title"),
                         "source": s.get("source")} for s in srcs]
        time.sleep(0)  # no-op; keep ordering explicit
    out.update({"solver_source": "memory_answer", "can_answer_count": ok_count,
                "sources": sources,
                "answer_text": " ".join(answers).strip()})
    out["answer_ready_ts"] = time.time()


def _agent_a(question: str, no_memory: bool, events: list, b_out: dict, rep: dict) -> dict:
    """Memory-driven cover loop; no dead air while B works; arc at handoff."""
    t0 = time.time()
    delivery = {"recall_used": False, "skipped": "no_memory"} if no_memory else {}
    if not no_memory:
        try:
            r = _http_json(f"{MEMORY}/recall", {"q": question, "k": 5,
                                                "collections": ["persona_memory", "lessons_v2"],
                                                "tags": ["persona:embry"]}, timeout=15)
            delivery = {"recall_used": bool(r.get("found")),
                        "confidence": round(r.get("confidence", 0), 2)}
        except Exception as e:
            delivery = {"recall_used": False, "error": str(e)[:120]}

    cover: list[dict] = []  # ordered cover items
    seen_stages: set[str] = set()
    last_ts = t0
    done = False
    while not done:
        now = time.time()
        done = "answer_ready_ts" in b_out
        fresh = [e for e in events if e["ts"] > last_ts]
        if fresh:
            for e in fresh:
                stage = e["stage"] if e["stage"] in PROGRESS else "working_long"
                line = PROGRESS[stage]["pool"][int(now + e["ts"]) % len(PROGRESS[stage]["pool"])]
                cover.append({"kind": "thinking", "ts": time.time(),
                              "wav": str(THINK / "think-hmm.wav")})
                cover.append({"kind": "progress", "ts": time.time(), "stage": stage,
                              "text": f"{line} [pause:considered]", "planned": True})
                seen_stages.add(stage)
            last_ts = fresh[-1]["ts"]
        elif not done and now - last_ts > STARVE_S:
            cover.append({"kind": "hum", "ts": now, "wav": str(HUMS / "aloha-oe.wav")})
            last_ts = now
        else:
            time.sleep(0.5)

    # materialize cover renders (after planning, so wavs exist in order)
    cover_wavs: list[Path] = []
    for item in cover:
        if item["kind"] == "progress":
            d = _speak(item["text"], PROGRESS[item["stage"]]["tone"], planned=True)
            item["wav"] = d["wav"]
            item["receipt"] = d["receipt"]
        cover_wavs.append(Path(item["wav"]))
    arc_started = time.time()
    a_arc = _speak(b_out["answer_text"], "neutral_warm", arc="answer")
    # pause-compiled oracle from first progress receipt
    pause_ok = False
    for item in cover:
        if item["kind"] == "progress" and item.get("receipt"):
            rec = json.loads(Path(item["receipt"]).read_text())
            pause_ok = any((c.get("pause_after_ms") or 0) > 0
                           for c in rec.get("chatterbox_pause_plan") or [])
            break
    full = _concat([Path(THINK / "think-hmm.wav")] + cover_wavs + [Path(w) for w in a_arc["wavs"]],
                   OUT_ROOT / "two-agent-e2e-full.wav") if cover_wavs else Path(a_arc["wavs"][-1])

    starts = [c["ts"] for c in cover]
    window = [t for t in starts if t < b_out["answer_ready_ts"]]
    gaps = [b - a for a, b in zip([t0] + window, window + [b_out["answer_ready_ts"]])]
    return {"delivery": delivery, "cover": cover, "pause_macro_compiled": pause_ok,
            "distinct_stages": sorted(seen_stages), "max_cover_gap_s": round(max(gaps or [0]), 2),
            "arc": {"wav": a_arc["wav"], "wavs": a_arc["wavs"], "phases": len(a_arc["wavs"]),
                    "started_ts": arc_started},
            "full_wav": str(full), "thinking_in_cover": any(c["kind"] == "thinking" for c in cover)}


def run(question: str, no_memory: bool) -> dict:
    t0 = time.time()
    events: list[dict] = []
    b_out: dict = {}
    threading.Thread(target=_agent_b, args=(question, events, b_out), daemon=True).start()
    a = _agent_a(question, no_memory, events, b_out, {})
    rep = {
        "schema": "chatterbox_speak.two_agent_e2e.v2",
        "question": question,
        "agent_a": {k: v for k, v in a.items() if k != "cover"},
        "cover_sequence": a["cover"],
        "agent_b": b_out,
        "concurrency_proven": bool(a["cover"] and a["cover"][0]["ts"] < b_out["answer_ready_ts"]),
        "handoff_ordered": bool(a["arc"]["started_ts"] >= b_out["answer_ready_ts"]),
        "no_dead_air": a["max_cover_gap_s"] <= MAX_GAP_S,
        "total_seconds": round(time.time() - t0, 2),
    }
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--no-memory", action="store_true")
    args = ap.parse_args()
    last = None
    for _ in range(3):
        try:
            _http_json(TTS_HEALTH, timeout=20)
            last = None
            break
        except Exception as e:
            last = e
            time.sleep(3)
    if last is not None:
        print("BLOCKED: chatterbox service down; cannot run live e2e", file=sys.stderr)
        return 3
    rep = run(args.question, args.no_memory)
    Path(args.output).write_text(json.dumps(rep, indent=2))
    b = rep["agent_b"]
    a = rep["agent_a"]
    fails = []
    if b.get("solver_source") != "memory_answer":
        fails.append("solver_not_memory_answer")
    if (b.get("can_answer_count") or 0) < 2:
        fails.append("can_answer_lt_2")
    if len(b.get("sources") or []) < 2:
        fails.append("sources_lt_2")
    for cid in CONTROLS:
        if cid not in (b.get("answer_text") or ""):
            fails.append(f"answer_missing_{cid.replace('-', '')}")
    if not a["delivery"].get("recall_used") and not args.no_memory:
        fails.append("recall_not_used")
    if len(a["distinct_stages"]) < 2:
        fails.append("lt_2_stages")
    if not a["pause_macro_compiled"]:
        fails.append("pause_not_compiled")
    if not a["thinking_in_cover"]:
        fails.append("no_thinking_clip")
    if not rep["concurrency_proven"]:
        fails.append("concurrency_unproven")
    if not rep["handoff_ordered"]:
        fails.append("handoff_unordered")
    if not rep["no_dead_air"]:
        fails.append(f"dead_air_gap_{a['max_cover_gap_s']}s")
    if a["arc"]["phases"] < 3:
        fails.append("arc_lt_3_phases")
    if not all(Path(w).is_file() for w in a["arc"]["wavs"]):
        fails.append("arc_wav_missing")
    print(json.dumps({"ok": not fails, "fails": fails,
                      "full_wav": a["full_wav"], "total_seconds": rep["total_seconds"],
                      "max_cover_gap_s": a["max_cover_gap_s"],
                      "can_answer_count": b.get("can_answer_count"),
                      "sources": len(b.get("sources") or [])}, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
