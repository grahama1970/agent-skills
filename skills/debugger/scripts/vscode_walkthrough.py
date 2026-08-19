#!/usr/bin/env python3
"""Walk a human through code with the live debugger, one narrated breakpoint at a time.

This is the `/debugger walkthrough` runtime. The agent authors a
`debugger.walkthrough.v1` spec -- an ordered list of stops, each naming a
file+line (or function/class), what to SAY there, and which locals to show --
and this drives the real VS Code debugger to each stop in turn: it reveals the
file in the human's editor, runs the program to the breakpoint, reads the live
paused state, and prints the narration alongside the observed values. Use it to
showcase finished work (`mode: review`) or to take the human straight to where
the agent is stuck (`mode: blocked`).

It reuses the same live bridge as scripts/vscode_bridge_session.py and is
capability-gated the same way: when no trusted VS Code bridge answers it prints
BRIDGE_BLOCKED and exits 3 (an eval marks the case BLOCKED, never a false PASS).

Workspace: --workspace PATH, else $DEBUGGER_VSCODE_WORKSPACE. The spec's file
paths are workspace-relative and the workspace must be open+trusted in VS Code
with the debugger-vscode-bridge extension active.

Output: a `── STOP i/N` block per stop with SAY and STATE lines, then
WALKTHROUGH-COMPLETE. With --transcript PATH it also writes a JSON transcript.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_NAME = "Debugger walkthrough ($debugger)"


def _stdin_has_line() -> bool:
    """True when a line is waiting on stdin (a keypress + Enter), non-blocking."""
    import select
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except (OSError, ValueError):
        return False


def resolve_line(path: Path, *, line, function, klass) -> int | None:
    """Resolve a stop to a source line: explicit line, else a function/class def."""
    if line is not None:
        return int(line)
    source = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {function}:
                    return node.lineno
                if isinstance(node, ast.ClassDef) and node.name in {klass}:
                    return node.lineno
    patterns = []
    if function:
        patterns.append(re.compile(rf"\b(?:def|function|fn)\s+{re.escape(function)}\b"))
    if klass:
        patterns.append(re.compile(rf"\bclass\s+{re.escape(klass)}\b"))
    for index, text in enumerate(source.splitlines(), start=1):
        if any(p.search(text) for p in patterns):
            return index
    return None


def acknowledge_pause() -> None:
    """Emit a short, natural spoken cue when Embry is interrupted, so the pause
    feels like a person yielding the floor rather than dead air.

    Uses the chatterbox emotion endpoint when available so the acknowledgment
    carries a warm/attentive affect; fail-soft to plain synthesis, then silence.
    """
    url = os.environ.get("DEBUGGER_SPEAK_EMOTION_URL", "http://127.0.0.1:8018/synthesize-emotion")
    out_map = os.environ.get("DEBUGGER_SPEAK_OUT_MAP", "/out:" + str(Path.home() / "workspace/experiments/chatterbox/logs"))
    cue = os.environ.get("DEBUGGER_PAUSE_CUE", "Mm-hmm, go ahead.")
    try:
        import httpx
        resp = httpx.post(url, json={"text": cue, "tone": "warm", "delivery_stage": "backchannel"}, timeout=45.0)
        if resp.status_code != 200:
            speak(cue)
            return
        audio = resp.json().get("audio")
        if not audio:
            return
        src, dst = out_map.split(":", 1)
        host_path = audio.replace(src, dst, 1) if audio.startswith(src) else audio
        if Path(host_path).is_file():
            subprocess.run(["aplay", "-q", host_path], check=False, capture_output=True, timeout=30)
    except Exception:
        return


def answer_question(question: str, stop: dict, state_str: str, spec: dict) -> str:
    """Answer a human question during the walkthrough, grounded in the paused state.

    If DEBUGGER_ANSWER_URL is set, POST {question, context} to it and use the
    returned `answer` (an LLM/Embry endpoint). Otherwise fall back to a concise
    answer grounded in this stop's narration and observed variables -- honest and
    source-bound rather than invented.
    """
    url = os.environ.get("DEBUGGER_ANSWER_URL")
    context = {"title": spec.get("title"), "say": stop.get("say"), "state": state_str,
               "file": stop.get("file"), "mode": spec.get("mode")}
    if url:
        try:
            import httpx
            resp = httpx.post(url, json={"question": question, "context": context}, timeout=60.0)
            resp.raise_for_status()
            answer = (resp.json() or {}).get("answer")
            if answer:
                return str(answer)
        except Exception:
            pass
    return (f"At this stop ({stop.get('file')}) the state is {state_str}. {stop.get('say')} "
            f"Ask me to continue, repeat, or go back, or ask another question.")


def remember_walkthrough(spec: dict, transcript: list[dict], key_seed: str) -> str | None:
    """Store the walkthrough conversation in /memory so Embry keeps the context.

    Writes one document per walkthrough into the `debugger_walkthroughs`
    collection with a deterministic _key, so re-running does not duplicate it and
    a later session can recall what was walked through. Fail-soft: returns the
    stored _key on success, None otherwise (the memory API is optional).
    """
    url = os.environ.get("DEBUGGER_MEMORY_URL", "http://127.0.0.1:8601")
    try:
        import hashlib
        import httpx
        key = hashlib.sha256(key_seed.encode()).hexdigest()[:16]
        document = {
            "_key": key,
            "schema": "debugger.walkthrough_transcript.v1",
            "title": spec["title"],
            "mode": spec["mode"],
            "turns": [
                {"role": "embry", "file": t["file"], "line": t["line"], "say": t["say"], "state": t["locals"]}
                for t in transcript
            ],
        }
        resp = httpx.post(f"{url}/store", json={"collection": "debugger_walkthroughs", "document": document}, timeout=15.0)
        resp.raise_for_status()
        return key if resp.json().get("stored") else None
    except Exception:
        return None


def speak(text: str, stop_flag: str | None = None, watch_stdin: bool = False) -> str:
    """Narrate a line aloud in the Embry voice via the chatterbox agent server.

    Returns "spoken", "interrupted" (the human said stop), or "silent" (server
    down / no audio). Playback is interruptible: while aplay runs, if `stop_flag`
    (a file path a barge-in listener touches) appears, playback is killed so the
    human can cut Embry off mid-sentence. Fail-soft otherwise -- the printed SAY
    line is the source of truth.
    """
    url = os.environ.get("DEBUGGER_SPEAK_URL", "http://127.0.0.1:8018/synthesize")
    out_map = os.environ.get("DEBUGGER_SPEAK_OUT_MAP", "/out:" + str(Path.home() / "workspace/experiments/chatterbox/logs"))
    try:
        import httpx
        resp = httpx.post(url, json={"text": text}, timeout=90.0)
        resp.raise_for_status()
        audio = resp.json().get("audio")
        if not audio:
            return "silent"
        src, dst = out_map.split(":", 1)
        host_path = audio.replace(src, dst, 1) if audio.startswith(src) else audio
        if not Path(host_path).is_file():
            return "silent"
        if stop_flag and Path(stop_flag).exists():
            Path(stop_flag).unlink(missing_ok=True)
        proc = subprocess.Popen(["aplay", "-q", host_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while proc.poll() is None:
            interrupted = stop_flag and Path(stop_flag).exists()
            # A keypress (Enter) during playback interrupts too -- the human can
            # cut Embry off at any moment, not only at line boundaries.
            if watch_stdin and _stdin_has_line():
                sys.stdin.readline()
                interrupted = True
            if interrupted:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if stop_flag:
                    Path(stop_flag).unlink(missing_ok=True)
                return "interrupted"
            time.sleep(0.05)
        return "spoken"
    except Exception:
        return "silent"


def write_launch(workspace: Path, launch: dict, config_name: str) -> None:
    cmd = [
        "uv", "run", "--project", str(SKILL), "python",
        str(SKILL / "scripts" / "write_vscode_launch.py"),
        "--workspace", str(workspace), "--name", config_name,
        "--python", launch.get("python", "/usr/bin/python3"),
        "--module", launch["module"],
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def reveal(workspace: Path, file: str, line: int) -> None:
    """Best-effort: jump the human's editor to the stop before we run to it."""
    try:
        subprocess.run(
            ["uv", "run", "--project", str(SKILL), "python",
             str(SKILL / "scripts" / "open_in_vscode.py"), str(workspace / file), "--line", str(line)],
            check=False, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def issue_stop(workspace: Path, config_name: str, file: str, line: int, locals_: list[str], timeout_ms: int) -> str:
    cmd = [
        "uv", "run", "--project", str(SKILL), "python",
        str(SKILL / "scripts" / "request_vscode_bridge.py"),
        "--workspace", str(workspace), "--action", "restart",
        "--launch-config-name", config_name,
        "--break", f"{workspace / file}:{line}",
        "--stop-timeout-ms", str(timeout_ms),
        "--expect-extension-host-kind", os.environ.get("DEBUGGER_VSCODE_HOST_KIND", "ui"),
    ]
    for name in locals_:
        cmd += ["--local", name]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads((workspace / ".vscode" / "debugger-bridge" / "request.json").read_text())["output"]


def poll_status(workspace: Path, output: str, deadline: float, probe_seconds: float = 20.0) -> dict | None:
    nonterminal = {"pending", "no-file", "starting", "launching", "running", "continuing"}
    status_path = workspace / output
    try:
        initial_stamp = json.loads(status_path.read_text()).get("updatedAt")
    except (OSError, json.JSONDecodeError):
        initial_stamp = None
    engaged = False
    probe_deadline = time.time() + probe_seconds
    while time.time() < deadline:
        try:
            status = json.loads(status_path.read_text())
        except (OSError, json.JSONDecodeError):
            status = {"status": "no-file"}
        state = status.get("status")
        if state not in nonterminal:
            return status
        if not engaged and (status.get("updatedAt") != initial_stamp or state != "pending"):
            engaged = True
        if not engaged and time.time() > probe_deadline:
            return None
        time.sleep(1.0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--transcript", type=Path, default=None)
    parser.add_argument("--wait-seconds", type=float, default=45.0)
    parser.add_argument("--speak", action="store_true", help="Narrate each stop aloud in the Embry voice (chatterbox).")
    parser.add_argument("--remember", action="store_true", help="Store the walkthrough conversation in /memory so Embry keeps the context.")
    parser.add_argument("--stop-flag", default=os.environ.get("DEBUGGER_STOP_FLAG", "/tmp/debugger-embry-stop.flag"),
                        help="File a barge-in listener touches to interrupt Embry mid-sentence.")
    parser.add_argument("--commands", default=None,
                        help="Semicolon-separated scripted commands for the pause-and-listen loop "
                             "(continue/repeat/back/quit/interrupt/<question>); for evals and automation.")
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if spec.get("schema") != "debugger.walkthrough.v1":
        print("spec is not a debugger.walkthrough.v1 object", file=sys.stderr)
        return 2
    workspace = Path(args.workspace or os.environ.get("DEBUGGER_VSCODE_WORKSPACE") or "").resolve()
    if not workspace.is_dir():
        print(f"workspace not found: {workspace} (set --workspace or DEBUGGER_VSCODE_WORKSPACE)", file=sys.stderr)
        return 2

    config_name = spec["launch"].get("config_name", DEFAULT_CONFIG_NAME)
    write_launch(workspace, spec["launch"], config_name)
    stops = spec["stops"]
    print(f"WALKTHROUGH mode={spec['mode']} stops={len(stops)} :: {spec['title']}")

    # Command source. --commands drives the pause-and-listen loop from a script
    # (for evals/automation); otherwise a real terminal reads the human live. A
    # non-interactive run with no script just auto-advances (base walkthrough).
    commands = [c.strip() for c in args.commands.split(";")] if args.commands is not None else None
    interactive = commands is not None or bool(sys.stdin and sys.stdin.isatty())
    if interactive and args.speak:
        print("(interrupt any time: press Enter or say a stop word; then continue / repeat / back / quit, or ask a question)")

    transcript: list[dict] = []

    def next_command() -> str:
        if commands is not None:
            return commands.pop(0) if commands else "continue"
        try:
            return input("  Embry paused — [Enter=continue · r=repeat · b=back · q=quit · or ask] > ").strip()
        except EOFError:
            return "quit"

    def finalize() -> None:
        if args.remember:
            key = remember_walkthrough(spec, transcript, f"debugger-walkthrough:{spec['title']}:{spec['mode']}")
            print(f"REMEMBERED /memory debugger_walkthroughs/{key}" if key else "REMEMBER-SKIPPED (memory API unavailable)")
        if args.transcript:
            args.transcript.write_text(
                json.dumps({"schema": "debugger.walkthrough_transcript.v1", "title": spec["title"],
                            "mode": spec["mode"], "stops": transcript}, indent=2) + "\n", encoding="utf-8")
            print(f"TRANSCRIPT {args.transcript}")

    index = 0
    while index < len(stops):
        stop = stops[index]
        human_index = index + 1
        path = workspace / stop["file"]
        line = resolve_line(path, line=stop.get("line"), function=stop.get("function"), klass=stop.get("class"))
        if line is None:
            print(f"STOP-UNRESOLVED {stop['file']} {stop.get('function') or stop.get('class')}", file=sys.stderr)
            return 1
        # The first request after a window opens can find the bridge warming up;
        # give it one retry before declaring the capability absent.
        attempts = 2 if index == 0 else 1
        status = None
        for attempt in range(attempts):
            output = issue_stop(workspace, config_name, stop["file"], line, stop.get("locals", []), int(args.wait_seconds * 1000))
            status = poll_status(workspace, output, time.time() + args.wait_seconds)
            if status is not None:
                break
            if attempt + 1 < attempts:
                time.sleep(3.0)
        if status is None:
            print("BRIDGE_BLOCKED no live VS Code bridge processed the request "
                  f"(workspace {workspace} open+trusted with the extension?).", file=sys.stderr)
            return 3
        if status.get("status") not in ("stopped", "stopped-not-proof"):
            print(f"STOP-FAILED {human_index} status={status.get('status')!r}: {status.get('error') or ''}", file=sys.stderr)
            return 1
        stopped = status.get("stoppedState", {}) or {}
        frame = stopped.get("frame", {}) or {}
        locals_map = stopped.get("locals", {}) or {}
        state_str = ", ".join(f"{k}={v}" for k, v in locals_map.items()) or "(no locals requested)"
        print(f"\n── STOP {human_index}/{len(stops)} · {stop['file']}:{frame.get('line')} in {frame.get('name')!r} ──")
        print(f"SAY: {stop['say']}")
        print(f"STATE: {state_str}")
        if args.speak:
            result = speak(stop["say"], stop_flag=args.stop_flag, watch_stdin=interactive)
            if result == "interrupted":
                print("  (interrupted — Embry pauses)")
                acknowledge_pause()
            elif result == "spoken":
                print("  (narrated aloud in the Embry voice)")
        for name, want in (stop.get("expect") or {}).items():
            if locals_map.get(name) != want:
                print(f"EXPECT-FAILED {name}={locals_map.get(name)!r} != {want!r}", file=sys.stderr)
                return 1
        transcript.append({"index": human_index, "file": stop["file"], "line": frame.get("line"),
                           "function": frame.get("name"), "say": stop["say"], "locals": locals_map,
                           "sessionId": stopped.get("sessionId")})

        # Non-interactive: just advance (base walkthrough behavior, keeps the eval green).
        if not interactive:
            index += 1
            continue

        # Pause-and-listen: after each stop Embry waits for the human. The human
        # can continue, repeat, go back, quit, or ask a different question (which
        # she answers, then keeps listening). This is the real interrupt loop.
        advanced = False
        while not advanced:
            cmd = next_command().strip()
            low = cmd.lower()
            if low in ("", "c", "continue", "next", "n"):
                index += 1
                advanced = True
            elif low in ("r", "repeat"):
                print("  (repeat)")
                if args.speak:
                    speak(stop["say"], stop_flag=args.stop_flag, watch_stdin=interactive)
            elif low in ("b", "back", "previous"):
                index = max(0, index - 1)
                advanced = True
                print(f"  (back to stop {index + 1})")
            elif low in ("q", "quit", "stop", "exit"):
                print(f"WALKTHROUGH-STOPPED by human at stop {human_index}")
                finalize()
                return 0
            elif low == "interrupt":
                # Scripted stand-in for a mid-speech interrupt: Embry pauses and
                # gives a natural acknowledgment, then keeps listening.
                print("  (interrupted — Embry pauses)")
                acknowledge_pause()
            else:
                print(f"  Q: {cmd}")
                answer = answer_question(cmd, stop, state_str, spec)
                print(f"  A: {answer}")
                if args.speak:
                    speak(answer, stop_flag=args.stop_flag, watch_stdin=interactive)

    print(f"\nWALKTHROUGH-COMPLETE mode={spec['mode']} stops={len(stops)}")
    finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
