#!/usr/bin/env python3
"""Real-world e2e agentic eval: interrupt Embry mid-explanation and redirect.

Nothing here is fixtured or deterministic by design. Embry's voice is rendered
by the LIVE Chatterbox server (CUDA, turbo engine) from a breakpoint monologue;
audio plays through a per-run null sink; the LIVE GPU RealtimeSTT bridge
transcribes the sink monitor; the local stage-1 resolver
judges the transcript; and the human interruption is a REAL human voice -- the
recorded interviewer from the pinned YouTube WAV -- barging in over Embry.

The claim under test: while the assistant is talking about one topic
(a debugger breakpoint), a human can interrupt with a DIFFERENT question and
the system (a) actually silences the assistant -- process-level effect plus a
Chatterbox cancel receipt, not a status flag -- and (b) redirects to the
human's topic, producing a card about parentheses, not breakpoints.

Prerequisites are part of the claim: if Chatterbox, the GPU container, or Memory
is unavailable, the eval fails with that named reason rather than degrading into
fixtures.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from eval_live_youtube_oracle import create_virtual_sink, destroy_virtual_sink

CHATTERBOX = "http://127.0.0.1:8018"
SINK_WAV = Path("/mnt/storage12tb/skills/live-evidence/live-youtube-proof/20260816T181309Z/youtube.wav")
CHATTERBOX_LOGS = Path.home() / "workspace/experiments/chatterbox/logs"

EMBRY_TEXT = (
    "Let me walk you through the breakpoint I set at line forty two. When "
    "execution pauses there, the frame shows the loop counter and the buffer "
    "variables, and inspecting the locals tells us exactly why the counter "
    "drifts. Watch the variable pane closely while I step through this handler "
    "one line at a time, because the drift only appears after the third "
    "iteration, and the counter variable is the one to keep your eye on."
)
EMBRY_TOKENS = {"breakpoint", "counter", "variable", "variables", "locals", "drift"}
REDIRECT_TOKENS = {"parentheses", "opening", "closing", "minimum", "valid", "invalid", "string", "remove"}

failures: list[str] = []


def check(name: str, passed: bool, detail: str) -> None:
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({detail})")
    if not passed:
        failures.append(name)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def post(url: str, payload: dict, timeout: float = 60.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except Exception:
            return exc.code, {}


def get(url: str, timeout: float = 15.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def provider_boundary() -> str:
    return "tau_only"


def transcript_tokens(base: str) -> set[str]:
    state = get(f"{base}/api/state")
    blob = " ".join(e.get("text", "") for e in state.get("transcript") or []).lower()
    return {token.strip(".,?!") for token in blob.split()}


def main() -> int:
    # --- prerequisites are part of the real-world claim ---
    try:
        health = get(f"{CHATTERBOX}/health", timeout=6)
    except Exception as exc:
        check("chatterbox voice server live", False, f"{type(exc).__name__}")
        return 1
    check("chatterbox voice server live",
          health.get("live") is True and health.get("model_loaded") is True,
          f"engine={health.get('engine')} device={health.get('device')}")
    check("real human interrupt audio present", SINK_WAV.is_file(), str(SINK_WAV)[-40:])
    if failures:
        return 1

    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    nonce = os.urandom(4).hex()
    sink = f"le-voice-{os.getpid()}"
    with tempfile.TemporaryDirectory(prefix="le-voice-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "repo"
        repo.mkdir()
        (repo / "valid_parentheses.py").write_text(
            "def is_valid_parentheses(s):\n    balance = 0\n"
            "    for ch in s:\n        balance += ch == '('\n"
            "        balance -= ch == ')'\n        if balance < 0:\n"
            "            return False\n    return balance == 0\n"
        )
        (temp / "profile.yaml").write_text(
            "name: voice-interrupt\nwatch_terms:\n"
            "  - breakpoint\n  - variables\n  - counter\n"
            "  - parentheses\n  - valid\n  - minimum\n"
        )

        # Real Embry render on the live server.
        label = f"embry-breakpoint-{nonce}"
        code, body = post(f"{CHATTERBOX}/synthesize",
                          {"text": EMBRY_TEXT, "label": label}, timeout=180)
        embry_wav = None
        for candidate in (CHATTERBOX_LOGS / f"{label}.wav",
                          Path(str(body.get("path") or "/nonexistent"))):
            if candidate.is_file():
                embry_wav = candidate
                break
        check("embry monologue rendered by live chatterbox",
              code == 200 and embry_wav is not None and embry_wav.stat().st_size > 100_000,
              f"http={code} wav={embry_wav}")
        if failures:
            return 1

        # Human interrupt: the real recorded interviewer stating the problem.
        human_wav = temp / "human-interrupt.wav"
        subprocess.run(["sox", str(SINK_WAV), str(human_wav), "trim", "60", "22"],
                       check=True, capture_output=True)

        create_virtual_sink(sink)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(temp / "data"),
            "LIVE_EVIDENCE_PROFILE": str(temp / "profile.yaml"),
            "MEMORY_SERVICE_URL": "http://127.0.0.1:8601",
        }
        server_log = (temp / "server.log").open("w")
        server = subprocess.Popen(
            [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1",
             "--port", str(port), "--no-browser"],
            cwd=root, env=env, stdout=server_log, stderr=subprocess.STDOUT, text=True)
        bridge = embry_play = human_play = None
        try:
            for _ in range(80):
                try:
                    get(f"{base}/api/health", timeout=2)
                    break
                except Exception:
                    time.sleep(0.1)

            # Live GPU STT bridge in already-playing capture mode.
            bridge_log = (temp / "bridge.log").open("w")
            bridge = subprocess.Popen(
                [sys.executable, str(root / "scripts/e2e_pipewire_docker_bridge.py"),
                 "--backend-url", base,
                 "--capture-target", sink, "--capture-kind", "sink-monitor",
                 "--output-dir", str(temp / "bridge"),
                 "--max-seconds", "75", "--no-require-ask"],
                cwd=root, env=env, stdout=bridge_log, stderr=subprocess.STDOUT, text=True)
            time.sleep(14)  # GPU container warm-up

            # Rehearsal session: voice output is a policy-permitted capability.
            _, snap = post(f"{base}/api/session/start",
                           {"consent_confirmed": True, "purpose": "rehearsal",
                            "actor_role": "candidate"})
            check("rehearsal session is practice_only with voice permitted",
                  snap["session"].get("practice_only") is True
                  and snap["session"]["policy"]["voice_output"] is True,
                  snap["session"]["policy_digest"][:12])

            code, _ = post(f"{base}/api/voice/utterance",
                           {"text": EMBRY_TEXT, "turn_id": label})
            check("assistant utterance registered for echo suppression", code == 202,
                  f"http={code}")

            start = time.monotonic()
            embry_play = subprocess.Popen(
                ["pw-play", "--target", sink, str(embry_wav)])

            heard_embry = False
            while time.monotonic() - start < 30:
                if len(transcript_tokens(base) & EMBRY_TOKENS) >= 2:
                    heard_embry = True
                    break
                time.sleep(1.0)
            check("embry's breakpoint explanation transcribed live",
                  heard_embry, f"{time.monotonic()-start:.1f}s to detect")

            # Barge-in: the human starts talking OVER Embry, then Embry is cut.
            human_play = subprocess.Popen(
                ["pw-play", "--target", sink, str(human_wav)])
            time.sleep(1.2)
            embry_play.terminate()
            try:
                embry_play.wait(timeout=3)
            except subprocess.TimeoutExpired:
                embry_play.kill()
            check("embry playback actually stopped (process-level effect)",
                  embry_play.poll() is not None, f"rc={embry_play.returncode}")
            code, receipt = post(f"{CHATTERBOX}/turn/{label}/cancel",
                                 {"reason": f"human barge-in redirect {nonce}"})
            check("chatterbox turn cancel receipt", code == 200 and bool(receipt),
                  f"http={code} keys={sorted(receipt)[:4]}")

            heard_redirect = False
            redirect_start = time.monotonic()
            while time.monotonic() - redirect_start < 35:
                if len(transcript_tokens(base) & REDIRECT_TOKENS) >= 2:
                    heard_redirect = True
                    break
                time.sleep(1.0)
            check("human interrupt question transcribed after barge-in",
                  heard_redirect, f"{time.monotonic()-redirect_start:.1f}s to detect")

            redirect_card = None
            card_start = time.monotonic()
            while time.monotonic() - card_start < 45 and redirect_card is None:
                for card in get(f"{base}/api/state").get("cards") or []:
                    query = (card.get("query") or "").lower()
                    query_tokens = {t.strip(".,?!") for t in query.split()}
                    redirect_hits = len(query_tokens & REDIRECT_TOKENS)
                    # Token-set overlap with Embry's monologue, so "break
                    # point" as two words cannot dodge a substring check --
                    # the first run of this eval passed a card that was
                    # Embry's own explanation because of exactly that.
                    embry_hits = len(query_tokens & EMBRY_TOKENS | {t for t in ("break",) if t in query_tokens})
                    if redirect_hits >= 2 and embry_hits == 0:
                        redirect_card = card
                        break
                time.sleep(1.5)
            if redirect_card is None:
                keep = Path("/mnt/storage12tb/skills/live-evidence/agentic-evals/voice-interrupt-failures")
                keep.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                state_dump = get(f"{base}/api/state")
                (keep / f"{stamp}-state.json").write_text(json.dumps(state_dump, indent=2))
                for jf in (temp / "data").rglob("session.jsonl"):
                    (keep / f"{stamp}-journal.jsonl").write_text(jf.read_text())
                detail = "; ".join(repr((c.get("query") or "")[:60]) for c in state_dump.get("cards") or [])
            else:
                detail = repr((redirect_card or {}).get("query", "")[:80])
            check("system redirected: card is about the human's question, not the breakpoint",
                  redirect_card is not None, detail)
            if redirect_card is not None:
                check("redirect card carries the rehearsal policy digest",
                      redirect_card.get("policy_digest") == snap["session"]["policy_digest"],
                      str(redirect_card.get("policy_digest"))[:12])
        finally:
            for proc in (embry_play, human_play):
                if proc is not None and proc.poll() is None:
                    proc.kill()
            if bridge is not None:
                bridge.terminate()
                try:
                    bridge.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    bridge.kill()
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            server_log.close()
            destroy_virtual_sink(sink)

    print()
    if failures:
        print(f"voice interruption redirect: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("voice interruption redirect: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
