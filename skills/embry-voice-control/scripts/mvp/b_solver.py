#!/usr/bin/env python3
"""Agent B (solver) — the SLOW lane of the two-agent MVP.

Actually solves a question via memory /answer and appends solver_event.v1 lines
to a shared JSONL log as it works, so Agent A can tail real progress. Ends with
answer_ready + done. stdlib only (urllib); flushes after every line.

Contract (solver_event.v1): {schema, seq, ts, stage, eta_ms?, steps?, answer_text?, done?}
"""
from __future__ import annotations
import json, os, sys, time, urllib.request
from pathlib import Path

MEM = os.environ.get("EMBRY_MEM_URL", "http://127.0.0.1:8601")


def emit(fh, seq: int, **fields) -> None:
    rec = {"schema": "solver_event.v1", "seq": seq, "ts": time.time(), **fields}
    fh.write(json.dumps(rec) + "\n")
    fh.flush()  # A tails line-by-line; never buffer a line B has "sent"


def answer(question: str, scope: str) -> dict:
    body = json.dumps({"q": question, "scope": scope, "k": 5}).encode()
    req = urllib.request.Request(MEM + "/answer", data=body,
                                 headers={"Content-Type": "application/json", "X-Caller-Skill": "embry-voice-control"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "What does control SC-7 require?"
    log = Path(sys.argv[2])
    scope = sys.argv[3] if len(sys.argv) > 3 else "sparta"
    seq = 0
    with log.open("a") as fh:
        emit(fh, seq, stage="working:intent", eta_ms=12000,
             steps=["what SC-7 requires at the boundary"]); seq += 1
        time.sleep(0.5)
        emit(fh, seq, stage="working:recall", eta_ms=9000); seq += 1
        t0 = time.time()
        try:
            data = answer(question, scope)
            ans = data.get("final_response") or data.get("source_answer") or ""
            if not ans and data.get("can_answer") is False:
                ans = "I don't have grounded evidence to answer that yet."
        except Exception as exc:
            emit(fh, seq, stage="error", answer_text=f"solver error: {exc}", done=True)
            return 1
        emit(fh, seq, stage="working:answer", eta_ms=1000,
             solve_seconds=round(time.time() - t0, 2)); seq += 1
        emit(fh, seq, stage="answer_ready", answer_text=ans.strip(), done=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
