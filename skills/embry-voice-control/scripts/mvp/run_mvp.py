#!/usr/bin/env python3
"""Two-agent MVP runner — launches Agent A (speaker) and Agent B (solver)
CONCURRENTLY over a shared solver_event.v1 JSONL log, then asserts the loop.

Proves (review's honest eval): both agents live, real B stream (not scripted),
A consumed real log offsets, A spoke BEFORE B finished, rendered answer == B's
answer_text, A/B timestamps overlap. Writes a combined receipt.

Usage: run_mvp.py [question] [scope]
"""
from __future__ import annotations
import json, subprocess, sys, time, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/mvp")


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "What does control SC-7 require?"
    scope = sys.argv[2] if len(sys.argv) > 2 else "sparta"
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    log = OUT / f"{run_id}.solver.jsonl"
    a_receipt = OUT / f"{run_id}.a-receipt.json"
    log.touch()  # P1: create the log FIRST so A can tail from byte 0

    t_launch = time.time()
    # launch B (solver) and A (speaker) concurrently
    b = subprocess.Popen([sys.executable, str(HERE / "b_solver.py"), question, str(log), scope])
    a = subprocess.Popen([sys.executable, str(HERE / "a_speaker.py"), str(log), str(a_receipt), "90"])
    b_rc = b.wait()
    a_rc = a.wait()

    events = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    stages = [e.get("stage") for e in events]
    rec = json.loads(a_receipt.read_text()) if a_receipt.exists() else {}

    def norm(s):
        return " ".join((s or "").split())
    b_answer = next((e.get("answer_text") for e in reversed(events) if e.get("answer_text")), None)
    # consumed (seq,stage) compared against the ACTUAL solver log, not A's word
    log_pairs = {(e.get("seq"), e.get("stage")) for e in events if e.get("seq") is not None}
    consumed_pairs = {(c.get("seq"), c.get("stage")) for c in rec.get("consumed_events", [])}
    chunks = rec.get("answer_chunks", [])
    checks = {
        "b_exit_ok": b_rc == 0,
        "a_exit_ok": a_rc == 0,
        "valid_event_sequence": bool(events) and stages[0].startswith("working:")
                                and stages[-1] == "answer_ready",
        "a_consumed_matches_log": bool(log_pairs) and log_pairs <= consumed_pairs,
        "cover_ready_before_b_done": rec.get("cover_ready_before_b_done") is True,
        "answer_matches_b": bool(b_answer) and norm(rec.get("answer_joined")) == norm(b_answer),
        "all_answer_chunks_real_audio": bool(chunks) and all(c.get("size", 0) > 1000
                                             and c.get("seconds", 0) > 0.3 for c in chunks),
        "timestamps_overlap": bool(rec.get("cover_ready_ts") and rec.get("b_done_ts")
                                   and rec.get("cover_ready_ts") < rec.get("b_done_ts")),
    }
    passed = all(checks.values())
    combined = OUT / f"{run_id}.mvp-receipt.json"
    combined.write_text(json.dumps({
        "schema": "embry_voice_control.mvp_receipt.v1", "run_id": run_id,
        "question": question, "scope": scope, "log": str(log),
        "launch_ts": t_launch, "b_rc": b_rc, "a_rc": a_rc,
        "stages": stages, "checks": checks, "passed": passed,
        "answer_text": rec.get("answer_text"), "answer_wav": rec.get("answer_wav"),
    }, indent=2) + "\n")
    for k, v in checks.items():
        print(f"  [{'OK' if v else 'FAIL'}] {k}")
    print(f"{'PASS' if passed else 'FAIL'}: two-agent MVP loop | receipt {combined}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
