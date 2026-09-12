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
import json, os, re, subprocess, sys, time, wave
from pathlib import Path


def wav_facts(w: str | None) -> dict:
    """Independent audio read-back: bytes + duration (not the renderer's word)."""
    p = Path(w) if w else None
    if not p or not p.exists():
        return {"wav": w, "size": 0, "seconds": 0.0}
    try:
        with wave.open(str(p)) as f:
            secs = f.getnframes() / float(f.getframerate() or 1)
    except Exception:
        secs = 0.0
    return {"wav": w, "size": p.stat().st_size, "seconds": round(secs, 2)}

CBSPEAK = Path.home() / "workspace/experiments/agent-skills/skills/chatterbox-speak/run.sh"
SFX = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library")
FUSED_MANIFEST = SFX / "fused-hmm/manifest.json"
HUMS = SFX / "song-hums"
PLAY = os.environ.get("MVP_PLAY") == "1"
HUM_LONG_MS = 7000  # hum only when B's remaining ETA is a genuinely long pause

# Dynamic emotion tags are chatterbox-speak's core mechanism: singular Turbo
# accepted_tags rendered as native events. The fast agent inserts them per beat.
# Answer tagging stays light for neutral/technical content (over-tagging is wrong).
THINK_TAG = "[sigh]"        # thinking/opener beat
RESTATE_TAG = "[clear throat]"  # natural throat-clear before restating
LOCK = "/mnt/storage12tb/skills/chatterbox-speak/outputs/contextual/playback.lock"


def mon(who: str, msg: str) -> None:
    """Live text monitor line, printed as the exchange happens."""
    print(f"  {time.strftime('%H:%M:%S')} {who:>2} | {msg}", flush=True)


def play(wav: str | None) -> None:
    if PLAY and wav and Path(wav).exists():
        with open(LOCK, "w") as lk:
            try:
                import fcntl
                fcntl.flock(lk, fcntl.LOCK_EX)
            except Exception:
                pass
            subprocess.run(["pw-play", wav], check=False)


def opener_clip() -> tuple[str, str] | None:
    """A pre-rendered ElevenLabs v3 fused-hmm opener (emotion tags baked in)."""
    try:
        entries = json.loads(FUSED_MANIFEST.read_text())["entries"]
        e = next((x for x in entries if x["band"] == "low"), entries[0])
        return e["wav"], e["text"]
    except Exception:
        return None


def hum_clip() -> tuple[str, str] | None:
    """A bone-dry ElevenLabs SFX hum to bed under the wait."""
    w = sorted(HUMS.glob("*.wav"))
    return (str(w[0]), w[0].stem) if w else None


def speak(text: str, pace: str | None = None) -> str | None:
    """Render one line via chatterbox-speak; return the produced wav path.

    Uses --pace (a VERIFIED audible lever: slow 3.53s vs brisk 2.74s) for the
    delivery arc; --tone is inert on Turbo (affect_effect.applied=false) so we
    do not use it.
    """
    args = ["bash", str(CBSPEAK), "speak", "--voice", "embry", "--text", text,
            "--context", "two-agent MVP"]
    if pace:
        args += ["--pace", pace]
    r = subprocess.run(args, capture_output=True, text=True)
    m = re.search(r'"wav":\s*"([^"]+\.wav)"', r.stdout)
    return m.group(1) if m else None


def speak_arc(text: str, arc: str) -> list[str]:
    """DELEGATE answer delivery to chatterbox-speak's own conversation-arc macro.
    speak --arc phases the answer across tone+PACE waypoints and compiles pauses;
    we do NOT re-implement phasing/pacing/tags here."""
    args = ["bash", str(CBSPEAK), "speak", "--voice", "embry", "--arc", arc,
            "--planned-pauses", "--text", text, "--context", "two-agent MVP"]
    if PLAY:
        args += ["--play"]
    r = subprocess.run(args, capture_output=True, text=True)
    return re.findall(r'"wav":\s*"([^"]+\.wav)"', r.stdout)


