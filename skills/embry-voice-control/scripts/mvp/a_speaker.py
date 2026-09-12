#!/usr/bin/env python3
"""Agent A (speaker) — the FAST lane of the two-agent MVP.

Robustly tails Agent B's solver_event.v1 JSONL log (from byte 0, newline-buffered,
final full-file read on timeout), speaks a cover opener while B works, then renders
B's answer via chatterbox-speak. Writes a receipt proving what it consumed and when.

P1 (from review): tail startup/partial-line race — create log first (runner does),
read from start, buffer partial lines, do a final read on timeout so a fast B answer
is never missed.

stdlib only; renders through chatterbox-speak run.sh (Chatterbox Turbo).
"""
from __future__ import annotations
import json, re, subprocess, sys, time
from pathlib import Path

CBSPEAK = Path.home() / "workspace/experiments/agent-skills/skills/chatterbox-speak/run.sh"


def speak(text: str, tone: str) -> str | None:
    """Render one line via chatterbox-speak; return the produced wav path."""
    r = subprocess.run(["bash", str(CBSPEAK), "speak", "--voice", "embry",
                        "--text", text, "--tone", tone, "--context", "two-agent MVP"],
                       capture_output=True, text=True)
    m = re.search(r'"wav":\s*"([^"]+\.wav)"', r.stdout)
    return m.group(1) if m else None


def main() -> int:
    log = Path(sys.argv[1])
    receipt_path = Path(sys.argv[2])
    timeout_s = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0
    a_start = time.time()
    consumed: list[dict] = []
    spoke_cover_ts = None
    answer_text = None
    b_done_ts = None
    pos = 0
    buf = ""
    opened = False

    def ingest(chunk: str):
        nonlocal buf, answer_text, b_done_ts
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                buf = line + "\n" + buf  # partial; wait for more
                return
            consumed.append({"seq": ev.get("seq"), "stage": ev.get("stage"),
                             "offset": pos, "recv_ts": time.time()})
            if ev.get("answer_text"):
                answer_text = ev["answer_text"]
            if ev.get("done") or ev.get("stage") == "answer_ready":
                b_done_ts = time.time()

    deadline = a_start + timeout_s
    while time.time() < deadline and b_done_ts is None:
        if log.exists():
            with log.open() as fh:
                fh.seek(pos)
                chunk = fh.read()
                pos = fh.tell()
            if chunk:
                ingest(chunk)
        # cover: as soon as we see any B activity, speak one opener (once)
        if consumed and not opened:
            opened = True
            wav = speak("Hmm, let me pull that up for you.", "neutral_warm")
            spoke_cover_ts = time.time()
            consumed.append({"cover_wav": wav, "spoke_ts": spoke_cover_ts})
        time.sleep(0.2)

    # final full-file read on timeout so a fast answer is never missed
    if log.exists():
        with log.open() as fh:
            fh.seek(pos)
            ingest(fh.read())

    # never speak an error payload aloud; the loop still records the failure
    speakable = bool(answer_text) and not str(answer_text).startswith("solver error:")
    answer_wav = speak(answer_text, "memory_confident") if speakable else None
    answer_done_ts = time.time()
    receipt = {
        "schema": "embry_voice_control.mvp_a_receipt.v1",
        "a_start_ts": a_start, "spoke_cover_ts": spoke_cover_ts,
        "b_done_ts": b_done_ts, "answer_rendered_ts": answer_done_ts,
        "answer_text": answer_text, "answer_wav": answer_wav,
        "spoke_cover_before_b_done": bool(spoke_cover_ts and b_done_ts and spoke_cover_ts < b_done_ts),
        "consumed_events": consumed,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in
          ("spoke_cover_before_b_done", "answer_text", "answer_wav")}, indent=2))
    return 0 if answer_text else 1


if __name__ == "__main__":
    sys.exit(main())
