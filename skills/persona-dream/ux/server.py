#!/usr/bin/env python3
"""Serve the persona-dream journal + chat UX, and close the conversation loop.

The static renderer (``render_journal_ux.py``) can show a journal and a past
conversation, but its composer only ever built a JSONL line for you to paste in
yourself. So the loop had an open joint at exactly the interesting place: her
entry reached a person, and nothing the person said got back.

This service closes it. It owns nothing it does not have to:

    reply text     -> Tau, through scripts/tau_text_reasoning_adapter.
                      Only Tau may reach scillm; this never calls a model.
    speech         -> Chatterbox /synthesize-batch, via scripts/speak_reply.
    the record     -> scripts/append_conversation.py, unchanged, still the
                      only writer, still append-only and gated.

That delegation is the point. `append_conversation.py` refuses an Embry turn
without both a delivery tone and rendered audio, and this service does not get
an exemption: her reply is generated, spoken, and only then appended. If
Chatterbox is down, the turn is refused rather than recorded as text she never
said.

What this does NOT do is decide whether she is right, or promote anything she
says to fact. A dream is what she made of her day, and a reply about a dream is
one step further out. The journal's own boundary fields ride along in the
payload so the UI can keep saying so.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
APP_DIST = Path(__file__).resolve().parent / "app" / "dist"

#: Where run directories are looked for. A run dir is any directory holding a
#: journal.md; nothing is invented when one is absent.
RUN_ROOTS = [
    Path(os.environ.get("PERSONA_DREAM_OUTPUTS",
                        "/mnt/storage12tb/skills/persona-dream/outputs")),
    Path("/tmp"),
]


def _load(name: str):
    """Import a script by path, the way the other scripts already do.

    The renderer lives beside this file in ux/; everything else is in scripts/.
    """
    for directory in (SCRIPTS, Path(__file__).resolve().parent):
        candidate = directory / f"{name}.py"
        if candidate.is_file():
            break
    else:
        raise RuntimeError(f"cannot find {name}.py")
    spec = importlib.util.spec_from_file_location(name, candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


app = FastAPI(title="persona-dream journal + chat")

# The Vite dev server runs on another origin during design iteration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- runs


def discover_runs() -> list[Path]:
    """Every directory that actually holds a journal, newest first."""
    found: list[Path] = []
    for root in RUN_ROOTS:
        if not root.is_dir():
            continue
        try:
            for path in root.iterdir():
                if path.is_dir() and (path / "journal.md").is_file():
                    found.append(path)
        except PermissionError:
            continue
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def resolve_run(run_id: str) -> Path:
    for path in discover_runs():
        if path.name == run_id:
            return path
    raise HTTPException(status_code=404, detail=f"no run directory named {run_id!r}")


@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    runs = []
    for path in discover_runs():
        packet = path / "dream_packet.json"
        persona = ""
        if packet.is_file():
            try:
                value = json.loads(packet.read_text(encoding="utf-8")).get("persona")
                persona = value.get("display_name", "") if isinstance(value, dict) else str(value or "")
            except Exception:
                persona = ""
        runs.append({
            "run_id": path.name,
            "run_dir": str(path),
            "persona": persona,
            "has_audio": (path / "journal.wav").is_file(),
            "turns": _turn_count(path / "conversation.jsonl"),
        })
    return {"schema": "persona_dream.ux_runs.v1", "runs": runs}


def _turn_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


# ------------------------------------------------------------------ journal


@app.get("/api/runs/{run_id}/journal")
def get_journal(run_id: str) -> dict[str, Any]:
    """The entry plus the boundary fields the UI must keep displaying."""
    run_dir = resolve_run(run_id)
    renderer = _load("render_journal_ux")
    run = renderer.load_run(run_dir)

    entry: dict[str, Any] = {}
    for name in ("journal_entry.json", "persona_journal.json"):
        candidate = run_dir / name
        if candidate.is_file():
            try:
                entry = json.loads(candidate.read_text(encoding="utf-8"))
                break
            except Exception:
                entry = {}

    # load_run nests the prose under "journal"; the rest sits at the top level.
    journal = run.get("journal") or {}
    audio = Path(run["audio"]).name if run.get("audio") else None

    return {
        "schema": "persona_dream.ux_journal.v1",
        "run_id": run["run_id"],
        "run_dir": str(run_dir),
        "persona": run.get("persona") or "",
        "title": journal.get("title") or "",
        "preamble": journal.get("preamble") or [],
        "paragraphs": journal.get("paragraphs") or [],
        "footnotes": journal.get("footnotes") or {},
        "journal_present": run.get("journal_present", False),
        "sources": run.get("sources") or [],
        "tensions": run.get("tensions") or [],
        "web": run.get("web") or {},
        "audio": audio,
        # Displayed, never dropped: an interpretation must not read as a record.
        "boundary": {
            "canon_status": entry.get("canon_status", "synthetic_self_reflection"),
            "never_promote_to_event_fact": entry.get("never_promote_to_event_fact", True),
            "asserts_only_own_inner_state": entry.get("asserts_only_own_inner_state", True),
            "note": (
                "A dream journal is what she made of her day, not a record of it. "
                "Tone chips say what was requested of the renderer."
            ),
        },
        "session_mood": entry.get("session_mood") or {},
        "unresolved_tension": entry.get("unresolved_tension") or "",
        "expanded_understanding": entry.get("expanded_understanding") or "",
    }


@app.get("/api/runs/{run_id}/audio/{name}")
def get_audio(run_id: str, name: str) -> FileResponse:
    run_dir = resolve_run(run_id)
    # Resolve inside the run dir; a crafted name must not escape it.
    path = (run_dir / name).resolve()
    if not str(path).startswith(str(run_dir.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail=f"no audio {name!r} in {run_id}")
    return FileResponse(path, media_type="audio/wav")


# ------------------------------------------------------------- conversation


@app.get("/api/runs/{run_id}/conversation")
def get_conversation(run_id: str) -> dict[str, Any]:
    run_dir = resolve_run(run_id)
    path = run_dir / "conversation.jsonl"
    turns: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {
        "schema": "persona_dream.ux_conversation.v1",
        "run_id": run_id,
        "turns": turns,
        "tone_boundary": (
            "A delivery tone is what was requested of Chatterbox. Per-render "
            "affect_effect receipts are what prove it was applied."
        ),
    }


class TurnIn(BaseModel):
    text: str
    role: str = "human"


def _append(run_dir: Path, role: str, text: str,
            tone: str | None = None, audio: str | None = None) -> dict[str, Any]:
    """Append through the existing writer. It stays the only writer."""
    cmd = [sys.executable, str(SCRIPTS / "append_conversation.py"),
           "--run-dir", str(run_dir), "--role", role, "--text", text, "--json"]
    if tone:
        cmd += ["--tone", tone]
    if audio:
        cmd += ["--audio", audio]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=(proc.stderr or proc.stdout)[-800:])


@app.post("/api/runs/{run_id}/conversation")
def post_turn(run_id: str, body: TurnIn) -> JSONResponse:
    """Say something to her. Your side needs no tone and no audio."""
    run_dir = resolve_run(run_id)
    if body.role not in ("human", "agent"):
        raise HTTPException(status_code=400, detail="use /reply for her side of the conversation")
    receipt = _append(run_dir, body.role, body.text)
    ok = receipt.get("status") == "PASS_CONVERSATION_APPENDED"
    return JSONResponse(receipt, status_code=200 if ok else 409)


# ------------------------------------------------------------------- reply


class ReplyIn(BaseModel):
    #: Optional: reply to a specific message rather than the last one.
    text: str | None = None


@app.post("/api/runs/{run_id}/reply")
def post_reply(run_id: str, body: ReplyIn) -> JSONResponse:
    """Generate her reply, speak it, and append it — in that order.

    Every step is delegated, and every step can refuse. A reply that cannot be
    spoken is never written down, because `append_conversation.py` requires her
    turns to carry tone and audio and this service does not get an exemption.
    """
    run_dir = resolve_run(run_id)
    reply = _load("speak_reply")
    result = reply.generate_and_speak(run_dir=run_dir, prompt_text=body.text)

    if result["status"] != "PASS_REPLY_SPOKEN":
        return JSONResponse(result, status_code=502)

    receipt = _append(run_dir, "embry", result["text"],
                      tone=result["tone"], audio=result["audio"])
    ok = receipt.get("status") == "PASS_CONVERSATION_APPENDED"
    return JSONResponse(
        {"reply": result, "append": receipt},
        status_code=200 if ok else 409,
    )


# -------------------------------------------------------------------- voice


@app.get("/api/voice/health")
def voice_health() -> dict[str, Any]:
    """What voice can actually do right now, so the UI never mimes a capability."""
    speak = _load("speak_reply")
    listen = _load("transcribe_turn")
    return {
        "schema": "persona_dream.ux_voice_health.v1",
        "speak": speak.chatterbox_health(),
        "listen": listen.stt_health(),
    }


@app.post("/api/voice/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> JSONResponse:
    """Dictate a turn. Returns text only; you still choose to send it."""
    listen = _load("transcribe_turn")
    suffix = Path(audio.filename or "utterance.webm").suffix or ".webm"
    result = listen.transcribe(await audio.read(), suffix=suffix)
    ok = result["status"] == "PASS_TRANSCRIBED"
    return JSONResponse(result, status_code=200 if ok else 422)


if APP_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(APP_DIST), html=True), name="app")


def main() -> int:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