def main() -> int:
    log = Path(sys.argv[1])
    receipt_path = Path(sys.argv[2])
    timeout_s = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0
    a_start = time.time()
    question = sys.argv[4] if len(sys.argv) > 4 else ""
    consumed: list[dict] = []
    cover_ready_ts = None
    answer_text = None
    restated = False
    announced_lookup = False
    last_eta_ms = None
    last_hum_ts = 0.0
    b_done_ts = None
    pos = 0
    buf = ""
    opened = False

    def nonlocal_eta(v):
        nonlocal last_eta_ms
        last_eta_ms = v

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
                             "recv_ts": time.time()})
            eta = f" eta={ev['eta_ms']}ms" if ev.get("eta_ms") else ""
            mon("B>", f"{ev.get('stage')}{eta}")
            if ev.get("eta_ms") is not None:
                nonlocal_eta(ev["eta_ms"])
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
            oc = opener_clip()  # ElevenLabs fused-hmm opener (tag baked in)
            if oc:
                mon("A>", f"[opener/ElevenLabs+tag] {oc[1]!r}")
                play(oc[0]); wav = oc[0]
            else:
                wav = speak(f"{THINK_TAG} Hmm, let me see.")
            cover_ready_ts = time.time()
            consumed.append({"cover_wav": wav})
        # 2) restate the problem back, after "let me see..."
        if opened and not restated and question:
            restated = True
            rst = f"{RESTATE_TAG} Let me restate the question so I'm sure I understand — you're asking: " + question
            mon("A>", f"[restate w/ tag] {rst}")
            play(speak(rst))
        # 3) announce the lookup once, then the hum bed fills the actual wait
        if opened and restated and not announced_lookup and b_done_ts is None:
            announced_lookup = True
            lk = "Okay — give me a second while I look that up."
            mon("A>", f"[lookup] {lk}")
            play(speak(lk))
        # 4) hum ONLY during a genuinely long pause (remaining ETA > threshold), spaced
        if opened and restated and b_done_ts is None and last_eta_ms and last_eta_ms > HUM_LONG_MS:
            if time.time() - last_hum_ts > 8:
                hc = hum_clip()
                if hc:
                    mon("A>", f"[hum/ElevenLabs SFX — long pause] {hc[1]}")
                    play(hc[0]); last_hum_ts = time.time()
                    consumed.append({"hum_wav": hc[0], "hum": hc[1]})
        time.sleep(0.2)

    # final full-file read on timeout so a fast answer is never missed
    if log.exists():
        with log.open() as fh:
            fh.seek(pos)
            ingest(fh.read())

    # never speak an error payload aloud; the loop still records the failure
    speakable = bool(answer_text) and not str(answer_text).startswith("solver error:")
    answer_wav = None
    first_answer_ts = None
    answer_chunks: list[dict] = []
    arc_used = None
    if speakable:
        # DELEGATE to chatterbox-speak's conversation-arc macro (tone+pace phases,
        # compiled pauses, native tags). Do not rebuild the arc here.
        arc_used = "reassure" if any(k in (question or "").lower()
                     for k in ("worried", "grief", "afraid", "scared", "anxious")) else "answer"
        mon("A>", f"[answer via chatterbox-speak: speak --arc {arc_used} --planned-pauses]")
        first_answer_ts = time.time()
        wavs = speak_arc(answer_text, arc_used)
        answer_chunks = [{"i": i, "arc": arc_used, **wav_facts(w)} for i, w in enumerate(wavs)]
        answer_wav = wavs[0] if wavs else None
    answer_done_ts = time.time()
    receipt = {
        "schema": "embry_voice_control.mvp_a_receipt.v1",
        "a_start_ts": a_start, "cover_ready_ts": cover_ready_ts,
        "b_done_ts": b_done_ts, "answer_rendered_ts": answer_done_ts,
        "first_answer_chunk_ts": first_answer_ts,
        "gap_cover_end_to_first_answer_s": (
            round(first_answer_ts - (cover_ready_ts + 2.5), 1)
            if first_answer_ts and cover_ready_ts else None),
        "answer_text": answer_text, "answer_wav": answer_wav,
        "answer_arc": arc_used,
        "answer_chunks": answer_chunks,
        "answer_joined": answer_text or "",
        "played_audio": PLAY,
        "cover_ready_before_b_done": bool(cover_ready_ts and b_done_ts and cover_ready_ts < b_done_ts),
        "consumed_events": [c for c in consumed if c.get("seq") is not None],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in
          ("cover_ready_before_b_done", "played_audio", "answer_text", "answer_wav")}, indent=2))
    return 0 if answer_text else 1


if __name__ == "__main__":
    sys.exit(main())
