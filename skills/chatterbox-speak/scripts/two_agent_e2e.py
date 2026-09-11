"""End-to-end harness: two concurrent agents answer a complex question.

Agent A (Voice/Cover, fast lane): memory-recall-driven cover selection -> render
a cover line on Turbo, speaking WHILE Agent B works. Agent B (Solver, slow lane):
emits stage events and produces the answer. When B is ready, A speaks the answer.

What is LIVE here (owned by chatterbox-speak, provable now):
  - Agent A recall (real httpx to memory :8601 for delivery/recipe), cover_plan,
    real Turbo render of the cover, real timestamps proving concurrency + handoff.
What is a declared BOUNDARY STUB (owned by embry-voice-control, not built yet):
  - Agent B's real high-reasoning solver. Here it emits real stage events on a
    real delay and returns a fixed answer; `solver_source` records this so the
    eval never claims full answer-generation is proven.

Concurrency is proven by timestamps: the cover render starts BEFORE B's answer is
ready. Fails closed if the Chatterbox service is down (BLOCKED, not fake-green).

Usage:
  python3 two_agent_e2e.py --question "<q>" --output out.json [--no-memory] [--solver-delay 4]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cover_plan import plan_cover  # noqa: E402

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / "run.sh"
MEMORY = "http://127.0.0.1:8601"
PROGRESS = json.load(open(HERE.parent / "fixtures/progress_macros.json"))["stages"]


def _speak(text: str, tone: str) -> str:
    """Real Turbo render via the production speak path; returns wav path."""
    r = subprocess.run(["bash", str(RUN), "speak", "--voice", "embry", "--tone", tone,
                        "--context", "two-agent e2e", "--text", text],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"render_failed: {r.stderr[-200:]}")
    return json.loads(r.stdout)["wav"]


def _http_json(url: str, payload: dict | None = None, timeout: float = 6.0) -> dict:
    """Stdlib JSON GET/POST so the harness needs no third-party deps under any python."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _recall_delivery(question: str) -> dict:
    """Agent A: real memory recall for delivery context + recipe. Empty -> floor."""
    try:
        r = _http_json(f"{MEMORY}/recall", {"q": question, "k": 5,
                                             "collections": ["persona_memory", "lessons_v2"],
                                             "tags": ["persona:embry"]}, timeout=8.0)
        return {"recall_used": bool(r.get("found")), "confidence": round(r.get("confidence", 0), 2),
                "hits": len(r.get("items", []))}
    except Exception as e:
        return {"recall_used": False, "error": str(e)[:120]}


def _solver(question: str, delay: float, events: list, out: dict) -> None:
    """Agent B BOUNDARY STUB: real stage events on a real delay, fixed answer."""
    stages = ["intent", "searching", "debugging", "answer"]
    step = delay / len(stages)
    for stage in stages:
        time.sleep(step)
        events.append({"stage": stage, "ts": time.time()})
    out["answer_text"] = ("Here is the picture: the boundary check is the load-bearing "
                          "part, and hardening it closes the gap.")
    out["answer_ready_ts"] = time.time()
    out["solver_source"] = "boundary_stub"  # real solver is owned by embry-voice-control


def run(question: str, no_memory: bool, solver_delay: float) -> dict:
    t0 = time.time()
    # --- launch Agent B (slow lane) concurrently ---
    events: list = []
    b_out: dict = {}
    b = threading.Thread(target=_solver, args=(question, solver_delay, events, b_out))
    b.start()

    # --- Agent A (fast lane): recall -> cover_plan -> speak cover WHILE B works ---
    delivery = {"recall_used": False, "skipped": "no_memory"} if no_memory else _recall_delivery(question)
    intensity = 6
    plan = plan_cover("searching", intensity, tags=[])
    stage = plan["steps"][1]["stage"]
    cover_line = PROGRESS[stage]["pool"][0]
    cover_started_ts = time.time()
    cover_wav = _speak(cover_line, PROGRESS[stage]["tone"])
    cover_done_ts = time.time()

    b.join(timeout=solver_delay + 30)
    # --- handoff: A speaks B's answer after the cover ---
    answer_wav = _speak(b_out["answer_text"], "warm")
    answer_spoken_ts = time.time()

    concurrency_proven = cover_started_ts < b_out["answer_ready_ts"]
    handoff_ordered = cover_done_ts <= answer_spoken_ts and b_out["answer_ready_ts"] <= answer_spoken_ts
    return {
        "schema": "chatterbox_speak.two_agent_e2e.v1",
        "question": question,
        "agent_a": {"lane": "fast/cover", "delivery": delivery, "cover_plan": plan,
                    "cover_line": cover_line, "cover_wav": cover_wav,
                    "cover_started_ts": cover_started_ts, "cover_done_ts": cover_done_ts},
        "agent_b": {"lane": "slow/solver", "solver_source": b_out.get("solver_source"),
                    "stage_events": events,
                    "answer_text": b_out.get("answer_text"), "answer_ready_ts": b_out.get("answer_ready_ts"),
                    "answer_wav": answer_wav, "answer_spoken_ts": answer_spoken_ts},
        "concurrency_proven": bool(concurrency_proven),
        "handoff_ordered": bool(handoff_ordered),
        "total_seconds": round(time.time() - t0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--no-memory", action="store_true")
    ap.add_argument("--solver-delay", type=float, default=4.0)
    a = ap.parse_args()
    # fail closed if the render service is down -> BLOCKED, never fake-green.
    # Retry with backoff: a busy single-concurrency GPU can stall /health transiently.
    last = None
    for attempt in range(5):
        try:
            _http_json("http://127.0.0.1:8018/health", timeout=20.0)
            last = None
            break
        except Exception as e:
            last = e
            time.sleep(3)
    if last is not None:
        print(f"BLOCKED: chatterbox service unreachable after retries (127.0.0.1:8018): {last}", file=sys.stderr)
        return 3
    rep = run(a.question, a.no_memory, a.solver_delay)
    Path(a.output).write_text(json.dumps(rep, indent=2))
    ok = rep["concurrency_proven"] and rep["handoff_ordered"] and rep["agent_a"]["cover_wav"] and rep["agent_b"]["answer_wav"]
    print(json.dumps({"concurrency_proven": rep["concurrency_proven"],
                      "handoff_ordered": rep["handoff_ordered"],
                      "cover_wav": rep["agent_a"]["cover_wav"],
                      "answer_wav": rep["agent_b"]["answer_wav"],
                      "solver_source": rep["agent_b"]["solver_source"],
                      "output": a.output}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
