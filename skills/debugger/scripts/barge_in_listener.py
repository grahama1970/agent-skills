#!/usr/bin/env python3
"""Listen for a spoken interrupt and cut Embry off by touching the stop flag.

While the walkthrough narrates in the Embry voice, this runs RealtimeSTT's
continuous voice-activity detection; when the human says a stop word ("stop",
"pause", "quiet", "enough", "hold on", "wait"), it touches the stop-flag file
that vscode_walkthrough.speak() polls, terminating playback mid-sentence. That
is what lets the human interrupt Embry and tell her to stop.

RealtimeSTT lives in the live-evidence venv, so launch this with that
interpreter, e.g.:

    /mnt/storage12tb/skills/live-evidence/.venv/bin/python \
        scripts/barge_in_listener.py /tmp/debugger-embry-stop.flag

Prints BARGE-IN-LISTENING once the recorder is warm, and a BARGE-IN line each
time it triggers. Ctrl-C to stop.
"""

from __future__ import annotations

import sys
from pathlib import Path

STOP_WORDS = ("stop", "pause", "quiet", "enough", "hold on", "hold up", "wait", "shush", "shut up")


def main() -> int:
    stop_flag = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/debugger-embry-stop.flag")
    try:
        from RealtimeSTT import AudioToTextRecorder
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"BARGE-IN-UNAVAILABLE RealtimeSTT import failed: {exc}", file=sys.stderr)
        return 3
    recorder = AudioToTextRecorder(
        model="tiny.en",
        language="en",
        spinner=False,
        post_speech_silence_duration=0.4,
    )
    print("BARGE-IN-LISTENING", flush=True)
    try:
        while True:
            heard = (recorder.text() or "").strip().lower()
            if heard and any(word in heard for word in STOP_WORDS):
                stop_flag.touch()
                print(f"BARGE-IN heard {heard!r} -> touched {stop_flag}", flush=True)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
