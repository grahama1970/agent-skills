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
import json, os, re, subprocess, sys, time, urllib.request, wave
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
SCILLM = os.environ.get("SCILLM_URL", "http://127.0.0.1:4001/v1/chat/completions")
SCILLM_KEY = (os.environ.get("SCILLM_MASTER_KEY") or os.environ.get("LITELLM_MASTER_KEY")
              or os.environ.get("SCILLM_PROXY_KEY") or "sk-dev-proxy-123")


def key_terms(text: str) -> set[str]:
    """Load-bearing tokens that MUST survive the rewrite (control IDs, CWE/acronyms, numbers)."""
    return set(re.findall(r'\b[A-Z]{2,}(?:-\d+(?:\([0-9a-z]+\))?)?\b', text or ""))


def compose_spoken_answer(question: str, raw: str) -> tuple[str, bool]:
    """WebGPT fix #1: A (fast model) rewrites B's raw answer as a natural spoken
    reply (direct answer + one essential caveat, 2-3 sentences). Hard constraint:
    preserve the conclusion — control IDs, negation, numbers, caveats. If the
    rewrite drops a load-bearing term, fall back to the raw answer (never distort).
    """
    # Preserve the SUBJECT the user asked about (question control IDs) + core
    # meaning; a spoken summary may drop supporting cross-refs (e.g. a CWE id).
    must = key_terms(question) & key_terms(raw)
    prompt = ("Rewrite the ANSWER as a natural spoken reply for a voice assistant: "
              "a direct answer plus at most one essential caveat, 2-3 short sentences, "
              "conversational, no lists, no preamble. Keep the primary control ID and the "
              "core meaning; do not flip any negation or change numbers.\n\n"
              f"QUESTION: {question}\nANSWER: {raw}\n\nSpoken reply:")
    body = json.dumps({"model": "zai-glm-flash",
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.4, "max_tokens": 220}).encode()
    try:
        req = urllib.request.Request(SCILLM, data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {SCILLM_KEY}",
                                              "X-Caller-Skill": "embry-voice-control"})
        with urllib.request.urlopen(req, timeout=45) as r:
            out = json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[compose] scillm call failed, using raw: {exc!r}", file=sys.stderr)
        return raw, False
    out = re.sub(r'^\s*Spoken reply:\s*', '', out)  # strip echoed label
    dropped = must - key_terms(out)
    if not out or dropped:
        print(f"[compose] guard fallback; dropped={sorted(dropped)}", file=sys.stderr)
        return raw, False
    return out, True
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
                wav = speak("Hmm, let me see.")  # opener stays plain (no compulsory tag)
            cover_ready_ts = time.time()
            consumed.append({"cover_wav": wav})
        # 2) restate the problem back, after "let me see..."
        if opened and not restated and question:
            restated = True
            rst = "So — to make sure I've got it: " + question
            mon("A>", f"[restate] {rst}")
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
    spoken_answer = None
    rewritten = False
    if speakable:
        # FIX #1: A composes the spoken answer (rewrite B's raw text conversationally,
        # conclusion preserved), THEN delegate delivery to chatterbox-speak's arc.
        spoken_answer, rewritten = compose_spoken_answer(question, answer_text)
        arc_used = "reassure" if any(k in (question or "").lower()
                     for k in ("worried", "grief", "afraid", "scared", "anxious")) else "answer"
        mon("A>", f"[answer rewritten={rewritten} via speak --arc {arc_used}] {spoken_answer[:60]}")
        first_answer_ts = time.time()
        wavs = speak_arc(spoken_answer, arc_used)
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
        "raw_answer": answer_text, "spoken_answer": spoken_answer,
        "rewritten": rewritten,
        "conclusion_preserved": bool(spoken_answer) and
            (key_terms(question) & key_terms(answer_text)) <= key_terms(spoken_answer),
        "answer_arc": arc_used,
        "answer_chunks": answer_chunks,
        "answer_joined": spoken_answer or answer_text or "",
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
